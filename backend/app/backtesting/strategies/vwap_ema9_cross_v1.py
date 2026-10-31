"""Ledger research strategy: session VWAP vs EMA9; crossed and approaching variants.

V1 decision logic uses completed 5m or 15m bars. The 1m chart is only the
execution clock: all signals execute at Ledger's NEXT 1m open.

There is no clairvoyant 'right before' cross. Early entries are predictive
rules that can fail, and expire if no actual cross follows.

For now hard-stop choices are defined in units of ATR / INITIAL RISK, not
unclarified percentage loss of leveraged margin or account balance.
Never use this file with a live order gateway.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.backtesting.models import EntrySignal, ExitSignal
from app.backtesting.strategies.base import Strategy, StrategySpec, ParameterSpec
from app.backtesting.strategies.registry import strategy_registry

NY = ZoneInfo('America/New_York')
SOURCE = 'backend/app/backtesting/strategies/vwap_ema9_cross_v1.py'


def _utc(value):
    t = pd.Timestamp(value)
    return t.tz_localize('UTC') if t.tzinfo is None else t.tz_convert('UTC')


def _session_key(ts: pd.Timestamp, kind: str) -> str:
    local = ts.tz_convert(NY)
    if kind == 'gold':
        # Session begins at 17:00 ET (DST automatically handled by zoneinfo).
        d = local.date() if local.time() >= time(17, 0) else (local - pd.Timedelta(days=1)).date()
    else:
        # Equity RTH VWAP begins at 09:30 ET (premarket bars are excluded).
        if local.time() < time(9, 30) or local.time() >= time(16, 0):
            return ''
        d = local.date()
    return str(d)


def _indicator_table(frame: pd.DataFrame, *, session: str) -> pd.DataFrame:
    """Causal EMA9, session-reset HLC3 VWAP and ATR14 on supplied completed bars.

    All history required for the current session must be in `frame`.
    """
    needed = {'timestamp', 'high', 'low', 'close', 'volume'}
    if not needed.issubset(frame.columns):
        return pd.DataFrame()
    f = frame.copy().reset_index(drop=True)
    for key in ('high', 'low', 'close', 'volume'):
        f[key] = pd.to_numeric(f[key], errors='coerce')
    f['time_utc'] = f['timestamp'].map(_utc)
    f['session'] = f['time_utc'].map(lambda t: _session_key(t, session))
    f['ema9'] = f['close'].ewm(span=9, adjust=False, min_periods=9).mean()
    f['vwap'] = np.nan
    valid = f['session'].ne('') & f['volume'].gt(0)
    typical = (f['high'] + f['low'] + f['close']) / 3
    for key, indices in f.loc[valid].groupby('session', sort=False).groups.items():
        ids = list(indices)
        weighted = (typical.loc[ids] * f.loc[ids, 'volume']).cumsum()
        weights = f.loc[ids, 'volume'].cumsum()
        f.loc[ids, 'vwap'] = (weighted / weights).values
    previous_close = f['close'].shift()
    tr = pd.concat([
        f['high'] - f['low'],
        (f['high'] - previous_close).abs(),
        (f['low'] - previous_close).abs(),
    ], axis=1).max(axis=1)
    f['atr14'] = tr.rolling(14, min_periods=14).mean()
    f['diff'] = f['ema9'] - f['vwap']
    return f


def _cross(prev: pd.Series, cur: pd.Series) -> str | None:
    if prev['session'] != cur['session'] or not cur['session']:
        return None
    p, d = float(prev['diff']), float(cur['diff'])
    if not np.isfinite(p) or not np.isfinite(d):
        return None
    if p <= 0 < d:
        return 'long'
    if p >= 0 > d:
        return 'short'
    return None


def _approach(table: pd.DataFrame, max_gap_atr: float) -> str | None:
    """Predictive pre-cross: gap contracts 3 bars, below ATR threshold;
    the candle closes on the intended side of EMA9. Does NOT use future bars.
    """
    if len(table) < 4:
        return None
    w = table.iloc[-4:]
    if w['session'].nunique() != 1 or w['session'].iloc[-1] == '':
        return None
    d = w['diff'].astype(float).values
    atr = float(w['atr14'].iloc[-1])
    if not np.all(np.isfinite(d)) or not np.isfinite(atr) or atr <= 0:
        return None
    # Latest gap must still be on same side of VWAP, but contracting.
    if not (abs(d[-1]) / atr <= max_gap_atr
            and abs(d[-3]) > abs(d[-2]) > abs(d[-1])):
        return None
    last = w.iloc[-1]
    if d[-1] < 0 and float(last['close']) > float(last['ema9']):
        return 'long'
    if d[-1] > 0 and float(last['close']) < float(last['ema9']):
        return 'short'
    return None


def _latest_cross_after(t: pd.DataFrame, start: pd.Timestamp, direction: str):
    if t.empty:
        return None
    # Scan only bars strictly AFTER the pre-cross signal candle.
    for i in range(1, len(t)):
        if t.iloc[i]['time_utc'] <= start:
            continue
        if _cross(t.iloc[i - 1], t.iloc[i]) == direction:
            return t.iloc[i]['time_utc']
    return None


class _VWAPEMA9Base(Strategy):
    TF = '5m'
    MODE = 'confirmed'
    _last_bar = None

    def __init__(self, **params):
        super().__init__(**params)
        self._last_bar = None
        self._last_signal_session = None

    def reset(self):
        self._last_bar = None
        self._last_signal_session = None

    def on_bar(self, ctx):
        if ctx.primary_timeframe != '1m':
            return None
        bars = ctx.bars(self.TF, count=(400 if self.TF == '5m' else 140))
        if len(bars) < 20:
            return None
        t = _indicator_table(bars, session=str(self.params.get('session', 'gold')))
        if len(t) < 20:
            return None
        latest = t.iloc[-1]
        bar_start = latest['time_utc']
        if self._last_bar == bar_start:
            return None
        self._last_bar = bar_start
        if not (np.isfinite(latest['ema9']) and np.isfinite(latest['vwap'])
                and np.isfinite(latest['atr14']) and latest['session']):
            return None

        if ctx.position is not None:
            return self._manage(ctx, t)
        previous = t.iloc[-2]
        direction = _cross(previous, latest) if self.MODE == 'confirmed' else _approach(
            t, float(self.params.get('early_gap_atr', 0.15)))
        if not direction:
            return None
        allowed = str(self.params.get('direction', 'both'))
        if allowed not in ('both', direction):
            return None
        # Pre-cross enters only once per anchored VWAP session to avoid repeated
        # speculative entries as the difference contracts further.
        if self.MODE == 'early' and self._last_signal_session == latest['session']:
            return None
        self._last_signal_session = latest['session']

        close = float(latest['close'])
        atr = float(latest['atr14'])
        stop_atr = float(self.params.get('stop_atr', 1.5))
        # Provisional interpretation of "-25/30%": percentage of BASELINE ATR STOP DISTANCE, NOT percentage of leveraged margin/equity. This is only a distance sensitivity; position size is re-computed by Ledger.
        risk_fraction = float(self.params.get('hard_stop_atr_fraction', 1.0))
        dist = atr * stop_atr * risk_fraction
        stop = close - dist if direction == 'long' else close + dist
        if not (np.isfinite(stop) and stop > 0 and dist > 0):
            return None
        metadata = {
            'strategy_version': self.spec.key,
            'cross_entry_mode': self.MODE,
            'signal_timeframe': self.TF,
            'signal_bar_start_utc': bar_start.isoformat(),
            'vwap_session_key': str(latest['session']),
            'vwap_session_type': str(self.params.get('session', 'gold')),
            'ema9_at_signal': float(latest['ema9']),
            'session_vwap_at_signal': float(latest['vwap']),
            'ema_vwap_gap': float(latest['diff']),
            'atr14_at_signal': atr,
            'initial_stop': stop,
            'hard_stop_atr_fraction': risk_fraction,
            'initial_stop_semantics': 'ATR14 x stop_atr x hard_stop_atr_fraction; sizing responds to distance',
            'ema_exit_rule': 'completed_signal_tf_bar_close_crosses_opposite_ema9; next_1m_open',
            'early_entry_expiry_bars': int(self.params.get('early_expiry_bars', 3)),
            'chart_indicators': ['ema9', 'session_vwap'],
        }
        return EntrySignal(direction=direction, stop_loss=stop,
                           reason=f'vwap_ema9_{self.TF}_{self.MODE}_{direction}',
                           metadata=metadata)

    def _manage(self, ctx, t: pd.DataFrame):
        pos = ctx.position
        meta = pos.metadata or {}
        if meta.get('strategy_version') != self.spec.key:
            return None
        cur = t.iloc[-1]
        direction = pos.direction
        if self.MODE == 'early':
            start = _utc(meta['signal_bar_start_utc'])
            crossed_at = _latest_cross_after(t, start, direction)
            after = t[t['time_utc'] > start]
            n_bars = len(after)
            if crossed_at is None:
                if n_bars >= int(self.params.get('early_expiry_bars', 3)):
                    return ExitSignal(reason='early_approach_no_cross_by_expiry')
                return None
        # For both modes, soft exit is checked on the completed signal TF candle.
        close, ema = float(cur['close']), float(cur['ema9'])
        if direction == 'long' and close < ema:
            return ExitSignal(reason='long_candle_closed_below_ema9')
        if direction == 'short' and close > ema:
            return ExitSignal(reason='short_candle_closed_above_ema9')
        return None


def _make_spec(tf: str, mode: str):
    return StrategySpec(
        key=f'vwap_ema9_{tf}_{mode}_v1',
        name=f'VWAP/EMA9 V1 · {tf} · {mode}',
        category='Research / VWAP crossover',
        description=(f'{tf} session VWAP vs EMA9 {mode} entry, 1m next-open fill; '
                     'completed signal-timeframe EMA9 close exit; ATR hard stop.'),
        defaults={'direction':'both', 'session':'gold', 'stop_atr':1.5,
                  'hard_stop_atr_fraction':1.0, 'early_gap_atr':0.15,
                  'early_expiry_bars':3},
        timeframes=('1m', tf),
        parameters=(
            ParameterSpec('direction','Direction','choice','both',choices=('both','long','short')),
            ParameterSpec('session','VWAP session','choice','gold',choices=('gold','equity_rth')),
            ParameterSpec('stop_atr','Emergency ATR stop multiplier','float',1.5,0.25,5.0,0.25),
            ParameterSpec('hard_stop_atr_fraction','Fraction of baseline ATR stop distance','float',1.0,0.25,1.0,0.05,
                          help='Optional stop-distance sensitivity ONLY; 0.25 is not a -25% trade/account loss threshold.'),
            ParameterSpec('early_gap_atr','Pre-cross max gap / ATR','float',0.15,0.02,0.5,0.01),
            ParameterSpec('early_expiry_bars','Pre-cross expiry TF bars','int',3,1,12,1),
        ),
        risk_management={
            'Entry': 'Confirmed bar close or causal pre-cross narrowing; next primary 1m open',
            'Exit': 'Completed signal-timeframe candle closes through EMA9; next 1m open',
            'Hard stop': 'ATR-based protective stop; percentage below refers to baseline ATR DISTANCE only',
            'Target': 'No fixed target; EMA-close exit or initial hard stop',
            'Data': 'VWAP requires positive OHLCV volume; no fabricated proxy volume',
        },
        source_file=SOURCE,
    )


@strategy_registry.register
class VWAPEMA9Confirmed5m(_VWAPEMA9Base):
    TF = '5m'
    MODE = 'confirmed'
    spec = _make_spec('5m', 'confirmed')


@strategy_registry.register
class VWAPEMA9Early5m(_VWAPEMA9Base):
    TF = '5m'
    MODE = 'early'
    spec = _make_spec('5m', 'early')


@strategy_registry.register
class VWAPEMA9Confirmed15m(_VWAPEMA9Base):
    TF = '15m'
    MODE = 'confirmed'
    spec = _make_spec('15m', 'confirmed')


@strategy_registry.register
class VWAPEMA9Early15m(_VWAPEMA9Base):
    TF = '15m'
    MODE = 'early'
    spec = _make_spec('15m', 'early')
