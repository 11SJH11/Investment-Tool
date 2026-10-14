"""Preregistered bounded development samples; never a portfolio or holdout test."""
from datetime import date, timedelta
from pydantic import model_validator
from .hypotheses import Strict
from .analysis import digest, compare, summary
from .sandbox import SandboxError


class Window(Strict):
    start: date
    end: date

    @model_validator(mode='after')
    def bounded(self):
        if not 0 <= (self.end-self.start).days <= 36525:
            raise ValueError('Robustness windows must be ordered and span at most 100 years')
        return self


def plan_windows(plan, *, full_windows=False):
    windows=[Window(start=w['start'],end=date.fromisoformat(w['end']) if full_windows else min(date.fromisoformat(w['end']),
             date.fromisoformat(w['start'])+timedelta(days=6))).model_dump(mode='json')
             for w in plan['internal_development_windows']]
    if len(windows)>3:
        raise ValueError('Bounded structural checks support at most three development windows')
    return windows


def simulation_count(windows):
    # Anchor: parent/control/child/prefix. Each window repeats those at 1x and 2x costs.
    return 4+8*len(windows)


def execute(windows, config, prepare, simulate, save, *, full_windows=False):
    """Callbacks retain the sandbox's existing firewall, deadline and Docker path."""
    cells=[]
    for index,window in enumerate(windows):
        for multiplier in (1,2):
            payload={**config,'start_date':window['start'],'end_date':window['end']}
            for key in ('commission_per_order','spread_bps','slippage_bps'):
                payload[key]=config.get(key,0)*multiplier
            cell=dict(window=index+1,start=window['start'],end=window['end'],cost_multiplier=multiplier,
                      status='PREPARING',configuration_sha256=digest(payload))
            cells.append(cell);save(cells)
            inputs,parent,fingerprint=prepare(payload)
            if multiplier==2 and fingerprint!=cells[-2]['data_fingerprint']:
                raise SandboxError('ROBUSTNESS_DATA_CHANGED_BETWEEN_COSTS')
            cell.update(status='RUNNING',data_fingerprint=fingerprint,parent_result_sha256=digest(parent))
            save(cells)
            prefix=f"ROBUSTNESS_{index+1}_COST_{multiplier}"
            control,_,_=simulate(payload,inputs,False,prefix+'_CONTROL',False)
            from .sandbox_runs import core, first_divergence
            if core(control)!=core(parent):
                cell.update(status='FAILED',first_divergence=first_divergence(core(parent),core(control)))
                save(cells)
                raise SandboxError('ROBUSTNESS_CONTROL_MISMATCH')
            child,trace,provenance=simulate(payload,inputs,True,prefix+'_CHILD',False)
            _,short,_=simulate(payload,inputs,True,prefix+'_PREFIX',True)
            if not short or trace[:len(short)]!=short:
                cell.update(status='FAILED');save(cells)
                raise SandboxError('ROBUSTNESS_CAUSALITY_MISMATCH')
            identity={**payload,'market_data_fingerprint':fingerprint}
            cell.update(status='COMPLETED',control_parity=True,prefix_signals_checked=len(short),
                        provenance=provenance,signal_trace_sha256=digest(trace),result_sha256=digest(child),
                        parent_result=parent,result=child,summary=summary(child['trades']),
                        comparison=compare({'config':identity,'result':parent},{'config':identity,'result':child}))
            save(cells)
    return dict(version='full_window_development_cost_checks_v1' if full_windows else 'bounded_development_cost_checks_v1',cells=cells,
                zero_cost_stress=not any(config.get(k,0) for k in ('commission_per_order','spread_bps','slippage_bps')),
                limitation=('Complete preregistered development windows at original and doubled costs, independently reset accounts. Not a combined portfolio or unseen validation.' if full_windows else 'First seven calendar days of each preregistered development window, independently reset accounts. Not full-period, portfolio or unseen validation.'))
