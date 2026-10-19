"""Read-only current-account sizing estimates. Never an execution approval."""
from decimal import Decimal, ROUND_FLOOR
from datetime import datetime, timezone
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.brokers.base import BrokerHistoryError


class SizingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    symbol: str = Field(min_length=1, max_length=256)
    side: Literal['buy', 'sell']
    entry: float = Field(gt=0)
    stop: float = Field(gt=0)
    risk_amount: float | None = Field(default=None, gt=0)
    risk_percent: float | None = Field(default=None, gt=0, le=100)

    @model_validator(mode='after')
    def valid(self):
        if (self.risk_amount is None) == (self.risk_percent is None):
            raise ValueError('Specify monetary risk or equity risk percent, not both')
        if not (self.stop < self.entry if self.side == 'buy' else self.stop > self.entry):
            raise ValueError('Stop must be on the loss side of entry')
        return self


def finite(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (positive and value <= 0):
        raise BrokerHistoryError('MT5 sizing facts are unavailable or invalid', category='history')
    return float(value)


def estimate(adapter, request):
    """Caller owns the shared terminal lifecycle and selected-account lock."""
    try:
        request = SizingRequest.model_validate(request)
        account, key = adapter._account()
        if key != adapter.account_key:
            raise BrokerHistoryError('MT5 account changed during sizing', category='connection')
        equity = finite(account.equity, positive=True)
        balance, free = finite(account.balance), finite(account.margin_free)
        module = adapter._module
        info = module.symbol_info(request.symbol)
        if info is None or info.name != request.symbol:
            raise BrokerHistoryError('Unknown MT5 broker symbol; no mapping was guessed', category='configuration')
        minimum, maximum, step, tick = [Decimal(str(finite(getattr(info, k, None), positive=True)))
            for k in ('volume_min', 'volume_max', 'volume_step', 'trade_tick_size')]
        if minimum > maximum or minimum % step != 0:
            raise BrokerHistoryError('Unsupported MT5 volume grid', category='configuration')
        if any(Decimal(str(price)) % tick != 0 for price in (request.entry, request.stop)):
            raise BrokerHistoryError('Entry and stop must align with the broker price tick', category='configuration')
        target = request.risk_amount if request.risk_amount is not None else equity * request.risk_percent / 100
        finite(target, positive=True)
        action = module.ORDER_TYPE_BUY if request.side == 'buy' else module.ORDER_TYPE_SELL
        def loss(lots):
            pnl = finite(module.order_calc_profit(action, request.symbol, float(lots), request.entry, request.stop))
            if pnl >= 0:
                raise BrokerHistoryError('Broker stop calculation did not produce a loss', category='history')
            return -pnl
        minimum_loss = loss(minimum)
        raw = Decimal(str(target)) / Decimal(str(minimum_loss)) * minimum
        quantity = (min(raw, maximum) / step).to_integral_value(rounding=ROUND_FLOOR) * step
        rejection = None
        risk = margin = 0.0
        if quantity < minimum:
            quantity = Decimal(0)
            rejection = 'minimum_lot_exceeds_target_risk'
        else:
            # Recalculate the actual rounded size, never trust scaling alone.
            risk = loss(quantity)
            margin = finite(module.order_calc_margin(action, request.symbol, float(quantity), request.entry))
            if margin < 0:
                raise BrokerHistoryError('Broker margin estimate is invalid', category='history')
            if risk > target:
                rejection = 'rounded_size_exceeds_target_risk'
            elif margin > free:
                rejection = 'insufficient_free_margin'
        if adapter._account()[1] != key:
            raise BrokerHistoryError('MT5 account changed during sizing', category='connection')
        return dict(provider='mt5', environment=adapter.environment, account_key=key,
            observed_at=datetime.now(timezone.utc).isoformat(), currency=adapter.currency,
            symbol=request.symbol, side=request.side, entry=request.entry, stop=request.stop,
            balance=balance, equity=equity, free_margin=free, target_risk=target,
            actual_estimated_risk=risk, quantity_lots=float(quantity), estimated_margin=margin,
            volume_min=float(minimum), volume_step=float(step), volume_max=float(maximum),
            trade_tick_size=float(tick), rejection_reason=rejection,
            sizing_limited=raw > maximum or risk < target, execution_enabled=False,
            basis='current_broker_calculation_at_supplied_prices',
            warnings=['Estimate only; not an order or execution approval.',
                      'Costs, slippage, gap risk and broker stop-distance rules are not included.',
                      'Margin calculation excludes existing positions and pending orders; free margin can change.',
                      'Current specifications and currency conversions are not historical backtest evidence.'])
    except BrokerHistoryError:
        raise
    except Exception:
        raise BrokerHistoryError('MT5 sizing estimate failed; check inputs and terminal availability', category='configuration') from None
