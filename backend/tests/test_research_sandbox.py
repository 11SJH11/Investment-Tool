import json
from pathlib import Path
import pytest
import pandas as pd
from app.research_agent.sandbox import context_message, RemoteStrategy, SandboxError
from app.research_agent.sandbox_wire import decode, signal_from_json, encode
from app.research_agent.sandbox_image import stage
from app.backtesting.context import StrategyContext


def test_build_context_has_no_host_config_secrets_services_or_strategy_modules(tmp_path):
    manifest=stage(tmp_path)
    names=set(manifest['files'])
    assert 'app/backtesting/strategies/base.py' in names
    assert not any(any(s in n for s in ('.env','config.py','services/','storage/','.venv','research_output')) for n in names)
    assert sorted(n for n in names if '/strategies/' in n)==['app/backtesting/strategies/__init__.py','app/backtesting/strategies/base.py']
    with pytest.raises(ValueError):stage(tmp_path)


@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}',b'['*25+b'0'+b']'*25])
def test_untrusted_json_is_bounded_and_strict(raw):
    with pytest.raises(ValueError):decode(raw)


@pytest.mark.parametrize('value',[
    {'type':'enqueue','value':{}}, {'type':'EntrySignal','value':{'direction':'long','stop_loss':True}},
    {'type':'EntrySignal','value':{'direction':'buy','stop_loss':10}},
    {'type':'ExitSignal','value':{'reason':'ok','job':{}}},
    {'type':'ManagePositionSignal','value':{'new_stop_loss':'nan'}},
])
def test_signal_rejects_authority_and_malformed_numbers(value):
    with pytest.raises((ValueError,TypeError)):signal_from_json(value)


def test_completed_frame_only_even_for_direct_private_frame_access():
    frame=pd.DataFrame({'timestamp':pd.date_range('2026-01-01',periods=4,freq='min',tz='UTC'),'close':[1,2,999,1000]})
    ctx=StrategyContext(symbol='QQQ',primary_timeframe='1m',decision_time=pd.Timestamp('2026-01-01T00:02Z'),frames={'1m':frame},position=None,equity=10000)
    message=context_message(ctx)
    assert len(message['frames']['1m']['rows'])==2
    frame.loc[2:,'close']=-999
    assert message==context_message(ctx)


def test_delayed_availability_excludes_future_htf_bar():
    frame=pd.DataFrame({'timestamp':[pd.Timestamp('2026-01-01T00:00Z')],'available_at':[pd.Timestamp('2026-01-02T22:00Z')],'close':[99]})
    ctx=StrategyContext(symbol='QQQ',primary_timeframe='1d',decision_time=pd.Timestamp('2026-01-02T21:00Z'),frames={'1d':frame},position=None,equity=10000)
    assert context_message(ctx)['frames']['1d']['rows']==[]


def test_remote_never_executes_source_in_host(tmp_path):
    marker=tmp_path/'executed'
    class Transport:
        provenance={}
        def request(self,message):return {'spec':{'key':'child','name':'Child'}}
    RemoteStrategy(Transport(),f"open({str(marker)!r},'w').write('bad')",'child',{})
    assert not marker.exists()


def test_posttrade_and_future_session_diagnostics_are_not_transmitted():
    frame=pd.DataFrame({'timestamp':[pd.Timestamp('2026-01-01T15:00Z')],'close':[1],
        'future_session_high':[999],'mfe':[50],'mae':[10],'future_swing':[123],'source_contract':['NQH26']})
    ctx=StrategyContext(symbol='QQQ',primary_timeframe='1m',decision_time=pd.Timestamp('2026-01-01T15:01Z'),frames={'1m':frame},position=None,equity=10000)
    columns=context_message(ctx)['frames']['1m']['columns']
    assert columns==['timestamp','close','source_contract']


def test_first_divergence_reports_first_value_without_evaluating_performance():
    from app.research_agent.sandbox_runs import first_divergence
    assert first_divergence({'trades':[{'entry':100}]},{'trades':[{'entry':101}]})=={'path':'$.trades[0].entry','reason':'value','expected':'100','actual':'101'}
    assert first_divergence({'x':[]},{'x':[]}) is None


def test_docker_unavailability_has_no_execution_fallback(monkeypatch,tmp_path):
    from app.research_agent.sandbox import Docker,Session
    docker=Docker('unavailable-unit')
    def unavailable(*args,**kwargs):raise SandboxError('DOCKER_UNAVAILABLE_OR_TIMEOUT')
    monkeypatch.setattr(docker,'call',unavailable)
    try:
        with pytest.raises(SandboxError):docker.image()
        with pytest.raises(SandboxError):Session(docker,'sha256:'+'a'*64)
        assert not list(tmp_path.iterdir())
    finally:docker.close()
