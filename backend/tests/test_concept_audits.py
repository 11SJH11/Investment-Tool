from copy import deepcopy
import json
from types import SimpleNamespace
import pandas as pd
import pytest
from app.market_concepts import registry
from app.market_concepts.base import ConceptRequest, Observation
from app.market_concepts.registry import Definition
from app.market_concepts.builtins import NoParams
from app.market_concepts.benchmark import benchmark
from app.research_agent.concept_audits import ConceptAudits, committee_evidence
from tests.test_market_concepts import bars
from tests.test_research_trials import research


def request(key='audit-fixture'):
    return dict(request_key=key,concept={'key':'swing.strict.v1','timeframe':'1m'},horizon_bars=2,acknowledgement='Audit this concept on verified development data; follow-up metrics are research only')


def test_swing_audit_followup_excludes_confirmation_bar_and_censors_tail():
    result=benchmark(ConceptRequest(key='swing.strict.v1'),bars(),'TEST',2)
    assert result['causality']['status']=='PASS'
    assert result['observation_count']==2
    assert result['confirmation_lag_seconds']['mean']==180
    assert result['followup']['complete_observations']==1
    assert result['followup']['right_censored_observations']==1
    assert result['followup']['upward_bps']['mean']==0
    assert result['followup']['downward_bps']['mean']==-5000
    assert result==benchmark(ConceptRequest(key='swing.strict.v1'),bars(),'TEST',2)
    for example in result['examples']:
        for line in example['overlays']:
            assert all(pd.Timestamp(p['timestamp'])>=pd.Timestamp(example['observation']['confirmed_at']) for p in line['values'])


def test_zone_touch_is_after_confirmation_and_not_an_inferred_fill():
    result=benchmark(ConceptRequest(key='fvg.three_candle.v1'),bars(),'TEST',2)
    first=next(x for x in result['examples'] if x['observation']['occurred_at'].startswith('2026-01-02T14:32'))
    assert first['followup']['first_touch_bars']==1
    assert result['followup']['complete_zones']>=1
    assert 'no inferred fill' in result['limitations'][2]


def test_series_has_no_trade_followup_and_htf_uses_explicit_completion():
    frame=bars();frame['available_at']=frame.timestamp+pd.Timedelta(minutes=15)
    result=benchmark(ConceptRequest(key='session_vwap.new_york.v1',timeframe='15m'),frame,'TEST',2)
    assert result['causality']['status']=='PASS'
    assert result['confirmation_lag_seconds']['mean']==900
    assert result['followup']['complete_observations']==0


def test_retrospective_detector_is_flagged_without_maturity_change(monkeypatch):
    def retrospective(frame,params,dependencies):
        if frame.empty:return []
        row=frame.iloc[0]
        return [Observation(kind='point',label='Future length '+str(len(frame)),occurred_at=row.timestamp,confirmed_at=row.available_at,value=1)]
    key='test.retrospective.v1'
    monkeypatch.setitem(registry.items,key,Definition(key,'Broken fixture',retrospective,NoParams))
    result=benchmark(ConceptRequest(key=key),bars(),'TEST',2)
    assert result['causality']['status']=='FAIL' and registry.items[key].status=='EXPERIMENTAL'


@pytest.fixture
def prepared(research):
    db,repo,project,_,_,service=research
    # Fixture's prepare requires baseline queue authorization; real prepare takes the saved config.
    backtest=SimpleNamespace(prepare=lambda payload:service.prepare(repo.get(project['id'])['baseline_payload']))
    return research,backtest


def test_audit_is_persisted_idempotent_and_does_not_enqueue_or_unlock(prepared):
    (db,repo,project,_,jobs,_),service=prepared;audits=ConceptAudits(db);before=len(jobs.list())
    result=audits.run(project['id'],request(),service)
    assert result['status']=='COMPLETED',result
    assert result['report']['causality']['status']=='PASS'
    assert audits.run(project['id'],request(),SimpleNamespace(prepare=lambda _:pytest.fail('Duplicate preparation'))) == result
    assert len(jobs.list())==before and repo.get(project['id'])['datasets'][1]['state']=='LOCKED_HOLDOUT'
    altered=request();altered['horizon_bars']=3
    with pytest.raises(ValueError,match='immutable'):audits.run(project['id'],altered,service)
    evidence=committee_evidence(db,repo.get(project['id']))
    assert 'concept_audit/'+result['id'] in evidence
    assert 'examples' not in evidence['concept_audit/'+result['id']]


def test_changed_data_fails_without_publishing_report(prepared):
    research,service=prepared;db,_,project,_,_,original=research;original.changed=True
    result=ConceptAudits(db).run(project['id'],request(),service)
    assert result['status']=='FAILED' and 'report' not in result
    assert result['error']=='Prepared development data changed'


def test_audit_scope_failure_and_safe_provider_errors(prepared):
    (db,repo,project,_,_,_),service=prepared
    def fail(_):raise RuntimeError('secret-token-must-not-escape')
    result=ConceptAudits(db).run(project['id'],request(),SimpleNamespace(prepare=fail))
    assert result['status']=='FAILED' and 'secret-token' not in json.dumps(result)
    repo.transition(project['id'],'PAUSED')
    with pytest.raises(ValueError,match='active verified'):ConceptAudits(db).run(project['id'],request('paused'),service)


def test_audit_api_requires_explicit_acknowledgement(prepared):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.research_agent import router
    (db,_,project,_,_,_),service=prepared
    app=FastAPI();app.state.services=SimpleNamespace(database=db,backtest=service);app.include_router(router)
    path='/strategy-lab/research-agent/'+project['id']+'/concept-audits'
    with TestClient(app) as client:
        payload=request();payload.pop('acknowledgement')
        assert client.post(path,json=payload).status_code==422
        response=client.post(path,json=request());assert response.status_code==200
        assert response.json()['status']=='COMPLETED'
        assert len(client.get(path).json()['items'])==1


def test_tampered_audit_is_not_sent_to_committee(prepared):
    (db,repo,project,_,_,_),service=prepared
    result=ConceptAudits(db).run(project['id'],request(),service);assert result['status']=='COMPLETED'
    result['report']['observation_count']=999
    with db.connect() as c:c.execute('UPDATE agent_concept_audits SET document=?',(json.dumps(result),))
    with pytest.raises(ValueError,match='evidence changed'):committee_evidence(db,repo.get(project['id']))


def test_attempt_limit_counts_failures_and_prevents_more_preparation(prepared):
    (db,_,project,_,_,_),service=prepared
    audits=ConceptAudits(db)
    def fail(_):raise RuntimeError('provider unavailable')
    for i in range(12):
        assert audits.run(project['id'],request(str(i)),SimpleNamespace(prepare=fail))['status']=='FAILED'
    with pytest.raises(ValueError,match='12 attempts'):
        audits.run(project['id'],request('thirteenth'),service)


def test_unprepared_timeframe_fails_without_fetching_extra_data(prepared):
    (db,_,project,_,_,_),service=prepared
    payload=request();payload['concept']['timeframe']='4h'
    result=ConceptAudits(db).run(project['id'],payload,service)
    assert result['status']=='FAILED' and 'report' not in result
    assert result['error']=='Requested concept timeframe was not prepared by the baseline'


def test_interrupted_audit_is_not_retried(prepared):
    (db,_,project,_,_,_),service=prepared
    audits=ConceptAudits(db);result=audits.run(project['id'],request(),service)
    result.update(status='RUNNING',deadline='2000-01-01T00:00:00+00:00')
    result.pop('report',None);result.pop('report_hash',None)
    with db.connect() as c:c.execute('UPDATE agent_concept_audits SET document=?',(json.dumps(result),))
    restored=audits.run(project['id'],request(),SimpleNamespace(prepare=lambda _:pytest.fail('Must not retry')))
    assert restored['status']=='INTERRUPTED' and 'report' not in restored


def test_benchmark_bounds_reject_empty_and_excessive_input():
    for frame in (bars().iloc[:0],pd.concat([bars()]*300,ignore_index=True)):
        with pytest.raises(ValueError):benchmark(ConceptRequest(key='swing.strict.v1'),frame,'TEST',2)


def test_multiple_series_do_not_mix_values_or_duplicate_chart_timestamps(monkeypatch):
    def two_series(frame,params,dependencies):
        return [Observation(kind='series',label=label,occurred_at=row.timestamp,confirmed_at=row.available_at,value=value)
                for _,row in frame.iterrows() for label,value in [('upper',20),('lower',10)]]
    key='test.bands.v1'
    monkeypatch.setitem(registry.items,key,Definition(key,'Bands fixture',two_series,NoParams))
    result=benchmark(ConceptRequest(key=key),bars(),'TEST',2)
    for example in result['examples']:
        values=example['overlays'][0]['values']
        assert len({v['timestamp'] for v in values})==len(values)
        assert {v['value'] for v in values}==({20} if example['observation']['label']=='upper' else {10})


def test_pause_during_preparation_prevents_publishing_evidence(prepared):
    (db,repo,project,_,_,_),service=prepared
    def prepare(payload):
        inputs=service.prepare(payload)
        repo.transition(project['id'],'PAUSED')
        return inputs
    result=ConceptAudits(db).run(project['id'],request(),SimpleNamespace(prepare=prepare))
    assert result['status']=='FAILED' and 'report' not in result
