from copy import deepcopy
import json
import os

import pytest

from tests.test_research_trials import research
from app.research_agent.candidates import Candidates
from app.research_agent.quarantine import store
from app.research_agent.validation import Validations, Criteria


def test_reference_freezes_actual_baseline_without_fake_numeric_trial(research):
    db,repo,project,_,_,backtest=research
    before=backtest.runs.get(project['baseline_run_id'])
    service=Candidates(db)
    reference=service.freeze_reference(project['id'])
    assert reference==service.freeze_reference(project['id'])
    assert reference['kind']=='CONTROL_REFERENCE' and reference['state']=='REFERENCE'
    assert reference['run_id']==project['baseline_run_id']
    assert reference['snapshot']['configuration']==before['config']
    assert reference['snapshot']['result_digest']==project['analyses'][str(project['baseline_run_id'])]['result_digest']
    service.verify_sandbox_parent(project['id'],reference)
    with db.connect() as c:
        assert c.execute('SELECT count(*) FROM agent_trials').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM agent_candidates').fetchone()[0]==1
    assert backtest.runs.get(project['baseline_run_id'])==before


def test_reference_cannot_consume_holdout(research):
    db,repo,project,_,_,_=research
    reference=Candidates(db).freeze_reference(project['id'])
    held=next(d for d in project['datasets'] if d['state']=='LOCKED_HOLDOUT')
    with pytest.raises(ValueError,match='Frozen candidate required'):
        Validations(db).approve(project['id'],reference['id'],held['id'],Criteria().model_dump())
    assert next(d for d in repo.get(project['id'])['datasets'] if d['id']==held['id'])['state']=='LOCKED_HOLDOUT'


def test_reference_detects_result_and_snapshot_mutation(research):
    db,_,project,_,_,_=research
    service=Candidates(db)
    reference=service.freeze_reference(project['id'])
    altered=deepcopy(reference);altered['snapshot']['configuration']['risk_value']=99
    with pytest.raises(ValueError,match='integrity'):service.verify_sandbox_parent(project['id'],altered)
    with db.connect() as c:
        result=json.loads(c.execute('SELECT result_json FROM backtest_runs WHERE id=?',(reference['run_id'],)).fetchone()[0])
        result['metrics']['untrusted_edit']=1
        c.execute('UPDATE backtest_runs SET result_json=? WHERE id=?',(json.dumps(result),reference['run_id']))
    with pytest.raises(ValueError,match='evidence changed'):service.verify_sandbox_parent(project['id'],reference)


def test_generated_source_on_reference_remains_inert(research,tmp_path):
    db,_,project,_,_,_=research
    reference=Candidates(db).freeze_reference(project['id'])
    sentinel=tmp_path/'must-not-exist'
    draft=store(db,project['id'],reference['id'],dict(request_key='reference-child',registry_key='research_child_reference',
        source=f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\n",
        rationale='Inert adversarial fixture',acknowledgement='Store this source as an inert quarantined draft; no execution or activation'))
    assert draft['state']=='QUARANTINED' and not sentinel.exists()


@pytest.mark.skipif(os.environ.get('LEDGER_TEST_DOCKER')!='1',reason='Opt-in Docker reference acceptance')
def test_reference_parent_runs_exact_docker_control_and_prefix_checks(research):
    from tests.test_sandbox_research_loop import setup,finish
    db,_,project,_,_,backtest=research
    reference=Candidates(db).freeze_reference(project['id'])
    before=backtest.runs.get(reference['run_id'])
    runner,project,reference,draft,request=setup((research,reference))
    try:
        result=finish(runner,runner.approve(project['id'],reference['id'],draft['id'],request))
        assert result['status']=='COMPLETED',result
        assert result['control_parity'] is True and result['causality']['prefix_match']
        assert backtest.runs.get(reference['run_id'])==before
    finally:runner.close()
