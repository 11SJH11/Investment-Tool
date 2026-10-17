"""Read-only exact decision matching; never infer counterparts by fill proximity."""
import json
from collections import defaultdict

from .bars import stamp
from .deployments import digest
from .paper_gateway import B_KEY
from app.storage.journal_repository import _trade


def shadow_decision(connection, trade):
    metadata = trade['source_metadata']
    # Frozen B uses next-open market entries. The preceding completed-bar
    # checkpoint must contain that exact pending market order, not a nearby one.
    row = connection.execute('SELECT evidence_json,sha256 FROM forward_checkpoints WHERE deployment_id=? AND decision_at=?',
                             (metadata['deployment_id'], stamp(trade['opened_at']).isoformat())).fetchone()
    if not row:
        return None
    evidence = json.loads(row[0])
    if digest(evidence) != row[1]:
        return None
    pending = evidence['engine']['pending_entries'].get(trade['ticker'])
    if not pending:
        return None
    signal = pending['signal']
    if signal['order_type'] != 'market' or signal['direction'] != trade['direction']:
        return None
    if stamp(pending['decision_time']) != stamp(trade['opened_at']):
        return None
    return stamp(pending['decision_time']).isoformat()


def paper_decision(connection, trade):
    metadata = trade['source_metadata']
    decision = metadata.get('decision_at')
    if not decision:
        return None
    row = connection.execute('SELECT document,sha256 FROM forward_paper_decisions WHERE deployment_id=? AND decision_at=?',
                             (metadata['deployment_id'], decision)).fetchone()
    if not row:
        return None
    record = json.loads(row[0])
    result = record.get('result')
    if digest(record) != row[1] or not result or result['kind'] != 'entry':
        return None
    if result['signal']['direction'] != trade['direction']:
        return None
    return stamp(decision).isoformat()


def compare(connection, experiment):
    groups = defaultdict(lambda: {'shadow': [], 'paper': []})
    unresolved = []
    for row in connection.execute("SELECT * FROM journal_trades WHERE strategy_id=? AND source IN ('forward_shadow','broker_alpaca_paper')", (B_KEY,)):
        trade = _trade(row)
        metadata = trade['source_metadata']
        if metadata.get('experiment_id') != experiment:
            continue
        mode = 'shadow' if trade['source'] == 'forward_shadow' else 'paper'
        try:
            decision = shadow_decision(connection, trade) if mode == 'shadow' else paper_decision(connection, trade)
        except (KeyError, TypeError, ValueError):
            decision = None
        fingerprint = metadata.get('definition_sha256')
        if not decision or not fingerprint:
            unresolved.append(dict(status='evidence_unavailable', mode=mode, journal_id=trade['id']))
            continue
        groups[(fingerprint, trade['ticker'], trade['direction'], decision)][mode].append(trade)
    items = []
    for (_, symbol, direction, decision), pair in sorted(groups.items()):
        shadows, papers = pair['shadow'], pair['paper']
        base = dict(symbol=symbol, direction=direction, decision_at=decision,
                    shadow_journal_ids=[t['id'] for t in shadows], paper_journal_ids=[t['id'] for t in papers])
        if len(shadows)>1 or len(papers)>1:
            items.append(dict(**base,status='ambiguous')); continue
        if not shadows or not papers:
            items.append(dict(**base,status='missing_closed_paper' if shadows else 'missing_closed_shadow')); continue
        shadow, paper = shadows[0], papers[0]
        sign = 1 if direction == 'long' else -1
        # Positive slippage means worse execution for either direction. Weighted
        # order averages are compared, never reinterpreted as individual fills.
        entry = sign*(paper['entry_price']-shadow['entry_price'])
        exit_ = sign*(shadow['exit_price']-paper['exit_price'])
        exact_times = all(e['metadata'].get('timestamp_basis') == 'broker_completed_fill'
                          for e in paper['source_metadata'].get('executions', [])) and bool(paper['source_metadata'].get('executions'))
        duration = lambda t: (stamp(t['closed_at'])-stamp(t['opened_at'])).total_seconds()
        entry_evidence=next((e for e in paper['source_metadata'].get('executions',[]) if e.get('role')=='entry'),{})
        times=entry_evidence.get('metadata',{})
        def delay(end,start):
            if not end or not start:return None
            try:
                value=(stamp(end)-stamp(start)).total_seconds()
                return value if value>=0 else None
            except (ValueError,TypeError):return None
        items.append(dict(**base,status='matched',entry_slippage_per_share=entry,exit_slippage_per_share=exit_,
                          pnl_difference=(paper['pnl_amount']-shadow['pnl_amount']) if paper['pnl_amount'] is not None and shadow['pnl_amount'] is not None else None,
                          duration_difference_seconds=duration(paper)-duration(shadow) if exact_times else None,
                          submission_latency_seconds=delay(times.get('broker_submitted_at'),decision),
                          fill_latency_seconds=delay(times.get('broker_filled_at'),times.get('broker_submitted_at'))))
    return dict(items=items,unresolved=unresolved,matched=sum(i['status']=='matched' for i in items),
                limitation='Closed Journal trades only. Missing counterpart may still be open or not imported. Exact decision/source matches only; positive slippage is adverse. Timing uses broker submission/completed-fill timestamps, not individual fills; missing or negative durations remain unavailable.')
