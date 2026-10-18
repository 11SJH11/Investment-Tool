"""Versioned exports of saved evidence, shared by manual and agent workflows."""
import csv
from hashlib import sha256
from io import BytesIO, StringIO
import json
import re
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
from typing import Literal
from pydantic import BaseModel, ConfigDict

from app.research_agent.analysis import analyze
from app.storage.reproducibility import export_manifest

FORMAT = 'ledger.research_pack.v1'
MAX_EXPORT_BYTES = 100 * 1024 * 1024


class ResearchPack(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format: Literal['ledger.research_pack.v1']
    run_id: int
    run: dict
    experiment_contract: dict | None
    configuration: dict
    provenance: dict
    metrics: dict | None
    recorded_analysis: dict | None
    research_analysis: dict | None
    research_evidence: dict | None
    microstructure: dict | None
    data: dict | None
    availability: dict[str, Literal['RECORDED','UNAVAILABLE']]
    limitations: list[str]


def json_bytes(value):
    return json.dumps(value, sort_keys=True, indent=2, default=str, allow_nan=False).encode('utf-8')


def csv_bytes(rows):
    columns = sorted({key for row in rows for key in row})
    def cell(value):
        if value is None:
            return ''
        if isinstance(value, (dict, list)):
            value = json_bytes(value).decode()
        if isinstance(value, str) and (re.match(r'^\s*[=+@-]', value) or value.startswith(('\t', '\r'))):
            return "'" + value
        return value
    stream = StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow([cell(c) for c in columns])
    for row in rows:
        writer.writerow([cell(row.get(c)) for c in columns])
    return ('\ufeff' + stream.getvalue()).encode('utf-8')


def research_pack(repository, run_id):
    run = repository.get(run_id)
    result = run['result']
    trades = result.get('trades')
    # Do not turn a missing trade section into a zero-trade research conclusion.
    analysis = analyze(run) if isinstance(trades, list) else None
    provenance = export_manifest(repository.database, run_id)
    pack = {
        'format': FORMAT, 'run_id':run_id,
        'run':{key:run.get(key) for key in ('name','notes','test_role','experiment_group','tags','created_at')},
        'experiment_contract':result.get('experiment_contract'),
        'configuration':run['config'], 'provenance':provenance,
        'metrics':result.get('metrics'), 'recorded_analysis':result.get('analysis'),
        'research_analysis':analysis, 'research_evidence':result.get('research_evidence'),
        'microstructure':result.get('microstructure'),
        'data':result.get('data'),
        'availability':{key:'RECORDED' if result.get(key) is not None else 'UNAVAILABLE'
                        for key in ('trades','metrics','analysis','microstructure','research_evidence')},
        'limitations':['Descriptive evidence only; no automatic winner or causal trading rule.',
                      'Raw market bars/ticks are not embedded. Data hashes do not prove complete history.',
                      'Legacy executor/contract metadata remains unavailable.',
                      'Configuration and authored metadata are included; review before sharing.']}
    return ResearchPack.model_validate(pack).model_dump(), run


def export_files(repository, run_id):
    pack, run = research_pack(repository, run_id)
    result = run['result']
    summary = {key:pack[key] for key in ('format','run_id','run','metrics','availability','experiment_contract')}
    files = {
        'research-pack.schema.json':json_bytes(ResearchPack.model_json_schema()),
        'research-pack.json':json_bytes(pack),
        'summary.json':json_bytes(summary),
        'analysis.json':json_bytes({'recorded':pack['recorded_analysis'], 'research':pack['research_analysis']}),
        'configuration-provenance.json':json_bytes({'configuration':run['config'],'provenance':pack['provenance']}),
        'saved-result.json':json_bytes(run),
    }
    if isinstance(result.get('trades'), list):
        files['trades.csv'] = csv_bytes(result['trades'])
    analysis_rows = []
    for name, rows in (result.get('analysis') or {}).get('breakdowns', {}).items():
        if isinstance(rows, list):
            analysis_rows.extend({'breakdown':name, **row} for row in rows if isinstance(row, dict))
    files['analysis.csv'] = csv_bytes(analysis_rows)
    files['manifest.json'] = json_bytes({'format':'ledger.research_bundle.v1', 'pack_schema':FORMAT,
        'run_id':run_id, 'files':{name:{'bytes':len(content),'sha256':sha256(content).hexdigest()}
                                for name,content in files.items()},
        'omissions':['Raw market data','Executable dependencies','Current strategy source']})
    if sum(map(len, files.values())) > MAX_EXPORT_BYTES:
        raise ValueError('Export exceeds the 100 MiB uncompressed budget')
    return files


def zip_files(files):
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as archive:
        for name, content in sorted(files.items()):
            # Stable timestamps/order: repeated exports of immutable evidence match.
            entry = ZipInfo(name, date_time=(1980,1,1,0,0,0))
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, content)
    return buffer.getvalue()
