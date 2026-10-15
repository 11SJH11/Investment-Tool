"""Single generated-feature removal, using already executed Docker controls.

This is not arbitrary internal-rule simplification or a significance test.
"""
import math

VERSION = 'single_feature_ablation_v1'


def assess(trial):
    request = trial.get('request', {})
    control = request.get('control_parameters', {})
    child = request.get('candidate_parameters', {})
    flag = 'research_feature_enabled'
    rows = []
    reasons = []
    if (control.get(flag) is not False or child.get(flag) is not True or
        {k: v for k, v in control.items() if k != flag} !=
        {k: v for k, v in child.items() if k != flag}):
        reasons.append('The comparison must change only the declared research feature switch.')
    robustness = trial.get('robustness', {})
    expected = [(i + 1, window['start'], window['end'], cost)
                for i, window in enumerate(request.get('windows', [])) for cost in (1, 2)]
    cells = robustness.get('cells', [])
    actual = [(c.get('window'), c.get('start'), c.get('end'), c.get('cost_multiplier')) for c in cells]
    if (not request.get('full_period') or not request.get('full_robustness_windows') or
        not expected or expected != actual or robustness.get('status') != 'COMPLETED'):
        reasons.append('Full-period and all preregistered cost-window controls are required.')
    if (trial.get('status') != 'COMPLETED' or not trial.get('control_parity') or
        not trial.get('causality', {}).get('prefix_match')):
        reasons.append('The anchor control or causality check is incomplete.')
    for index, cell in enumerate([trial, *cells]):
        if index and (cell.get('status') != 'COMPLETED' or not cell.get('control_parity') or
                      not cell.get('prefix_signals_checked')):
            reasons.append('A development-window control or causality check is incomplete.')
        comparison = cell.get('comparison', {})
        parent = comparison.get('parent', {}).get('summary', {})
        child_summary = cell.get('summary', {})
        a, b = parent.get('average_r'), child_summary.get('average_r')
        finite = lambda value: type(value) in (int, float) and math.isfinite(value)
        if not finite(a) or not finite(b):
            reasons.append('A paired expectancy is unavailable.')
        rows.append(dict(scope='full_period' if index == 0 else 'development_window',
                         window=cell.get('window'), start=cell.get('start'), end=cell.get('end'),
                         cost_multiplier=cell.get('cost_multiplier', 1),
                         parent_n=parent.get('n'), child_n=child_summary.get('n'),
                         parent_average_r=a, child_average_r=b,
                         delta_average_r=b-a if finite(a) and finite(b) else None))
    verdict = ('INCOMPLETE' if reasons else 'FEATURE_CONTRIBUTION_OBSERVED'
               if any(row['delta_average_r'] > 0 for row in rows) else 'PREFER_SIMPLER_PARENT')
    return dict(version=VERSION, verdict=verdict, rows=rows, reasons=list(dict.fromkeys(reasons)),
                additional_simulations=0,
                limitation='Disables the one declared generated feature using exact parent-parity controls. '
                'Does not remove arbitrary parent rules or establish statistical significance. '
                'Other sample, cost, drawdown, winner-retention and validation gates still apply.')
