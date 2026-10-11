"""Director progression using existing baseline, author and Docker services."""
from . import workflow
from .author import CONSENT
from .candidates import Candidates
from .repository import ResearchRepository
from .sandbox_runs import ACK, Approval


def sandbox_authorized(database,project,candidate_id,draft_id,request):
    from .campaigns import Campaigns
    from .director import permitted
    campaign=Campaigns(database).get(project['campaign_id'])
    entry=next((e for e in campaign.get('execution',{}).get('entries',[]) if e.get('reference_project_id')==project['id']),None)
    if not entry or entry['state']!='SANDBOX' or not permitted(database,project['id']):
        raise ValueError('Campaign sandbox authorization is inactive')
    parameters=dict(entry['payload'].get('strategy_params',{}))
    expected=dict(control_parameters={**parameters,'research_feature_enabled':False},
                  candidate_parameters={**parameters,'research_feature_enabled':True},
                  timeout_seconds=min(600,entry['max_minutes']*60),acknowledgement=ACK,
                  windows=entry.get('robustness_windows',[]))
    expected=Approval.model_validate(expected).model_dump(mode='json')
    if candidate_id!=entry['reference_id'] or draft_id!=entry['draft_id'] or request!=expected:
        raise ValueError('Sandbox request differs from frozen campaign authorization')


def advance(director, campaign, entry):
    services=director.services
    pid=entry['reference_project_id']
    if entry['state']=='REFERENCE':
        project=ResearchRepository(director.database).get(pid)
        if project['state'] in {'CREATED','BASELINE_PENDING'}:
            project=workflow.start(services,pid,entry['reference_payload'],campaign_dispatch=True)
        else:
            project=workflow.observe(services,pid)
        if project['state']=='BASELINE_ANALYSIS':
            reference=Candidates(director.database).freeze_reference(pid)
            entry.update(state='AUTHOR',reference_id=reference['id'],reference_run_id=reference['run_id'])
            director._save(campaign,'STRUCTURAL_REFERENCE_FROZEN')
        elif project['state'] not in {'BASELINE_PENDING','BASELINE_RUNNING'}:
            entry.update(state='FAILED',error='structural_reference_failed')
            director._save(campaign,'STRUCTURAL_FAILED')
        return
    if entry['state']=='AUTHOR':
        author=services.research_author
        if author.thread and author.thread.is_alive():
            return
        result=author.start(pid,dict(request_key='campaign-structural-v1',consent=CONSENT),campaign_id=campaign['id'])
        if result['status']=='COMPLETED':
            entry.update(state='SANDBOX',author_id=result['id'],draft_id=result['draft_id'])
            director._save(campaign,'STRUCTURAL_SOURCE_QUARANTINED')
        elif result['status']!='RUNNING':
            entry.update(state='RESEARCH_STOPPED',author_id=result['id'],reason=result.get('error') or 'structural_proposal_rejected')
            director._save(campaign,'STRUCTURAL_STOPPED')
        return
    runner=services.research_sandbox
    if entry.get('sandbox_id'):
        result=runner.get(entry['sandbox_id'])
    else:
        if runner.thread and runner.thread.is_alive():
            return
        parameters=dict(entry['payload'].get('strategy_params',{}))
        result=runner.approve(pid,entry['reference_id'],entry['draft_id'],dict(
            control_parameters={**parameters,'research_feature_enabled':False},
            candidate_parameters={**parameters,'research_feature_enabled':True},
            timeout_seconds=min(600,entry['max_minutes']*60),acknowledgement=ACK,
            windows=entry.get('robustness_windows',[])))
        entry['sandbox_id']=result['id']
        director._save(campaign,'STRUCTURAL_DOCKER_DISPATCHED')
    if result['status'] not in {'QUEUED','RUNNING'}:
        entry.update(state='COMPLETED' if result['status']=='COMPLETED' else 'RESEARCH_STOPPED',
                     structural_result=dict(status=result['status'],control_parity=result.get('control_parity'),
                        causality=result.get('causality'),error=result.get('error'),summary=result.get('summary'),
                        robustness_status=result.get('robustness',{}).get('status'),
                        limitation='Bounded development checks only; no full-period, portfolio or unseen profitability claim.'))
        director._save(campaign,'STRUCTURAL_CHECK_FINISHED')
