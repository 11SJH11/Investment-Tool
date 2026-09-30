"""Failure injection uses isolated files/SQLite and no live provider credentials."""
import os
import duckdb
from types import SimpleNamespace

import pandas as pd
import pytest

from app.frame_cache import frames
from app.services.market_data import MarketDataService
from app.storage.database import Database
from app.storage.market_cache_repository import MarketCacheRepository
from app.storage.market_store import MarketStore

START = pd.Timestamp('2026-01-01T00:00Z').to_pydatetime()
END = pd.Timestamp('2026-01-03T00:00Z').to_pydatetime()
TAIL = pd.Timestamp('2026-01-04T00:00Z').to_pydatetime()


def bars():
    return pd.DataFrame(dict(timestamp=pd.date_range(START, periods=4, freq='D'),
        open=[10., 11., 12., 13.], high=[11., 12., 13., 14.],
        low=[9., 10., 11., 12.], close=[10.5, 11.5, 12.5, 13.5], volume=[100., 200., 300., 400.]))


@pytest.fixture
def cache(tmp_path):
    frames.clear()
    database = Database(tmp_path / 'isolated.db')
    database.initialize()
    calls = []
    def fetch(ticker, timeframe, start, end):
        calls.append((start, end))
        data = bars()
        return data.loc[(data.timestamp >= start) & (data.timestamp <= end)].reset_index(drop=True)
    provider = SimpleNamespace(key='fixture', cache_namespace='fixture', get_bars=fetch)
    store = MarketStore(tmp_path / 'market')
    coverage = MarketCacheRepository(database)
    return MarketDataService(provider, store, coverage), calls


def load(service, start=START, end=END):
    return service.get_bars('AAPL', '1m', start, end)


def path(service):
    return service.store._path('fixture', 'AAPL', '1m')


def covered(service):
    return service.coverage.get('fixture', 'AAPL', '1m')


@pytest.mark.parametrize('failure', ['validation', 'fsync', 'replace'])
def test_interrupted_append_preserves_existing_payload_and_coverage(cache, monkeypatch, failure):
    service, calls = cache
    expected = load(service)
    original = path(service).read_bytes()
    original_coverage = covered(service)
    def fail(*args, **kwargs):
        assert list(path(service).parent.glob('*.tmp'))  # Temporary already exists.
        raise OSError('injected interruption')
    with monkeypatch.context() as patch:
        if failure == 'validation':
            patch.setattr(service.store, '_validate_payload', fail)
        else:
            patch.setattr(os, 'fsync' if failure == 'fsync' else 'replace', fail)
        with pytest.raises(OSError, match='injected interruption'):
            load(service, end=TAIL)
    assert path(service).read_bytes() == original
    assert covered(service) == original_coverage
    assert not list(path(service).parent.glob('*.tmp'))
    pd.testing.assert_frame_equal(load(service), expected)
    assert len(load(service, end=TAIL)) == 4


def test_corrupt_temporary_is_not_published(cache, monkeypatch):
    service, _ = cache
    load(service)
    original = path(service).read_bytes()
    validate = service.store._validate_payload
    def corrupt(temporary, columns, rows):
        temporary.write_bytes(b'not parquet')
        validate(temporary, columns, rows)
    with monkeypatch.context() as patch:
        patch.setattr(service.store, '_validate_payload', corrupt)
        with pytest.raises(duckdb.InvalidInputException):
            load(service, end=TAIL)
    assert path(service).read_bytes() == original
    assert covered(service) == (START, END)
    assert not list(path(service).parent.glob('*.tmp'))


def test_failure_after_replace_before_coverage_is_conservative_and_retry_safe(cache, monkeypatch):
    service, _ = cache
    load(service)
    def fail(*args):
        raise RuntimeError('coverage commit interrupted')
    with monkeypatch.context() as patch:
        patch.setattr(service.coverage, 'extend', fail)
        with pytest.raises(RuntimeError, match='coverage commit interrupted'):
            load(service, end=TAIL)
    assert covered(service) == (START, END)
    assert len(service.store.read_bars('fixture', 'AAPL', '1m')) == 4
    result = load(service, end=TAIL)
    assert len(result) == 4 and result.timestamp.is_unique
    assert covered(service) == (START, TAIL)


@pytest.mark.parametrize('damage', ['missing', 'corrupt'])
def test_coverage_disagreement_repairs_entire_interval_and_survives_restart(cache, damage):
    service, calls = cache
    expected = load(service)
    if damage == 'missing':
        path(service).unlink()
    else:
        path(service).write_bytes(b'broken parquet')
    frames.clear()
    middle = pd.Timestamp('2026-01-02T00:00Z').to_pydatetime()
    load(service, middle, END)
    assert calls[-1] == (START, END)
    restarted = MarketDataService(service.provider, MarketStore(service.store.root), service.coverage)
    count = len(calls)
    pd.testing.assert_frame_equal(load(restarted), expected)
    assert len(calls) == count


def test_failed_repair_keeps_old_evidence_and_coverage(cache, monkeypatch):
    service, _ = cache
    load(service)
    path(service).write_bytes(b'broken parquet')
    def fail(*args):
        raise RuntimeError('provider unavailable')
    monkeypatch.setattr(service.provider, 'get_bars', fail)
    with pytest.raises(RuntimeError, match='provider unavailable'):
        load(service)
    assert path(service).read_bytes() == b'broken parquet'
    assert covered(service) == (START, END)


def test_empty_response_has_durable_payload_and_does_not_refetch(cache, monkeypatch):
    service, calls = cache
    def empty(*args):
        calls.append(args)
        return pd.DataFrame()
    monkeypatch.setattr(service.provider, 'get_bars', empty)
    assert load(service).empty
    assert path(service).exists()
    frames.clear()
    restarted = MarketDataService(service.provider, MarketStore(service.store.root), service.coverage)
    assert load(restarted).empty
    assert len(calls) == 1
    assert covered(service) == (START, END)


def test_orphan_temporary_from_process_crash_is_never_read(cache):
    service, calls = cache
    expected = load(service)
    orphan = path(service).with_suffix('.parquet.crashed.tmp')
    orphan.write_bytes(b'partial download')
    frames.clear()
    pd.testing.assert_frame_equal(load(service), expected)
    assert len(calls) == 1


def test_corrupt_derived_cache_rebuilds_without_provider_calls(tmp_path):
    from tests.test_continuous_execution import provider, ROLL
    p = provider(tmp_path)
    db = Database(tmp_path / 'isolated.db')
    db.initialize()
    store = MarketStore(tmp_path / 'market')
    service = MarketDataService(p, store, MarketCacheRepository(db))
    start, end = (ROLL - pd.Timedelta(days=2)).to_pydatetime(), (ROLL + pd.Timedelta(days=1)).to_pydatetime()
    expected = service.get_bars('NQ1!', '1m', start, end)
    calls = len(p.http.calls)
    derived = store._path('derived-continuous-v1-' + p.cache_namespace, 'NQ1!', '1m')
    derived.write_bytes(b'broken parquet')
    frames.clear()
    actual = service.get_bars('NQ1!', '1m', start, end)
    pd.testing.assert_frame_equal(actual, expected)
    assert len(p.http.calls) == calls
    assert actual.source_contract.tolist() == ['NQM6', 'NQU6']


def test_first_write_failure_never_publishes_coverage(cache, monkeypatch):
    service, _ = cache
    def fail(*args):
        raise OSError('replace interrupted')
    with monkeypatch.context() as patch:
        patch.setattr(os, 'replace', fail)
        with pytest.raises(OSError, match='replace interrupted'):
            load(service)
    assert covered(service) is None
    assert not path(service).exists()
    assert not list(path(service).parent.glob('*.tmp'))
    assert len(load(service)) == 3


def test_access_failure_is_not_treated_as_corruption(cache, monkeypatch):
    service, calls = cache
    load(service)
    original = path(service).read_bytes()
    def fail(*args, **kwargs):
        raise PermissionError('access denied')
    monkeypatch.setattr(service.store, 'read_bars', fail)
    with pytest.raises(PermissionError):
        load(service)
    assert len(calls) == 1
    assert path(service).read_bytes() == original


def test_payload_without_coverage_is_merged_safely_after_restart(cache):
    service, calls = cache
    service.store.write_bars('fixture', 'AAPL', '1m', bars())
    assert covered(service) is None
    result = load(service, end=TAIL)
    assert len(result) == 4 and result.timestamp.is_unique
    assert calls == [(START, TAIL)]
    assert covered(service) == (START, TAIL)


def test_empty_append_preserves_payload_bytes_and_research_dtypes(cache, monkeypatch):
    service, _ = cache
    expected = load(service)
    original = path(service).read_bytes()
    monkeypatch.setattr(service.provider, 'get_bars', lambda *args: pd.DataFrame())
    load(service, end=TAIL)
    assert path(service).read_bytes() == original
    assert covered(service) == (START, TAIL)
    frames.clear()
    pd.testing.assert_frame_equal(load(service), expected)


def test_first_nonempty_append_keeps_provider_dtypes_after_empty_cache(cache, monkeypatch):
    service, _ = cache
    original_fetch = service.provider.get_bars
    with monkeypatch.context() as patch:
        patch.setattr(service.provider, 'get_bars', lambda *args: pd.DataFrame())
        assert load(service).empty
    service.get_bars('AAPL', '1m', START, END, force_refresh=True)
    pd.testing.assert_frame_equal(load(service), service.store._normalize(original_fetch('AAPL', '1m', START, END)),
                                  check_dtype=False)
    assert load(service).close.dtype == bars().close.dtype
