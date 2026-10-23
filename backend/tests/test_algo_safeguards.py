import json
from types import SimpleNamespace

from app.services.algo_monitoring import report
from app.services.algo_safeguards import safeguards
from app.storage.database import Database
from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
from tests.test_mt5_execution_ledger import policy
from tests.test_mt5_execution_risk import facts, proposed, NOW


def test_shared_account_safeguards_preserve_identity_and_do_not_grant_authority(tmp_path):
    db = Database(tmp_path/'monitor.db'); db.initialize()
    ledger = MT5ExecutionLedger(db)
    first = ledger.configure(policy())
    shared = ledger.configure(policy() | dict(strategy_key='second'))
    other = ledger.configure(policy() | dict(account_key='b'*64, currency='EUR'))
    ledger.assess_risk(first['id'], facts(), proposed(), now_ms=NOW, session_key='2026-10-18-NY')
    ledger.assess_risk(first['id'], facts(unresolved_submissions=1), proposed(), now_ms=NOW, session_key='2026-10-18-NY')
    with db.connect() as c:
        c.execute('INSERT INTO mt5_execution_account_guards VALUES(?,?,?,?,?)',
                  ('a'*64, 'SECRET_OWNER', 'SECRET_TOKEN', 'RECONCILIATION_REQUIRED', '2026-10-23T00:00:00Z'))
        # A historical attempt is evidence, not a trade or proof of an open position.
        intent = dict(id='intent', state='DRAFT')
        c.execute('INSERT INTO mt5_execution_intents VALUES(?,?,?,?)', ('intent', first['id'], 'key', json.dumps(intent)))
        c.execute('INSERT INTO mt5_execution_attempts VALUES(?,?,?,?,?)',
                  ('attempt', 'intent', 'a'*64, None, json.dumps({'secret':'SECRET_ATTEMPT'})))
        before = c.execute('SELECT * FROM mt5_execution_account_guards').fetchall()
    result = report(SimpleNamespace(database=db))
    rows = {row['id']: row for row in result['items']}
    a, b, separate = [rows[p['id']]['safeguards'] for p in (first, shared, other)]
    assert a['guard'] == b['guard'] == dict(state='RECONCILIATION_REQUIRED', since='2026-10-23T00:00:00Z')
    assert a['recorded_account_attempts'] == b['recorded_account_attempts'] == 1
    assert separate['guard'] is None and separate['recorded_account_attempts'] == 0
    assert b['latest_risk_assessment'] is None and separate['latest_risk_assessment'] is None
    assert a['latest_risk_assessment']['reasons'] == ['uncertain_submission']
    assert a['latest_risk_assessment']['allowed'] is False
    assert a['latest_risk_assessment']['projected_loss_budget'] == 100
    assert all(not row['execution_enabled'] and row['metrics'] is None for row in rows.values())
    assert 'SECRET_' not in json.dumps(result)
    assert 'facts' not in a['latest_risk_assessment']
    with db.connect() as c:
        assert c.execute('SELECT * FROM mt5_execution_account_guards').fetchall() == before
        assert c.execute('SELECT owner FROM mt5_execution_owner').fetchone()[0] == ledger.owner


def test_missing_evidence_is_unknown_and_passing_diagnostic_is_not_authority(tmp_path):
    db = Database(tmp_path/'monitor.db'); db.initialize()
    with db.connect() as c:
        unknown = safeguards(c, set(), [dict(id='x', policy=policy())])['x']
    assert unknown['guard'] is None and unknown['recorded_account_attempts'] is None
    assert unknown['latest_risk_assessment'] is None and not unknown['execution_enabled']
    ledger = MT5ExecutionLedger(db); saved = ledger.configure(policy())
    ledger.assess_risk(saved['id'], facts(), proposed(), now_ms=NOW, session_key='2026-10-18-NY')
    row = report(SimpleNamespace(database=db))['items'][0]
    assert row['safeguards']['latest_risk_assessment']['allowed'] is True
    assert row['status'] == 'NOT_DEPLOYED' and not row['execution_enabled']


def test_safeguard_query_count_does_not_grow_with_preparations(tmp_path):
    db = Database(tmp_path/'monitor.db'); db.initialize(); MT5ExecutionLedger(db)
    policies = [dict(id=str(i), policy=policy() | dict(strategy_key=str(i))) for i in range(500)]
    with db.connect() as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        statements = []; c.set_trace_callback(statements.append)
        result = safeguards(c, tables, policies)
    assert len(result) == 500
    assert len(statements) == 3
