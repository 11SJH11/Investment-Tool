from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest
from tests.test_research_trials import research
from tests.test_generated_validation import generated
from app.research_agent.campaign_policy import CampaignPolicy
from app.research_agent.campaign_validation import advance, contract, authorize
from app.research_agent.campaigns import Campaigns
from app.research_agent.director import ResearchDirector
from app.research_agent.validation import Validations
from app.research_agent.repository import ResearchRepository


@pytest.fixture
def automatic(generated):
    runner,project,candidate=generated;db=runner.database;campaigns=Campaigns(db)
    policy=CampaignPolicy(holdout='one_frozen_candidate').model_dump()
    campaign={'id':'campaign','status':'DEVELOPMENT_COMPLETE','request':{'policy':policy},
        'deadline':(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),
        'reserved':{'simulations':4,'compute_minutes':10},
        'execution':{'validation_contract':contract(policy),'entries':[{'reference_project_id':project['id'],
            'frozen_candidate_id':candidate['id'],'frozen_candidate_hash':candidate['snapshot_hash']}]}}
    with db.connect() as c:
        c.execute('INSERT INTO agent_campaigns VALUES (?,?,?)',('campaign','fixture',json.dumps(campaign)))
        p=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project['id'],)).fetchone()[0]);p['campaign_id']='campaign'
        c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(p),project['id']))
        for row in c.execute('SELECT id,document FROM agent_datasets').fetchall():
            d=json.loads(row['document']);d['campaign_id']='campaign'
            c.execute('UPDATE agent_datasets SET document=? WHERE id=?',(json.dumps(d),row['id']))
    director=ResearchDirector(SimpleNamespace(database=db,research_sandbox=runner),start_thread=False)
    yield director,runner,project,candidate
    director.close()


def tick(automatic):
    director,_,_,_=automatic;director.tick();return director.campaigns.get('campaign')


def test_policy_dispatches_exactly_once_and_reconciles_terminal_evidence(automatic):
    director,runner,project,candidate=automatic
    initial=director.campaigns.get('campaign');current=tick(automatic)
    assert current['validation']['status']=='ACTIVE'
    store=Validations(runner.database);grant=store.list(project['id'])[0]
    assert grant['authorization']=='campaign_policy' and grant['criteria']==contract(initial['request']['policy'])['criteria']
    assert current['reserved']['simulations']==initial['reserved']['simulations']+4
    assert tick(automatic)['reserved']==current['reserved']
    # Restart recovery interrupts instead of replaying the paid/exposed experiment.
    runner.recovered=False;runner.recover()
    terminal=tick(automatic)
    assert terminal['validation']['validation_status']=='INTERRUPTED'
    assert not terminal['validation']['automatic_acceptance']
    assert len(store.list(project['id']))==1
    assert ResearchRepository(runner.database).get(project['id'])['datasets'][1]['state']=='INSPECTED_VALIDATION'
    assert tick(automatic)==terminal


@pytest.mark.parametrize('fault',['legacy','human','policy_changed','ambiguous','no_candidate','expired','inspected','budget'])
def test_no_authority_or_ambiguous_selection_leaves_holdout_unconsumed(automatic,fault):
    director,runner,project,_=automatic
    with runner.database.connect() as c:
        campaign=director.campaigns._get(c,'campaign')
        if fault=='legacy':campaign['execution'].pop('validation_contract')
        elif fault=='human':
            campaign['request']['policy']['holdout']='human_approval';campaign['execution']['validation_contract']=None
        elif fault=='policy_changed':campaign['request']['policy']['minimum_trades']=1
        elif fault=='ambiguous':campaign['execution']['entries']*=2
        elif fault=='no_candidate':campaign['execution']['entries']=[]
        elif fault=='expired':campaign['deadline']='2000-01-01T00:00:00+00:00'
        elif fault=='budget':
            campaign['reserved']['simulations']=campaign['request']['policy']['budget']['simulations']
        elif fault=='inspected':
            d=deepcopy(project['datasets'][1]);d.update(state='INSPECTED_VALIDATION',campaign_id='campaign')
            c.execute('UPDATE agent_datasets SET document=? WHERE id=?',(json.dumps(d),d['id']))
        director.campaigns._save(c,campaign)
    result=tick(automatic)
    assert not Validations(runner.database).list(project['id'])
    assert ResearchRepository(runner.database).get(project['id'])['datasets'][1]['state']==('INSPECTED_VALIDATION' if fault=='inspected' else 'LOCKED_HOLDOUT')
    if fault not in {'legacy','human'}:assert result['validation']['status']=='REVIEW_REQUIRED'


def test_reserved_selection_cannot_be_changed_or_manually_bypassed(automatic):
    director,runner,project,candidate=automatic
    runner.thread=SimpleNamespace(is_alive=lambda:True,join=lambda **kw:None)
    reserved=tick(automatic)
    assert reserved['validation']['status']=='RESERVED'
    with pytest.raises(ValueError):authorize(reserved,project['id'],candidate['id'],'different',reserved['validation']['criteria'])
    runner.thread=None
    with pytest.raises(ValueError,match='reserved'):
        runner.approve_validation(project['id'],candidate['id'],project['datasets'][1]['id'],{})
    assert not Validations(runner.database).list(project['id'])
    assert tick(automatic)['validation']['status']=='ACTIVE'
