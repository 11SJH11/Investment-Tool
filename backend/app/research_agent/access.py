"""Thread-local research access gate. Ordinary manual workflows are unchanged."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta, date
from zoneinfo import ZoneInfo
import json
from app.data.instruments import instrument_spec, normalize_symbol
from .repository import ResearchRepository

_active=ContextVar('research_access',default=None)
class ResearchAccessError(ValueError):pass

def active():return _active.get() is not None

def family(symbol):
    spec=instrument_spec(symbol)
    return 'future:'+spec.root if spec.asset_type=='future' else normalize_symbol(symbol)

@contextmanager
def scope(database,project_id,validation_id=None):
    if not project_id:
        yield;return
    token=_active.set((ResearchRepository(database),project_id,validation_id))
    try:yield
    finally:_active.reset(token)

def check(symbol,timeframe,start,end,namespace=None):
    current=_active.get()
    if current is None:return
    repo,id,validation_id=current
    if start.utcoffset() is None or end.utcoffset() is None:raise ResearchAccessError('Research data needs timezone-aware boundaries')
    zone=ZoneInfo('America/New_York')
    begin=start.astimezone(zone).date().isoformat();finish=(end-timedelta(microseconds=1)).astimezone(zone).date().isoformat()
    with repo.database.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT document FROM agent_projects WHERE id=?',(id,)).fetchone()
        if not row:raise ResearchAccessError('Unknown research project')
        project=json.loads(row[0])
        if project['state'] in {'PAUSED','ARCHIVED','FAILED'}:raise ResearchAccessError('Research is not active')
        datasets=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_datasets')]
        def same(d):return family(symbol) in {family(s) for s in d['symbols']}
        def overlap(d):return same(d) and begin<=d['end'] and d['start']<=finish
        if any(overlap(d) and d['state'] in {'LOCKED_HOLDOUT','FUTURE_OOS'} for d in datasets):raise ResearchAccessError('Holdout firewall blocked a market-data request')
        # Initial queue path is DEVELOPMENT ONLY; explicit approval never gives an automatic validation grant.
        granted=[d for d in datasets if d['project_id']==id and d['state'] in {'DEVELOPMENT','INSPECTED'} and same(d) and d['start']<=begin and finish<=d['end']]
        if validation_id:
            row=c.execute('SELECT document FROM agent_validations WHERE id=?',(validation_id,)).fetchone()
            grant=json.loads(row[0]) if row else None
            from .trials import now
            if not grant or grant['project_id']!=id or grant['status']!='ACTIVE' or now()>=grant['deadline']:
                raise ResearchAccessError('Candidate validation grant is not active')
            available=[d for d in datasets if d['project_id']==id and same(d) and (d['state'] in {'DEVELOPMENT','INSPECTED'} or (d['id']==grant['dataset_id'] and d['state']=='INSPECTED_VALIDATION'))]
            cursor=date.fromisoformat(begin)
            for d in sorted(available,key=lambda d:d['start']):
                if date.fromisoformat(d['start'])<=cursor<=date.fromisoformat(d['end']):cursor=date.fromisoformat(d['end'])+timedelta(days=1)
            if cursor>date.fromisoformat(finish):granted=[d for d in available if overlap(d)]
        if not granted:raise ResearchAccessError('Requested data or warmup is outside declared development periods or the exact candidate validation grant')
        bindings=project.setdefault('provider_bindings',{})
        binding=family(symbol)+':'+timeframe
        if namespace:
            if binding in bindings and bindings[binding]!=namespace:raise ResearchAccessError('Research provider namespace changed; start a separate project')
            bindings[binding]=namespace
        c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(project),id))
        c.execute('INSERT INTO agent_events(project_id,dataset_id,action,detail) VALUES (?,?,?,?)',
            (id,granted[0]['id'],'market_data',json.dumps({'symbol':symbol,'timeframe':timeframe,'start':start.isoformat(),'end':end.isoformat(),'namespace':namespace})))
