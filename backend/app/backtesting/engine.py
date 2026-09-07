from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, time, timedelta, timezone
import math
from statistics import median
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd

from app.backtesting.context import StrategyContext, timeframe_delta
from app.backtesting.models import BacktestConfig, BacktestTrade, EntrySignal, ExitSignal, ManagePositionSignal, Position
from app.backtesting.strategies.base import Strategy


class BacktestEngine:
    """Deterministic event-driven OHLCV backtester.

    Execution contract
    ------------------
    * Strategies only see completed bars.
    * Signals created at a bar close fill at the next primary-bar open.
    * Stops/targets are active after an entry fill, including the rest of the
      entry bar.
    * A gap through a stop fills at the available bar open, not at the stale
      stop price.
    * Same-bar stop/target ambiguity is resolved by the explicit policy.
    * Entry windows/day/risk guardrails are engine rules, so a strategy plugin
      cannot accidentally bypass them.
    """

    def __init__(self, config: BacktestConfig):
        self.config = config
        self._tz = ZoneInfo(config.exchange_timezone)
        self._entry_windows = tuple((_parse_clock(a), _parse_clock(b)) for a, b in config.entry_windows)
        self._session_end = _parse_clock(config.session_end)
        self._force_close = _parse_clock(config.force_close_time) if config.force_close_time else None

    def run(
        self,
        *,
        symbol_frames: dict[str, dict[str, pd.DataFrame]],
        strategies: dict[str, Strategy],
        primary_timeframe: str,
    ) -> dict[str, Any]:
        self._validate()
        if not symbol_frames:
            raise ValueError("No market data supplied")

        prepared: dict[str, dict[str, pd.DataFrame]] = {}
        primary_rows: dict[str, dict[pd.Timestamp, Any]] = {}
        daily_last_bar: dict[str, dict[object, pd.Timestamp]] = {}
        for symbol, frames in symbol_frames.items():
            prepared[symbol] = {timeframe: _prepare_frame(frame) for timeframe, frame in frames.items()}
            primary = prepared[symbol].get(primary_timeframe)
            if primary is None or primary.empty:
                continue
            rows = {pd.Timestamp(row.timestamp): row for row in primary.itertuples(index=False)}
            primary_rows[symbol] = rows
            local = primary["timestamp"].dt.tz_convert(self._tz)
            per_day: dict[object, pd.Timestamp] = {}
            for ts, local_ts in zip(primary["timestamp"], local):
                day = local_ts.date()
                stamp = pd.Timestamp(ts)
                if day not in per_day or stamp > per_day[day]:
                    per_day[day] = stamp
            daily_last_bar[symbol] = per_day
        if not primary_rows:
            raise ValueError("No primary timeframe bars available")

        for strategy in strategies.values():
            strategy.reset()

        event_times = sorted({timestamp for rows in primary_rows.values() for timestamp in rows})
        balance = float(self.config.starting_balance)
        positions: dict[str, Position] = {}
        pending_entries: dict[str, dict[str, Any]] = {}
        setup_records: list[dict[str, Any]] = []
        pending_exits: dict[str, ExitSignal] = {}
        pending_management: dict[str, ManagePositionSignal] = {}
        current_prices: dict[str, float] = {}
        trades: list[BacktestTrade] = []
        equity_curve: list[dict[str, Any]] = []
        rejected_signals: list[dict[str, Any]] = []
        last_bars: dict[str, pd.Series] = {}
        indicator_caches: dict[str, dict] = {symbol: {} for symbol in prepared}

        entries_by_day: dict[object, int] = defaultdict(int)
        day_results: dict[object, dict[str, float | int]] = defaultdict(
            lambda: {"r": 0.0, "consecutive_losses": 0}
        )
        cooldown_until: dict[str, datetime] = {}

        first_time = _to_datetime(event_times[0])
        equity_curve.append({
            "timestamp": first_time.isoformat(), "equity": balance,
            "realized_pnl": 0.0, "closed_trades": [],
        })

        for timestamp in event_times:
            timestamp_dt = _to_datetime(timestamp)
            symbols_now = sorted(symbol for symbol, rows in primary_rows.items() if timestamp in rows)
            closed_here: list[BacktestTrade] = []
            force_boundary_symbols: set[str] = set()

            # 1) Fill orders generated from already-completed earlier bars.
            for symbol in symbols_now:
                bar = _row_to_series(primary_rows[symbol][timestamp])
                last_bars[symbol] = bar
                current_prices[symbol] = float(bar["open"])

                if symbol in pending_management and symbol in positions:
                    management = pending_management.pop(symbol)
                    balance = self._apply_management(
                        positions[symbol], timestamp_dt, float(bar["open"]), management, balance
                    )

                if symbol in pending_exits and symbol in positions:
                    signal = pending_exits.pop(symbol)
                    trade, balance = self._close_position(
                        positions.pop(symbol), timestamp_dt, float(bar["open"]), signal.reason,
                        balance, market_fill=True,
                    )
                    trades.append(trade); closed_here.append(trade)
                    _register_trade_result(trade, day_results, self._tz)
                    cooldown_until[symbol] = timestamp_dt + timedelta(minutes=max(0, self.config.cooldown_minutes))

                if symbol in pending_entries and symbol not in positions:
                    pending = pending_entries[symbol]
                    signal: EntrySignal = pending["signal"]
                    raw_fill = _entry_fill_price(signal, bar)
                    if raw_fill is None:
                        pending["age"] = int(pending.get("age", 0)) + 1
                        max_wait = signal.max_wait_bars
                        if max_wait is not None and pending["age"] > int(max_wait):
                            pending_entries.pop(symbol, None)
                            record = setup_records[pending["record_index"]]
                            record.update({"status": "not_filled", "resolution_time": timestamp_dt.isoformat(), "resolution_reason": "limit_expired"})
                        continue

                    pending_entries.pop(symbol, None)
                    allowed, reason = self._entry_allowed(
                        timestamp_dt, symbol, entries_by_day, day_results, cooldown_until
                    )
                    record = setup_records[pending["record_index"]]
                    if not allowed:
                        rejected_signals.append(_rejected(symbol, timestamp_dt, reason))
                        record.update({"status": "filtered", "resolution_time": timestamp_dt.isoformat(), "resolution_reason": reason})
                    elif len(positions) >= max(1, int(self.config.max_open_positions)):
                        rejected_signals.append(_rejected(symbol, timestamp_dt, "max_open_positions"))
                        record.update({"status": "filtered", "resolution_time": timestamp_dt.isoformat(), "resolution_reason": "max_open_positions"})
                    else:
                        current_exposure = sum(position.notional for position in positions.values())
                        outcome = self._open_position(
                            symbol=symbol,
                            timestamp=timestamp_dt,
                            raw_open=float(raw_fill),
                            signal=signal,
                            balance=balance,
                            current_exposure=current_exposure,
                        )
                        if isinstance(outcome, Position):
                            positions[symbol] = outcome
                            balance -= outcome.entry_commission
                            entries_by_day[timestamp_dt.astimezone(self._tz).date()] += 1
                            record.update({"status": "filled", "entry_time": timestamp_dt.isoformat(), "fill_price": float(outcome.entry_price)})
                        else:
                            rejected_signals.append(_rejected(symbol, timestamp_dt, outcome))
                            record.update({"status": "rejected", "resolution_time": timestamp_dt.isoformat(), "resolution_reason": outcome})

            # 2) Intrabar protective exits.
            for symbol in list(symbols_now):
                if symbol not in positions:
                    continue
                bar = _row_to_series(primary_rows[symbol][timestamp])
                position = positions[symbol]
                exit_hit = self._intrabar_exit(position, bar)
                if exit_hit is not None:
                    raw_price, reason, market_fill = exit_hit
                    trade, balance = self._close_position(
                        position, timestamp_dt, raw_price, reason, balance,
                        market_fill=market_fill,
                    )
                    trades.append(trade); closed_here.append(trade)
                    del positions[symbol]
                    pending_exits.pop(symbol, None)
                    pending_management.pop(symbol, None)
                    _register_trade_result(trade, day_results, self._tz)
                    cooldown_until[symbol] = timestamp_dt + timedelta(minutes=max(0, self.config.cooldown_minutes))

            # 3) Mark current closes.
            for symbol in symbols_now:
                bar = _row_to_series(primary_rows[symbol][timestamp])
                current_prices[symbol] = float(bar["close"])

            # The timestamp stored on a bar is its start. The decision time is its
            # close, clamped to the selected session end for partial 1h/4h bars.
            decision_time = self._bar_close_time(timestamp_dt, primary_timeframe)

            # 4) Optional intraday flattening. This occurs at the bar close, after
            # stops/targets have had the opportunity to execute during that bar.
            if not self.config.allow_overnight:
                for symbol in symbols_now:
                    is_boundary = self._is_force_close_bar(
                        symbol, timestamp, decision_time, daily_last_bar
                    )
                    if not is_boundary:
                        continue
                    force_boundary_symbols.add(symbol)
                    if symbol in positions:
                        bar = _row_to_series(primary_rows[symbol][timestamp])
                        trade, balance = self._close_position(
                            positions.pop(symbol), decision_time, float(bar["close"]),
                            "session_close", balance, market_fill=True,
                        )
                        trades.append(trade); closed_here.append(trade)
                        pending_exits.pop(symbol, None)
                        pending_management.pop(symbol, None)
                        _register_trade_result(trade, day_results, self._tz)
                        cooldown_until[symbol] = decision_time + timedelta(minutes=max(0, self.config.cooldown_minutes))
                    # Never let an unfilled signal leak into the next session.
                    if symbol in pending_entries:
                        pending = pending_entries.pop(symbol, None)
                        if pending is not None:
                            setup_records[pending["record_index"]].update({"status": "not_filled", "resolution_time": decision_time.isoformat(), "resolution_reason": "session_boundary"})
                        rejected_signals.append(_rejected(symbol, decision_time, "session_boundary"))

            # 5) Strategy evaluation. A returned entry signal is still gated by
            # engine-level time/day/risk rules both here and again at its fill.
            marked_equity = balance + _unrealized_total(positions, current_prices)
            for symbol in symbols_now:
                strategy = strategies[symbol]
                ctx = StrategyContext(
                    symbol=symbol,
                    primary_timeframe=primary_timeframe,
                    decision_time=decision_time,
                    frames=prepared[symbol],
                    position=positions.get(symbol),
                    equity=marked_equity,
                    indicator_cache=indicator_caches[symbol],
                )
                decision = strategy.on_bar(ctx)
                if isinstance(decision, EntrySignal):
                    if symbol in force_boundary_symbols:
                        rejected_signals.append(_rejected(symbol, decision_time, "session_boundary"))
                        continue
                    if symbol not in positions and symbol not in pending_entries:
                        setup_record = {
                            "symbol": symbol,
                            "direction": decision.direction,
                            "detected_at": decision_time.isoformat(),
                            "order_type": decision.order_type,
                            "entry_price": decision.entry_price,
                            "stop_loss": decision.stop_loss,
                            "take_profit": decision.take_profit,
                            "status": "pending",
                            "reason": decision.reason,
                            "metadata": dict(decision.metadata),
                        }
                        setup_records.append(setup_record)
                        record_index = len(setup_records) - 1
                        allowed, reason = self._entry_allowed(
                            decision_time, symbol, entries_by_day, day_results, cooldown_until
                        )
                        if allowed:
                            pending_entries[symbol] = {"signal": decision, "age": 0, "record_index": record_index}
                        else:
                            rejected_signals.append(_rejected(symbol, decision_time, reason))
                            setup_record.update({"status": "filtered", "resolution_time": decision_time.isoformat(), "resolution_reason": reason})
                elif isinstance(decision, ExitSignal):
                    if symbol in positions:
                        pending_management.pop(symbol, None)
                        pending_exits[symbol] = decision
                elif isinstance(decision, ManagePositionSignal):
                    if symbol in positions and symbol not in pending_exits:
                        pending_management[symbol] = decision

            equity = balance + _unrealized_total(positions, current_prices)
            equity_curve.append({
                "timestamp": decision_time.isoformat(),
                "equity": equity,
                "realized_pnl": sum(t.net_pnl for t in closed_here),
                "closed_trades": [_trade_event(t) for t in closed_here],
            })

        # Close any remaining positions at the final known close. This only occurs
        # when overnight is allowed or the dataset itself ends before a boundary.
        final_events: list[BacktestTrade] = []
        final_time: datetime | None = None
        for symbol, position in list(positions.items()):
            bar = last_bars.get(symbol)
            if bar is None:
                continue
            bar_start = _to_datetime(pd.Timestamp(bar["timestamp"]))
            exit_time = self._bar_close_time(bar_start, primary_timeframe)
            trade, balance = self._close_position(
                position, exit_time, float(bar["close"]), "end_of_data", balance,
                market_fill=True,
            )
            trades.append(trade); final_events.append(trade)
            final_time = max(final_time, exit_time) if final_time else exit_time
            _register_trade_result(trade, day_results, self._tz)
            del positions[symbol]
        if final_events and final_time is not None:
            equity_curve.append({
                "timestamp": final_time.isoformat(), "equity": balance,
                "realized_pnl": sum(t.net_pnl for t in final_events),
                "closed_trades": [_trade_event(t) for t in final_events],
            })

        for pending in pending_entries.values():
            setup_records[pending["record_index"]].update({"status": "not_filled", "resolution_reason": "end_of_data"})

        equity_curve = _merge_equity_points(equity_curve)
        equity_curve = _decorate_equity_curve(self.config.starting_balance, equity_curve)
        ordered_trades = sorted(trades, key=lambda t: (t.exit_time, t.symbol))
        metrics = calculate_metrics(ordered_trades, self.config.starting_balance, balance, equity_curve)
        analysis = calculate_analysis(ordered_trades, self._tz)
        return {
            "metrics": metrics,
            "trades": [_trade_dict(trade) for trade in ordered_trades],
            "equity_curve": equity_curve,
            "breakdown_by_symbol": analysis["breakdowns"]["symbol"],
            "analysis": analysis,
            "setups": setup_records,
            "setup_metrics": _setup_metrics(setup_records),
            "rejected_signals": rejected_signals,
            "rejected_signal_summary": _rejection_summary(rejected_signals),
            "execution_model": {
                "signal_timing": "bar_close",
                "entry_timing": "market: next_bar_open; limit: first subsequent bar that trades through the limit",
                "same_bar_policy": self.config.same_bar_policy,
                "stop_gap_policy": "fill_at_open",
                "target_gap_policy": "fill_at_open",
                "commission_per_order": self.config.commission_per_order,
                "slippage_bps": self.config.slippage_bps,
                "spread_bps": self.config.spread_bps,
                "entry_windows": [list(window) for window in self.config.entry_windows],
                "trading_weekdays": list(self.config.trading_weekdays),
                "allow_overnight": self.config.allow_overnight,
                "force_close_time": self.config.force_close_time or (self.config.session_end if not self.config.allow_overnight else None),
                "max_trades_per_day": self.config.max_trades_per_day,
                "max_daily_loss_r": self.config.max_daily_loss_r,
                "max_consecutive_losses": self.config.max_consecutive_losses,
                "cooldown_minutes": self.config.cooldown_minutes,
                "strategy_management": "next_bar_open_stop_target_updates_and_partial_market_exits",
            },
        }

    def _validate(self) -> None:
        if self.config.starting_balance <= 0:
            raise ValueError("starting_balance must be positive")
        if self.config.sizing_mode not in {"risk_pct", "cash_risk", "quantity", "cash_position", "position_pct"}:
            raise ValueError("Unsupported sizing_mode")
        if self.config.same_bar_policy not in {"stop_first", "target_first"}:
            raise ValueError("same_bar_policy must be stop_first or target_first")
        if self.config.risk_value <= 0:
            raise ValueError("risk_value must be positive")
        if self.config.commission_per_order < 0 or self.config.slippage_bps < 0 or self.config.spread_bps < 0:
            raise ValueError("commission, spread and slippage cannot be negative")
        if self.config.max_leverage <= 0:
            raise ValueError("max_leverage must be positive")
        if not self.config.trading_weekdays or any(day < 0 or day > 6 for day in self.config.trading_weekdays):
            raise ValueError("trading_weekdays must contain weekday numbers 0-6")
        for start, end in self._entry_windows:
            if start >= end:
                raise ValueError("Each entry window must have a start earlier than its end")
        for name, value in (
            ("max_trades_per_day", self.config.max_trades_per_day),
            ("max_consecutive_losses", self.config.max_consecutive_losses),
        ):
            if value is not None and int(value) <= 0:
                raise ValueError(f"{name} must be positive when enabled")
        if self.config.max_daily_loss_r is not None and float(self.config.max_daily_loss_r) <= 0:
            raise ValueError("max_daily_loss_r must be positive when enabled")
        if self.config.cooldown_minutes < 0:
            raise ValueError("cooldown_minutes cannot be negative")

    def _bar_close_time(self, timestamp: datetime, primary_timeframe: str) -> datetime:
        candidate = timestamp + timeframe_delta(primary_timeframe)
        if primary_timeframe.endswith("d") or primary_timeframe.endswith("w"):
            return candidate
        local_start = timestamp.astimezone(self._tz)
        session_end_local = datetime.combine(local_start.date(), self._session_end, tzinfo=self._tz)
        if candidate.astimezone(self._tz) > session_end_local and local_start < session_end_local:
            return session_end_local.astimezone(timezone.utc)
        return candidate

    def _entry_allowed(
        self,
        when: datetime,
        symbol: str,
        entries_by_day: dict[object, int],
        day_results: dict[object, dict[str, float | int]],
        cooldown_until: dict[str, datetime],
    ) -> tuple[bool, str]:
        local = when.astimezone(self._tz)
        day = local.date()
        if local.weekday() not in self.config.trading_weekdays:
            return False, "weekday_filtered"
        if self._entry_windows and not any(start <= local.time() < end for start, end in self._entry_windows):
            return False, "outside_entry_window"
        close_at = self._force_close or self._session_end
        if not self.config.allow_overnight and local.time() >= close_at:
            return False, "after_force_close"
        cooldown = cooldown_until.get(symbol)
        if cooldown is not None and when < cooldown:
            return False, "cooldown"
        if self.config.max_trades_per_day is not None and entries_by_day[day] >= int(self.config.max_trades_per_day):
            return False, "max_trades_per_day"
        results = day_results[day]
        if self.config.max_daily_loss_r is not None and float(results["r"]) <= -abs(float(self.config.max_daily_loss_r)):
            return False, "daily_loss_limit"
        if self.config.max_consecutive_losses is not None and int(results["consecutive_losses"]) >= int(self.config.max_consecutive_losses):
            return False, "consecutive_loss_limit"
        return True, ""

    def _is_force_close_bar(
        self,
        symbol: str,
        timestamp: pd.Timestamp,
        decision_time: datetime,
        daily_last_bar: dict[str, dict[object, pd.Timestamp]],
    ) -> bool:
        local_start = _to_datetime(timestamp).astimezone(self._tz)
        if self._force_close is not None:
            local_end = decision_time.astimezone(self._tz)
            return local_start.time() < self._force_close <= local_end.time()
        return daily_last_bar.get(symbol, {}).get(local_start.date()) == pd.Timestamp(timestamp)

    def _open_position(
        self,
        *,
        symbol: str,
        timestamp: datetime,
        raw_open: float,
        signal: EntrySignal,
        balance: float,
        current_exposure: float,
    ) -> Position | str:
        entry = _apply_market_costs(
            raw_open, signal.direction, entering=True,
            slippage_bps=self.config.slippage_bps, spread_bps=self.config.spread_bps,
        )
        stop = float(signal.stop_loss)
        target = float(signal.take_profit) if signal.take_profit is not None else None
        if signal.direction == "long":
            if stop >= entry:
                return "invalid_long_stop_after_gap"
            if target is not None and target <= entry:
                return "target_already_passed_after_gap"
        else:
            if stop <= entry:
                return "invalid_short_stop_after_gap"
            if target is not None and target >= entry:
                return "target_already_passed_after_gap"

        risk_per_share = abs(entry - stop)
        if risk_per_share <= 0:
            return "zero_stop_distance"
        quantity = self._quantity(balance, entry, risk_per_share, current_exposure)
        if quantity <= 0 or not math.isfinite(quantity):
            return "position_size_zero"
        initial_risk = risk_per_share * quantity
        commission = max(0.0, float(self.config.commission_per_order))
        return Position(
            symbol=symbol,
            direction=signal.direction,
            entry_time=timestamp,
            entry_price=entry,
            quantity=quantity,
            stop_loss=stop,
            take_profit=target,
            initial_risk_per_share=risk_per_share,
            initial_risk_amount=initial_risk,
            entry_commission=commission,
            signal_reason=signal.reason,
            metadata=dict(signal.metadata),
        )

    def _quantity(self, balance: float, entry: float, risk_per_share: float, current_exposure: float) -> float:
        mode = self.config.sizing_mode
        value = float(self.config.risk_value)
        if mode == "risk_pct":
            quantity = (balance * value / 100.0) / risk_per_share
        elif mode == "cash_risk":
            quantity = value / risk_per_share
        elif mode == "quantity":
            quantity = value
        elif mode == "cash_position":
            quantity = value / entry
        elif mode == "position_pct":
            quantity = (balance * value / 100.0) / entry
        else:  # validated earlier
            raise ValueError(f"Unsupported sizing_mode '{mode}'")
        max_total_notional = max(0.0, balance * float(self.config.max_leverage))
        remaining_notional = max(0.0, max_total_notional - max(0.0, current_exposure))
        if entry > 0:
            quantity = min(quantity, remaining_notional / entry)
        return max(0.0, quantity)

    def _apply_management(
        self,
        position: Position,
        timestamp: datetime,
        raw_open: float,
        signal: ManagePositionSignal,
        balance: float,
    ) -> float:
        """Apply a strategy management decision at the next bar open.

        Stop/target changes become active before that bar's intrabar protective
        checks. Partial exits are market-like fills and remain part of the same
        logical trade, so trade counts/expectancy are not inflated by scale-outs.
        """
        if signal.new_stop_loss is not None:
            new_stop = float(signal.new_stop_loss)
            if not math.isfinite(new_stop):
                raise ValueError("Managed stop must be finite")
            position.stop_loss = new_stop
        if signal.new_take_profit is not None:
            new_target = float(signal.new_take_profit)
            if not math.isfinite(new_target):
                raise ValueError("Managed target must be finite")
            position.take_profit = new_target

        fraction = signal.reduce_fraction
        if fraction is not None:
            fraction = float(fraction)
            if not 0 < fraction < 1:
                raise ValueError("reduce_fraction must be greater than 0 and less than 1; use ExitSignal for a full exit")
            quantity = position.quantity * fraction
            if quantity > 1e-12:
                exit_price = _apply_market_costs(
                    raw_open, position.direction, entering=False,
                    slippage_bps=self.config.slippage_bps, spread_bps=self.config.spread_bps,
                )
                multiplier = 1.0 if position.direction == "long" else -1.0
                gross = (exit_price - position.entry_price) * quantity * multiplier
                commission = max(0.0, float(self.config.commission_per_order))
                balance += gross - commission
                position.realized_gross += gross
                position.exit_commissions += commission
                position.weighted_exit_value += exit_price * quantity
                position.exited_quantity += quantity
                position.quantity -= quantity
                position.partial_exits.append({
                    "timestamp": timestamp.isoformat(),
                    "price": exit_price,
                    "quantity": quantity,
                    "fraction_of_remaining": fraction,
                    "gross_pnl": gross,
                    "commission": commission,
                    "reason": signal.reason,
                })
        if signal.metadata:
            position.metadata.update(dict(signal.metadata))
        return balance

    def _intrabar_exit(self, position: Position, bar: pd.Series) -> tuple[float, str, bool] | None:
        open_price = float(bar["open"])
        high = float(bar["high"])
        low = float(bar["low"])
        stop = position.stop_loss
        target = position.take_profit
        if position.direction == "long":
            if open_price <= stop:
                return open_price, "stop_gap", True
            if target is not None and open_price >= target:
                return open_price, "target_gap", False
            hit_stop = low <= stop
            hit_target = target is not None and high >= target
        else:
            if open_price >= stop:
                return open_price, "stop_gap", True
            if target is not None and open_price <= target:
                return open_price, "target_gap", False
            hit_stop = high >= stop
            hit_target = target is not None and low <= target

        if hit_stop and hit_target:
            if self.config.same_bar_policy == "target_first":
                return float(target), "target_same_bar", False
            return stop, "stop_same_bar", True
        if hit_stop:
            return stop, "stop", True
        if hit_target:
            return float(target), "target", False
        return None

    def _close_position(
        self,
        position: Position,
        timestamp: datetime,
        raw_price: float,
        reason: str,
        balance: float,
        *,
        market_fill: bool,
    ) -> tuple[BacktestTrade, float]:
        exit_price = (
            _apply_market_costs(
                raw_price, position.direction, entering=False,
                slippage_bps=self.config.slippage_bps, spread_bps=self.config.spread_bps,
            )
            if market_fill else float(raw_price)
        )
        multiplier = 1.0 if position.direction == "long" else -1.0
        remaining_quantity = float(position.quantity)
        final_gross = (exit_price - position.entry_price) * remaining_quantity * multiplier
        exit_commission = max(0.0, float(self.config.commission_per_order))
        gross = position.realized_gross + final_gross
        fees = position.entry_commission + position.exit_commissions + exit_commission
        net = gross - fees
        # Partial fills have already affected balance when they occurred. At the
        # final exit apply only the remaining gross P&L and final commission.
        new_balance = balance + final_gross - exit_commission
        r_multiple = net / position.initial_risk_amount if position.initial_risk_amount > 0 else None
        planned_target = position.initial_take_profit
        planned_rr = (
            abs(planned_target - position.entry_price) / position.initial_risk_per_share
            if planned_target is not None and position.initial_risk_per_share > 0 else None
        )
        initial_notional = position.initial_notional
        pnl_pct = net / initial_notional * 100 if initial_notional > 0 else None
        total_exit_quantity = position.exited_quantity + remaining_quantity
        weighted_exit_value = position.weighted_exit_value + exit_price * remaining_quantity
        average_exit_price = weighted_exit_value / total_exit_quantity if total_exit_quantity > 0 else exit_price
        result = "win" if net > 1e-9 else "loss" if net < -1e-9 else "breakeven"
        trade = BacktestTrade(
            symbol=position.symbol,
            direction=position.direction,
            entry_time=position.entry_time,
            exit_time=timestamp,
            entry_price=position.entry_price,
            exit_price=average_exit_price,
            quantity=float(position.initial_quantity or total_exit_quantity),
            stop_loss=float(position.initial_stop_loss if position.initial_stop_loss is not None else position.stop_loss),
            take_profit=position.initial_take_profit,
            initial_risk_amount=position.initial_risk_amount,
            gross_pnl=gross,
            fees=fees,
            net_pnl=net,
            pnl_pct=pnl_pct,
            r_multiple=r_multiple,
            planned_rr=planned_rr,
            result=result,
            exit_reason=reason,
            signal_reason=position.signal_reason,
            metadata={
                **dict(position.metadata),
                "final_stop_loss": position.stop_loss,
                "final_take_profit": position.take_profit,
                "partial_exits": list(position.partial_exits),
            },
        )
        return trade, new_balance


def _entry_fill_price(signal: EntrySignal, bar: pd.Series) -> float | None:
    if signal.order_type == "market":
        return float(bar["open"])
    if signal.order_type != "limit" or signal.entry_price is None:
        return None
    price = float(signal.entry_price)
    open_price, high, low = float(bar["open"]), float(bar["high"]), float(bar["low"])
    if signal.direction == "long":
        if open_price <= price:
            return open_price
        return price if low <= price else None
    if open_price >= price:
        return open_price
    return price if high >= price else None


def _setup_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    filled = sum(1 for row in records if row.get("status") == "filled")
    not_filled = sum(1 for row in records if row.get("status") == "not_filled")
    return {
        "setups": total,
        "filled_entries": filled,
        "not_filled": not_filled,
        "entry_fill_rate_pct": (filled / total * 100.0) if total else None,
    }


def calculate_metrics(
    trades: list[BacktestTrade],
    starting_balance: float,
    ending_balance: float,
    equity_curve: list[dict[str, Any]],
) -> dict[str, Any]:
    rs = [float(t.r_multiple) for t in trades if t.r_multiple is not None]
    planned = [float(t.planned_rr) for t in trades if t.planned_rr is not None]
    wins = [t for t in trades if t.result == "win"]
    losses = [t for t in trades if t.result == "loss"]
    breakeven = [t for t in trades if t.result == "breakeven"]
    positive_r = sum(r for r in rs if r > 0)
    negative_r = abs(sum(r for r in rs if r < 0))
    gross_profit = sum(max(0.0, t.net_pnl) for t in trades)
    gross_loss = abs(sum(min(0.0, t.net_pnl) for t in trades))
    max_dd_cash, max_dd_pct = _equity_drawdown(starting_balance, equity_curve, ending_balance)
    max_dd_r = _r_drawdown(rs)
    avg_win_r = sum(float(t.r_multiple or 0) for t in wins) / len(wins) if wins else None
    avg_loss_r = sum(float(t.r_multiple or 0) for t in losses) / len(losses) if losses else None
    durations = [max(0.0, (t.exit_time - t.entry_time).total_seconds() / 60.0) for t in trades]
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate_pct": (len(wins) / len(trades) * 100) if trades else None,
        "average_r": (sum(rs) / len(rs)) if rs else None,
        "expectancy_r": (sum(rs) / len(rs)) if rs else None,
        "median_r": median(rs) if rs else None,
        "total_r": sum(rs),
        "average_planned_rr": (sum(planned) / len(planned)) if planned else None,
        "average_winner_r": avg_win_r,
        "average_loser_r": avg_loss_r,
        "largest_winner_r": max((r for r in rs if r > 0), default=None),
        "largest_loser_r": min((r for r in rs if r < 0), default=None),
        "profit_factor_r": (positive_r / negative_r) if negative_r > 0 else None,
        "profit_factor_cash": (gross_profit / gross_loss) if gross_loss > 0 else None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_pnl": ending_balance - starting_balance,
        "starting_balance": starting_balance,
        "ending_balance": ending_balance,
        "return_pct": ((ending_balance / starting_balance) - 1) * 100 if starting_balance else None,
        "max_drawdown_cash": max_dd_cash,
        "max_drawdown_pct": max_dd_pct,
        "max_drawdown_r": max_dd_r,
        "longest_losing_streak": _longest_losing_streak(trades),
        "average_hold_minutes": sum(durations) / len(durations) if durations else None,
    }


def calculate_analysis(trades: list[BacktestTrade], tz: ZoneInfo) -> dict[str, Any]:
    def symbol(t: BacktestTrade) -> str: return t.symbol
    def direction(t: BacktestTrade) -> str: return t.direction
    def exit_reason(t: BacktestTrade) -> str: return t.exit_reason
    def signal_reason(t: BacktestTrade) -> str: return t.signal_reason or "unspecified"
    def session(t: BacktestTrade) -> str: return str((t.metadata or {}).get("session") or "unlabelled")
    def entry_hour(t: BacktestTrade) -> str:
        hour = t.entry_time.astimezone(tz).hour
        return f"{hour:02d}:00–{hour:02d}:59 ET"
    def weekday(t: BacktestTrade) -> str:
        return t.entry_time.astimezone(tz).strftime("%A")
    def month(t: BacktestTrade) -> str:
        return t.entry_time.astimezone(tz).strftime("%Y-%m")

    breakdowns = {
        "symbol": _group_breakdown(trades, symbol, "symbol"),
        "direction": _group_breakdown(trades, direction, "direction"),
        "session": _group_breakdown(trades, session, "session"),
        "entry_hour": _group_breakdown(trades, entry_hour, "entry_hour"),
        "weekday": _ordered_weekday_breakdown(trades, weekday),
        "month": _group_breakdown(trades, month, "month"),
        "exit_reason": _group_breakdown(trades, exit_reason, "exit_reason"),
        "signal_reason": _group_breakdown(trades, signal_reason, "signal_reason"),
    }
    observations: list[dict[str, str]] = []
    rs = [float(t.r_multiple) for t in trades if t.r_multiple is not None]
    if rs:
        expectancy = sum(rs) / len(rs)
        observations.append({
            "kind": "overall",
            "title": "Overall sample expectancy",
            "text": f"This sample averaged {expectancy:+.2f}R per completed trade across {len(rs)} completed trade{'s' if len(rs) != 1 else ''}.",
        })
    qualified_hours = [row for row in breakdowns["entry_hour"] if row["trades"] >= 5 and row["average_r"] is not None]
    if qualified_hours:
        best = max(qualified_hours, key=lambda row: row["average_r"])
        worst = min(qualified_hours, key=lambda row: row["average_r"])
        observations.append({
            "kind": "time",
            "title": "Time-of-day spread",
            "text": f"Among entry-hour buckets with at least 5 trades, {best['entry_hour']} had the highest sample expectancy ({best['average_r']:+.2f}R) and {worst['entry_hour']} the lowest ({worst['average_r']:+.2f}R).",
        })
    directions = {row["direction"]: row for row in breakdowns["direction"] if row["trades"] >= 5}
    if "long" in directions and "short" in directions:
        long_r = directions["long"]["average_r"]
        short_r = directions["short"]["average_r"]
        if long_r is not None and short_r is not None:
            observations.append({
                "kind": "direction",
                "title": "Long vs short",
                "text": f"Long trades averaged {long_r:+.2f}R in this sample; short trades averaged {short_r:+.2f}R.",
            })
    gap_trades = [t for t in trades if "gap" in t.exit_reason]
    if gap_trades:
        total_gap_r = sum(float(t.r_multiple or 0) for t in gap_trades)
        worst_gap = min(gap_trades, key=lambda t: float(t.r_multiple or 0))
        observations.append({
            "kind": "gaps",
            "title": "Gap exposure",
            "text": f"{len(gap_trades)} gap-related exit{'s' if len(gap_trades) != 1 else ''} contributed {total_gap_r:+.2f}R in total. The largest was {worst_gap.symbol} at {float(worst_gap.r_multiple or 0):+.2f}R.",
        })
    session_closes = [t for t in trades if t.exit_reason == "session_close"]
    if session_closes:
        avg = sum(float(t.r_multiple or 0) for t in session_closes) / len(session_closes)
        observations.append({
            "kind": "session",
            "title": "Forced session closes",
            "text": f"{len(session_closes)} trade{'s' if len(session_closes) != 1 else ''} {'were' if len(session_closes) != 1 else 'was'} flattened by the no-overnight rule; those exits averaged {avg:+.2f}R.",
        })

    largest_losses = sorted(
        (_trade_dict(t) for t in trades if t.r_multiple is not None),
        key=lambda t: float(t["r_multiple"]),
    )[:5]
    return {
        "breakdowns": breakdowns,
        "observations": observations,
        "largest_losses": largest_losses,
        "note": "Descriptive analysis only. Do not change a strategy because one historical bucket looks better; re-test hypotheses on validation/out-of-sample data.",
    }


def _group_breakdown(
    trades: list[BacktestTrade],
    key_fn: Callable[[BacktestTrade], str],
    label_key: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[BacktestTrade]] = defaultdict(list)
    for trade in trades:
        grouped[str(key_fn(trade))].append(trade)
    rows = []
    for label, items in sorted(grouped.items(), key=lambda pair: pair[0]):
        rs = [float(t.r_multiple) for t in items if t.r_multiple is not None]
        planned = [float(t.planned_rr) for t in items if t.planned_rr is not None]
        wins = sum(1 for t in items if t.result == "win")
        pos = sum(r for r in rs if r > 0)
        neg = abs(sum(r for r in rs if r < 0))
        rows.append({
            label_key: label,
            "trades": len(items),
            "win_rate_pct": wins / len(items) * 100 if items else None,
            "average_r": sum(rs) / len(rs) if rs else None,
            "total_r": sum(rs),
            "net_pnl": sum(t.net_pnl for t in items),
            "profit_factor_r": pos / neg if neg > 0 else None,
            "average_planned_rr": sum(planned) / len(planned) if planned else None,
        })
    return rows


def _ordered_weekday_breakdown(trades: list[BacktestTrade], key_fn) -> list[dict[str, Any]]:
    order = {name: i for i, name in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])}
    return sorted(_group_breakdown(trades, key_fn, "weekday"), key=lambda row: order.get(row["weekday"], 99))


def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    working = frame.copy()
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(working.columns)
    if missing:
        raise ValueError(f"Bars missing required columns: {', '.join(sorted(missing))}")
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        if column in working.columns:
            working[column] = pd.to_numeric(working[column], errors="coerce")
    return working.dropna(subset=["timestamp", "open", "high", "low", "close"]).drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


def _row_to_series(row: Any) -> pd.Series:
    if isinstance(row, pd.Series):
        return row
    return pd.Series(row._asdict())


def _apply_market_costs(price: float, direction: str, *, entering: bool, slippage_bps: float, spread_bps: float) -> float:
    # OHLC bars are trade prices, not true historical bid/ask quotes. This is an
    # explicit approximation: half of the assumed full spread plus slippage is
    # applied adversely to market-like executions.
    adverse_bps = max(0.0, float(slippage_bps)) + max(0.0, float(spread_bps)) / 2.0
    adverse = adverse_bps / 10_000.0
    if adverse == 0:
        return float(price)
    adverse_up = (direction == "long" and entering) or (direction == "short" and not entering)
    return float(price) * (1 + adverse if adverse_up else 1 - adverse)


def _unrealized_total(positions: dict[str, Position], prices: dict[str, float]) -> float:
    total = 0.0
    for symbol, position in positions.items():
        price = prices.get(symbol)
        if price is None:
            continue
        multiplier = 1.0 if position.direction == "long" else -1.0
        total += (price - position.entry_price) * position.quantity * multiplier
    return total


def _merge_equity_points(curve: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a strictly increasing timestamp series for charting.

    A final end-of-data liquidation can occur at the same timestamp as the last
    mark-to-market point. Lightweight Charts rejects duplicate timestamps, so
    merge same-time events rather than emitting two points. This is also safer
    for future multi-position end-of-data handling.
    """
    merged: dict[datetime, dict[str, Any]] = {}
    for raw in curve:
        timestamp = datetime.fromisoformat(str(raw["timestamp"]).replace("Z", "+00:00"))
        existing = merged.get(timestamp)
        if existing is None:
            merged[timestamp] = {
                **raw,
                "timestamp": timestamp.isoformat(),
                "realized_pnl": float(raw.get("realized_pnl") or 0.0),
                "closed_trades": list(raw.get("closed_trades") or []),
            }
            continue
        existing["equity"] = float(raw["equity"])
        existing["realized_pnl"] = float(existing.get("realized_pnl") or 0.0) + float(raw.get("realized_pnl") or 0.0)
        existing["closed_trades"] = [*(existing.get("closed_trades") or []), *(raw.get("closed_trades") or [])]
    return [merged[key] for key in sorted(merged)]


def _decorate_equity_curve(starting_balance: float, curve: list[dict[str, Any]]) -> list[dict[str, Any]]:
    peak = float(starting_balance)
    cumulative_r = 0.0
    output = []
    for point in curve:
        value = float(point["equity"])
        peak = max(peak, value)
        drawdown_cash = value - peak
        drawdown_pct = drawdown_cash / peak * 100 if peak else 0.0
        cumulative_r += sum(float(trade.get("r_multiple") or 0.0) for trade in point.get("closed_trades") or [])
        return_pct = ((value / starting_balance) - 1) * 100 if starting_balance else 0.0
        output.append({
            **point,
            "drawdown_cash": drawdown_cash,
            "drawdown_pct": drawdown_pct,
            "peak_equity": peak,
            "return_pct": return_pct,
            "cumulative_r": cumulative_r,
        })
    return output


def _equity_drawdown(starting_balance: float, curve: list[dict[str, Any]], ending_balance: float) -> tuple[float, float]:
    values = [float(starting_balance)] + [float(point["equity"]) for point in curve] + [float(ending_balance)]
    peak = values[0]
    worst_cash = 0.0
    worst_pct = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = value - peak
        pct = (drawdown / peak * 100) if peak else 0.0
        worst_cash = min(worst_cash, drawdown)
        worst_pct = min(worst_pct, pct)
    return worst_cash, worst_pct


def _r_drawdown(rs: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for r_value in rs:
        equity += r_value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def _longest_losing_streak(trades: list[BacktestTrade]) -> int:
    best = current = 0
    for trade in sorted(trades, key=lambda t: (t.exit_time, t.symbol)):
        if trade.result == "loss":
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _register_trade_result(trade: BacktestTrade, day_results: dict, tz: ZoneInfo) -> None:
    day = trade.exit_time.astimezone(tz).date()
    state = day_results[day]
    state["r"] = float(state["r"]) + float(trade.r_multiple or 0.0)
    if trade.result == "loss":
        state["consecutive_losses"] = int(state["consecutive_losses"]) + 1
    else:
        state["consecutive_losses"] = 0


def _trade_event(trade: BacktestTrade) -> dict[str, Any]:
    return {
        "symbol": trade.symbol,
        "direction": trade.direction,
        "entry_time": trade.entry_time.isoformat(),
        "exit_time": trade.exit_time.isoformat(),
        "exit_reason": trade.exit_reason,
        "net_pnl": trade.net_pnl,
        "r_multiple": trade.r_multiple,
    }


def _trade_dict(trade: BacktestTrade) -> dict[str, Any]:
    value = asdict(trade)
    value["entry_time"] = trade.entry_time.isoformat()
    value["exit_time"] = trade.exit_time.isoformat()
    value["duration_minutes"] = max(0.0, (trade.exit_time - trade.entry_time).total_seconds() / 60.0)
    return value



def _rejection_summary(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[str(item.get("reason") or "unknown")] += 1
    return [
        {"reason": reason, "count": count}
        for reason, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]

def _rejected(symbol: str, timestamp: datetime, reason: str) -> dict[str, Any]:
    return {"symbol": symbol, "timestamp": timestamp.isoformat(), "reason": reason}


def _parse_clock(value: str | None) -> time:
    if not value:
        raise ValueError("Time value is required")
    try:
        hour, minute = str(value).split(":", 1)
        return time(hour=int(hour), minute=int(minute))
    except Exception as exc:
        raise ValueError(f"Invalid time '{value}'; expected HH:MM") from exc


def _to_datetime(value: pd.Timestamp) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.to_pydatetime().astimezone(timezone.utc)
