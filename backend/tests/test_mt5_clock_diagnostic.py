import pytest
from app.brokers.mt5_clock_diagnostic import summarize


def samples(offset=10800):
    return [dict(receipt_ms=1800000000000+i*1000,tick_ms=1800000000000+i*1000+offset*1000) for i in range(5)]


@pytest.mark.parametrize('offset',[0,7200,10800])
def test_observation_does_not_authorize_conversion_or_execution(offset):
    result=summarize(samples(offset))
    assert result['observed_offset_seconds']==offset
    assert not result['dst_rule_verified'] and not result['execution_enabled']


@pytest.mark.parametrize('failure',['stationary','backwards','host_clock','unknown_offset','invalid','few'])
def test_ambiguous_clock_evidence_fails_closed(failure):
    rows=samples()
    if failure=='stationary':
        for row in rows: row['tick_ms']=rows[0]['tick_ms']
    if failure=='backwards': rows[2]['tick_ms']=rows[0]['tick_ms']
    if failure=='host_clock': rows[2]['receipt_ms']=rows[0]['receipt_ms']
    if failure=='unknown_offset': rows=samples(3600)
    if failure=='invalid': rows[0]['tick_ms']=float('nan')
    if failure=='few': rows=rows[:2]
    assert summarize(rows)['observed_offset_seconds'] is None
