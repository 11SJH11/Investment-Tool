"""Campaign-owned history ingestion through the existing durable cache warmer.

Fixed bounds precede provider calls. Only timestamp evidence enters planning;
downloaded prices remain in the canonical market store, never model context.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.data.instruments import instrument_spec
from .campaigns import Campaigns, utcnow
from .dataset_planner import known_exposure
from .discovery import campaign_coverage, required_timeframes, queue


def require(database, identifier, timeframe, *, now=None):
    now = now or utcnow()
    item = Campaigns(database).get(identifier)
    prep = item.get('preparation')
    if item['status'] != 'PREPARING' or not prep or timeframe not in prep['timeframes']:
        raise ValueError('Campaign history preparation is not authorized')
    if now >= datetime.fromisoformat(prep['deadline']):
        raise ValueError('Campaign preparation deadline expired')
    for symbol in prep['symbols']:
        for exposure in known_exposure(database, symbol):
            if (exposure['kind'] in {'LOCKED_HOLDOUT', 'FUTURE_OOS', 'INSPECTED_VALIDATION'}
                    and exposure['start'] < prep['end_date'] and prep['start_date'] <= exposure['end']):
                raise ValueError('Campaign history request overlaps protected or consumed validation data')
    return prep


def start(services, identifier, lookback_days=1460):
    if type(lookback_days) is not int or not 1 <= lookback_days <= 3650:
        raise ValueError('History lookback must be 1 to 3650 calendar days')
    repo = Campaigns(services.database)
    item = repo.get(identifier)
    if item.get('preparation'):
        if item['preparation']['lookback_days'] != lookback_days:
            raise ValueError('Preparation bounds are immutable')
        return item
    if item['status'] != 'DRAFT':
        raise ValueError('Only a draft campaign can request history preparation')
    if services.market_data is None or getattr(services, 'market_warmup', None) is None:
        raise ValueError('Market-data warming service unavailable')
    rejected=[]
    entries = queue(item['request'],rejections=rejected)
    policy = item['request']['policy']
    if any(instrument_spec(s).session_profile not in {'us_equity','oanda_24h'} for s in policy['symbols']):
        raise ValueError('Automatic preparation requires supported equity or spot-metal identity')
    timeframes = required_timeframes(entries, policy['timeframes'])
    if any(t not in {'1m','5m','15m','30m','1h','4h','1d'} for t in timeframes):
        raise ValueError('Automatic history preparation requires supported bars')
    clock = repo.clock()
    end_date = min(clock.date(), clock.astimezone(ZoneInfo('America/New_York')).date())
    start_date = end_date-timedelta(days=lookback_days)
    namespaces = {s: services.market_data.provider_for(s).cache_namespace for s in policy['symbols']}
    minutes = min(30, policy['budget']['wall_minutes'], policy['budget']['compute_minutes'])
    if minutes >= policy['budget']['compute_minutes']:
        raise ValueError('Leave compute budget for research after history preparation')
    with services.database.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        current = repo._get(c, identifier)
        if current != item:
            raise ValueError('Campaign changed during preparation authorization; retry')
        current.update(status='PREPARING', started_at=clock.isoformat(),
                       deadline=(clock+timedelta(minutes=policy['budget']['wall_minutes'])).isoformat())
        current['reserved']['compute_minutes'] += minutes
        current['preparation'] = dict(version='campaign_history_v1', lookback_days=lookback_days,
            symbols=policy['symbols'], timeframes=timeframes, namespaces=namespaces,rejected_families=rejected,
            start_date=start_date.isoformat(), end_date=end_date.isoformat(), entries=entries,
            start=datetime.combine(start_date,time.min,tzinfo=ZoneInfo('America/New_York')).isoformat(),
            end=datetime.combine(end_date,time.min,tzinfo=ZoneInfo('America/New_York')).isoformat(),
            deadline=(clock+timedelta(minutes=minutes)).isoformat(), jobs={}, retries={}, status='AUTHORIZED')
        repo._save(c,current)
        repo._event(c,identifier,'HISTORY_PREPARATION_AUTHORIZED',current['preparation'])
    # Authorization is durable before any job submission. Director reconciles it.
    if getattr(services,'research_director',None): services.research_director.wake.set()
    return current


def stop_jobs(services, item):
    warmer = getattr(services,'market_warmup',None)
    if not warmer: return
    for job_id in item.get('preparation',{}).get('jobs',{}).values():
        try: warmer.pause(job_id)
        except ValueError: pass


def advance(services, identifier):
    repo = Campaigns(services.database)
    item = repo.get(identifier)
    if item['status'] != 'PREPARING': return
    prep = item['preparation']
    try:
        for timeframe in prep['timeframes']:
            require(services.database,identifier,timeframe)
            job = services.market_warmup.start_research(identifier,timeframe)
            prep['jobs'][timeframe] = job['id']
            if job['status'] in {'queued','running','pausing'}:
                break
            if job['status'] == 'paused':
                services.market_warmup.resume(job['id'])
                break
            if job['status'] == 'failed':
                if job.get('error_category') not in {'rate_limited','provider'}:
                    raise ValueError('History preparation failed; inspect the safe provider category')
                retry_at = job.get('retry_at')
                if retry_at and utcnow() < datetime.fromisoformat(retry_at): break
                attempts = prep['retries'].get(timeframe,0)
                if attempts >= 3: raise ValueError('History preparation retry limit reached')
                retries_at = prep.setdefault('retry_not_before',{})
                if timeframe not in retries_at:
                    retries_at[timeframe]=(utcnow()+timedelta(seconds=30*2**attempts)).isoformat()
                    break
                if utcnow() < datetime.fromisoformat(retries_at[timeframe]): break
                # Persist the retry allowance BEFORE releasing another provider attempt.
                prep['retries'][timeframe] = attempts+1
                retries_at.pop(timeframe,None)
                _save(repo,item,'HISTORY_RETRY_RESERVED')
                services.market_warmup.resume(job['id'])
                return
        else:
            for symbol in prep['symbols']:
                if services.market_data.provider_for(symbol).cache_namespace != prep['namespaces'][symbol]:
                    raise ValueError('Provider namespace changed during preparation')
            coverages=campaign_coverage(services.market_data,item['request']['policy'],prep['entries'],
                now=datetime.combine(datetime.fromisoformat(prep['end_date']).date(),time(12),tzinfo=ZoneInfo('UTC')),
                start=prep['start'],end=prep['end'])
            discovery=dict(version='provider_cache_discovery_v1', warmup_job_ids=list(prep['jobs'].values()),rejected_families=prep.get('rejected_families',[]),
                price_columns_read=False, bounds={'start':prep['start'],'end':prep['end']},
                warnings=['History ingestion uses the selected provider; no entitlement or complete exchange calendar is inferred.',
                          'Only observed cached timestamps determine fixed splits; no performance selection.',
                          'Historical universe may contain survivorship bias.'])
            prep['status']='COMPLETED'
            _save(repo,item,'HISTORY_READY')
            return repo.prepare(identifier,prep['entries'],coverages,discovery=discovery)
        _save(repo,item,'HISTORY_PROGRESS')
    except Exception as exc:
        from .preparation_errors import preparation_failure
        detail=preparation_failure(exc)
        # Provider details are already sanitized in the durable warmup record.
        with services.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            current=repo._get(c,identifier)
            if current['status']=='PREPARING':
                current['preparation'].update(status='FAILED',error='history_preparation_failed')
                current['status']='PAUSED'
                current.update(last_error='history_preparation_failed',last_error_detail=detail)
                repo._save(c,current)
                repo._event(c,identifier,'HISTORY_PREPARATION_FAILED',detail,exception=exc)
        stop_jobs(services,item)


def _save(repo,item,event):
    with repo.database.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        current=repo._get(c,item['id'])
        if current['status']!='PREPARING': raise ValueError('Preparation authorization revoked')
        current['preparation']=item['preparation']
        repo._save(c,current)
        repo._event(c,item['id'],event,{'jobs':item['preparation']['jobs']})
