import pandas as pd
import pytest

from app.market_concepts import registry


def ticks():
    return pd.DataFrame({'timestamp':pd.date_range('2026-01-02T10:00Z', periods=5, freq='30s'),
                         'bid':[100.]*5, 'ask':[101.,102.,103.,104.,105.]})


def evaluate(key, frame, decision='2026-01-02T10:02Z'):
    return registry.evaluate({'key':key, 'timeframe':'ticks'}, frame, symbol='mt5:fixture', decision_time=pd.Timestamp(decision))


@pytest.mark.parametrize('key', ['spread.current.v1','spread.mean_window.v1','tick_activity.count.v1'])
def test_tick_concepts_prefix_causality_and_provenance(key):
    frame = ticks()
    full = evaluate(key, frame)['observations']
    prefix = evaluate(key, frame.iloc[:3], '2026-01-02T10:01Z')['observations']
    future_mutated = frame.copy()
    future_mutated.loc[3:, 'ask'] = 999
    assert prefix == full[:3] == evaluate(key, future_mutated, '2026-01-02T10:01Z')['observations']
    assert all(o.occurred_at == o.confirmed_at == o.available_at for o in full)
    assert len(evaluate(key, frame)['data_fingerprint']) == 64


def test_exact_spread_count_and_warmup():
    frame = ticks()
    assert [o.value for o in evaluate('spread.current.v1', frame)['observations']] == [1,2,3,4,5]
    assert [o.value for o in evaluate('spread.mean_window.v1', frame)['observations']] == [None,None,2.5,3.5,4.5]
    assert [o.value for o in evaluate('tick_activity.count.v1', frame)['observations']] == [None,None,2,2,2]


def test_delayed_availability_and_missing_quote():
    frame = ticks()
    frame['available_at'] = frame.timestamp + pd.Timedelta(seconds=30)
    result = evaluate('spread.current.v1', frame, '2026-01-02T10:01Z')['observations']
    assert len(result) == 2 and result[-1].available_at == pd.Timestamp('2026-01-02T10:01Z')
    frame.loc[1,'ask'] = float('nan')
    assert evaluate('spread.current.v1', frame)['observations'][1].value is None
    assert evaluate('spread.mean_window.v1', frame)['observations'][2].value is None


def test_ticks_not_substituted_for_bar_volume_and_bad_availability_rejects():
    with pytest.raises(ValueError, match='Bar concept'):
        evaluate('session_vwap.new_york.v1', ticks())
    frame = ticks()
    frame['available_at'] = frame.timestamp - pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match='availability'):
        evaluate('spread.current.v1', frame)


def test_equal_timestamp_events_counted_in_provider_order():
    frame = ticks().iloc[:3]
    frame = pd.concat([frame, frame.iloc[-1:]], ignore_index=True)
    output = evaluate('tick_activity.count.v1', frame)['observations']
    assert [o.value for o in output] == [None,None,2,3]


def test_tick_times_cannot_silently_assume_local_or_utc_timezone():
    frame = ticks()
    frame['timestamp'] = frame.timestamp.dt.tz_localize(None)
    with pytest.raises(ValueError, match='timezone'):
        evaluate('spread.current.v1', frame)
