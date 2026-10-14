"""Atomic campaign provisioning into the existing research registry.

Every family uses the same dataset IDs for a market/timeframe. Consuming a
holdout therefore consumes it for the whole campaign, including after restart.
This module creates no jobs, loads no performance and grants no holdout access.
"""
import json
from uuid import NAMESPACE_URL, uuid5

from app.backtesting.strategies import strategy_registry
from .analysis import digest
from .campaigns import Campaigns
from .hypotheses import Budget
from .repository import ResearchRepository


def identity(campaign_id, kind, key):
    return str(uuid5(NAMESPACE_URL, 'ledger-campaign:' + campaign_id + ':' + kind + ':' + key))


def reference_project(database, campaign_id, parent_id, *, full_period=False):
    """Predeclare a frozen control reference; legacy campaigns retain one session.

    Membership reuses the campaign's existing datasets/holdout state. Dates are
    fixed by the plan, not selected using trade performance.
    """
    pid = identity(campaign_id, 'control-reference', parent_id)
    with database.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        parent = json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?', (parent_id,)).fetchone()[0])
        if parent.get('campaign_id') != campaign_id:
            raise ValueError('Reference parent belongs to another campaign')
        old = c.execute('SELECT document FROM agent_projects WHERE id=?', (pid,)).fetchone()
        if old:
            if json.loads(old[0]).get('campaign_reference_for') != parent_id:
                raise ValueError('Reference identity changed')
            return pid
        child = {**parent, 'id': pid, 'name': parent['name'] + (' / full-period control' if full_period else ' / bounded control'),
                 'state': 'CREATED', 'baseline_run_id': None, 'analyses': {}, 'lineage': [],
                 'campaign_reference_for': parent_id,
                 'reference_limitation': ('Complete planned development period with declared warmup. Not unseen validation.' if full_period else 'First planned development session only. Control/causality check, not full-period performance.')}
        c.execute('INSERT INTO agent_projects VALUES (?,?)', (pid, json.dumps(child)))
        c.execute('INSERT INTO agent_dataset_memberships SELECT ?,dataset_id FROM agent_dataset_memberships WHERE project_id=?', (pid, parent_id))
    return pid


def provision(database, campaign_id):
    campaigns = Campaigns(database)
    ResearchRepository(database)
    with database.connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS agent_dataset_memberships(project_id TEXT NOT NULL, dataset_id TEXT NOT NULL, PRIMARY KEY(project_id,dataset_id))')
        c.execute('BEGIN IMMEDIATE')
        campaign = campaigns._get(c, campaign_id)
        if campaign['status'] != 'PREPARED':
            raise ValueError('Provisioning requires a prepared campaign')
        if campaign.get('projects'):
            # Never refill deleted projects or recreate consumed holdouts on retry.
            for link in campaign['projects']:
                row = c.execute('SELECT document FROM agent_projects WHERE id=?', (link['project_id'],)).fetchone()
                if not row or json.loads(row[0]).get('campaign_id') != campaign_id:
                    raise ValueError('Campaign project missing or identity changed; no automatic recreation')
                ids = {r[0] for r in c.execute('SELECT dataset_id FROM agent_dataset_memberships WHERE project_id=?', (link['project_id'],))}
                if ids != set(link['dataset_ids']) or any(not c.execute('SELECT 1 FROM agent_datasets WHERE id=?', (d,)).fetchone() for d in ids):
                    raise ValueError('Campaign dataset membership changed; no automatic recreation')
            return campaign['projects']
        policy = campaign['request']['policy']
        frozen = dict(queue=campaign['queue'], plans=campaign['plans'], policy=policy)
        if digest(frozen) != campaign['plan_hash']:
            raise ValueError('Campaign plan integrity failed')
        for entry in campaign['queue']:
            if strategy_registry.provenance(entry['strategy_key']) != entry['source']:
                raise ValueError('Strategy changed after campaign preparation')
        count = len(campaign['queue']) * len(campaign['plans'])
        allowance = policy['budget']
        if allowance['simulations'] < count:
            raise ValueError('Campaign budget cannot fund one baseline per project')
        budget = Budget(max_trial_runs=min(600, allowance['simulations']//count),
                        max_trial_minutes=min(1440, allowance['compute_minutes']//count or 1),
                        max_llm_calls=min(120, allowance['llm_calls']//count),
                        max_llm_spend_usd=allowance['llm_usd']/count,
                        max_hypotheses=min(100, max(1, allowance['hypotheses']//count))).model_dump()
        records = []
        links = []
        for key, plan in campaign['plans'].items():
            if digest({k:v for k,v in plan.items() if k != 'plan_hash'}) != plan['plan_hash']:
                raise ValueError('Dataset plan integrity failed')
            owner = identity(campaign_id, 'project', campaign['queue'][0]['family_id'] + ':' + key)
            datasets = []
            for index, proposal in enumerate(plan['dataset_proposal']):
                record = {**proposal, 'id': identity(campaign_id, 'dataset', key + ':' + str(index)),
                          'project_id': owner, 'campaign_id': campaign_id,
                          'plan_hash': plan['plan_hash']}
                records.append(record)
                datasets.append(record['id'])
            for entry in campaign['queue']:
                pid = identity(campaign_id, 'project', entry['family_id'] + ':' + key)
                link = dict(project_id=pid, family_id=entry['family_id'], plan_key=key, dataset_ids=datasets)
                links.append(link)
                project = dict(id=pid, name=(campaign['request']['prompt'] or 'Research campaign')[:80] + ' / ' + key,
                               strategy_key=entry['strategy_key'], state='CREATED', mode='READ_ONLY',
                               research_budget=budget, strategy_provenance=entry['source'],
                               baseline_run_id=None, analyses={}, lineage=[], campaign_id=campaign_id,
                               campaign_family_id=entry['family_id'], campaign_plan_hash=campaign['plan_hash'])
                if campaign.get('discovery', {}).get('version') in {'cached_discovery_v1','provider_cache_discovery_v1'}:
                    from .access import family
                    coverage = plan['coverage']
                    project['provider_bindings'] = {family(coverage['symbol']) + ':' + coverage['timeframe']: coverage['provider_namespace']}
                c.execute('INSERT INTO agent_projects VALUES (?,?)', (pid, json.dumps(project)))
                c.executemany('INSERT INTO agent_dataset_memberships VALUES (?,?)', [(pid, d) for d in datasets])
                c.execute('INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)',
                          (pid, 'campaign_project_created', json.dumps(link)))
        # Recheck exposure in the same write transaction as registration. A run or
        # another project created after planning must not silently become unseen.
        existing = [json.loads(r[0]) for r in c.execute('SELECT document FROM agent_datasets')]
        saved = [dict(symbols=json.loads(r['symbols']), start=r['start_date'], end=r['end_date'])
                 for r in c.execute('SELECT symbols,start_date,end_date FROM backtest_runs')]
        for d in records:
            for old in existing:
                if ResearchRepository.overlap(d, old) and (d['state'] == 'LOCKED_HOLDOUT' or old['state'] in {'LOCKED_HOLDOUT', 'FUTURE_OOS'}):
                    raise ValueError('Dataset exposure changed since planning; fixed split cannot be registered')
            if d['state'] == 'LOCKED_HOLDOUT' and any(ResearchRepository.overlap(d, r) for r in saved):
                raise ValueError('Holdout inspected since planning; fixed split cannot be registered')
            existing.append(d)
        c.executemany('INSERT INTO agent_datasets VALUES (?,?)', [(d['id'], json.dumps(d)) for d in records])
        campaign['projects'] = links
        campaigns._save(c, campaign)
        campaigns._event(c, campaign_id, 'PROJECTS_PROVISIONED', {'projects': links})
    return links
