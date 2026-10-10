"""Deterministic evidence from immutable engine results, never LLM arithmetic."""
from collections import defaultdict
from hashlib import sha256
import json
from statistics import median
from .diagnostics import diagnostics, excursions, number, outcome, large_winner, timestamp


def digest(value):return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,default=str).encode()).hexdigest()

def summary(trades):
    rs=[number(t.get('r_multiple')) for t in trades if number(t.get('r_multiple')) is not None]
    pnls=[number(t.get('net_pnl')) for t in trades if number(t.get('net_pnl')) is not None]
    profits=sum(max(0,r) for r in rs);losses=-sum(min(0,r) for r in rs)
    return {**excursions(trades),'n':len(trades),'r_observations':len(rs),'total_r':sum(rs) if rs or not trades else None,'average_r':sum(rs)/len(rs) if rs else None,
        'median_r':median(rs) if rs else None,'average_winner_r':sum(r for r in rs if r>0)/sum(r>0 for r in rs) if any(r>0 for r in rs) else None,'average_loser_r':sum(r for r in rs if r<0)/sum(r<0 for r in rs) if any(r<0 for r in rs) else None,'profit_factor_r':profits/losses if losses else None,
        'win_rate_pct':100*sum(p>0 for p in pnls)/len(pnls) if pnls else None,
        'net_pnl':sum(pnls) if len(pnls)==len(trades) else None,'low_sample':len(trades)<30}

def analyze(run):
    result=run['result'];trades=result.get('trades') or []
    diagnostic=diagnostics(trades,summary)
    fingerprint=run['config'].get('market_data_fingerprint') or result.get('data',{}).get('fingerprint')
    return {'summary':summary(trades),'engine_metrics':result.get('metrics',{}),**diagnostic,
        'strategy_provenance':result.get('strategy',{}).get('implementation'),
        'concepts':result.get('strategy',{}).get('concepts',{}),'data_fingerprint':fingerprint,
        'result_digest':digest({'trades':trades,'metrics':result.get('metrics'), 'equity_curve':result.get('equity_curve')}),
        'warnings':['Descriptive findings are not causal evidence. Low sample means N < 30 (heuristic).']+([] if fingerprint else ['No full market-data fingerprint was saved; reproducibility cannot be established.'])}

def compare(parent,child):
    def indexed(run):
        result={}
        for trade in run['result'].get('trades',[]):
            when=timestamp(trade.get('entry_time'))
            if when is None:raise ValueError('Trade identity requires a timezone-aware entry timestamp')
            key=(trade['symbol'],trade['direction'],when.isoformat())
            if key in result:raise ValueError('Ambiguous duplicate trade identity; comparison stopped')
            result[key]=trade
        return result
    a,b=indexed(parent),indexed(child);retained=a.keys()&b.keys()
    removed=[a[k] for k in sorted(a.keys()-b.keys())];added=[b[k] for k in sorted(b.keys()-a.keys())]
    identity=lambda trade:{key:trade.get(key) for key in ('symbol','direction','entry_time','exit_time','net_pnl','r_multiple','exit_reason')}
    pa,ca=analyze(parent),analyze(child)
    return {'parent':pa,'child':ca,'retained':len(retained),'changed_retained':sum(a[k]!=b[k] for k in retained),
        'removed':summary(removed),'introduced':summary(added),
        'removed_winners':summary([t for t in removed if outcome(t)=='winner']),
        'removed_losers':summary([t for t in removed if outcome(t)=='loser']),
        'removed_large_winners':summary([t for t in removed if large_winner(t)]),
        'removed_session_close_winners':summary([t for t in removed if outcome(t)=='winner' and t.get('exit_reason')=='session_close']),
        'retained_large_winners':summary([a[k] for k in sorted(retained) if large_winner(a[k])]),
        'retained_parent':summary([a[k] for k in sorted(retained)]),'retained_child':summary([b[k] for k in sorted(retained)]),
        'removed_trades':[identity(t) for t in removed],'introduced_trades':[identity(t) for t in added],
        'data_equivalent':bool(pa['data_fingerprint'] and pa['data_fingerprint']==ca['data_fingerprint']),
        'control_parity':pa['result_digest']==ca['result_digest'],
        'warning':'New entries are observed path differences, not proof that a specific removed entry caused a replacement. No static-filter promotion.'}
