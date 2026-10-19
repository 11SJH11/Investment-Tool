import pytest

from app.brokers.mt5_execution_risk import assess
from tests.test_mt5_execution_ledger import ledger, policy


NOW = 1792368000000  # 2026-10-19T00:00:00Z


def facts(**changes):
    return dict(account_key='a'*64, environment='demo', currency='USD',
                observed_at_ms=NOW, complete=True, reconciled=True,
                risk_day_utc='2026-10-19', session_key='2026-10-18-NY', strategy_key='fixture',
                equity=10000., free_margin=2000., open_positions=0, pending_entries=0,
                unresolved_submissions=0, gross_exposure=0., pending_gross_exposure=0.,
                realized_losses_today=0., floating_losses=0., remaining_stop_risk=0.,
                pending_stop_risk=0., session_entries=0) | changes


def proposed(**changes):
    return dict(symbol='XAUUSDs', estimated_stop_risk=100., estimated_margin=200., gross_exposure=5000.) | changes


def check(f=None, p=None, **kwargs):
    return assess(policy(), f or facts(), p or proposed(), now_ms=NOW,
                  session_key='2026-10-18-NY', **kwargs)


def test_passing_assessment_never_authorizes_order():
    result = check()
    assert result['allowed'] and not result['execution_enabled']
    assert result['projected_loss_budget'] == 100
    assert result['projected_gross_exposure'] == 5000


@pytest.mark.parametrize('changes,reason', [
    ({'environment': 'live'}, 'demo_required'),
    ({'account_key': 'b'*64}, 'account_mismatch'),
    ({'currency': 'EUR'}, 'currency_mismatch'),
    ({'complete': False}, 'incomplete_reconciliation'),
    ({'reconciled': False}, 'incomplete_reconciliation'),
    ({'observed_at_ms': NOW-5001}, 'stale_or_future_account_facts'),
    ({'observed_at_ms': NOW+1}, 'stale_or_future_account_facts'),
    ({'risk_day_utc': '2026-10-18'}, 'risk_day_mismatch'),
    ({'session_key': 'other'}, 'session_identity_mismatch'),
    ({'strategy_key': 'other'}, 'session_identity_mismatch'),
    ({'unresolved_submissions': 1}, 'uncertain_submission'),
    ({'free_margin': 199.99}, 'insufficient_free_margin'),
    ({'open_positions': 2}, 'position_limit'),
    ({'open_positions': 1, 'pending_entries': 1}, 'position_limit'),
    ({'gross_exposure': 4000., 'pending_gross_exposure': 1000.01}, 'gross_exposure_limit'),
    ({'realized_losses_today': 200.01}, 'daily_loss_budget'),
    ({'floating_losses': 200.01}, 'daily_loss_budget'),
    ({'remaining_stop_risk': 200.01}, 'daily_loss_budget'),
    ({'pending_stop_risk': 200.01}, 'daily_loss_budget'),
    ({'session_entries': 1}, 'session_trade_limit'),
])
def test_account_wide_rejections(changes, reason):
    result = check(facts(**changes))
    assert not result['allowed'] and reason in result['reasons']


@pytest.mark.parametrize('changes,reason', [
    ({'symbol': 'NASUSD'}, 'symbol_outside_policy'),
    ({'estimated_stop_risk': 100.01}, 'trade_risk_limit'),
    ({'gross_exposure': 10000.01}, 'gross_exposure_limit'),
])
def test_proposed_trade_rejections(changes, reason):
    assert reason in check(p=proposed(**changes))['reasons']


def test_exact_boundaries_and_combined_loss_budget():
    result = check(facts(observed_at_ms=NOW-5000, open_positions=1, gross_exposure=5000.,
                         free_margin=200., realized_losses_today=50., floating_losses=50.,
                         remaining_stop_risk=50., pending_stop_risk=50.))
    assert result['allowed'] and result['projected_loss_budget'] == 300
    assert not check(facts(realized_losses_today=50., floating_losses=50.,
                           remaining_stop_risk=50., pending_stop_risk=50.01))['allowed']


@pytest.mark.parametrize('changes', [
    {'gross_exposure': None}, {'remaining_stop_risk': float('nan')},
    {'pending_stop_risk': -1.}, {'complete': 'true'}, {'open_positions': True},
    {'free_margin': float('inf')}, {'realized_losses_today': -100.},
    {'account_password': 'not-accepted'},
])
def test_unknown_nonfinite_coerced_or_untrusted_facts_rejected(changes):
    with pytest.raises(ValueError):
        check(facts(**changes))


def test_policy_live_rejected_even_when_observation_says_demo():
    result = assess(policy() | {'environment': 'live'}, facts(), proposed(), now_ms=NOW,
                    session_key='2026-10-18-NY')
    assert result['reasons'] == ['demo_required']


def test_session_limit_is_independent_from_current_open_positions():
    assert check(facts(session_entries=1), max_session_trades=2)['allowed']
    assert not check(facts(session_entries=2), max_session_trades=2)['allowed']


@pytest.mark.parametrize('limit', [0, -1, True, 1.5])
def test_invalid_session_limit_rejected(limit):
    with pytest.raises(ValueError):
        check(max_session_trades=limit)


def test_assessments_are_durable_audit_not_authorization(ledger):
    from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
    p = ledger.configure(policy())
    passed = ledger.assess_risk(p['id'], facts(), proposed(), now_ms=NOW, session_key='2026-10-18-NY')
    rejected = ledger.assess_risk(p['id'], facts(unresolved_submissions=1), proposed(),
                                  now_ms=NOW, session_key='2026-10-18-NY')
    assert passed['decision']['allowed'] and not rejected['decision']['allowed']
    assert ledger.risk_assessments(p['id']) == [rejected, passed]
    assert ledger.risk_assessments(p['id'], limit=1) == [rejected]
    assert not ledger.policies()[0]['enabled']
    with pytest.raises(ValueError, match='disabled'):
        ledger.authorize_submission(passed['id'])
    restarted = MT5ExecutionLedger(ledger.database)
    assert restarted.risk_assessments(p['id']) == [rejected, passed]
    with pytest.raises(ValueError, match='superseded'):
        ledger.assess_risk(p['id'], facts(), proposed(), now_ms=NOW, session_key='2026-10-18-NY')


def test_assessments_isolate_accounts_and_cannot_be_created_by_research(ledger):
    from app.research_agent.access import preparation_scope
    p = ledger.configure(policy())
    other = ledger.configure(policy() | {'account_key': 'b'*64})
    result = ledger.assess_risk(other['id'], facts(), proposed(), now_ms=NOW, session_key='2026-10-18-NY')
    assert result['decision']['reasons'] == ['account_mismatch']
    assert ledger.risk_assessments(p['id']) == []
    with preparation_scope(ledger.database, 'fixture'):
        with pytest.raises(ValueError, match='Research'):
            ledger.assess_risk(p['id'], facts(), proposed(), now_ms=NOW, session_key='2026-10-18-NY')


def test_invalid_facts_leave_no_audit_rows(ledger):
    p = ledger.configure(policy())
    with pytest.raises(ValueError):
        ledger.assess_risk(p['id'], facts(password='not-stored'), proposed(), now_ms=NOW,
                           session_key='2026-10-18-NY')
    assert ledger.risk_assessments(p['id']) == []
