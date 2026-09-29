"""Exact, bounded parameter experiments.

Every research cell is a real BacktestEngine simulation.  In addition to ordinary
threshold spectra, paired min/max parameters may be explored as non-overlapping
bands (lower inclusive, upper exclusive).  Bands are deliberately executed rather
than derived by subtracting cumulative results because rejecting one opportunity
can change later strategy state.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext
from itertools import product

from app.backtesting.strategies import strategy_registry


def decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError('Values must be finite numbers') from exc
    if not result.is_finite():
        raise ValueError('Values must be finite numbers')
    return result


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), 'f')
    return '0' if text in {'-0', '-0.0'} else text


def _validate_value(value, spec):
    default = decimal(spec.default)
    if spec.kind == 'int' and value != value.to_integral_value():
        raise ValueError(f'{spec.label} requires integers')
    if spec.minimum is not None and value < decimal(spec.minimum):
        raise ValueError(f'{spec.label} is below its minimum')
    if spec.maximum is not None and value > decimal(spec.maximum):
        raise ValueError(f'{spec.label} exceeds its maximum')
    # A declared sentinel/default remains legal even when it is off the lattice.
    if spec.step and value != default:
        origin = decimal(spec.minimum if spec.minimum is not None else 0)
        if (value - origin) % decimal(spec.step):
            raise ValueError(f'{spec.label} must align with step {spec.step}')


def _ordinary_values(axis, spec, limit):
    mode = axis.get('mode', 'explicit')
    if mode == 'explicit':
        raw = axis.get('values', [])
        raw = raw.split(',') if isinstance(raw, str) else raw
        values = [decimal(v.strip() if isinstance(v, str) else v) for v in raw if str(v).strip()]
    elif mode == 'range':
        start, end = decimal(axis.get('start')), decimal(axis.get('end'))
        if end < start:
            raise ValueError('End must be at least start')
        if axis.get('count') is not None and axis.get('step') is not None:
            raise ValueError('Choose step or number of values, not both')
        if axis.get('count') is not None:
            count = decimal(axis['count'])
            if count != count.to_integral_value() or not 2 <= count <= limit:
                raise ValueError(f'Number of values must be an integer from 2 to {limit}')
            with localcontext() as ctx:
                ctx.prec = 28
                step = (end - start) / (int(count) - 1)
                values = [start + step * i for i in range(int(count))]
                values[-1] = end
        else:
            step = decimal(axis.get('step'))
            if step <= 0:
                raise ValueError('Step must be positive')
            count = int((end - start) // step) + 1
            if count > limit:
                raise ValueError(f'Axis exceeds {limit} values')
            values = [start + step * i for i in range(count)]
    else:
        raise ValueError('Unknown value generation mode')
    if not 1 <= len(values) <= limit:
        raise ValueError(f'Use 1 to {limit} values per axis')
    if len(set(values)) != len(values):
        raise ValueError('Duplicate axis values are not allowed')
    for value in values:
        _validate_value(value, spec)
    convert = int if spec.kind == 'int' else float
    return {
        'parameter': spec.key, 'label': spec.label, 'default': spec.default,
        'kind': spec.kind, 'minimum': spec.minimum, 'maximum': spec.maximum, 'step': spec.step,
        'mode': mode, 'values': [convert(v) for v in values],
        'labels': [_plain(v) for v in values], 'bound_semantics': spec.bound_semantics or '',
    }


def _band_values(axis, lower_spec, upper_spec, limit):
    if not lower_spec.paired_max_key or lower_spec.paired_max_key != upper_spec.key:
        raise ValueError(f'{lower_spec.label} does not declare a compatible upper-bound parameter')
    # Explicit band mode treats values as EDGES, e.g. 1,1.25,1.5 -> two cells.
    raw = axis.get('values', [])
    if isinstance(raw, str):
        raw = [v.strip() for v in raw.split(',') if v.strip()]
    if raw:
        edges = [decimal(v) for v in raw]
    else:
        start, end = decimal(axis.get('start')), decimal(axis.get('end'))
        if end <= start:
            raise ValueError('Band end must be greater than band start')
        if axis.get('count') is not None and axis.get('step') is not None:
            raise ValueError('Choose band step or number of bands, not both')
        if axis.get('count') is not None:
            count = decimal(axis['count'])
            if count != count.to_integral_value() or not 1 <= count <= limit:
                raise ValueError(f'Number of bands must be an integer from 1 to {limit}')
            count = int(count)
            with localcontext() as ctx:
                ctx.prec = 28
                step = (end - start) / count
                edges = [start + step * i for i in range(count + 1)]
                edges[-1] = end
        else:
            step = decimal(axis.get('step'))
            if step <= 0:
                raise ValueError('Band step must be positive')
            intervals = int((end - start) // step)
            edges = [start + step * i for i in range(intervals + 1)]
            if not edges or edges[-1] != end:
                edges.append(end)
    if not 2 <= len(edges) <= limit + 1:
        raise ValueError(f'Use 2 to {limit + 1} edges ({limit} bands maximum)')
    if len(set(edges)) != len(edges) or any(b <= a for a, b in zip(edges, edges[1:])):
        raise ValueError('Band edges must be unique and strictly increasing')
    for value in edges[:-1]:
        _validate_value(value, lower_spec)
    for value in edges[1:]:
        _validate_value(value, upper_spec)
    convert = int if lower_spec.kind == 'int' else float
    bands = [[convert(a), convert(b)] for a, b in zip(edges, edges[1:])]
    return {
        'parameter': lower_spec.key, 'upper_parameter': upper_spec.key,
        'label': lower_spec.label.replace('Minimum ', '').replace(' minimum', ''),
        'default': lower_spec.default, 'kind': lower_spec.kind,
        'minimum': lower_spec.minimum, 'maximum': upper_spec.maximum, 'step': lower_spec.step,
        'mode': 'bands', 'values': [band[0] for band in bands], 'bands': bands,
        'labels': [f'{_plain(a)}–{_plain(b)}' for a, b in zip(edges, edges[1:])],
        'bound_semantics': '[lower, upper)',
    }


def axis_values(axis, spec, parameters, limit):
    if spec.kind not in ('int', 'float'):
        raise ValueError('Only numeric parameters support spectra')
    if axis.get('mode') != 'bands':
        return _ordinary_values(axis, spec, limit)
    if not spec.paired_max_key:
        raise ValueError(f'{spec.label} has no paired maximum and cannot be tested as bands')
    upper = parameters.get(spec.paired_max_key)
    if upper is None or upper.kind != spec.kind:
        raise ValueError(f'Paired upper bound {spec.paired_max_key} is unavailable')
    return _band_values(axis, spec, upper, limit)


def _overrides(axes, cell):
    params = {}
    for axis, value in zip(axes, cell):
        params[axis['parameter']] = value
        if axis.get('mode') == 'bands':
            try:
                index = axis['values'].index(value)
            except ValueError as exc:
                raise ValueError('Research band cell does not belong to its axis') from exc
            params[axis['upper_parameter']] = axis['bands'][index][1]
    return params


def _cell_label(axes, cell):
    parts = []
    for axis, value in zip(axes, cell):
        if axis.get('mode') == 'bands':
            index = axis['values'].index(value)
            parts.append(f"{axis['parameter']}=[{axis['labels'][index]})" if '–' not in axis['labels'][index] else f"{axis['parameter']}={axis['labels'][index]} [lower,upper)")
        else:
            parts.append(f"{axis['parameter']}={value}")
    return ', '.join(parts)


def preview(base, axes):
    if len(axes) not in (1, 2):
        raise ValueError('Choose one spectrum axis or two interaction axes')
    if len({a.get('parameter') for a in axes}) != len(axes):
        raise ValueError('Interaction axes must use different parameters')
    specs = {s.key: s for s in strategy_registry.specs()}
    strategy_spec = specs.get(base.get('strategy_key'))
    if strategy_spec is None:
        raise ValueError('Unknown strategy')
    parameters = {p.key: p for p in (*strategy_spec.parameters, *strategy_spec.research_parameters)}
    generated = []
    effective_keys = set()
    for axis in axes:
        parameter = parameters.get(axis.get('parameter'))
        if parameter is None:
            raise ValueError('Unknown research parameter')
        generated_axis = axis_values(axis, parameter, parameters, 25 if len(axes) == 1 else 8)
        keys = {generated_axis['parameter']}
        if generated_axis.get('upper_parameter'):
            keys.add(generated_axis['upper_parameter'])
        if effective_keys & keys:
            raise ValueError('Interaction axes may not override the same effective parameter')
        effective_keys |= keys
        generated.append(generated_axis)
    symbols = base.get('symbols', [])
    symbols = symbols.replace(',', ' ').split() if isinstance(symbols, str) else symbols
    if len(symbols) != 1:
        raise ValueError('Research experiments require exactly one symbol; create a separate experiment for each symbol')
    cells = list(product(*(a['values'] for a in generated)))
    for cell in cells:
        params = {**base.get('strategy_params', {}), **_overrides(generated, cell)}
        strategy_registry.create(strategy_spec.key, **params)
    return {
        'kind': 'spectrum' if len(axes) == 1 else 'interaction', 'axes': generated,
        'job_count': len(cells), 'cells': [list(cell) for cell in cells],
        'exact_simulations': True,
        'note': 'Band cells are executed as exact [lower, upper) simulations; they are not derived by subtracting cumulative runs.',
    }


def children(base, axes, request_key, name='', notes='', tags=None, role='development'):
    if role not in ('development', 'validation', 'out_of_sample'):
        raise ValueError('Invalid experiment role')
    plan = preview(base, axes)
    group = 'research:' + request_key
    runs = []
    for index, cell in enumerate(plan['cells']):
        child = deepcopy(base)
        params = _overrides(plan['axes'], cell)
        child['strategy_params'] = {**child.get('strategy_params', {}), **params}
        child.update(
            save_run=True, experiment_group=group, test_role=role,
            run_name=f"{name or 'Research experiment'} · {_cell_label(plan['axes'], cell)}",
            run_notes=notes, run_tags=list(tags or []),
        )
        child['research_experiment'] = {
            **deepcopy(plan), 'name': name, 'cell_index': index, 'cell': cell,
            'cell_overrides': params,
        }
        runs.append(child)
    return plan, runs
