import json
from copy import deepcopy

import pytest

from tests.test_research_campaigns import repo
from app.research_agent.campaign_report import evidence_report
from app.research_agent.repository import ResearchRepository


def fixture(repo,status):
    ResearchRepository(repo.database)
    project={'analyses':{'7':{'summary':{'n':50,'average_r':.2}}}}
    trial=dict(status=status,summary={'n':2,'average_r':10},source_sha256='source',control_parity=True,
               comparison={'removed_large_winners':{'n':3},'introduced':{'n':1}})
    with repo.database.connect() as c:
        c.execute('INSERT INTO agent_projects VALUES (?,?)',('project',json.dumps(project)))
        c.execute('CREATE TABLE agent_sandbox_runs(id TEXT PRIMARY KEY,document TEXT)')
        c.execute('INSERT INTO agent_sandbox_runs VALUES (?,?)',('sandbox',json.dumps(trial)))
    return dict(request={'policy':{'minimum_trades':30}},execution={'entries':[
        dict(project_id='project',family_id='vwap',state='SANDBOX',run_id=7,sandbox_id='sandbox')]})


def test_lucrative_tiny_sample_never_becomes_accepted_and_winner_loss_is_visible(repo):
    campaign=fixture(repo,'COMPLETED')
    before=deepcopy(campaign)
    report=evidence_report(repo.database,campaign)
    family=report['families'][0]
    assert family['verdict']=='ROBUSTNESS_REQUIRED' and family['automatic_acceptance'] is False
    assert any('sample' in w for w in family['warnings'])
    assert any('large parent winners' in w for w in family['warnings'])
    assert family['path']['removed_large_winners']['n']==3
    assert family['baseline_summary']['n']==50 and family['child_summary']['n']==2
    assert campaign==before


@pytest.mark.parametrize('status',['QUEUED','RUNNING','FAILED','INTERRUPTED','CANCELLED'])
def test_pending_checks_are_not_reported_as_failed_or_accepted(repo,status):
    campaign=fixture(repo,status)
    row=evidence_report(repo.database,campaign)['families'][0]
    assert row['verdict']==('CHECK_IN_PROGRESS' if status in {'QUEUED','RUNNING'} else 'CHECK_FAILED')
    assert row['automatic_acceptance'] is False


def test_missing_baseline_is_not_silently_counted_as_zero_trades(repo):
    campaign=fixture(repo,'RUNNING')
    campaign['execution']['entries'][0].pop('run_id')
    row=evidence_report(repo.database,campaign)['families'][0]
    assert row['baseline_summary'] is None
    assert not row['warnings']


def test_bounded_window_results_are_separate_and_zero_costs_warn(repo):
    campaign=fixture(repo,'COMPLETED')
    with repo.database.connect() as c:
        trial=json.loads(c.execute('SELECT document FROM agent_sandbox_runs').fetchone()[0])
        trial['robustness']=dict(status='COMPLETED',zero_cost_stress=True,limitation='Bounded samples only.',
            cells=[dict(window=1,start='2025-01-01',end='2025-01-07',cost_multiplier=2,status='COMPLETED',
                        summary={'n':2,'average_r':10},result={'large_private_raw_result':True})])
        c.execute('UPDATE agent_sandbox_runs SET document=?',(json.dumps(trial),))
    row=evidence_report(repo.database,campaign)['families'][0]
    assert row['robustness']['cells'][0]['summary']['n']==2
    assert 'result' not in row['robustness']['cells'][0]
    assert any('no cost stress' in w for w in row['warnings'])
    assert not any('first development session only' in w for w in row['warnings'])
    assert row['verdict']=='ROBUSTNESS_REQUIRED' and not row['automatic_acceptance']
