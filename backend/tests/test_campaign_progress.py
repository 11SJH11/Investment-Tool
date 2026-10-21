from datetime import datetime, timezone
import json

import pytest

from app.research_agent.campaign_progress import baseline_progress
from app.storage.database import Database


@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path/'progress.db')
    db.initialize()
    with db.connect() as c:
        c.execute('''CREATE TABLE backtest_jobs(id TEXT,request_key TEXT,ordinal INTEGER,
            status TEXT,processed INTEGER,total INTEGER,run_id INTEGER,error TEXT,
            created_at TEXT,updated_at TEXT)''')
    return db


def campaign(status='ACTIVE', state='RUNNING'):
    return dict(status=status, execution=dict(entries=[dict(family_id='family', project_id='p', state=state,
                                                          error='baseline_compute_deadline' if state=='FAILED' else None)]))


def job(db, *, key='agent-baseline:p', status='running', processed=25, total=100, updated='2026-10-21 12:00:00'):
    with db.connect() as c:
        c.execute('INSERT INTO backtest_jobs VALUES(?,?,?,?,?,?,?,?,?,?)',
                  ('job',key,0,status,processed,total,None,None,updated,updated))


def report(db, item=None):
    return baseline_progress(db,item or campaign(),now=datetime(2026,10,21,12,5,tzinfo=timezone.utc))


def test_actual_progress_is_not_completed_work(db):
    job(db)
    result = report(db)
    assert result['counts']['running'] == 1 and result['counts']['completed'] == 0
    assert result['jobs'][0]['bar_progress_percent'] == 25
    assert not result['jobs'][0]['suspected_stall']
    assert result['eta_seconds'] is None


def test_failed_terminal_campaign_not_presented_as_success(db):
    job(db,status='cancelled')
    item=campaign('DEVELOPMENT_COMPLETE','FAILED')
    before=json.dumps(item)
    assert report(db,item)['outcome']=='FAILED'
    assert json.dumps(item)==before


def test_stale_progress_is_only_suspected_stall(db):
    job(db,updated='2026-10-21 11:00:00')
    result=report(db)
    assert result['jobs'][0]['suspected_stall']
    assert result['jobs'][0]['status']=='running'


def test_other_campaign_and_holdout_jobs_not_exposed(db):
    job(db,key='agent-baseline:another')
    job(db,key='agent-validation:p:0')
    assert report(db)['jobs']==[]


@pytest.mark.parametrize('processed,total', [(None,100),(20,None),(200,100),(-1,100),(0,0)])
def test_missing_or_invalid_progress_is_indeterminate(db,processed,total):
    job(db,processed=processed,total=total)
    assert report(db)['jobs'][0]['bar_progress_percent'] is None


def test_terminal_jobs_not_reported_as_stalled(db):
    job(db,status='completed',updated='2026-10-20 12:00:00')
    assert not report(db)['jobs'][0]['suspected_stall']


def test_reference_jobs_have_separate_identity(db):
    item=campaign();item['execution']['entries'][0]['reference_project_id']='reference'
    job(db,key='agent-baseline:reference')
    assert report(db,item)['jobs'][0]['role']=='reference'


def test_numeric_current_attempts_are_scoped_and_payloads_not_exposed(db):
    from app.research_agent.trials import request_key
    trial=dict(id='trial',status='ACTIVE',cells=[dict(index=0,role='control',attempt=1,status='RUNNING',
        job_id='job',payload={'secret_fixture':'not public'},result={'holdout_fixture':'not public'}),
        dict(index=1,role='variant',attempt=0,status='PENDING')])
    with db.connect() as c:
        c.execute('CREATE TABLE agent_trials(project_id TEXT,document TEXT)')
        c.execute('INSERT INTO agent_trials VALUES(?,?)',('p',json.dumps(trial)))
        c.execute('INSERT INTO agent_trials VALUES(?,?)',('other',json.dumps(dict(trial,id='other'))))
    job(db,key=request_key(trial,trial['cells'][0]))
    job(db,key='agent-trial:trial:0:0',status='failed')
    job(db,key='agent-trial:other:0:1')
    result=report(db)
    assert len(result['jobs'])==1
    assert result['jobs'][0]['role']=='numeric_control'
    assert result['counts']['running']==1 and result['counts']['failed']==0
    assert len(result['numeric_trials'][0]['cells'])==2
    assert 'secret_fixture' not in json.dumps(result) and 'holdout_fixture' not in json.dumps(result)
    assert len(result['numeric_trials'])==1


def test_numeric_schema_absence_remains_compatible(db):
    assert report(db)['numeric_trials']==[]
