"""Additive canonical result metadata; existing Ledger arrays remain authoritative.

Never recalculate metrics or annotate historical results with today's code identity.
Executors supply facts explicitly. Missing evidence stays UNAVAILABLE.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FORMAT = 'ledger.experiment.v1'


class ExecutorIdentity(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    kind: Literal['ledger_python', 'mt5_tester', 'mt5_remote', 'unavailable']
    version: str | None = None
    source_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    execution_tier: Literal['fast_bars', 'microstructure_validation', 'tick_strategy', 'unavailable'] = 'unavailable'


class ExperimentContract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    format: Literal['ledger.experiment.v1'] = FORMAT
    executor: ExecutorIdentity
    configuration_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    strategy: dict
    data: dict
    period: dict
    lineage: dict
    test_role: str
    execution_model: dict | None = None
    cost_model: dict | None = None
    availability: dict[str, str]
    limitations: list[str] = Field(default_factory=list)


def configuration_hash(config):
    return sha256(json.dumps(config, sort_keys=True, separators=(',', ':'),
                             default=str, allow_nan=False).encode()).hexdigest()


def python_executor_identity():
    root = Path(__file__).resolve().parent
    # Explicit core scope, not a claim to archive every dependency or executable.
    files = ('engine.py', 'context.py', 'models.py')
    digest = sha256()
    for name in files:
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    return ExecutorIdentity(kind='ledger_python', version='ledger-bar-engine-v1',
                            source_sha256=digest.hexdigest(), execution_tier='fast_bars')


def canonical_result(result, config, *, executor, test_role='unclassified',
                     execution_model=None, cost_model=None):
    """Normalize the envelope without copying large arrays or inventing results."""
    if not isinstance(result, dict):
        raise ValueError('Experiment result must be a mapping')
    for key, expected in (('metrics', dict), ('trades', list), ('equity_curve', list), ('analysis', dict)):
        if result.get(key) is not None and not isinstance(result[key], expected):
            raise ValueError('Invalid canonical result section: ' + key)
    strategy = result.get('strategy') or {}
    data = result.get('data') or {}
    implementation = strategy.get('implementation') or {}
    sections = ('metrics', 'trades', 'equity_curve', 'analysis', 'setups', 'rejected_signals',
                'research_evidence', 'microstructure')
    availability = {key: 'RECORDED' if key in result and result[key] is not None else 'UNAVAILABLE'
                    for key in sections}
    lineage_keys = ('research_program_id', 'family_id', 'research_project_id', 'research_trial_id',
                    'research_validation_id', 'research_parent_id', 'research_campaign_id', 'experiment_group')
    contract = ExperimentContract(
        executor=ExecutorIdentity.model_validate(executor),
        configuration_sha256=configuration_hash(config),
        strategy={'key': strategy.get('key') or config.get('strategy_key'),
                  'family_id': config.get('family_id'),
                  'source_sha256': implementation.get('source_sha256'),
                  'implementation': deepcopy(implementation) or None},
        data={'fingerprint': data.get('fingerprint') or config.get('market_data_fingerprint'),
              'providers': deepcopy(data.get('providers')),
              'instruments': deepcopy(data.get('instruments')),
              'broker_symbols': deepcopy(data.get('broker_symbols')),
              'dataset_state': config.get('dataset_state'),
              'coverage': deepcopy(data.get('coverage'))},
        period={'start':result.get('start'), 'end':result.get('end'),
                'primary_timeframe':result.get('primary_timeframe'), 'session':result.get('session')},
        lineage={key: config.get(key) for key in lineage_keys}, test_role=test_role,
        execution_model=deepcopy(execution_model), cost_model=deepcopy(cost_model),
        availability=availability,
        limitations=['Unavailable sections are not zero-valued results.',
                     'Executor identity is not a Python/MT5 parity certificate.',
                     'Core source hash is not a complete archived executable/dependency environment.'])
    return {**result, 'experiment_contract':contract.model_dump(mode='json')}


def validate_contract(result, config):
    """Legacy snapshots remain byte-for-byte unchanged; validate only explicit v1."""
    if 'experiment_contract' not in result:
        return
    contract = ExperimentContract.model_validate(result['experiment_contract'])
    if contract.configuration_sha256 != configuration_hash(config):
        raise ValueError('Experiment configuration does not match its recorded hash')
    for key, status in contract.availability.items():
        expected = 'RECORDED' if key in result and result[key] is not None else 'UNAVAILABLE'
        if status != expected:
            raise ValueError('Experiment section availability does not match its evidence')


def finalize_result(result, config, *, test_role):
    """Parent adds lineage after a worker run; retain the worker's code identity."""
    recorded = result.get('experiment_contract')
    if recorded is None:
        return result
    contract = ExperimentContract.model_validate(recorded)
    return canonical_result(result, config, executor=contract.executor, test_role=test_role,
                            execution_model=contract.execution_model, cost_model=contract.cost_model)
