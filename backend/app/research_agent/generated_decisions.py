"""Reverify saved isolated evidence without importing or executing generated code."""
from copy import deepcopy
from hashlib import sha256
import json

from .analysis import compare, digest
from .validation import verdict


def verify(connection, candidate, validation, dataset, approval):
    snapshot=candidate['snapshot']
    if (candidate.get('state')!='FROZEN_DEVELOPMENT' or
        validation.get('kind')!='GENERATED_ISOLATED' or approval.get('kind')!='GENERATED_ISOLATED' or
        validation.get('project_id')!=candidate['project_id'] or validation.get('candidate_id')!=candidate['id'] or
        validation.get('dataset_id')!=dataset['id']):
        raise ValueError('Isolated validation identity changed')
    freezes=[json.loads(r[0]) for r in connection.execute(
        "SELECT detail FROM agent_events WHERE project_id=? AND action='generated_candidate_frozen'",(candidate['project_id'],))]
    if digest(snapshot)!=candidate['snapshot_hash'] or not any(
        e.get('candidate_id')==candidate['id'] and e.get('snapshot_hash')==candidate['snapshot_hash'] for e in freezes):
        raise ValueError('Generated freeze audit identity changed')
    row=connection.execute('SELECT document FROM agent_sandbox_runs WHERE id=? AND project_id=?',
                           (snapshot['sandbox_id'],candidate['project_id'])).fetchone()
    if not row or digest(json.loads(row[0]))!=snapshot['evidence_sha256']:
        raise ValueError('Frozen generated development evidence changed')
    provenance=validation.get('provenance',{})
    if (sha256(snapshot['source'].encode()).hexdigest()!=snapshot['source_sha256'] or
        sha256(json.dumps(snapshot['dependencies'],sort_keys=True).encode()).hexdigest()!=snapshot['provenance']['dependency_sha256'] or
        any(not provenance.get(k) or provenance[k]!=snapshot['provenance'].get(k)
            for k in ('source_sha256','dependency_sha256','image_id')) or
        validation.get('image_id')!=provenance.get('image_id')):
        raise ValueError('Generated validation source or image identity changed')
    config=deepcopy(snapshot['configuration'])
    for name in list(config):
        if name.startswith('research_') or name in {'queue_job_id','market_data_fingerprint','strategy_provenance','workspace'}:
            config.pop(name)
    config.update(start_date=dataset['start'],end_date=dataset['end'],save_run=False,test_role='validation')
    if (config!=validation.get('configuration') or digest(config)!=provenance.get('configuration_sha256') or
        set(config['symbols'])!=set(dataset['symbols']) or config['primary_timeframe']!=dataset['timeframe']):
        raise ValueError('Generated validation configuration or dataset changed')
    declared=validation.get('dataset',{})
    if any(declared.get(k)!=dataset.get(k) for k in ('id','start','end','symbols','timeframe')):
        raise ValueError('Approved validation dataset boundaries changed')
    causality=validation.get('causality',{})
    if (validation.get('control_parity') is not True or causality.get('prefix_match') is not True or
        type(causality.get('prefix_signals_checked')) is not int or causality['prefix_signals_checked']<1):
        raise ValueError('Generated validation control or prefix evidence missing')
    if (not validation.get('data_fingerprint') or
        digest(validation.get('result'))!=validation.get('result_sha256') or
        digest(validation.get('parent_result'))!=validation.get('parent_result_sha256')):
        raise ValueError('Generated validation result evidence changed')
    identity={**config,'market_data_fingerprint':validation['data_fingerprint']}
    comparison=compare({'config':identity,'result':validation['parent_result']},
                       {'config':identity,'result':validation['result']})
    if not comparison['data_equivalent'] or comparison!=validation.get('comparison'):
        raise ValueError('Generated validation comparison changed')
    if verdict(comparison['child']['summary'],validation['criteria'])!='VALIDATION_PASS':
        raise ValueError('Generated validation criteria no longer pass')
    return validation
