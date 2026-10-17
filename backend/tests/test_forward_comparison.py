import json
import pytest
from app.forward.comparison import compare, shadow_decision
from app.forward.deployments import digest
from app.forward.journal import ShadowJournal
from app.forward.paper_gateway import B_KEY
from app.storage.journal_repository import JournalRepository
from tests.test_forward_deployments import repository
from tests.test_forward_runtime import running, minutes


@pytest.fixture
def paired(running):
    runtime, experiment, _ = running
    runtime.ingest(experiment, minutes(6))
    ShadowJournal(runtime.database).sync(experiment)
    repo = JournalRepository(runtime.database)
    shadow = next(t for t in repo.list_trades() if t['strategy_id']==B_KEY)
    with runtime.database.connect() as c:
        decision = shadow_decision(c, shadow)
        assert decision == shadow['opened_at']
        c.execute('CREATE TABLE forward_paper_decisions(deployment_id TEXT,decision_at TEXT,document TEXT,sha256 TEXT)')
        record = dict(result=dict(kind='entry', signal=dict(direction=shadow['direction'])))
        c.execute('INSERT INTO forward_paper_decisions VALUES (?,?,?,?)', ('paper',decision,json.dumps(record),digest(record)))
    paper = repo.create_trade({**shadow,'source':'broker_alpaca_paper','external_provider':'alpaca_paper','external_id':'paper',
        'entry_price':shadow['entry_price']+.25,'exit_price':shadow['exit_price']-.5,'pnl_amount':None,
        'source_metadata':dict(experiment_id=experiment,deployment_id='paper',definition_sha256=shadow['source_metadata']['definition_sha256'],
                               decision_at=decision,executions=[{'metadata':{'timestamp_basis':'broker_completed_fill'}}])})
    return runtime.database, experiment, repo, shadow, paper


def test_exact_decision_match_and_unknown_pnl(paired):
    db, experiment, _, shadow, paper = paired
    with db.connect() as c: result = compare(c,experiment)
    assert result['matched']==1
    item = next(i for i in result['items'] if i['status']=='matched')
    assert item['shadow_journal_ids']==[shadow['id']] and item['paper_journal_ids']==[paper['id']]
    assert item['entry_slippage_per_share']==.25 and item['exit_slippage_per_share']==.5
    assert item['pnl_difference'] is None and item['submission_latency_seconds'] is None
    assert item['duration_difference_seconds']==0


@pytest.mark.parametrize('fault',['decision','definition','checksum','observation'])
def test_no_nearby_or_incompatible_matching_and_no_invented_latency(paired,fault):
    db, experiment, repo, shadow, paper = paired
    metadata = paper['source_metadata']
    if fault=='decision':metadata['decision_at']='2026-01-02T14:31:01+00:00'
    if fault=='definition':metadata['definition_sha256']='different'
    if fault=='observation':metadata['executions'][0]['metadata']['timestamp_basis']='first_observed_fill'
    repo.update_trade(paper['id'],{'source_metadata':metadata})
    with db.connect() as c:
        if fault=='checksum':c.execute("UPDATE forward_checkpoints SET sha256='corrupt'")
        result=compare(c,experiment)
    if fault=='observation':
        assert result['matched']==1
        assert next(i for i in result['items'] if i['status']=='matched')['duration_difference_seconds'] is None
    else:assert result['matched']==0


def test_duplicate_counterpart_is_ambiguous_and_report_does_not_mutate_reviews(paired):
    db, experiment, repo, shadow, paper = paired
    repo.update_trade(shadow['id'],{'notes':'Keep'})
    repo.create_trade({**paper,'external_id':'second'})
    before=repo.list_trades()
    with db.connect() as c:result=compare(c,experiment)
    assert result['matched']==0 and any(i['status']=='ambiguous' for i in result['items'])
    assert repo.list_trades()==before


def test_broker_timing_uses_reported_times_and_negative_delay_is_unknown(paired):
    from datetime import timedelta
    from app.forward.bars import stamp
    db,experiment,repo,_,paper=paired
    metadata=paper['source_metadata'];decision=stamp(metadata['decision_at'])
    metadata['executions'][0].update(role='entry')
    times=metadata['executions'][0]['metadata']
    times.update(broker_submitted_at=(decision+timedelta(seconds=2)).isoformat(),
                 broker_filled_at=(decision+timedelta(seconds=5)).isoformat())
    repo.update_trade(paper['id'],{'source_metadata':metadata})
    with db.connect() as c:item=next(i for i in compare(c,experiment)['items'] if i['status']=='matched')
    assert item['submission_latency_seconds']==2 and item['fill_latency_seconds']==3
    times['broker_filled_at']=(decision-timedelta(seconds=1)).isoformat()
    repo.update_trade(paper['id'],{'source_metadata':metadata})
    with db.connect() as c:item=next(i for i in compare(c,experiment)['items'] if i['status']=='matched')
    assert item['fill_latency_seconds'] is None
