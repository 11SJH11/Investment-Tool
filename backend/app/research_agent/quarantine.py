"""Inert generated-code drafts. Parsing is advisory; nothing here executes or registers Python."""
import ast
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Literal
from uuid import uuid4
from pydantic import Field
from .hypotheses import Strict
from .analysis import digest
from .candidates import Candidates
from .repository import ResearchRepository


class Draft(Strict):
    request_key: str = Field(min_length=1,max_length=120)
    registry_key: str = Field(pattern=r'^research_child_[a-z0-9_]{1,80}$')
    source: str = Field(min_length=1,max_length=100000)
    rationale: str = Field(min_length=1,max_length=4000)
    acknowledgement: Literal['Store this source as an inert quarantined draft; no execution or activation']


def inspect_source(source):
    try:
        tree=ast.parse(source)
        nodes=list(ast.walk(tree))
        if len(nodes)>10000:return {'syntax_valid':False,'error':'AST node limit exceeded'}
        imports=sorted({n.module or '' for n in nodes if isinstance(n,ast.ImportFrom)}|{a.name for n in nodes if isinstance(n,ast.Import) for a in n.names})
        classes=[n.name for n in tree.body if isinstance(n,ast.ClassDef)]
        return {'syntax_valid':True,'node_count':len(nodes),'declared_classes':classes,'imports':imports,
                'interface_validated':False,'safe_to_execute':False,'limitation':'Parsing does not validate StrategySpec, causality, behavior, dependencies or security. Isolation and control parity remain required.'}
    except (SyntaxError,ValueError,RecursionError,MemoryError) as exc:
        return {'syntax_valid':False,'error':type(exc).__name__,'line':getattr(exc,'lineno',None),'safe_to_execute':False}


def store(database,project_id,candidate_id,payload):
    request=Draft.model_validate(payload).model_dump()
    project=ResearchRepository(database).get(project_id)
    candidate=next((c for c in Candidates(database).list(project_id) if c['id']==candidate_id),None)
    if not candidate or digest(candidate['snapshot'])!=candidate['snapshot_hash']:raise ValueError('Valid frozen parent candidate required')
    if project['state']!='BASELINE_ANALYSIS':raise ValueError('Project must be active')
    raw=request.pop('source');source_hash=sha256(raw.encode('utf-8')).hexdigest()
    identity=digest({'request':request,'source_sha256':source_hash,'candidate_hash':candidate['snapshot_hash']})
    document={'id':str(uuid4()),'project_id':project_id,'candidate_id':candidate_id,'parent_hash':candidate['snapshot_hash'],
              'request':request,'source_sha256':source_hash,'identity':identity,'state':'QUARANTINED',
              'created_at':datetime.now(timezone.utc).isoformat(),'inspection':inspect_source(raw),
              'execution_enabled':False,'required_before_execution':['Working isolated runtime','Dependency and interface validation inside isolation','Disabled-change control parity','Causality tests','Explicit development run approval']}
    with database.connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS agent_code_drafts(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,request_key TEXT NOT NULL,registry_key TEXT NOT NULL,document TEXT NOT NULL,source TEXT NOT NULL,UNIQUE(project_id,request_key),UNIQUE(registry_key))')
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT document FROM agent_code_drafts WHERE project_id=? AND request_key=?',(project_id,request['request_key'])).fetchone()
        if old:
            old=json.loads(old[0])
            if old['identity']!=identity:raise ValueError('Draft request key is immutable')
            return old
        if c.execute('SELECT COUNT(*) FROM agent_code_drafts WHERE project_id=?',(project_id,)).fetchone()[0]>=10:raise ValueError('Project draft limit reached (10)')
        from app.backtesting.strategies import strategy_registry
        if request['registry_key'] in {s.key for s in strategy_registry.specs()} or c.execute('SELECT 1 FROM agent_code_drafts WHERE registry_key=?',(request['registry_key'],)).fetchone():raise ValueError('Child registry key must be unique')
        current=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project_id,)).fetchone()[0])
        if current['state']!='BASELINE_ANALYSIS':raise ValueError('Project must be active')
        c.execute('INSERT INTO agent_code_drafts VALUES (?,?,?,?,?,?)',(document['id'],project_id,request['request_key'],request['registry_key'],json.dumps(document),raw))
        c.execute('INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)',(project_id,'code_draft_quarantined',json.dumps({'draft_id':document['id'],'source_sha256':source_hash,'candidate_hash':candidate['snapshot_hash']})))
    return document



def list_drafts(database,project_id,candidate_id):
    if not any(c['id']==candidate_id for c in Candidates(database).list(project_id)):raise ValueError('Unknown parent candidate')
    with database.connect() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_code_drafts'").fetchone():return []
        return [json.loads(r[0]) for r in c.execute("SELECT document FROM agent_code_drafts WHERE project_id=? AND json_extract(document,'$.candidate_id')=? ORDER BY rowid",(project_id,candidate_id))]


def export_draft(database,project_id,candidate_id,draft_id):
    if not any(d['id']==draft_id for d in list_drafts(database,project_id,candidate_id)):raise ValueError('Unknown quarantined draft')
    with database.connect() as c:row=c.execute('SELECT document,source FROM agent_code_drafts WHERE id=?',(draft_id,)).fetchone()
    document=json.loads(row[0]);source=row[1]
    if sha256(source.encode('utf-8')).hexdigest()!=document['source_sha256']:raise ValueError('Quarantined source integrity failed')
    return {'format':'ledger_quarantined_source_v1','draft':document,'source':source,'execution_enabled':False}
