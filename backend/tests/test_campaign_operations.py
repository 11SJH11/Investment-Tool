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
