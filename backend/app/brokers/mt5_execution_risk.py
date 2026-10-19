"""Deterministic demo-entry risk evaluation; never authorizes a broker call.

All monetary observations must be in the account currency, include manual trades
and other strategies, and come from a complete reconciled broker observation.
The eventual submission gateway must serialize observation/reservation/submission
per account. A passing assessment is not a reusable reservation.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.brokers.mt5_execution_ledger import RiskPolicy


class AccountRiskFacts(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True)
    account_key: str = Field(pattern=r'^[a-f0-9]{64}$')
    environment: Literal['demo', 'live']
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    observed_at_ms: int = Field(gt=0)
    complete: bool
    reconciled: bool
    risk_day_utc: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    session_key: str = Field(min_length=1, max_length=128)
    strategy_key: str = Field(min_length=1, max_length=200)
    equity: float = Field(gt=0)
    free_margin: float = Field(ge=0)
    open_positions: int = Field(ge=0)
    pending_entries: int = Field(ge=0)
    unresolved_submissions: int = Field(ge=0)
    gross_exposure: float = Field(ge=0)
    pending_gross_exposure: float = Field(ge=0)
    # Losses are gross loss amounts (including fees), never offset by winners.
    realized_losses_today: float = Field(ge=0)
    floating_losses: float = Field(ge=0)
    remaining_stop_risk: float = Field(ge=0)
    pending_stop_risk: float = Field(ge=0)
    session_entries: int = Field(ge=0)


class ProposedRisk(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True)
    symbol: str = Field(min_length=1, max_length=256)
    estimated_stop_risk: float = Field(gt=0)
    estimated_margin: float = Field(ge=0)
    gross_exposure: float = Field(gt=0)


def assess(policy, facts, proposed, *, now_ms, session_key, max_session_trades=1):
    """Conservative UTC-day budget, also charging remaining open/pending risk.

    An unknown stop/conversion/history must make facts.complete false; callers
    must never substitute zero. Pending entries count as potential positions.
    """
    policy = RiskPolicy.model_validate(policy)
    facts = AccountRiskFacts.model_validate(facts)
    proposed = ProposedRisk.model_validate(proposed)
    if type(now_ms) is not int or now_ms <= 0 or type(max_session_trades) is not int or max_session_trades < 1:
        raise ValueError('Invalid risk evaluation clock or session limit')
    day = datetime.fromtimestamp(now_ms / 1000, timezone.utc).date().isoformat()
    reasons = []
    def reject(condition, code):
        if condition:
            reasons.append(code)
    reject(policy.environment != 'demo' or facts.environment != 'demo', 'demo_required')
    reject(facts.account_key != policy.account_key, 'account_mismatch')
    reject(facts.currency != policy.currency, 'currency_mismatch')
    reject(not facts.complete or not facts.reconciled, 'incomplete_reconciliation')
    reject(not 0 <= now_ms - facts.observed_at_ms <= 5000, 'stale_or_future_account_facts')
    reject(facts.risk_day_utc != day, 'risk_day_mismatch')
    reject(facts.session_key != session_key or facts.strategy_key != policy.strategy_key, 'session_identity_mismatch')
    reject(facts.unresolved_submissions > 0, 'uncertain_submission')
    reject(proposed.symbol not in policy.symbols, 'symbol_outside_policy')
    d = lambda value: Decimal(str(value))
    exposure = d(facts.gross_exposure) + d(facts.pending_gross_exposure) + d(proposed.gross_exposure)
    consumed = d(facts.realized_losses_today) + d(facts.floating_losses)
    budget = consumed + d(facts.remaining_stop_risk) + d(facts.pending_stop_risk) + d(proposed.estimated_stop_risk)
    reject(d(proposed.estimated_stop_risk) > d(policy.max_trade_risk), 'trade_risk_limit')
    reject(d(proposed.estimated_margin) > d(facts.free_margin), 'insufficient_free_margin')
    reject(facts.open_positions + facts.pending_entries + 1 > policy.max_positions, 'position_limit')
    reject(exposure > d(policy.max_gross_exposure), 'gross_exposure_limit')
    reject(consumed >= d(policy.max_daily_loss) or budget > d(policy.max_daily_loss), 'daily_loss_budget')
    reject(facts.session_entries >= max_session_trades, 'session_trade_limit')
    return dict(allowed=not reasons, reasons=reasons, execution_enabled=False,
                evaluated_at_ms=now_ms, risk_day_utc=day, session_key=session_key,
                projected_gross_exposure=float(exposure), projected_loss_budget=float(budget),
                basis='account_currency_gross_losses_utc_day_v1')
