"""Immutable loaded-strategy source bundles. Data only: never imported or executed."""
import base64
from hashlib import sha256
import json
import re

SCOPE = 'Loaded strategy modules only; excludes engine, base classes, external dependencies and market data. Not a complete executable environment.'
MAX_BYTES = 32 * 1024 * 1024


def manifest_for(sources):
    if not isinstance(sources, dict) or not sources or len(sources)>2000:
        raise ValueError('Invalid strategy source bundle')
    if any(not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.py', name) or not isinstance(content,bytes) for name,content in sources.items()):
        raise ValueError('Invalid strategy source module or bytes')
    if sum(len(content) for content in sources.values())>MAX_BYTES:
        raise ValueError('Strategy source bundle exceeds archive size limit')
    manifest = {name:sha256(content).hexdigest() for name,content in sources.items()}
    identifier = sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
    return manifest, identifier


def store(connection, provenance, sources):
    if not provenance.get('source_sha256') or not provenance.get('registry_sha256'):
        return {'status':'unavailable','reason':'Loaded strategy has no complete registry source identity','scope':SCOPE}
    manifest, identifier = manifest_for(sources)
    filename = provenance.get('module','').rsplit('.',1)[-1]+'.py'
    if identifier!=provenance['registry_sha256'] or manifest.get(filename)!=provenance['source_sha256']:
        raise ValueError('Captured strategy source differs from executed provenance')
    connection.execute('CREATE TABLE IF NOT EXISTS strategy_source_blobs(sha256 TEXT PRIMARY KEY,content BLOB NOT NULL)')
    connection.execute('CREATE TABLE IF NOT EXISTS strategy_source_archives(sha256 TEXT PRIMARY KEY,manifest TEXT NOT NULL)')
    for name, content in sources.items():
        checksum = manifest[name]
        old = connection.execute('SELECT content FROM strategy_source_blobs WHERE sha256=?',(checksum,)).fetchone()
        if old and bytes(old[0])!=content:raise ValueError('Stored strategy source integrity failed')
        if not old:connection.execute('INSERT INTO strategy_source_blobs VALUES (?,?)',(checksum,content))
    encoded = json.dumps(manifest,sort_keys=True)
    old = connection.execute('SELECT manifest FROM strategy_source_archives WHERE sha256=?',(identifier,)).fetchone()
    if old and old[0]!=encoded:raise ValueError('Stored strategy manifest integrity failed')
    if not old:connection.execute('INSERT INTO strategy_source_archives VALUES (?,?)',(identifier,encoded))
    return {'status':'archived','sha256':identifier,'module':filename,'module_sha256':manifest[filename],
            'module_count':len(manifest),'scope':SCOPE}


def export_run(database, run_id):
    with database.connect() as c:
        row=c.execute("SELECT json_extract(result_json,'$.strategy.source_archive'),json_extract(result_json,'$.strategy.implementation') FROM backtest_runs WHERE id=?",(run_id,)).fetchone()
        if not row:raise ValueError('Saved run was not found')
        archive=json.loads(row[0]) if row[0] else {}
        provenance=json.loads(row[1]) if row[1] else {}
        if archive.get('status')!='archived':raise ValueError('No captured source archive exists for this saved run; current source is not a historical substitute')
        if archive.get('sha256')!=provenance.get('registry_sha256') or archive.get('module_sha256')!=provenance.get('source_sha256'):
            raise ValueError('Saved strategy archive identity differs')
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='strategy_source_archives'").fetchone():raise ValueError('Saved source archive storage is missing')
        row=c.execute('SELECT manifest FROM strategy_source_archives WHERE sha256=?',(archive['sha256'],)).fetchone()
        if not row:raise ValueError('Saved source manifest is missing')
        manifest=json.loads(row[0]);sources={}
        for name, checksum in manifest.items():
            blob=c.execute('SELECT content FROM strategy_source_blobs WHERE sha256=?',(checksum,)).fetchone()
            if not blob or sha256(bytes(blob[0])).hexdigest()!=checksum:raise ValueError('Saved strategy source integrity failed')
            sources[name]=bytes(blob[0])
        actual, identifier=manifest_for(sources)
        filename=provenance.get('module','').rsplit('.',1)[-1]+'.py'
        if identifier!=archive['sha256'] or actual!=manifest or manifest.get(filename)!=archive.get('module_sha256'):
            raise ValueError('Saved source manifest integrity failed')
        return {'format':'ledger_strategy_source_bundle_v1','run_id':run_id,'provenance':provenance,'archive':archive,
                'encoding':'base64','manifest':manifest,'files':{name:base64.b64encode(content).decode('ascii') for name,content in sources.items()},
                'warning':SCOPE+' Archive contents are untrusted source text; exporting does not authorize execution.'}
