import json
import pytest
from tests.test_research_trials import research, terminal
from tests.test_research_committee import FakeModel
from tests.test_backtest_jobs import wait_for
from app.research_agent.trials import Trials
from app.research_agent.committee import Committee


def completed(research):
    db,repo,project,hypothesis,jobs,service = research
    trials=Trials(db); trial=trials.approve(project['id'],hypothesis['id'])
    wait_for(lambda:terminal(trials,trial['id']))
    assert trials.get(trial['id'])['status']=='COMPLETED'
    return trials.get(trial['id'])


def test_feedback_includes_all_cells_path_changes_and_no_raw_records(research):
    trial=completed(research);db,_,project,hypothesis,_,_=research
    model=FakeModel(hypothesis);review=Committee(db,model).review(project['id'],'feedback')
    assert review['status']=='COMPLETED',review
    evidence=review['evidence']; feedback=evidence['evidence']['trial/'+trial['id']]
    assert len(feedback['cells'])==3 and feedback['control_parity']
    assert feedback['cells'][2]['removed']['n']>0
    assert feedback['cells'][2]['summary']['n']==0
    assert evidence['trial_evidence_coverage']['included_trials']==1
    assert 'removed_trades' not in json.dumps(evidence) and '2027-01-01' not in json.dumps(evidence)
    assert all('trial/'+trial['id'] in call[1]['evidence'] for call in model.calls)


def test_feedback_rejects_changed_saved_result_before_model_call(research):
    trial=completed(research);db,_,project,hypothesis,_,_=research
    with db.connect() as c:
        run_id=trial['cells'][1]['run_id'];row=c.execute('SELECT result_json FROM backtest_runs WHERE id=?',(run_id,)).fetchone()
        result=json.loads(row[0]);result['metrics']['tampered']=True
        c.execute('UPDATE backtest_runs SET result_json=? WHERE id=?',(json.dumps(result),run_id))
    model=FakeModel(hypothesis)
    with pytest.raises(ValueError,match='results changed'):Committee(db,model).review(project['id'],'tampered')
    assert not model.calls


def test_feedback_rejects_holdout_reference_before_model_call(research):
    trial=completed(research);db,_,project,hypothesis,_,_=research
    with db.connect() as c:
        run_id=trial['cells'][1]['run_id'];row=c.execute('SELECT config_json FROM backtest_runs WHERE id=?',(run_id,)).fetchone()
        config=json.loads(row[0]);config['start_date']='2027-01-01'
        c.execute('UPDATE backtest_runs SET config_json=? WHERE id=?',(json.dumps(config),run_id))
    model=FakeModel(hypothesis)
    with pytest.raises(ValueError,match='scope changed'):Committee(db,model).review(project['id'],'held')
    assert not model.calls
