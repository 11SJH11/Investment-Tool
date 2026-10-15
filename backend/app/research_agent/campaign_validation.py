"""One policy-authorized generated validation, with durable selection before dispatch."""
from datetime import datetime, timezone
import json

from .analysis import digest
from .validation import Criteria, Validations


def contract(policy):
    if policy.get('holdout')!='one_frozen_candidate':return None
    return {'version':'one_generated_validation_v1','policy_sha256':digest(policy),
            'criteria':Criteria(minimum_trades=policy['minimum_trades']).model_dump()}


def authorize(campaign, project_id, candidate_id, dataset_id, criteria):
    frozen=campaign.get('execution',{}).get('validation_contract')
    selected=campaign.get('validation',{})
    if (not frozen or frozen!=contract(campaign['request']['policy']) or
        selected.get('status')!='RESERVED' or selected.get('project_id')!=project_id or
        selected.get('candidate_id')!=candidate_id or selected.get('dataset_id')!=dataset_id or
        criteria!=frozen['criteria'] or selected.get('criteria')!=criteria):
        raise ValueError('Campaign validation is outside frozen authority')


def advance(director, item):
    database=director.database
    if not item.get('execution',{}).get('validation_contract'):return  # Legacy executions gain no authority.
    runner=getattr(director.services,'research_sandbox',None)
    if not runner:return
    # Selection is committed before any provider/Docker call. A restart resumes
    # this exact selection and the existing candidate-bound grant, never another.
    with database.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        campaign=director.campaigns._get(c,item['id'])
        if campaign['status']!='DEVELOPMENT_COMPLETE':return
        selected=campaign.get('validation')
        if selected and selected['status'] not in {'RESERVED','ACTIVE'}:return
        if not selected:
            reason=None
            frozen=campaign['execution']['validation_contract']
            if frozen!=contract(campaign['request']['policy']):reason='frozen_validation_policy_changed'
            elif not campaign.get('deadline') or director.clock()>=datetime.fromisoformat(campaign['deadline']):reason='campaign_validation_deadline_expired'
            eligible=[e for e in campaign['execution']['entries'] if e.get('frozen_candidate_id')]
            if not reason and len(eligible)!=1:reason='exactly_one_frozen_candidate_required'
            if not reason:
                entry=eligible[0];pid=entry['reference_project_id'];cid=entry['frozen_candidate_id']
                row=c.execute('SELECT document FROM agent_candidates WHERE id=? AND project_id=?',(cid,pid)).fetchone()
                candidate=json.loads(row[0]) if row else {}
                if candidate.get('snapshot_hash')!=entry['frozen_candidate_hash']:reason='frozen_candidate_identity_changed'
            if not reason:
                from .repository import dataset_ids
                accessible=dataset_ids(c,pid)
                config=candidate['snapshot']['configuration']
                datasets=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_datasets')]
                eligible_data=[d for d in datasets if d['id'] in accessible and d.get('campaign_id')==campaign['id'] and
                    d['state'] in {'LOCKED_HOLDOUT','FUTURE_OOS'} and d['timeframe']==config['primary_timeframe'] and set(d['symbols'])==set(config['symbols'])]
                if len(eligible_data)!=1:reason='exactly_one_untouched_validation_dataset_required'
            if not reason and c.execute("SELECT 1 FROM sqlite_master WHERE name='agent_validations'").fetchone():
                grants=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_validations')]
                if any(g.get('campaign_id')==campaign['id'] or g.get('dataset_id') in {d['id'] for d in datasets if d.get('campaign_id')==campaign['id']} for g in grants):
                    reason='campaign_validation_already_consumed'
            if reason:
                selected={'status':'REVIEW_REQUIRED','reason':reason}
            else:
                selected={'status':'RESERVED','project_id':pid,'candidate_id':cid,'candidate_hash':candidate['snapshot_hash'],
                          'dataset_id':eligible_data[0]['id'],'criteria':frozen['criteria']}
            campaign['validation']=selected
            director.campaigns._save(c,campaign)
            director.campaigns._event(c,campaign['id'],'VALIDATION_SELECTION',selected)
    if selected['status'] not in {'RESERVED','ACTIVE'}:return
    try:
        store=Validations(database)
        grant=next((v for v in store.list(selected['project_id']) if v['candidate_id']==selected['candidate_id']),None)
        if grant is None:
            if runner.thread and runner.thread.is_alive():return
            grant=runner.approve_validation(selected['project_id'],selected['candidate_id'],selected['dataset_id'],
                                           selected['criteria'],campaign_dispatch=True)
        if (grant.get('authorization')!='campaign_policy' or grant['candidate_hash']!=selected['candidate_hash'] or
            grant['dataset_id']!=selected['dataset_id'] or grant['criteria']!=selected['criteria']):
            raise ValueError('Validation grant differs from reserved campaign selection')
        update={'status':'ACTIVE' if grant['status']=='ACTIVE' else 'COMPLETED',
                'validation_id':grant['id'],'validation_status':grant['status'],'verdict':grant['verdict'],
                'automatic_acceptance':False}
    except Exception:
        update={'status':'REVIEW_REQUIRED','reason':'isolated_validation_dispatch_failed_no_automatic_retry'}
    with database.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        campaign=director.campaigns._get(c,item['id'])
        current=campaign.get('validation',{})
        if campaign['status']!='DEVELOPMENT_COMPLETE' or current!=selected:return
        campaign['validation']={**selected,**update}
        director.campaigns._save(c,campaign)
        if campaign['validation']!=selected:
            director.campaigns._event(c,campaign['id'],'VALIDATION_PROGRESS',campaign['validation'])
