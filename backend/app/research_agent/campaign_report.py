"""Read-only morning report. No ranking, unseen-data access or LLM arithmetic."""
import json


def evidence_report(database,campaign):
    rows=[]
    with database.connect() as c:
        for entry in campaign.get('execution',{}).get('entries',[]):
            project_row=c.execute('SELECT document FROM agent_projects WHERE id=?',(entry['project_id'],)).fetchone()
            project=json.loads(project_row[0]) if project_row else {}
            baseline=project.get('analyses',{}).get(str(entry.get('run_id')), {})
            item=dict(family_id=entry['family_id'],project_id=entry['project_id'],state=entry['state'],
                      baseline_run_id=entry.get('run_id'),baseline_summary=baseline.get('summary'),
                      numeric_cycles=entry.get('completed_cycles',0),reason=entry.get('error') or entry.get('reason'),
                      verdict='DEVELOPMENT_ONLY',warnings=[],automatic_acceptance=False)
            item['research_decision']=entry.get('research_decision')
            item['structural_attempts']=entry.get('structural_attempts',[])
            item['family_outcome']=entry.get('family_outcome')
            if baseline.get('summary') and baseline['summary']['n']<campaign['request']['policy']['minimum_trades']:
                item['warnings'].append('Baseline sample is below the campaign minimum.')
            if entry.get('sandbox_id'):
                row=c.execute('SELECT document FROM agent_sandbox_runs WHERE id=?',(entry['sandbox_id'],)).fetchone()
                trial=json.loads(row[0]) if row else {}
                comparison=trial.get('comparison',{})
                item.update(sandbox_id=entry['sandbox_id'],reference_run_id=entry.get('reference_run_id'),
                            child_summary=trial.get('summary'),control_parity=trial.get('control_parity'),
                            prefix_causality=trial.get('causality'),source_sha256=trial.get('source_sha256'),
                            path={k:comparison.get(k) for k in ('retained','removed','introduced','removed_large_winners','removed_session_close_winners')})
                robustness=trial.get('robustness',{})
                item['robustness']={k:v for k,v in robustness.items() if k!='cells'}
                item['robustness']['cells']=[{k:v for k,v in cell.items() if k in
                    {'window','start','end','cost_multiplier','status','summary','control_parity','prefix_signals_checked','data_fingerprint','result_sha256'}}
                    for cell in robustness.get('cells',[])]
                if trial.get('status')=='COMPLETED':
                    item['verdict']='ROBUSTNESS_REQUIRED'
                    if robustness.get('status')=='COMPLETED':
                        item['warnings'].append(robustness['limitation'])
                        if robustness.get('zero_cost_stress'):
                            item['warnings'].append('Configured costs are zero; doubling them provides no cost stress.')
                        if any(cell.get('summary',{}).get('n',0)<campaign['request']['policy']['minimum_trades'] for cell in robustness.get('cells',[])):
                            item['warnings'].append('At least one development sample is below the campaign minimum; no acceptance.')
                    else:
                        item['warnings'].append('Child was checked on the first development session only. No full-period or out-of-sample performance claim.')
                    if trial.get('summary',{}).get('n',0)<campaign['request']['policy']['minimum_trades']:
                        item['warnings'].append('Child sample is below the campaign minimum; no acceptance.')
                    if comparison.get('removed_large_winners',{}).get('n',0):
                        item['warnings'].append('Child removes large parent winners. Inspect retention before further research.')
                elif trial.get('status') in {'QUEUED','RUNNING'}:
                    item['verdict']='CHECK_IN_PROGRESS'
                else:
                    item.update(verdict='CHECK_FAILED',reason=trial.get('error') or trial.get('status') or 'Missing sandbox evidence')
            rows.append(item)
    return dict(version='campaign_morning_report_v1',families=rows,
                conclusions=['Development results do not establish an edge. No strategy has been automatically accepted or deployed.',
                             'Independent strategy returns are not combined into a portfolio.',
                             'Generated children still require preregistered multi-period robustness, cost reruns and candidate-bound holdout approval.'])
