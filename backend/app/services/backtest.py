from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.backtesting.engine import BacktestEngine
from app.backtesting.models import BacktestConfig
from app.backtesting.momentum_reporting import completed_daily_frame, annotate_result
from app.backtesting.strategies.momentum_vcp_breakout_baseline_v1 import KEY as MOMENTUM_KEY
from app.backtesting.strategies import strategy_registry
from app.backtesting.strategies.intraday_baselines import KEYS as INTRADAY_KEYS, validate_market
from app.backtesting.intraday_reporting import annotate_intraday
from app.backtesting.strategies.gold_experiments import KEYS as GOLD_EXPERIMENT_KEYS
from app.backtesting.gold_reporting import annotate_gold
from app.indicators import indicator_registry
from app.services.chart_data import prepare_chart_bars
from app.services.replay_snapshot import aggregate_revealed
from app.services.market_data import MarketDataService
from app.data.instruments import instrument_spec
from app.data.futures import validate_execution_symbol, validate_execution_frame
from app.storage.backtest_run_repository import BacktestRunRepository

NY = ZoneInfo("America/New_York")
SUPPORTED_TIMEFRAMES = ("1m", "5m", "15m", "30m", "1h", "4h", "1d")
SESSION_ENDS = {"regular": "16:00", "extended": "20:00", "24h": "23:59"}


class BacktestService:
    def __init__(self, market_data: MarketDataService | None, runs: BacktestRunRepository | None = None):
        self.market_data = market_data
        self.runs = runs

    def _instrument(self, symbol: str):
        if self.market_data is not None and hasattr(self.market_data, "instrument_info"):
            return self.market_data.instrument_info(symbol)
        return instrument_spec(symbol)

    def _provider(self, symbol: str):
        if self.market_data is None:
            return None
        if hasattr(self.market_data, "provider_for"):
            return self.market_data.provider_for(symbol)
        return getattr(self.market_data, "provider", None)

    def _delay(self, symbol: str) -> int:
        if self.market_data is not None and hasattr(self.market_data, "historical_delay_minutes"):
            return max(0, int(self.market_data.historical_delay_minutes(symbol)))
        return max(0, int(getattr(self._provider(symbol), "historical_delay_minutes", 0)))

    def _latest_available_end(self, symbol: str, timeframe: str, reference: datetime) -> datetime:
        if self.market_data is not None and hasattr(self.market_data, "latest_available_end"):
            return self.market_data.latest_available_end(symbol, timeframe, reference)
        return reference

    def strategies(self) -> list[dict]:
        result = []
        for spec in strategy_registry.specs():
            item = asdict(spec)
            item["parameters"] = [asdict(parameter) for parameter in spec.parameters]
            item["research_parameters"] = [asdict(parameter) for parameter in spec.research_parameters]
            result.append(item)
        return result

    def indicators(self) -> list[dict]:
        return [asdict(spec) for spec in indicator_registry.specs()]

    def run(self, payload: dict, *, progress=None, persist=None) -> dict:
        progress = progress or (lambda *args: None)
        progress('preparing data', None, None)
        if self.market_data is None:
            raise RuntimeError("No market data provider is configured")
        strategy_key = str(payload.get("strategy_key") or "").strip()
        if not strategy_key:
            raise ValueError("strategy_key is required")
        try:
            strategy_spec = next(spec for spec in strategy_registry.specs() if spec.key == strategy_key)
        except StopIteration as exc:
            raise ValueError(f"Unknown strategy '{strategy_key}'") from exc

        symbols = _symbols(payload.get("symbols"))
        if not symbols:
            raise ValueError("At least one symbol is required")
        if len(symbols) > 20:
            raise ValueError("Phase 5 limits one run to 20 symbols; split larger research runs into batches")

        for symbol in symbols:
            validate_execution_symbol(symbol)

        primary = str(payload.get("primary_timeframe") or strategy_spec.timeframes[0])
        if primary not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported primary timeframe '{primary}'")
        requested_session = str(payload.get("session") or "auto")
        if requested_session not in {"auto", "regular", "extended", "24h"}:
            raise ValueError("session must be auto, regular, extended or 24h")
        profiles = {self._instrument(symbol).session_profile for symbol in symbols}
        session = ("regular" if profiles == {"us_equity"} else "24h") if requested_session == "auto" else requested_session
        momentum = strategy_key == MOMENTUM_KEY
        if strategy_key in GOLD_EXPERIMENT_KEYS and (symbols != ["XAUUSD"] or primary != "1m"):
            raise ValueError("Gold experiments require XAUUSD only and primary 1m")
        if strategy_key in INTRADAY_KEYS:
            for symbol in symbols:
                validate_market(symbol, primary)
        if momentum and (primary != "1d" or profiles != {"us_equity"}
                         or session != "regular" or not bool(payload.get("allow_overnight", True))
                         or payload.get("additional_timeframes")):
            raise ValueError("Momentum baseline requires US equity daily bars, regular/auto session, overnight enabled and no extra timeframes")

        start_date = _as_date(payload.get("start_date"), "start_date")
        end_date = _as_date(payload.get("end_date"), "end_date")
        if start_date > end_date:
            raise ValueError("start_date must be on or before end_date")
        start = datetime.combine(start_date, time.min, tzinfo=NY).astimezone(timezone.utc)
        end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=NY).astimezone(timezone.utc)
        delay = max(self._delay(symbol) for symbol in symbols)
        latest_allowed = datetime.now(timezone.utc) - timedelta(minutes=delay + (1 if delay else 0))
        provider_ends = [self._latest_available_end(symbol, primary, latest_allowed) for symbol in symbols]
        latest_allowed = min([latest_allowed, *provider_ends])
        if end > latest_allowed:
            end = latest_allowed
        if start >= end:
            raise ValueError("Requested period is too recent for the configured historical-data delay")

        additional = [str(tf) for tf in (payload.get("additional_timeframes") or []) if str(tf) in SUPPORTED_TIMEFRAMES]
        requested_timeframes = list(dict.fromkeys([primary, *strategy_spec.timeframes, *additional]))
        frames_by_symbol: dict[str, dict] = {}
        for symbol in symbols:
            frames: dict = {}
            for timeframe in requested_timeframes:
                progress('preparing data', None, None)
                frames[timeframe] = self._load_timeframe(symbol, timeframe, start, end, session)
                if momentum:
                    frames[timeframe] = completed_daily_frame(frames[timeframe], end)
            frames_by_symbol[symbol] = frames

        params = dict(payload.get("strategy_params") or {})
        strategies = {symbol: strategy_registry.create(strategy_key, **params) for symbol in symbols}
        entry_windows = _entry_windows(payload.get("entry_windows"))
        weekdays = _weekdays(payload.get("trading_weekdays"))
        allow_overnight = bool(payload.get("allow_overnight", True))
        force_close_time = _optional_clock(payload.get("force_close_time")) if not allow_overnight else None
        config = BacktestConfig(
            starting_balance=float(payload.get("starting_balance") or 10_000),
            sizing_mode=str(payload.get("sizing_mode") or "risk_pct"),
            risk_value=float(payload.get("risk_value") or 1.0),
            commission_per_order=float(payload.get("commission_per_order") or 0.0),
            slippage_bps=float(payload.get("slippage_bps") or 0.0),
            spread_bps=float(payload.get("spread_bps") or 0.0),
            max_leverage=float(payload.get("max_leverage") or 1.0),
            max_open_positions=int(payload.get("max_open_positions") or 5),
            same_bar_policy=str(payload.get("same_bar_policy") or "stop_first"),
            entry_windows=entry_windows,
            trading_weekdays=weekdays,
            session_end=SESSION_ENDS[session],
            allow_overnight=allow_overnight,
            force_close_time=force_close_time,
            max_trades_per_day=_optional_positive_int(payload.get("max_trades_per_day")),
            max_daily_loss_r=_optional_positive_float(payload.get("max_daily_loss_r")),
            max_consecutive_losses=_optional_positive_int(payload.get("max_consecutive_losses")),
            cooldown_minutes=max(0, int(payload.get("cooldown_minutes") or 0)),
        )
        result = BacktestEngine(config).run(
            symbol_frames=frames_by_symbol,
            strategies=strategies,
            primary_timeframe=primary,
            progress=lambda done, total: progress('running', done, total),
        )
        result.update({
            "strategy": {"key": strategy_spec.key, "name": strategy_spec.name, "params": params},
            "symbols": symbols,
            "primary_timeframe": primary,
            "additional_timeframes": additional,
            "session": session,
            "requested_session": requested_session,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "data": {
                "historical_delay_minutes": delay,
                "providers": {
                    symbol: {
                        "provider": getattr(self._provider(symbol), "key", None),
                        "feed": getattr(self._provider(symbol), "historical_feed", None),
                        "adjustment": 'unadjusted' if self._instrument(symbol).asset_type == 'future' else getattr(self._provider(symbol), "adjustment", None),
                        'roll_schedule_versions': sorted(set(str(v) for frame in frames_by_symbol[symbol].values() if 'roll_schedule_version' in frame for v in frame.roll_schedule_version)),
                        "instrument": self._instrument(symbol).as_dict(),
                    } for symbol in symbols
                },
                "bar_counts": {
                    symbol: {timeframe: len(frame) for timeframe, frame in frames.items()}
                    for symbol, frames in frames_by_symbol.items()
                },
            },
        })
        if momentum:
            annotate_result(result, frames_by_symbol, strategies[symbols[0]].params)
            payload = {**payload, "strategy_params": dict(strategies[symbols[0]].params)}
        if strategy_key in INTRADAY_KEYS:
            annotate_intraday(result, frames_by_symbol)
            result["strategy"]["params"] = dict(strategies[symbols[0]].params)
            payload = {**payload, "strategy_params": dict(strategies[symbols[0]].params)}
        if strategy_key in GOLD_EXPERIMENT_KEYS or strategy_key == "xau_liquidity_type3_baseline_v1":
            annotate_gold(result, frames_by_symbol, config, strategies[symbols[0]].params)
            payload = {**payload, "strategy_params": dict(strategies[symbols[0]].params)}
        if self.runs is not None and bool(payload.get("save_run", True)):
            def save():
                return self.runs.create(
                    config=_snapshot_config(payload, strategy_key=strategy_key, symbols=symbols),
                    result=result,
                    name=str(payload.get("run_name") or ""),
                    notes=str(payload.get("run_notes") or ""),
                    test_role=str(payload.get("test_role") or "development"),
                    experiment_group=str(payload.get("experiment_group") or ""),
                    tags=payload.get("run_tags") or [],
                )
            saved = persist(save) if persist else save()
            result["saved_run"] = {
                "id": saved["id"], "name": saved["name"], "test_role": saved["test_role"],
                "experiment_group": saved.get("experiment_group", ""), "tags": saved.get("tags", []),
                "created_at": saved["created_at"],
            }
        return result

    def list_runs(self, *, limit: int = 100) -> list[dict]:
        if self.runs is None:
            return []
        return self.runs.list(limit=limit)

    def get_run(self, run_id: int) -> dict:
        if self.runs is None:
            raise ValueError("Backtest run history is unavailable")
        return self.runs.get(run_id)

    def get_experiment(self, experiment_group: str) -> dict:
        if self.runs is None:
            raise ValueError("Backtest run history is unavailable")
        group = str(experiment_group or "").strip()
        if not group:
            raise ValueError("experiment_group is required")
        runs = self.runs.list_by_experiment(group)
        if not runs:
            raise ValueError(f"Validation experiment '{group}' was not found")
        return {"experiment_group": group, "runs": runs}


    def update_run(self, run_id: int, *, name=None, notes=None, test_role=None, tags=None) -> dict:
        if self.runs is None:
            raise ValueError("Backtest run history is unavailable")
        return self.runs.update_metadata(run_id, name=name, notes=notes, test_role=test_role, tags=tags)

    def delete_run(self, run_id: int) -> None:
        if self.runs is None:
            raise ValueError("Backtest run history is unavailable")
        self.runs.delete(run_id)

    def replay_bars(
        self, *, symbol: str, timeframe: str, session: str, replay_date: date,
        start_time: str, context_bars: int = 100, replay_end_date: date | None = None,
        context_days: int | None = None,
        frontier: datetime | None = None,
    ) -> dict:
        """Load a multi-session historical replay dataset with a strict reveal boundary."""
        if self.market_data is None:
            raise RuntimeError("No market data provider is configured")
        symbol = str(symbol or "").strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        if timeframe not in SUPPORTED_TIMEFRAMES or timeframe == "1d":
            raise ValueError(f"Unsupported timeframe '{timeframe}'")
        if session not in {"regular", "extended", "24h"}:
            raise ValueError("session must be regular, extended or 24h")
        clock = _required_clock(start_time)
        context_bars = max(0, min(50_000, int(context_bars or 0)))
        if context_days is not None:
            context_days = max(1, min(365, int(context_days)))
        replay_end_date = replay_end_date or replay_date
        if replay_end_date < replay_date:
            raise ValueError("replay_end_date must be on or after replay_date")
        if replay_end_date > replay_date + timedelta(days=366):
            raise ValueError("Replay horizon cannot exceed 366 calendar days in one load")

        hour, minute = map(int, clock.split(":"))
        reveal_at = datetime.combine(replay_date, time(hour, minute), tzinfo=NY).astimezone(timezone.utc)
        if self._instrument(symbol).session_profile == "us_equity":
            eh, em = map(int, SESSION_ENDS[session].split(":"))
            requested_end = datetime.combine(replay_end_date, time(eh, em), tzinfo=NY).astimezone(timezone.utc)
        else:
            requested_end = datetime.combine(replay_end_date + timedelta(days=1), time.min, tzinfo=NY).astimezone(timezone.utc)

        spec = self._instrument(symbol)
        provider = self._provider(symbol)
        delay = self._delay(symbol)
        latest_allowed = datetime.now(timezone.utc) - timedelta(minutes=delay + (1 if delay else 0))
        latest_allowed = self._latest_available_end(symbol, timeframe, latest_allowed)
        if reveal_at > latest_allowed:
            raise ValueError("Replay start is too recent for the configured historical-data delay")
        replay_end = min(requested_end, latest_allowed)

        if context_days is not None:
            frame, aggregation = self._load_replay_timeframe(symbol, "1m", reveal_at - timedelta(days=context_days), replay_end, session)
        else:
            before_days = _audit_calendar_days(timeframe, session, context_bars)
            frame = None
            for _ in range(6):
                frame, aggregation = self._load_replay_timeframe(symbol, "1m", reveal_at - timedelta(days=before_days), replay_end, session)
                if frame is not None and not frame.empty:
                    import pandas as pd
                    ts = pd.to_datetime(frame["timestamp"], utc=True)
                    known = aggregate_revealed(frame.loc[ts < pd.Timestamp(reveal_at)], timeframe, session, spec.session_profile)
                    if len(known) >= context_bars:
                        break
                before_days = min(900, max(before_days + 1, before_days * 2))

        if frame is None or frame.empty:
            raise ValueError("No historical bars were returned for this replay")
        import pandas as pd
        working = frame.copy().sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
        timestamps = pd.to_datetime(working["timestamp"], utc=True)
        local_dates = timestamps.dt.tz_convert(NY).dt.date
        requested_replay_date = replay_date
        effective_reveal_at = reveal_at
        if int((local_dates == replay_date).sum()) <= 0 or not (timestamps <= pd.Timestamp(reveal_at)).any():
            # A weekend/holiday should not make Replay unusable. Move the reveal
            # frontier to the first available displayed bar after the requested
            # start, while preserving the originally requested date in metadata.
            candidates = working.index[timestamps >= pd.Timestamp(reveal_at)].tolist()
            if not candidates:
                raise ValueError("No session bars exist on or after the selected replay date in the loaded range")
            first_available_idx = candidates[0]
            effective_reveal_at = timestamps.iloc[first_available_idx].to_pydatetime()
            replay_date = local_dates.iloc[first_available_idx]
        if context_days is None:
            initial = aggregate_revealed(working.loc[timestamps <= pd.Timestamp(effective_reveal_at)], timeframe, session, spec.session_profile)
            first_stamp = initial.iloc[max(0, len(initial)-1-context_bars)].timestamp
            working = working.loc[timestamps >= first_stamp].reset_index(drop=True)
            timestamps = pd.to_datetime(working["timestamp"], utc=True)
        visible = max(1, int((timestamps <= pd.Timestamp(effective_reveal_at)).sum()))
        cutoff = pd.Timestamp(frontier or effective_reveal_at)
        if cutoff.tzinfo is None:
            raise ValueError("Replay frontier must include a timezone")
        if cutoff < pd.Timestamp(effective_reveal_at) or cutoff > pd.Timestamp(replay_end):
            raise ValueError("Replay frontier must lie within the replay horizon")
        revealed = working.loc[timestamps <= cutoff].copy()
        validate_execution_frame(symbol,revealed)
        display = aggregate_revealed(revealed, timeframe, session, spec.session_profile)
        display["timestamp"] = display["timestamp"].astype(str)
        revealed["timestamp"] = revealed["timestamp"].astype(str)
        working["timestamp"] = working["timestamp"].astype(str)
        replay_dates = pd.to_datetime(working["timestamp"], utc=True).dt.tz_convert(NY).dt.date
        return {
            "symbol": symbol, "timeframe": timeframe, "session": session,
            "replay_date": replay_date.isoformat(), "requested_replay_date": requested_replay_date.isoformat(),
            "replay_end_date": replay_end_date.isoformat(),
            "start_time": clock, "session_timezone": "America/New_York",
            "context_bars": context_bars if context_days is None else None, "context_days": context_days,
            "initial_visible_count": min(visible, len(working)), "count": len(working),
            "replay_session_dates": sorted({d.isoformat() for d in replay_dates if d >= replay_date}),
            "bars": display.to_dict(orient="records"),
            "source_bars": revealed.to_dict(orient="records"),
            "timeline": working["timestamp"].tolist(),
            "frontier": str(revealed["timestamp"].iloc[-1]),
            "visible_count": len(revealed),
            "provider": getattr(provider, "key", None),
            "feed": getattr(provider, "historical_feed", None),
            "adjustment": 'unadjusted' if spec.asset_type == 'future' else getattr(provider, "adjustment", None),
            "instrument": spec.as_dict(),
            "effective_session": session if spec.session_profile == "us_equity" else "24h",
            "source_timeframe": "1m" if timeframe not in {"1d", "1w"} else timeframe,
            "aggregation": "replay_causal_aligned_from_1m",
        }

    def replay_indicator(
        self, *, symbol: str, timeframe: str, session: str, replay_date: date,
        start_time: str, context_bars: int, key: str, params: dict | None = None,
        replay_end_date: date | None = None, context_days: int | None = None,
        frontier: datetime | None = None,
    ) -> dict:
        import pandas as pd
        replay = self.replay_bars(
            symbol=symbol, timeframe=timeframe, session=session, replay_date=replay_date,
            replay_end_date=replay_end_date, start_time=start_time, context_bars=context_bars,
            context_days=context_days, frontier=frontier,
        )
        try:
            indicator = indicator_registry.create(key)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        if not indicator.spec.causal:
            raise ValueError("Replay only permits causal indicators so future bars cannot alter past values")
        frame = pd.DataFrame(replay["bars"])
        values = indicator.calculate(frame, **(params or {}))
        if getattr(values, "ndim", 1) > 1:
            raise ValueError("This Replay version supports single-series indicators only")
        output = []
        for index, value in values.items():
            if value is None or pd.isna(value):
                continue
            try:
                row = frame.iloc[int(index)] if isinstance(index, int) else frame.loc[index]
            except Exception:
                continue
            output.append({"timestamp": str(row["timestamp"]), "value": float(value)})
        return {"key": key, "params": params or {}, "values": output,
                "overlay": bool(indicator.spec.overlay), "name": indicator.spec.name}

    def audit_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
        session: str,
        start: datetime | None = None,
        end: datetime | None = None,
        entry: datetime | None = None,
        exit: datetime | None = None,
        before_bars: int = 50,
        after_bars: int = 20,
    ) -> dict:
        if self.market_data is None:
            raise RuntimeError("No market data provider is configured")
        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe '{timeframe}'")
        if session not in {"regular", "extended", "24h"}:
            raise ValueError("session must be regular, extended or 24h")

        use_context = entry is not None or exit is not None
        if use_context:
            if entry is None or exit is None:
                raise ValueError("Both entry and exit timestamps are required for bar-count audit context")
            if entry.tzinfo is None or exit.tzinfo is None:
                raise ValueError("Audit timestamps must include a timezone")
            entry = entry.astimezone(timezone.utc)
            exit = exit.astimezone(timezone.utc)
            if exit < entry:
                raise ValueError("Audit exit must be on or after entry")
            before_bars = max(0, min(500, int(before_bars)))
            after_bars = max(0, min(200, int(after_bars)))
            output = self._load_audit_context(
                symbol.upper(), timeframe, session, entry, exit, before_bars, after_bars,
            )
        else:
            if start is None or end is None:
                raise ValueError("Audit requires either entry/exit or start/end timestamps")
            if start.tzinfo is None or end.tzinfo is None:
                raise ValueError("Audit timestamps must include a timezone")
            start = start.astimezone(timezone.utc)
            end = end.astimezone(timezone.utc)
            if start >= end:
                raise ValueError("Audit start must be before end")
            if end - start > timedelta(days=900):
                raise ValueError("Trade audit window cannot exceed 900 days")
            delay = self._delay(symbol)
            latest_allowed = datetime.now(timezone.utc) - timedelta(minutes=delay + (1 if delay else 0))
            latest_allowed = self._latest_available_end(symbol, timeframe, latest_allowed)
            end = min(end, latest_allowed)
            output = self._load_timeframe(symbol.upper(), timeframe, start, end, session)

        output = output.copy()
        actual_before = actual_after = None
        if use_context and "timestamp" in output.columns:
            import pandas as pd
            timestamps = pd.to_datetime(output["timestamp"], utc=True)
            actual_before = int((timestamps < pd.Timestamp(entry)).sum())
            actual_after = int((timestamps > pd.Timestamp(exit)).sum())
        if "timestamp" in output.columns:
            output["timestamp"] = output["timestamp"].astype(str)
        return {
            "symbol": symbol.upper(), "timeframe": timeframe, "session": session,
            "count": len(output), "bars": output.to_dict(orient="records"),
            "requested_before_bars": before_bars if use_context else None,
            "requested_after_bars": after_bars if use_context else None,
            "actual_before_bars": actual_before,
            "actual_after_bars": actual_after,
            "provider": getattr(self._provider(symbol), "key", None),
            "feed": getattr(self._provider(symbol), "historical_feed", None),
            "adjustment": getattr(self._provider(symbol), "adjustment", None),
            "instrument": self._instrument(symbol).as_dict(),
        }

    def _load_audit_context(
        self,
        symbol: str,
        timeframe: str,
        session: str,
        entry: datetime,
        exit: datetime,
        before_bars: int,
        after_bars: int,
    ):
        """Return real displayed-bar counts around a trade, not wall-clock padding.

        Session filtering means 50 five-minute bars before a 09:35 ET entry may live on
        the previous trading day. A simple ``50 * 5 minutes`` request therefore cannot
        satisfy the UI. We deliberately widen the calendar window until enough filtered
        bars exist, then slice the prepared series by bar count.
        """
        delay = self._delay(symbol)
        latest_allowed = datetime.now(timezone.utc) - timedelta(minutes=delay + (1 if delay else 0))
        latest_allowed = self._latest_available_end(symbol, timeframe, latest_allowed)
        exit_for_fetch = min(exit, latest_allowed)
        if entry > latest_allowed:
            raise ValueError("Trade is too recent for the configured historical-data delay")

        before_days = _audit_calendar_days(timeframe, session, before_bars)
        after_days = _audit_calendar_days(timeframe, session, after_bars)
        frame = None
        for _ in range(4):
            start = entry - timedelta(days=before_days)
            end = min(exit_for_fetch + timedelta(days=after_days), latest_allowed)
            if start >= end:
                end = min(latest_allowed, start + timedelta(days=1))
            frame = self._load_timeframe(symbol, timeframe, start, end, session)
            sliced, available_before, available_after = _slice_audit_frame(
                frame, entry, exit, before_bars, after_bars
            )
            if available_before >= before_bars and available_after >= after_bars:
                return sliced
            before_days = min(900, max(before_days + 1, before_days * 2))
            after_days = min(900, max(after_days + 1, after_days * 2))
        return sliced if frame is not None else frame

    def _load_replay_timeframe(self, symbol: str, timeframe: str, start: datetime, end: datetime, session: str):
        """Replay uses one canonical 1-minute intraday source across timeframes.

        This keeps timeframe switches causally consistent. Phase 6.2.4 reduces the
        default replay horizon/context instead of changing this invariant.
        """
        spec = self._instrument(symbol)
        source_timeframe = timeframe if timeframe in {"1d", "1w"} else "1m"
        frame = self._execution_bars(symbol, source_timeframe, start, end)
        return prepare_chart_bars(frame, timeframe, session, session_profile=spec.session_profile)

    def _load_timeframe(self, symbol: str, timeframe: str, start: datetime, end: datetime, session: str):
        spec = self._instrument(symbol)
        source_timeframe = "30m" if spec.session_profile == "us_equity" and timeframe in {"1h", "4h"} else timeframe
        frame = self._execution_bars(symbol, source_timeframe, start, end)
        prepared, _ = prepare_chart_bars(frame, timeframe, session, session_profile=spec.session_profile)
        return prepared

    def _execution_bars(self, symbol, timeframe, start, end):
        if self._instrument(symbol).asset_type == 'future' and hasattr(self.market_data,'get_execution_bars'):
            return self.market_data.get_execution_bars(symbol,timeframe,start,end)
        if self._instrument(symbol).security_type == 'continuous_future' and getattr(self._provider(symbol),'back_adjust',False):
            raise ValueError('Back-adjusted continuous history is chart-only; execution requires a raw provider path')
        return self.market_data.get_bars(symbol,timeframe,start,end)


def _audit_calendar_days(timeframe: str, session: str, bars: int) -> int:
    if bars <= 0:
        return 1
    if timeframe == "1d":
        sessions = bars
    else:
        minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}.get(timeframe, 5)
        session_minutes = 390 if session == "regular" else (960 if session == "extended" else 1440)
        bars_per_session = max(1, (session_minutes + minutes - 1) // minutes)
        sessions = (bars + bars_per_session - 1) // bars_per_session
    # Convert trading sessions to calendar days and leave room for weekends/holidays.
    return min(900, max(3, ((sessions * 7 + 4) // 5) + 3))


def _slice_audit_frame(frame, entry: datetime, exit: datetime, before_bars: int, after_bars: int):
    import pandas as pd

    if frame is None or frame.empty or "timestamp" not in frame.columns:
        return frame, 0, 0
    working = frame.copy().sort_values("timestamp").reset_index(drop=True)
    timestamps = pd.to_datetime(working["timestamp"], utc=True)
    entry_ts = pd.Timestamp(entry)
    exit_ts = pd.Timestamp(exit)
    before_idx = working.index[timestamps < entry_ts].tolist()
    after_idx = working.index[timestamps > exit_ts].tolist()
    start_idx = max(0, (before_idx[-1] + 1 if before_idx else 0) - before_bars)
    end_idx = min(len(working), (after_idx[0] if after_idx else len(working)) + after_bars)
    sliced = working.iloc[start_idx:end_idx].reset_index(drop=True)
    available_before = int((pd.to_datetime(sliced["timestamp"], utc=True) < entry_ts).sum())
    available_after = int((pd.to_datetime(sliced["timestamp"], utc=True) > exit_ts).sum())
    return sliced, available_before, available_after


def _symbols(value) -> list[str]:
    if isinstance(value, str):
        raw = value.replace("\n", ",").split(",")
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    result: list[str] = []
    for item in raw:
        symbol = str(item).strip().upper()
        if symbol and symbol not in result:
            result.append(symbol)
    return result


def _as_date(value, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not value:
        raise ValueError(f"{field} is required")
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def _entry_windows(value) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("entry_windows must be a list")
    output: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each entry window must contain start and end")
        start = _required_clock(item.get("start"))
        end = _required_clock(item.get("end"))
        output.append((start, end))
    return tuple(output)


def _weekdays(value) -> tuple[int, ...]:
    if value is None:
        return (0, 1, 2, 3, 4)
    if not isinstance(value, list):
        raise ValueError("trading_weekdays must be a list")
    output = tuple(sorted({int(day) for day in value}))
    if not output or any(day < 0 or day > 6 for day in output):
        raise ValueError("Select at least one valid trading weekday")
    return output


def _required_clock(value) -> str:
    if value is None:
        raise ValueError("Time is required")
    text = str(value)
    try:
        hour, minute = text.split(":", 1)
        parsed = time(int(hour), int(minute))
    except Exception as exc:
        raise ValueError(f"Invalid time '{text}'; expected HH:MM") from exc
    return parsed.strftime("%H:%M")


def _optional_clock(value) -> str | None:
    if value in (None, ""):
        return None
    return _required_clock(value)


def _optional_positive_int(value) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("Enabled integer limits must be positive")
    return parsed


def _optional_positive_float(value) -> float | None:
    if value in (None, "", 0, "0"):
        return None
    parsed = float(value)
    if parsed <= 0:
        raise ValueError("Enabled numeric limits must be positive")
    return parsed


def _snapshot_config(payload: dict, *, strategy_key: str, symbols: list[str]) -> dict:
    """Keep the user-facing run definition needed to reproduce/duplicate a run."""
    keys = (
        "start_date", "end_date", "primary_timeframe", "additional_timeframes", "session",
        "strategy_params", "starting_balance", "sizing_mode", "risk_value",
        "commission_per_order", "slippage_bps", "spread_bps", "max_leverage",
        "max_open_positions", "same_bar_policy", "entry_windows", "trading_weekdays",
        "allow_overnight", "force_close_time", "max_trades_per_day", "max_daily_loss_r",
        "max_consecutive_losses", "cooldown_minutes", "queue_job_id",
    )
    snapshot = {key: payload.get(key) for key in keys if key in payload}
    snapshot["strategy_key"] = strategy_key
    snapshot["symbols"] = list(symbols)
    return snapshot
