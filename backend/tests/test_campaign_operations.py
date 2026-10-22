import json
from datetime import datetime,timezone
import pytest
from app.research_agent.campaign_operations import operations
from tests.test_research_campaigns import repo


def test_operation_scope_metering_and_unknown_cost(repo):
    with repo.database.connect() as c:
        c.execute('CREATE TABLE agent_reviews(project_id TEXT,document TEXT)')
        record=dict(id='review',status='RUNNING',reserved_calls=3,reserved_cost_microusd=500,
            deadline='2026-10-22T12:00:00+00:00',operation=dict(role='Devil',status='RUNNING',started_at='2026-10-22T11:59:00Z'),
            usage={'Researcher':{'input_tokens':10,'output_tokens':20,'estimated_cost_microusd':100},'unknown':{}},
            evidence={'secret':'DO_NOT_EXPOSE'},roles={'source':'DO_NOT_EXPOSE'},provider={'api_key':'DO_NOT_EXPOSE'})
        c.execute('INSERT INTO agent_reviews VALUES(?,?)',('p',json.dumps(record)))
        c.execute('INSERT INTO agent_reviews VALUES(?,?)',('other',json.dumps(dict(record,id='other'))))
    result=operations(repo.database,{'execution':{'entries':[{'project_id':'p','family_id':'family'}]}},now=datetime(2026,10,22,12,1,tzinfo=timezone.utc))
    row=result['model_operations'][0]
    assert len(result['model_operations'])==1 and row['elapsed_seconds']==120
    assert row['deadline_elapsed'] is True
    assert row['returned_usage_calls']==2 and row['estimated_reported_cost_microusd']==100
    assert row['unpriced_returned_calls']==1
    assert 'DO_NOT_EXPOSE' not in json.dumps(result)


def test_legacy_operation_never_fabricates_timing_or_zero_cost(repo):
    with repo.database.connect() as c:
        c.execute('CREATE TABLE agent_reviews(project_id TEXT,document TEXT)')
        c.execute('INSERT INTO agent_reviews VALUES(?,?)',('p',json.dumps(dict(id='legacy',status='COMPLETED'))))
    row=operations(repo.database,{'execution':{'entries':[{'project_id':'p','family_id':'family'}]}})['model_operations'][0]
    assert row['elapsed_seconds'] is None and row['estimated_reported_cost_microusd'] is None
    assert row['deadline_elapsed'] is False


def test_empty_campaign_without_review_schema(repo):
    assert operations(repo.database,{})['model_operations']==[]


def test_sandbox_progress_scope_stalls_and_stale_phase(repo):
    with repo.database.connect() as c:
        c.execute('CREATE TABLE agent_sandbox_runs(project_id TEXT,document TEXT)')
        record=dict(id='sandbox',status='RUNNING',phase='CANDIDATE',updated_at='2026-10-22T11:00:00Z',
            progress=dict(phase='CANDIDATE',processed=25,total=100,observed_at='2026-10-22T11:00:00Z'),
            source='DO_NOT_EXPOSE',result={'private':'DO_NOT_EXPOSE'},
            sandbox_events=[dict(event='backtest_running',phase='CANDIDATE',reason='DO_NOT_EXPOSE')]*15)
        c.execute('INSERT INTO agent_sandbox_runs VALUES(?,?)',('p',json.dumps(record)))
        c.execute('INSERT INTO agent_sandbox_runs VALUES(?,?)',('other',json.dumps(record)))
    campaign={'execution':{'entries':[{'project_id':'p','family_id':'f'}]}}
    result=operations(repo.database,campaign,now=datetime(2026,10,22,12,tzinfo=timezone.utc))
    row=result['sandbox_operations'][0]
    assert len(result['sandbox_operations'])==1 and row['suspected_stall']
    assert row['progress']['processed']==25 and len(row['lifecycle'])==10
    assert 'DO_NOT_EXPOSE' not in json.dumps(result)
    record.update(phase='CAUSALITY_PREFIX',status='COMPLETED')
    with repo.database.connect() as c:c.execute('UPDATE agent_sandbox_runs SET document=? WHERE project_id=?',(json.dumps(record),'p'))
    row=operations(repo.database,campaign)['sandbox_operations'][0]
    assert row['progress']['processed'] is None and not row['suspected_stall']


def test_host_progress_throttles_writes_but_checks_every_callback(monkeypatch):
    from types import SimpleNamespace
    from app.research_agent.sandbox_runs import SandboxRuns
    guards=[];saves=[];ticks=iter([0.,.5,2.1])
    monkeypatch.setattr('app.research_agent.sandbox_runs.time.monotonic',lambda:next(ticks))
    runner=SimpleNamespace(_guard=lambda *a:guards.append(a),_save=lambda item:saves.append(dict(item['progress'])))
    item={'phase':'CANDIDATE'}
    update=SandboxRuns._progress(runner,item,100)
    update(1,100);update(2,100);update('running',3,100)
    assert len(guards)==3 and [x['processed'] for x in saves]==[1,3]
    assert all(x['phase']=='CANDIDATE' for x in saves)
