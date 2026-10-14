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
                  timeout_seconds=min(21600 if entry.get('full_period') else 600,entry['max_minutes']*60),acknowledgement=ACK,
                  full_period=entry.get('full_period',False),
                  full_robustness_windows=entry.get('full_robustness_windows',False),
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
        attempt=len(entry.get('structural_attempts',[]))
        key='campaign-structural-v1' if attempt==0 else 'campaign-structural-v1-'+str(attempt)
        result=author.start(pid,dict(request_key=key,consent=CONSENT),campaign_id=campaign['id'])
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
            timeout_seconds=min(21600 if entry.get('full_period') else 600,entry['max_minutes']*60),acknowledgement=ACK,
            full_period=entry.get('full_period',False),
            full_robustness_windows=entry.get('full_robustness_windows',False),
            windows=entry.get('robustness_windows',[])))
        entry['sandbox_id']=result['id']
        director._save(campaign,'STRUCTURAL_DOCKER_DISPATCHED')
    if result['status'] not in {'QUEUED','RUNNING'}:
        from .research_verdict import assess
        decision=assess(result,campaign['request']['policy'])
        attempt=dict(author_id=entry['author_id'],draft_id=entry['draft_id'],sandbox_id=entry['sandbox_id'],
                     source_sha256=result.get('source_sha256'),summary=result.get('summary'),decision=decision)
        attempts=entry.setdefault('structural_attempts',[])
        if not any(a['sandbox_id']==attempt['sandbox_id'] for a in attempts):attempts.append(attempt)
        entry['research_decision']=decision
        retry=(result['status']=='COMPLETED' and decision['verdict'] in {'REJECTED_DEVELOPMENT','INSUFFICIENT_EVIDENCE'}
               and len(attempts)<min(entry.get('structural_cycles',1),campaign['request']['policy']['max_failed_hypotheses_per_family'])
               and campaign['status']=='ACTIVE')
        if retry:
            entry.update(state='AUTHOR')
            for field in ('author_id','draft_id','sandbox_id'):entry.pop(field,None)
            director._save(campaign,'STRUCTURAL_NEXT_HYPOTHESIS')
            return
        if decision['verdict']=='PROMISING_DEVELOPMENT' and entry.get('full_robustness_windows'):
            from .structural_candidates import freeze
            frozen=freeze(director.database,campaign['id'],pid,entry['sandbox_id'])
            entry['frozen_candidate_id']=frozen['id']
            entry['frozen_candidate_hash']=frozen['snapshot_hash']
        entry.update(state='COMPLETED' if result['status']=='COMPLETED' else 'RESEARCH_STOPPED',
                     family_outcome=('FROZEN_REQUIRES_VALIDATION' if entry.get('frozen_candidate_id') else 'REQUIRES_VALIDATION') if decision['verdict']=='PROMISING_DEVELOPMENT' else 'STOPPED_WITHOUT_ACCEPTANCE',
                     structural_result=dict(status=result['status'],control_parity=result.get('control_parity'),
                        causality=result.get('causality'),error=result.get('error'),summary=result.get('summary'),
                        robustness_status=result.get('robustness',{}).get('status'),
                        limitation=('Full development-period evaluation with warmup; cost-check scope is recorded separately. No unseen validation or deployment authority.' if entry.get('full_period') else 'Bounded development checks only; no full-period, portfolio or unseen profitability claim.')))
        director._save(campaign,'STRUCTURAL_CHECK_FINISHED')
