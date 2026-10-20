from concurrent.futures import ThreadPoolExecutor
import os
import subprocess
import sys

import pytest

from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
from tests.test_mt5_execution_ledger import ledger, policy


def test_normal_operation_releases_without_authorizing(ledger):
    p = ledger.configure(policy())
    assert ledger.account_guard_status(p['id'])['state'] == 'IDLE'
    with ledger.account_guard(p['id']) as token:
        assert token and ledger.account_guard_status(p['id'])['state'] == 'HELD'
        with pytest.raises(ValueError, match='disabled'):
            ledger.authorize_submission(token)
    assert ledger.account_guard_status(p['id']) == dict(state='IDLE', since=None, execution_enabled=False)


def test_account_wide_exclusion_across_strategies(ledger):
    first = ledger.configure(policy())
    second = ledger.configure(policy() | {'strategy_key': 'another'})
    def attempt(_):
        with pytest.raises(ValueError, match='busy'):
            with ledger.account_guard(second['id']):
                pytest.fail('Second strategy obtained the same account')
    with ledger.account_guard(first['id']):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(attempt, range(12)))
    with ledger.account_guard(second['id']):
        assert ledger.account_guard_status(first['id'])['state'] == 'HELD'


def test_different_accounts_are_independent(ledger):
    a = ledger.configure(policy())
    b = ledger.configure(policy() | {'account_key': 'b'*64})
    with ledger.account_guard(a['id']):
        with ledger.account_guard(b['id']):
            assert ledger.account_guard_status(b['id'])['state'] == 'HELD'


@pytest.mark.parametrize('error', [RuntimeError, KeyboardInterrupt, SystemExit])
def test_failure_retains_account_until_reconciliation(ledger, error):
    p = ledger.configure(policy())
    with pytest.raises(error):
        with ledger.account_guard(p['id']):
            raise error('secret-native-error')
    status = ledger.account_guard_status(p['id'])
    assert status['state'] == 'RECONCILIATION_REQUIRED'
    assert 'secret-native-error' not in str(status)
    with pytest.raises(ValueError, match='reconciliation'):
        with ledger.account_guard(p['id']):
            pytest.fail('Failed operation was silently retried')


def test_restart_fences_active_owner_and_never_steals_guard(ledger):
    p = ledger.configure(policy())
    with pytest.raises(ValueError, match='superseded'):
        with ledger.account_guard(p['id']):
            newer = MT5ExecutionLedger(ledger.database)
            assert newer.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'
            with pytest.raises(ValueError, match='reconciliation'):
                with newer.account_guard(p['id']):
                    pytest.fail('Restart stole an active account')
    assert newer.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'


def test_failed_owner_cannot_erase_restarted_guard(ledger):
    p = ledger.configure(policy())
    with pytest.raises(RuntimeError):
        with ledger.account_guard(p['id']):
            newer = MT5ExecutionLedger(ledger.database)
            raise RuntimeError('provider disconnected')
    assert newer.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'


def test_research_and_live_policy_cannot_acquire_authority(ledger):
    from app.research_agent.access import preparation_scope
    p = ledger.configure(policy())
    live = ledger.configure(policy() | {'environment': 'live'})
    with pytest.raises(ValueError, match='demo'):
        with ledger.account_guard(live['id']):
            pytest.fail('Live authority acquired')
    with preparation_scope(ledger.database, 'fixture'):
        with pytest.raises(ValueError, match='Research'):
            with ledger.account_guard(p['id']):
                pytest.fail('Research obtained authority')
    assert ledger.account_guard_status(p['id'])['state'] == 'IDLE'


def test_emergency_stop_still_disables_policies_inside_guard(ledger):
    p = ledger.configure(policy())
    with ledger.account_guard(p['id']):
        ledger.emergency_stop()
        assert ledger.policies()[0]['status'] == 'EMERGENCY_STOP'
        assert not ledger.policies()[0]['enabled']
    assert not ledger.policies()[0]['enabled']


def test_actual_process_death_retains_guard(tmp_path):
    from app.storage.database import Database
    dbpath = tmp_path / 'crash.db'
    db = Database(dbpath)
    db.initialize()
    # No provider, terminal, credentials or network. Exit bypasses Python's
    # context-manager cleanup, modelling a killed execution host.
    script = """
import os, sys
from app.storage.database import Database
from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
from tests.test_mt5_execution_ledger import policy
ledger = MT5ExecutionLedger(Database(sys.argv[1]))
p = ledger.configure(policy())
with ledger.account_guard(p['id']):
    os._exit(0)
"""
    result = subprocess.run([sys.executable, '-c', script, str(dbpath)],
                            cwd=os.getcwd(), timeout=30, capture_output=True)
    assert result.returncode == 0
    recovered = MT5ExecutionLedger(db)
    p = recovered.configure(policy())
    assert recovered.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'
    with pytest.raises(ValueError, match='reconciliation'):
        with recovered.account_guard(p['id']):
            pytest.fail('Crash was treated as permission to retry')
