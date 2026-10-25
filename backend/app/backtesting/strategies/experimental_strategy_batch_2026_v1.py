"""Ledger independent, causal research hypotheses (October 2026).

No broker IO, model calls, order sending or access to future candles. All signals
are informational backtest signals; Ledger owns fills, spread/slippage and sizing.
The exact rules below are transparent interpretations of previously discussed
ideas, NOT proven profitable edges or exact source-trader implementations.

Best used with a 1m primary timeframe unless a strategy below says otherwise.
The module is intentionally self-contained for source archiving/provenance.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, time
from math import isfinite
from zoneinfo import ZoneInfo

import pandas as pd

from app.backtesting.models import EntrySignal, ManagePositionSignal
from app.backtesting.strategies.base import Strategy, StrategySpec, ParameterSpec
from app.backtesting.strategies.registry import strategy_registry

NY = ZoneInfo('America/New_York')
SOURCE = 'backend/app/backtesting/strategies/experimental_strategy_batch_2026_v1.py'


def price(row, key):
    return float(row[key])


def valid_bars(frame, length=1):
    if frame is None or len(frame) < length:
        return False
    subset = frame.tail(length)
    try:
        if not all(isfinite(float(x)) for x in subset[['open', 'high', 'low', 'close']].to_numpy().flat):
            return False
        return bool(((subset.high >= subset[['open', 'close', 'low']].max(axis=1)) &
                    (subset.low <= subset[['open', 'close', 'high']].min(axis=1))).all())
    except (KeyError, ValueError, TypeError):
        return False


def contiguous(frame, minutes):
    if frame is None or frame.empty:
        return False
    dates = pd.to_datetime(frame['timestamp'], utc=True)
    return bool(dates.is_monotonic_increasing and
                (dates.diff().iloc[1:] == pd.Timedelta(minutes=minutes)).all())


def atr(frame, length=14):
    if not valid_bars(frame, length + 1):
        return None
    f = frame.tail(length + 1)
    if f.empty:
        return None
    h, l, c = f.high.astype(float), f.low.astype(float), f.close.astype(float)
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    result = float(tr.iloc[1:].mean())
    return result if isfinite(result) and result > 0 else None


def ts(row):
    return pd.Timestamp(row['timestamp']).tz_localize('UTC') if pd.Timestamp(row['timestamp']).tzinfo is None else pd.Timestamp(row['timestamp']).tz_convert('UTC')


def nydate(ctx):
    return pd.Timestamp(ctx.decision_time).tz_convert(NY).date() if pd.Timestamp(ctx.decision_time).tzinfo else pd.Timestamp(ctx.decision_time).tz_localize('UTC').tz_convert(NY).date()


def local_stamp(row):
    return ts(row).tz_convert(NY)


def dir_allowed(params, direction):
    return params.get('direction','both') in ('both', direction)


def signal(direction, stop, reference, *, rr=2.0, tp=None, reason='', meta=None, limit=None, wait=None):
    """Use target_r for market orders to price from actual fill, not signal close."""
    if not all(isfinite(v) for v in (stop, reference)):
        return None
    if (direction == 'long' and stop >= reference) or (direction == 'short' and stop <= reference):
        return None
    if tp is not None and ((direction == 'long' and tp <= reference) or
                           (direction == 'short' and tp >= reference)):
        return None
    if limit is not None and ((direction == 'long' and stop >= limit) or
                              (direction == 'short' and stop <= limit)):
        return None
    return EntrySignal(direction, stop_loss=stop, take_profit=tp,
                       target_r=float(rr) if tp is None else None, reason=reason,
                       metadata=meta or {}, order_type='limit' if limit is not None else 'market',
                       entry_price=limit, max_wait_bars=wait)


# === A1-A4: 15m support/resistance levels with 1m confirmations ============
A_DEFAULTS = {'direction':'short', 'lookback_15m':24, 'atr_length':14,
              'level_tolerance_atr':0.20, 'stop_buffer_atr':0.12, 'target_r':2.0}
A_PARAMS = (
    ParameterSpec('direction','Direction','choice','short',choices=('both','long','short')),
    ParameterSpec('lookback_15m','15m level lookback','int',24,8,96,1),
    ParameterSpec('level_tolerance_atr','Touch tolerance / ATR','float',0.20,0.02,1.0,0.02),
)
A_RESEARCH = (
    ParameterSpec('stop_buffer_atr','Stop buffer / 15m ATR','float',0.12,0.01,1.0,0.01),
    ParameterSpec('target_r','Fixed target R','float',2.0,0.5,6.0,0.25),
)

class _Resistance(Strategy):
    VARIANT = 1
    spec = StrategySpec(key='_resistance_base', name='base', category='Experimental',
        timeframes=('1m','15m','1h'), defaults=A_DEFAULTS, parameters=A_PARAMS,
        research_parameters=A_RESEARCH, source_file=SOURCE)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.reset()
    def reset(self):
        self.traded = set()
        self.last15 = None
        self.flip = None
    def on_bar(self, ctx):
        if ctx.primary_timeframe != '1m' or ctx.position is not None:
            return None
        b = ctx.bars('1m', count=5)
        h = ctx.bars('15m', count=max(int(self.params['lookback_15m']) + 3, 20))
        if not valid_bars(b,3) or not valid_bars(h,18):
            return None
        current, prev = b.iloc[-1], b.iloc[-2]
        day = nydate(ctx)
        if day in self.traded:
            return None
        # Levels are calculated from earlier COMPLETED 15m candles only.
        prior = h.iloc[:-1].tail(int(self.params['lookback_15m']))
        v = atr(h.iloc[:-1], int(self.params['atr_length']))
        if not v or len(prior) < 8:
            return None
        high, low = float(prior.high.max()), float(prior.low.min())
        tol = v * float(self.params['level_tolerance_atr'])
        buf = v * float(self.params['stop_buffer_atr'])
        bar = h.iloc[-1]
        barid = ts(bar)
        if self.VARIANT == 3 and self.last15 != barid:
            self.last15 = barid
            # A3: 15m support lost on close; wait for a LOWER-high retest from below.
            if price(bar,'close') < low - tol:
                self.flip = (low, ctx.decision_time + timedelta(minutes=90), v, ctx.decision_time)
            elif self.flip is not None and price(bar,'close') > self.flip[0] + tol:
                self.flip = None
        cand = None
        mode = 'rejection'
        for direction in ('short','long'):
            if not dir_allowed(self.params,direction):
                continue
            if self.VARIANT == 3:
                if (direction != 'short' or not self.flip or ctx.decision_time > self.flip[1] or
                    ts(current) < pd.Timestamp(self.flip[3])):
                    continue
                level = self.flip[0]
                if price(current,'high') >= level - tol and price(current,'close') < level - tol*0.15 and price(current,'close') < price(current,'open'):
                    cand = (direction, max(price(current,'high'),level)+buf, level, 'support_flip')
            elif direction == 'short':
                touch = price(current,'high') >= high - tol and price(current,'close') < high and price(current,'close') < price(current,'open')
                if self.VARIANT == 2:
                    touch = (price(current,'high') > high + tol*0.5 and price(current,'close') < high - tol*0.1)
                    mode = 'sweep_reclaim'
                if self.VARIANT == 4:
                    hours = ctx.bars('1h',count=55)
                    if not valid_bars(hours,30): continue
                    ema = hours.close.astype(float).ewm(span=30,adjust=False).mean()
                    touch = touch and float(ema.iloc[-1]) < float(ema.iloc[-4]) and price(hours.iloc[-1],'close') < float(ema.iloc[-1])
                    mode = 'trend_filtered_rejection'
                if touch: cand = ('short', max(price(current,'high'),high)+buf, high,mode)
            else:
                touch = price(current,'low') <= low + tol and price(current,'close') > low and price(current,'close') > price(current,'open')
                if self.VARIANT == 2:
                    touch = price(current,'low') < low - tol*0.5 and price(current,'close') > low + tol*0.1
                    mode = 'sweep_reclaim'
                if self.VARIANT == 4:
                    hours=ctx.bars('1h',count=55)
                    if not valid_bars(hours,30):continue
                    ema=hours.close.astype(float).ewm(span=30,adjust=False).mean()
                    touch = touch and float(ema.iloc[-1]) > float(ema.iloc[-4]) and price(hours.iloc[-1],'close') > float(ema.iloc[-1])
                    mode='trend_filtered_rejection'
                if touch:cand=('long',min(price(current,'low'),low)-buf,low,mode)
        if cand is None:return None
        direction,stop,level,reason=cand
        entry=price(current,'close')
        out=signal(direction,stop,entry,rr=float(self.params['target_r']),reason='gold_sr_'+reason,
                   meta=dict(family='gold_sr',variant=f'A{self.VARIANT}',level=level,
                             atr15=v,confirmation_time=ctx.decision_time.isoformat()))
        if out:self.traded.add(day)
        return out

@strategy_registry.register
class GoldResistanceA1(_Resistance):
    VARIANT=1
    spec=replace(_Resistance.spec,key='gold_sr_a1_rejection_v1',name='Gold SR A1 · 1m rejection',
                 description='15m range extreme rejected by completed 1m candle; stop beyond extreme; 2R.')

@strategy_registry.register
class GoldResistanceA2(_Resistance):
    VARIANT=2
    spec=replace(_Resistance.spec,key='gold_sr_a2_sweep_v1',name='Gold SR A2 · sweep/reclaim',
                 description='1m sweep beyond prior 15m resistance/support then reclaim; 2R.')

@strategy_registry.register
class GoldResistanceA3(_Resistance):
    VARIANT=3
    spec=replace(_Resistance.spec,key='gold_sr_a3_support_flip_v1',name='Gold SR A3 · support flip',
                 description='Completed 15m close breaks support, then 1m retests former support from below.')

@strategy_registry.register
class GoldResistanceA4(_Resistance):
    VARIANT=4
    spec=replace(_Resistance.spec,key='gold_sr_a4_trend_rejection_v1',name='Gold SR A4 · trend filter',
                 description='A1 resistance rejection gated by completed 1h EMA30 trend and slope.')


# === R01-R05: 15m bullish impulse, compressed high range, 1m short ========== 
R_DEFAULTS = {'impulse_bars':3,'range_bars':6,'impulse_atr':2.0,
              'max_range_atr':2.0,'top_tolerance_pct':0.20,'stop_buffer_atr':0.10,
              'max_setup_minutes':45}
R_PARAMS=(ParameterSpec('impulse_bars','Impulse bars','int',3,2,6,1),
          ParameterSpec('range_bars','Range bars','int',6,4,12,1),
          ParameterSpec('impulse_atr','Impulse minimum ATR multiple','float',2.0,0.5,5.0,0.25),
          ParameterSpec('max_range_atr','Max range / 15m ATR','float',2.0,0.5,5.0,0.25))

class _ImpulseRange(Strategy):
    VARIANT=1
    spec=StrategySpec(key='_range_base',name='base',category='Experimental',
        defaults=R_DEFAULTS,parameters=R_PARAMS,timeframes=('1m','15m'),source_file=SOURCE)
    def __init__(self,**kwargs):
        super().__init__(**kwargs);self.reset()
    def reset(self):
        self.setup=None;self.last15=None;self.used=set()
    def _identify(self,ctx):
        n=int(self.params['range_bars']);imp=int(self.params['impulse_bars'])
        h=ctx.bars('15m',count=n+imp+23)
        if not valid_bars(h,n+imp+16):return None
        tail=h.tail(n+imp+1)
        if not contiguous(tail,15):return None
        av=atr(h.iloc[:-(n+imp)],14)  # prior to impulse: no impulse/formation leakage into ATR
        if av is None:return None
        rng=tail.tail(n);impulse=tail.iloc[-(n+imp):-n]
        base = h.iloc[-(n+imp+1)]
        if (price(impulse.iloc[-1],'close') - price(base,'close')) < float(self.params['impulse_atr'])*av:
            return None
        top=float(rng.high.max());bottom=float(rng.low.min());width=top-bottom
        if not 0<width<=av*float(self.params['max_range_atr']):return None
        # Require repeated tests of the range top without a sustained breakout.
        near=top-width*float(self.params['top_tolerance_pct'])
        if sum(float(x)>=near for x in rng.high)<2:return None
        if price(rng.iloc[-1],'close') >= top:return None
        return dict(top=top,bottom=bottom,atr=av,created=ctx.decision_time,
                    expiry=ctx.decision_time+timedelta(minutes=int(self.params['max_setup_minutes'])))
    def on_bar(self,ctx):
        if ctx.primary_timeframe!='1m':return None
        if ctx.position is not None:
            return self._manage(ctx)
        day=nydate(ctx)
        if day in self.used:return None
        h=ctx.bars('15m',count=1)
        if h.empty:return None
        stamp=ts(h.iloc[-1])
        if stamp!=self.last15:
            self.last15=stamp
            self.setup=self._identify(ctx)
        s=self.setup
        if s is None or ctx.decision_time>s['expiry']:return None
        b=ctx.bars('1m',count=4)
        if not valid_bars(b,3):return None
        c,p=b.iloc[-1],b.iloc[-2]
        # The 15m range becomes known only at its completion, not during its last 1m.
        if self.VARIANT != 1 and ts(c) < pd.Timestamp(s['created']):return None
        top,bot=s['top'],s['bottom']
        width=top-bot
        stop=max(top,price(c,'high'))+s['atr']*float(self.params['stop_buffer_atr'])
        ref=price(c,'close')
        near=top-width*float(self.params['top_tolerance_pct'])
        if self.VARIANT==1:
            # Limit on range top; only attempt after range is fully confirmed.
            entry=near
            out=signal('short',top+s['atr']*float(self.params['stop_buffer_atr']),entry,
                       tp=bot,limit=entry,wait=45,reason='impulse_range_limit',
                       meta=dict(family='post_impulse_range',variant='R01',top=top,bottom=bot))
        else:
            rejection=(price(c,'high')>=near and price(c,'close')<price(c,'open')
                       and price(c,'close')<top and price(c,'close')<price(p,'close'))
            sweep=price(c,'high')>top and price(c,'close')<top and price(c,'close')<price(c,'open')
            if (self.VARIANT==3 and not sweep) or (self.VARIANT!=3 and not rejection):return None
            if not bot<ref<stop:return None
            out=signal('short',stop,ref,tp=bot,
                       reason='impulse_range_sweep' if self.VARIANT==3 else 'impulse_range_rejection',
                       meta=dict(family='post_impulse_range',variant=f'R0{self.VARIANT}',top=top,bottom=bot,
                                 entry_reference=ref))
        if out:self.used.add(day)
        return out
    def _manage(self,ctx):
        if self.VARIANT not in (4,5):return None
        pos=ctx.position
        if not pos or pos.direction!='short' or (pos.metadata or {}).get('family')!='post_impulse_range':return None
        risk=float(pos.initial_risk_per_share)
        if risk<=0:return None
        close=price(ctx.current_bar,'close')
        if self.VARIANT==4 and not (pos.metadata or {}).get('range_half_partial'):
            top=float(pos.metadata.get('top',0));bottom=float(pos.metadata.get('bottom',0))
            middle=(top+bottom)/2
            if bottom<close<=middle:
                return ManagePositionSignal(reduce_fraction=0.5,reason='range_midpoint_partial',
                                            metadata={'range_half_partial':True})
        if self.VARIANT==5 and float(pos.entry_price)-close>=2*risk:
            # Trail to prior THREE completed 1m highs; stop must never widen.
            b=ctx.bars('1m',count=4)
            if len(b)<4:return None
            candidate=max(float(x) for x in b.high.iloc[-3:])
            if candidate<float(pos.stop_loss) and candidate>close:
                return ManagePositionSignal(new_stop_loss=candidate,reason='range_2r_trailing')
        return None

@strategy_registry.register
class RangeR01(_ImpulseRange):
    VARIANT=1
    spec=replace(_ImpulseRange.spec,key='gold_range_r01_limit_v1',name='Gold Range R01 · upper-range limit',
                 description='15m impulse + compressed upper range; sell limit at top 20% and target range low.')
@strategy_registry.register
class RangeR02(_ImpulseRange):
    VARIANT=2
    spec=replace(_ImpulseRange.spec,key='gold_range_r02_rejection_v1',name='Gold Range R02 · 1m rejection',
                 description='15m impulse + compressed range; sell on completed 1m high rejection; target low.')
@strategy_registry.register
class RangeR03(_ImpulseRange):
    VARIANT=3
    spec=replace(_ImpulseRange.spec,key='gold_range_r03_failed_break_v1',name='Gold Range R03 · failed breakout',
                 description='15m impulse + upper range; sell after a 1m wick above range high and close back inside.')
@strategy_registry.register
class RangeR04(_ImpulseRange):
    VARIANT=4
    spec=replace(_ImpulseRange.spec,key='gold_range_r04_midpoint_partial_v1',name='Gold Range R04 · midpoint partial',
                 description='R02 plus 50% position reduction after completed 1m closes below range midpoint.')
@strategy_registry.register
class RangeR05(_ImpulseRange):
    VARIANT=5
    spec=replace(_ImpulseRange.spec,key='gold_range_r05_trailing_v1',name='Gold Range R05 · 2R trailing',
                 description='R02 with stop trailed to 3-bar highs once completed close is at least +2R.')


# === D / 1h / 5m breakout, retest and CHoCH ================================
@strategy_registry.register
class DailyHourlyFiveMinRetest(Strategy):
    USE_DAILY_BIAS = True
    spec=StrategySpec(key='mtf_d1_h1_m5_retest_v1',name='Daily / 1H / 5m breakout-retest',
        description='20D EMA direction and slope; hourly level; 5m breakout, subsequent level retest and CHoCH.',
        category='Experimental',timeframes=('5m','1h','1d'),
        defaults={'daily_ema':20,'hourly_lookback':12,'max_wait_5m':24,'stop_buffer_pct':0.0005,'target_r':2.0},
        parameters=(ParameterSpec('hourly_lookback','Hourly range lookback','int',12,6,48,1),),
        research_parameters=(ParameterSpec('target_r','Target R','float',2.0,0.5,5.0,0.25),),source_file=SOURCE)
    def __init__(self,**kwargs):super().__init__(**kwargs);self.reset()
    def reset(self):self.state=None;self.used=set();self.last5=None
    def on_bar(self,ctx):
        if ctx.primary_timeframe!='5m' or ctx.position is not None:return None
        b=ctx.bars('5m',count=9)
        if not valid_bars(b,7):return None
        stamp=ts(b.iloc[-1]);
        if stamp==self.last5:return None
        self.last5=stamp
        d=ctx.bars('1d',count=30);h=ctx.bars('1h',count=60)
        look=int(self.params['hourly_lookback'])
        if not valid_bars(d,25) or not valid_bars(h,look+4):return None
        e=d.close.astype(float).ewm(span=int(self.params['daily_ema']),adjust=False).mean()
        long_bias=price(d.iloc[-1],'close')>float(e.iloc[-1])>float(e.iloc[-4])
        short_bias=price(d.iloc[-1],'close')<float(e.iloc[-1])<float(e.iloc[-4])
        if not self.USE_DAILY_BIAS: long_bias=short_bias=True
        hourly=h.iloc[-(look+1):-1]
        high,low=float(hourly.high.max()),float(hourly.low.min())
        c,p=b.iloc[-1],b.iloc[-2]; close=price(c,'close')
        day=nydate(ctx)
        if day in self.used:return None
        if self.state:
            s=self.state
            if (ctx.decision_time-s['time']).total_seconds()>int(self.params['max_wait_5m'])*300:
                self.state=None
            elif s['direction']=='long' and price(c,'low')<=s['level'] and close>s['level'] and close>max(float(x) for x in b.high.iloc[-4:-1]):
                stop=min(float(x) for x in b.low.iloc[-4:])*(1-float(self.params['stop_buffer_pct']))
                out=signal('long',stop,close,rr=float(self.params['target_r']),reason='mtf_retest_choch',meta={'daily_bias':'up','hourly_breakout_level':s['level']})
                if out:self.used.add(day);self.state=None
                return out
            elif s['direction']=='short' and price(c,'high')>=s['level'] and close<s['level'] and close<min(float(x) for x in b.low.iloc[-4:-1]):
                stop=max(float(x) for x in b.high.iloc[-4:])*(1+float(self.params['stop_buffer_pct']))
                out=signal('short',stop,close,rr=float(self.params['target_r']),reason='mtf_retest_choch',meta={'daily_bias':'down','hourly_breakout_level':s['level']})
                if out:self.used.add(day);self.state=None
                return out
            return None
        # Freeze level only after FIRST completed 5m breakout; future levels do not replace it.
        if long_bias and close>high and price(p,'close')<=high:
            self.state=dict(direction='long',level=high,time=ctx.decision_time)
        elif short_bias and close<low and price(p,'close')>=low:
            self.state=dict(direction='short',level=low,time=ctx.decision_time)
        return None


# === Powell 10am NY liquidity reversal ====================================
@strategy_registry.register
class PowellTenAMReversal(Strategy):
    spec=StrategySpec(key='powell_10am_sweep_reversal_v1',name='Powell 10am · sweep reversal research',
        description='09:30–09:59 ET range; 10:00–10:30 ET liquidity sweep/reclaim + prior 1m microstructure confirmation.',
        category='Experimental',timeframes=('1m',),
        defaults={'pre_minutes':30,'signal_end_minute':31,'sweep_buffer_bps':1.0,'target_r':2.0,'direction':'both'},
        parameters=(ParameterSpec('direction','Direction','choice','both',choices=('both','long','short')),),
        research_parameters=(ParameterSpec('sweep_buffer_bps','Sweep buffer bps','float',1,0,15,0.5),
                             ParameterSpec('target_r','Target R','float',2,0.5,5,0.25)),source_file=SOURCE)
    def __init__(self,**kwargs):super().__init__(**kwargs);self.reset()
    def reset(self):self.date=None;self.high=None;self.low=None;self.sweep=None;self.done=False
    def on_bar(self,ctx):
        if ctx.primary_timeframe!='1m' or ctx.position is not None:return None
        bars=ctx.bars('1m',count=150)
        if not valid_bars(bars,4):return None
        c=bars.iloc[-1];loc=local_stamp(c);d=loc.date();minute=loc.hour*60+loc.minute
        if self.date!=d:self.date=d;self.high=None;self.low=None;self.sweep=None;self.done=False
        if self.done or not 600<=minute<=630:return None
        prior=bars[(pd.to_datetime(bars.timestamp,utc=True).dt.tz_convert(NY).dt.date==d)]
        mins=pd.to_datetime(prior.timestamp,utc=True).dt.tz_convert(NY).dt.hour*60+pd.to_datetime(prior.timestamp,utc=True).dt.tz_convert(NY).dt.minute
        pre=prior[(mins>=570)&(mins<600)]
        if len(pre)!=30 or not contiguous(pre,1):return None
        if self.high is None:self.high=float(pre.high.max());self.low=float(pre.low.min())
        high,low=self.high,self.low;close=price(c,'close')
        buffer=close*float(self.params['sweep_buffer_bps'])/10000
        if self.sweep is None:
            if price(c,'low')<low-buffer and price(c,'high')>high+buffer:return None
            if price(c,'low')<low-buffer:self.sweep=('long',price(c,'low'),ctx.decision_time)
            elif price(c,'high')>high+buffer:self.sweep=('short',price(c,'high'),ctx.decision_time)
            return None
        direction,extreme,detected=self.sweep
        if (ctx.decision_time-detected).total_seconds()>15*60:return None
        if direction=='long':
            extreme=min(extreme,price(c,'low'));self.sweep=(direction,extreme,detected)
            confirmed=close>low and close>max(float(x) for x in bars.high.iloc[-4:-1])
            stop=extreme-buffer
        else:
            extreme=max(extreme,price(c,'high'));self.sweep=(direction,extreme,detected)
            confirmed=close<high and close<min(float(x) for x in bars.low.iloc[-4:-1])
            stop=extreme+buffer
        if not confirmed or not dir_allowed(self.params,direction):return None
        out=signal(direction,stop,close,rr=float(self.params['target_r']),reason='powell_10am_sweep',
                   meta=dict(range_high=high,range_low=low,sweep_extreme=extreme,session_day=d.isoformat()))
        if out:self.done=True
        return out


# === New York failed 15m opening-range breakout ===========================
@strategy_registry.register
class FailedOpeningRangeBreakout(Strategy):
    spec=StrategySpec(key='ny_failed_orb_15m_v1',name='NY failed opening-range breakout',
        description='09:30–09:44 ET first 15m range; 1m wick sweeps outside, closes back inside; fade with structural stop.',
        category='Experimental',timeframes=('1m',),defaults={'target_r':1.5,'direction':'both'},
        parameters=(ParameterSpec('direction','Direction','choice','both',choices=('both','long','short')),),
        research_parameters=(ParameterSpec('target_r','Target R','float',1.5,0.5,5,0.25),),source_file=SOURCE)
    def __init__(self,**kwargs):super().__init__(**kwargs);self.reset()
    def reset(self):self.used=set()
    def on_bar(self,ctx):
        if ctx.primary_timeframe!='1m' or ctx.position is not None:return None
        b=ctx.bars('1m',count=230)
        if not valid_bars(b,17):return None
        c=b.iloc[-1];day=nydate(ctx);local=local_stamp(c);minute=local.hour*60+local.minute
        if day in self.used or not 585<=minute<660:return None
        local_all=pd.to_datetime(b.timestamp,utc=True).dt.tz_convert(NY)
        opening=b[(local_all.dt.date==day)&(local_all.dt.hour*60+local_all.dt.minute>=570)&(local_all.dt.hour*60+local_all.dt.minute<585)]
        if len(opening)!=15 or not contiguous(opening,1):return None
        high,low=float(opening.high.max()),float(opening.low.min());close=price(c,'close')
        if price(c,'high')>high and low<close<high and dir_allowed(self.params,'short'):
            direction='short';stop=price(c,'high')+0.05*(high-low)
        elif price(c,'low')<low and low<close<high and dir_allowed(self.params,'long'):
            direction='long';stop=price(c,'low')-0.05*(high-low)
        else:return None
        out=signal(direction,stop,close,rr=float(self.params['target_r']),reason='failed_15m_opening_range',
                   meta={'or_high':high,'or_low':low,'session_day':day.isoformat()})
        if out:self.used.add(day)
        return out


# === FullView-inspired HTF liquidity + 5m FVG inversion screening =========
@strategy_registry.register
class FullviewIFVGCISDProxy(Strategy):
    spec=StrategySpec(key='fullview_ifvg_cisd_proxy_v1',name='FullView-inspired IFVG/CISD · proxy',
        description='Research proxy: 5m 3-candle FVG, subsequent first inversion close, 1h sweep proximity and 5m displacement.',
        category='Experimental',timeframes=('5m','1h'),
        defaults={'max_inversion_bars':12,'min_gap_bps':1.5,'target_r':2.0},
        research_parameters=(ParameterSpec('target_r','Target R','float',2,0.5,5,0.25),),source_file=SOURCE)
    def __init__(self,**kwargs):super().__init__(**kwargs);self.reset()
    def reset(self):self.gap=None;self.last5=None;self.used=set()
    def on_bar(self,ctx):
        if ctx.primary_timeframe!='5m' or ctx.position is not None:return None
        b=ctx.bars('5m',count=28);h=ctx.bars('1h',count=18)
        if not valid_bars(b,18) or not valid_bars(h,10):return None
        stamp=ts(b.iloc[-1])
        if stamp==self.last5:return None
        self.last5=stamp
        c=b.iloc[-1];a=b.iloc[-3];close=price(c,'close')
        day=nydate(ctx)
        if day in self.used:return None
        if self.gap:
            g=self.gap
            if ctx.decision_time>g['expiry']:self.gap=None
            else:
                inverted=(g['origin']=='bull' and close<g['lower']) or (g['origin']=='bear' and close>g['upper'])
                direction='short' if g['origin']=='bull' else 'long'
                candle_range=price(c,'high')-price(c,'low')
                avg_range=(b.high.astype(float)-b.low.astype(float)).tail(15).mean()
                if inverted and candle_range>=1.2*avg_range:
                    recent=h.iloc[-9:-1]
                    # Only a proxy to a higher-timeframe liquidity location.
                    near_h=price(c,'high')>=float(recent.high.max())*0.999
                    near_l=price(c,'low')<=float(recent.low.min())*1.001
                    if (direction=='short' and near_h) or (direction=='long' and near_l):
                        stop=(max(price(c,'high'),g['upper']) if direction=='short' else min(price(c,'low'),g['lower']))
                        stop=stop*(1.0002 if direction=='short' else 0.9998)
                        out=signal(direction,stop,close,rr=float(self.params['target_r']),reason='ifvg_inversion_cisd_proxy',
                                   meta=dict(gap_lower=g['lower'],gap_upper=g['upper'],origin=g['origin'],
                                             note='HTF liquidity/CISD mechanical proxy'))
                        self.gap=None
                        if out:self.used.add(day)
                        return out
                if inverted:self.gap=None
        # freeze a new 5m gap after the three candles are completed
        upper_a=price(a,'high');lower_a=price(a,'low');upper_c=price(c,'high');lower_c=price(c,'low')
        if upper_a<lower_c:
            origin,lower,upper='bull',upper_a,lower_c
        elif lower_a>upper_c:
            origin,lower,upper='bear',upper_c,lower_a
        else:return None
        if (upper-lower)/close*10000<float(self.params['min_gap_bps']):return None
        self.gap=dict(origin=origin,lower=lower,upper=upper,
                      expiry=ctx.decision_time+timedelta(minutes=5*int(self.params['max_inversion_bars'])))
        return None


# === Gold supply impulse / retracement (short only) =======================
@strategy_registry.register
class GoldSupplyRetrace(Strategy):
    spec=StrategySpec(key='gold_supply_618_786_retrace_v1',name='Gold supply 0.618–0.786 retracement',
        description='30m bearish EMA filter; bearish 15m impulse; 1m rejection in 61.8%–78.6% retracement zone.',
        category='Experimental',timeframes=('1m','15m','30m'),defaults={'target_r':2.0,'impulse_atr':1.5},
        research_parameters=(ParameterSpec('target_r','Target R','float',2,0.5,5,0.25),),source_file=SOURCE)
    def __init__(self,**kwargs):super().__init__(**kwargs);self.reset()
    def reset(self):self.setup=None;self.last15=None;self.used=set()
    def on_bar(self,ctx):
        if ctx.primary_timeframe!='1m' or ctx.position is not None:return None
        b=ctx.bars('1m',count=4);h=ctx.bars('15m',count=21);higher=ctx.bars('30m',count=35)
        if not valid_bars(b,3) or not valid_bars(h,18) or not valid_bars(higher,30):return None
        e=higher.close.astype(float).ewm(span=20,adjust=False).mean()
        bearish=price(higher.iloc[-1],'close')<float(e.iloc[-1])<float(e.iloc[-4])
        stamp=ts(h.iloc[-1]);day=nydate(ctx)
        if day in self.used:return None
        if stamp!=self.last15:
            self.last15=stamp;current=h.iloc[-1];a=atr(h.iloc[:-1],14)
            if bearish and a and price(current,'open')-price(current,'close')>a*float(self.params['impulse_atr']):
                top=price(current,'high');bot=price(current,'low');height=top-bot
                self.setup=dict(lo=bot+height*0.618,hi=bot+height*0.786,stop=top+a*0.1,
                                expires=ctx.decision_time+timedelta(minutes=75),created=ctx.decision_time)
            elif not bearish:self.setup=None
        s=self.setup
        if not s or ctx.decision_time>s['expires'] or not bearish:return None
        c=b.iloc[-1];close=price(c,'close')
        if ts(c) < pd.Timestamp(s['created']):return None
        if price(c,'high')>=s['lo'] and close<s['lo'] and close<price(c,'open') and close<s['stop']:
            out=signal('short',s['stop'],close,rr=float(self.params['target_r']),reason='gold_supply_retrace',
                       meta=dict(zone_low=s['lo'],zone_high=s['hi']))
            if out:self.used.add(day);self.setup=None
            return out
        return None


# === BTC high-timeframe trend breakout + BTC 5m mean reversion =============
@strategy_registry.register
class BTC15mBreakout(Strategy):
    spec=StrategySpec(key='btc_15m_donchian_trend_v1',name='BTC 15m breakout / 1H trend',
        description='15m close beyond prior 20 bars, gated by 1h EMA30, ATR stop and 2R target.',
        category='Experimental',timeframes=('15m','1h'),defaults={'lookback':20,'target_r':2.0},
        parameters=(ParameterSpec('lookback','Donchian lookback','int',20,8,60,1),),source_file=SOURCE)
    def __init__(self,**kwargs):super().__init__(**kwargs);self.reset()
    def reset(self):self.last=None
    def on_bar(self,ctx):
        if ctx.primary_timeframe!='15m' or ctx.position is not None:return None
        n=int(self.params['lookback']);b=ctx.bars('15m',count=n+20);h=ctx.bars('1h',count=40)
        if not valid_bars(b,n+15) or not valid_bars(h,35):return None
        c=b.iloc[-1];stamp=ts(c)
        if stamp==self.last:return None
        self.last=stamp;prev=b.iloc[-n-1:-1];a=atr(b.iloc[:-1],14)
        if not a:return None
        ema=h.close.astype(float).ewm(span=30,adjust=False).mean();ref=price(c,'close')
        if ref>float(prev.high.max()) and price(h.iloc[-1],'close')>float(ema.iloc[-1]):direction='long';stop=ref-1.5*a
        elif ref<float(prev.low.min()) and price(h.iloc[-1],'close')<float(ema.iloc[-1]):direction='short';stop=ref+1.5*a
        else:return None
        return signal(direction,stop,ref,rr=float(self.params['target_r']),reason='btc_donchian_trend',meta={'atr':a,'lookback':n})

@strategy_registry.register
class BTC5mMeanReversion(Strategy):
    spec=StrategySpec(key='btc_5m_mean_reversion_v1',name='BTC 5m mean-reversion · research',
        description='5m close >2.2 standard deviations from completed 30-bar mean; enter toward mean with ATR stop.',
        category='Experimental',timeframes=('5m',),defaults={'lookback':30,'z_threshold':2.2,'target_r':1.5},
        parameters=(ParameterSpec('lookback','Rolling bars','int',30,20,100,5),),source_file=SOURCE)
    def __init__(self,**kwargs):super().__init__(**kwargs);self.reset()
    def reset(self):self.last=None;self.cooldown=0
    def on_bar(self,ctx):
        if ctx.primary_timeframe!='5m' or ctx.position is not None:return None
        n=int(self.params['lookback']);b=ctx.bars('5m',count=n+3)
        if not valid_bars(b,n+1):return None
        c=b.iloc[-1];stamp=ts(c)
        if stamp==self.last:return None
        self.last=stamp
        if self.cooldown>0:self.cooldown-=1;return None
        old=b.close.astype(float).iloc[-(n+1):-1]
        mean=float(old.mean());std=float(old.std(ddof=1));a=atr(b.iloc[:-1],14)
        if not std or not a:return None
        ref=price(c,'close');z=(ref-mean)/std
        if z>=float(self.params['z_threshold']):direction='short';stop=ref+1.5*a
        elif z<=-float(self.params['z_threshold']):direction='long';stop=ref-1.5*a
        else:return None
        # Target at historical mean, skip cases with no reward relative to stop.
        out=signal(direction,stop,ref,tp=mean,reason='btc_5m_mean_reversion',meta={'z':z,'mean':mean,'atr':a})
        if out:self.cooldown=12
        return out


# === Controlled ablations / confluence additions ============================
@strategy_registry.register
class DailyHourlyFiveMinNoBias(DailyHourlyFiveMinRetest):
    USE_DAILY_BIAS=False
    spec=replace(DailyHourlyFiveMinRetest.spec,key='mtf_h1_m5_retest_no_daily_v1',
        name='1H / 5m breakout-retest · no daily bias',
        description='Ablation of D1 filter from Daily/1H/5m model, otherwise identical.')

@strategy_registry.register
class PowellTenAMLimit(PowellTenAMReversal):
    spec=replace(PowellTenAMReversal.spec,key='powell_10am_half_retrace_v1',
        name='Powell 10am · 50% retracement limit',
        description='Same 10am sweep+confirmation as base, then limit at midpoint of confirmation 1m body, 10-bar expiry.')
    def on_bar(self,ctx):
        out=super().on_bar(ctx)
        if not isinstance(out,EntrySignal):return out
        last=ctx.bars('1m',count=1).iloc[-1]
        midpoint=(price(last,'open')+price(last,'close'))/2
        if ((out.direction=='short' and midpoint<=out.stop_loss) or
            (out.direction=='long' and midpoint>=out.stop_loss)):
            return replace(out,order_type='limit',entry_price=midpoint,max_wait_bars=10,
                           reason=out.reason+'_body_half_limit')
        return None


# Uses original coded Type-3 strategy, never changes the original source.
from app.backtesting.strategies.xau_liquidity_type3 import XauLiquiditySweepType3Baseline

@strategy_registry.register
class GoldType3HourlyTrend(XauLiquiditySweepType3Baseline):
    spec=replace(XauLiquiditySweepType3Baseline.spec,
        key='gold_type3_1h_trend_filter_v1',
        name='Gold Type-3 · 1H EMA trend filter',
        description='Existing XAU Type-3 liquidity sweep + 50% limit, plus hourly EMA30 trend/slope gate.',
        source_file=SOURCE)
    def on_bar(self,ctx):
        out=super().on_bar(ctx)
        if not isinstance(out,EntrySignal):return out
        h=ctx.bars('1h',count=40)
        if not valid_bars(h,35):return None
        e=h.close.astype(float).ewm(span=30,adjust=False).mean()
        c=price(h.iloc[-1],'close')
        valid=(out.direction=='long' and c>float(e.iloc[-1])>float(e.iloc[-4])) or (
               out.direction=='short' and c<float(e.iloc[-1])<float(e.iloc[-4]))
        if not valid:return None
        return replace(out,reason=out.reason+'_1h_ema_filter',
                       metadata={**out.metadata,'hourly_ema30':float(e.iloc[-1]),
                                 'hourly_ema30_3bars_prior':float(e.iloc[-4]),
                                 'research_confluence':'1h_ema30_direction_slope'})
