"""Deterministic development triage. Never grants unseen-data or live authority."""
import math
from .analysis import digest


def assess(trial,policy):
    reasons=[]
    cells=list(trial.get('robustness',{}).get('cells',[]))
    if cells and trial.get('request',{}).get('full_period'):
        cells.append(dict(status=trial.get('status'),summary=trial.get('summary',{}),
            comparison=trial.get('comparison',{}),result=trial.get('result',{})))
    if trial.get('status')!='COMPLETED' or not trial.get('control_parity') or not trial.get('causality',{}).get('prefix_match'):
        verdict='INVALID_EXECUTION';reasons.append('Control, causality or execution did not complete.')
    elif not cells or any(c.get('status')!='COMPLETED' for c in cells):
        verdict='INSUFFICIENT_EVIDENCE';reasons.append('Preregistered robustness cells are incomplete.')
    else:
        def finite(value):return type(value) in (int,float) and math.isfinite(value)
        if any(c.get('summary',{}).get('n',0)<policy['minimum_trades'] for c in cells):
            reasons.append('At least one development/cost sample is below the frozen minimum N.')
        if trial.get('robustness',{}).get('zero_cost_stress'):
            reasons.append('Zero execution costs do not establish cost robustness.')
        if reasons:verdict='INSUFFICIENT_EVIDENCE'
        else:
            for cell in cells:
                summary=cell['summary'];comparison=cell.get('comparison',{})
                parent=comparison.get('parent',{}).get('summary',{})
                if not finite(summary.get('average_r')) or summary['average_r']<=0:
                    reasons.append('A development/cost sample has non-positive or unavailable expectancy.')
                if not finite(parent.get('average_r')) or summary['average_r']<parent['average_r']:
                    reasons.append('A development/cost sample does not retain parent expectancy.')
                metrics=cell.get('result',{}).get('metrics',{})
                drawdown=metrics.get('max_drawdown_pct')
                if not finite(drawdown) or abs(drawdown)>policy['max_development_drawdown_percent']:
                    reasons.append('Drawdown is unavailable or exceeds the frozen policy.')
                if comparison.get('removed_large_winners',{}).get('n',0)>0:
                    reasons.append('Large parent winners were removed; automatic promotion is blocked.')
            verdict='REJECTED_DEVELOPMENT' if reasons else 'PROMISING_DEVELOPMENT'
    return dict(version='development_triage_v1',verdict=verdict,reasons=list(dict.fromkeys(reasons)),
                evidence_sha256=digest(trial),policy_sha256=digest(policy),
                accepted=False,validation_authorized=False,
                limitation='Development triage is not unseen validation, a profitability claim or deployment authorization.')
