from copy import deepcopy

import pytest

from app.backtesting.experiment_result import canonical_result, validate_contract, python_executor_identity
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository
from app.storage.reproducibility import export_manifest


def result():
    return {'strategy':{'key':'fixture','implementation':{'source_sha256':'a'*64}},
            'metrics':{'trades':1,'net_pnl':4},'trades':[{'symbol':'NASUSD','net_pnl':4,'metadata':{'broker_symbol':'NASUSD'}}],
            'data':{'fingerprint':'fixture-data'},'start':'2026-01-01','end':'2026-01-02'}


def test_missing_fields_stay_unavailable_and_arrays_unchanged():
    original = result()
    before = deepcopy(original)
    normalized = canonical_result(original, {}, executor={'kind':'mt5_tester','version':'fixture'})
    assert original == before
    assert normalized['trades'] is original['trades']
    contract = normalized['experiment_contract']
    assert contract['availability']['trades'] == 'RECORDED'
    assert contract['availability']['equity_curve'] == 'UNAVAILABLE'
    assert contract['availability']['research_evidence'] == 'UNAVAILABLE'
    assert 'profit_factor_r' not in normalized['metrics']
    assert contract['data']['broker_symbols'] is None
    assert contract['executor']['execution_tier'] == 'unavailable'


@pytest.mark.parametrize('executor', ['ledger_python','mt5_tester','mt5_remote'])
def test_same_store_roundtrip_for_explicit_executor_without_running_code(tmp_path, executor):
    db = Database(tmp_path/'db');db.initialize();repo = BacktestRunRepository(db)
    config = {'research_parent_id':2,'family_id':'fixture-family'}
    normalized = canonical_result(result(), config, executor={'kind':executor, 'version':'fixture-only'})
    saved = repo.create(config=config,result=normalized,test_role='unclassified')
    assert saved['result'] == normalized
    assert saved['result']['experiment_contract']['lineage']['research_parent_id'] == 2
    assert export_manifest(db,saved['id'])['experiment_contract'] == normalized['experiment_contract']


def test_tampered_hash_and_availability_rejected():
    normalized = canonical_result(result(), {'x':1}, executor=python_executor_identity())
    validate_contract(normalized, {'x':1})
    with pytest.raises(ValueError, match='hash'):
        validate_contract(normalized, {'x':2})
    normalized['experiment_contract']['availability']['equity_curve'] = 'RECORDED'
    with pytest.raises(ValueError, match='availability'):
        validate_contract(normalized, {'x':1})


def test_legacy_saved_result_remains_unchanged(tmp_path):
    db = Database(tmp_path/'db');db.initialize();repo = BacktestRunRepository(db)
    original = result()
    saved = repo.create(config={},result=original)
    assert repo.get(saved['id'])['result'] == original
    assert 'experiment_contract' not in repo.get(saved['id'])['result']
    assert export_manifest(db,saved['id'])['experiment_contract'] is None


def test_parent_lineage_finalization_preserves_worker_identity():
    from app.backtesting.experiment_result import finalize_result
    original = canonical_result(result(), {}, executor={'kind':'ledger_python','source_sha256':'b'*64})
    final = finalize_result(original, {'research_parent_id':'parent'}, test_role='validation')
    assert final['experiment_contract']['executor'] == original['experiment_contract']['executor']
    assert final['experiment_contract']['configuration_sha256'] != original['experiment_contract']['configuration_sha256']
    assert final['experiment_contract']['lineage']['research_parent_id'] == 'parent'
    assert final['trades'] == original['trades']
