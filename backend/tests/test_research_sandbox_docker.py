"""Opt-in real Docker acceptance. No credentials, network providers or live LLM calls."""
import os
import json
import time
from threading import Event
import pytest
import pandas as pd
from app.research_agent.sandbox import Docker,Session,RemoteStrategy,SandboxError,LABEL
from app.backtesting.context import StrategyContext

pytestmark=pytest.mark.skipif(os.environ.get('LEDGER_TEST_DOCKER')!='1',reason='Set LEDGER_TEST_DOCKER=1 for real Docker acceptance')

SOURCE='''from app.backtesting.strategies.base import Strategy, StrategySpec
from app.backtesting.models import EntrySignal
class Child(Strategy):
    spec=StrategySpec(key='research_child_fixture',name='Fixture',defaults={'enabled':False},timeframes=('1m',))
    def reset(self): self.entered=False
    def on_bar(self,ctx):
        if self.params['enabled']: return None
        if not self.entered:
            self.entered=True
            return EntrySignal('long',float(ctx.current_bar['close'])-2)
'''


@pytest.fixture
def docker():
    runtime=Docker('acceptance-test-'+str(os.getpid()))
    runtime.cleanup()
    yield runtime
    runtime.cleanup()
    assert not runtime.call('ps','-aq','--filter',f'label={LABEL}={runtime.owner}')
    runtime.close()


def context():
    frame=pd.DataFrame({'timestamp':[pd.Timestamp('2026-01-01T15:00Z')],'open':[100.],'high':[101.],'low':[99.],'close':[100.],'volume':[10.]})
    return StrategyContext(symbol='QQQ',primary_timeframe='1m',decision_time=pd.Timestamp('2026-01-01T15:01Z'),frames={'1m':frame},position=None,equity=10000)


def test_real_readiness_worker_is_removed(docker):
    report=docker.preflight()
    assert report['status']=='ready' and report['cleanup_completed']
    assert not docker.call('ps','-aq','--filter',f'label={LABEL}={docker.owner}')


def test_gold_ifvg_control_parity_on_sunday_completed_frames(docker):
    from pathlib import Path
    from app.backtesting.engine import BacktestEngine
    from app.backtesting.models import BacktestConfig
    from app.backtesting.strategies.gold_asia_15m_ifvg_research_v1 import GoldAsia15mIfvgResearchV1
    from app.research_agent.sandbox_runs import core
    from tests.test_gold_ifvg_acceptance import fixture
    frames=fixture('2026-03-08')
    config=BacktestConfig(trading_weekdays=(0,1,2,3,4,6))
    source=Path('app/backtesting/strategies/gold_asia_15m_ifvg_research_v1.py').read_text(encoding='utf-8')
    expected=BacktestEngine(config).run(symbol_frames={'XAUUSD':frames},strategies={'XAUUSD':GoldAsia15mIfvgResearchV1()},primary_timeframe='1m')
    session=Session(docker,docker.image(),seconds=60)
    try:
        remote=RemoteStrategy(session,source,'gold_asia_15m_ifvg_research_v1',{})
        actual=BacktestEngine(config).run(symbol_frames={'XAUUSD':frames},strategies={'XAUUSD':remote},primary_timeframe='1m')
        assert core(actual)==core(expected)
        assert len(actual['trades'])==1 and actual['trades'][0]['r_multiple']==pytest.approx(1)
        assert actual['trades'][0]['metadata']['asia_session_key']=='2026-03-08'
    finally:
        session.close()


def test_real_strategy_interface_signal_and_container_policy(docker):
    session=Session(docker,docker.image())
    try:
        strategy=RemoteStrategy(session,SOURCE,'research_child_fixture',{})
        strategy.reset();signal=strategy.on_bar(context())
        assert signal.direction=='long' and signal.stop_loss==98
        policy=json.loads(docker.call('inspect',session.name))[0]
        assert policy['HostConfig']['NetworkMode']=='none'
        assert policy['HostConfig']['ReadonlyRootfs'] and not policy['HostConfig']['Privileged']
        assert policy['HostConfig']['Memory']==536870912 and policy['HostConfig']['PidsLimit']==64
    finally:session.close()


def test_delta_stream_retains_history_and_isolates_context_mutations(docker):
    source='''from app.backtesting.strategies.base import Strategy, StrategySpec
from app.backtesting.models import EntrySignal
class Child(Strategy):
    spec=StrategySpec(key='delta_fixture',name='Delta fixture',timeframes=('1m',))
    def on_bar(self,ctx):
        bars=ctx.bars('1m')
        assert list(bars.close)==list(range(100,100+len(bars)))
        close=float(bars.close.iloc[-1])
        ctx._frames['1m'].loc[0,'close']=-999
        return EntrySignal('long',close-2,metadata={'count':len(bars)})
'''
    frame=pd.DataFrame({'timestamp':pd.date_range('2026-01-01T15:00Z',periods=30,freq='min'),
                        'close':range(100,130)})
    session=Session(docker,docker.image(),seconds=60)
    try:
        remote=RemoteStrategy(session,source,'delta_fixture',{});remote.reset()
        for n in range(1,31):
            ctx=StrategyContext(symbol='QQQ',primary_timeframe='1m',decision_time=frame.timestamp.iloc[n-1]+pd.Timedelta(minutes=1),frames={'1m':frame},position=None,equity=10000)
            signal=remote.on_bar(ctx)
            assert signal.stop_loss==100+n-3 and signal.metadata['count']==n
        remote.reset();ctx.decision_time=frame.timestamp.iloc[0]+pd.Timedelta(minutes=1)
        assert remote.on_bar(ctx).metadata['count']==1
        assert frame.close.tolist()==list(range(100,130))
    finally:session.close()


def test_full_period_delta_engine_parity_with_warmup_across_sessions(docker):
    from app.backtesting.engine import BacktestEngine
    from app.backtesting.models import BacktestConfig
    from tests.test_phase52_saved_runs_and_chart_series import HoldToEnd
    from app.research_agent.sandbox_runs import core,check_input_limits
    source=SOURCE.replace("float(ctx.current_bar['close'])-2", "float(ctx.current_bar['close'])-50,take_profit=float(ctx.current_bar['close'])+100,reason='hold_to_end'")
    frame=pd.DataFrame({'timestamp':pd.date_range('2026-01-01T14:30Z',periods=10020,freq='min'),
                        'open':100.,'high':101.,'low':99.,'close':100.,'volume':100.})
    frames={'QQQ':{'1m':frame}};start=frame.timestamp.iloc[1000]
    check_input_limits({'symbols':['QQQ'],'frames_by_symbol':frames},full_period=True)
    config=BacktestConfig(starting_balance=10000,sizing_mode='quantity',risk_value=1,allow_overnight=True)
    expected=BacktestEngine(config).run(symbol_frames=frames,strategies={'QQQ':HoldToEnd()},primary_timeframe='1m',evaluation_start=start)
    session=Session(docker,docker.image(),seconds=600)
    try:
        remote=RemoteStrategy(session,source,'research_child_fixture',{})
        actual=BacktestEngine(config).run(symbol_frames=frames,strategies={'QQQ':remote},primary_timeframe='1m',evaluation_start=start)
        assert core(actual)==core(expected)
        assert len(remote.trace)==9020 and len(actual['trades'])==1
        assert pd.Timestamp(actual['trades'][0]['entry_time'])>start
        assert actual['trades'][0]['exit_reason']=='end_of_data'
    finally:session.close()


def test_hostile_source_cannot_reach_secrets_network_docker_or_write_code(docker):
    attacks='''
import os, socket
for key in ('OANDA_ACCESS_TOKEN','OPENAI_API_KEY','TRADELOCKER_PASSWORD','MT5_PASSWORD','DATABASE_URL'):
    assert key not in os.environ
for path in ('/var/run/docker.sock','/run/docker.sock','/backend/.env','/repo/.env','/backend/data/ledger.db','/opt/ledger/app/core/config.py','/opt/ledger/app/services/backtest_jobs.py','/opt/ledger/app/brokers'):
    assert not os.path.exists(path)
for module in ('app.services.backtest_jobs','app.brokers.oanda','app.storage.database'):
    try:__import__(module)
    except ImportError:pass
    else:raise AssertionError('host authority imported')
for path in ('/escape','/dev/shm/escape','/opt/ledger/app/backtesting/strategies/base.py','/opt/ledger/app/indicators/builtins.py'):
    try: open(path,'w').write('mutated')
    except OSError: pass
    else: raise AssertionError('write escaped scratch')
for address in ('1.1.1.1','host.docker.internal'):
    try: socket.create_connection((address,443),timeout=.3)
    except OSError: pass
    else: raise AssertionError('network escape')
try:socket.getaddrinfo('example.com',443)
except OSError:pass
else:raise AssertionError('external DNS resolved')
open('/scratch/allowed','w').write('ok')
assert os.getuid()==65532
assert 'Seccomp:\\t2' in open('/proc/self/status').read()
assert 'NoNewPrivs:\\t1' in open('/proc/self/status').read()
'''
    session=Session(docker,docker.image())
    try:
        strategy=RemoteStrategy(session,attacks+SOURCE,'research_child_fixture',{})
        strategy.reset();assert strategy.on_bar(context()).direction=='long'
    finally:session.close()


@pytest.mark.parametrize('source',['while True: pass','import os\nos._exit(0)','x=bytearray(2*1024**3)','import os\nos.write(1,b"x"*100000)','import os\nwhile True: os.write(2,b"x"*4096)'])
def test_hostile_hang_exit_memory_and_output_fail_closed(docker,source):
    session=Session(docker,docker.image(),seconds=3)
    started=time.monotonic()
    try:
        with pytest.raises((SandboxError,ValueError)):RemoteStrategy(session,source,'research_child_fixture',{})
    finally:session.close()
    assert time.monotonic()-started<20


def test_cancellation_cleanup(docker):
    from threading import Timer
    cancel=Event();session=Session(docker,docker.image(),seconds=30,cancel=cancel)
    timer=Timer(1,cancel.set);timer.start()
    try:
        with pytest.raises(SandboxError):RemoteStrategy(session,'while True: pass','research_child_fixture',{})
    finally:session.close();timer.join()


@pytest.mark.parametrize('source',['this is ! syntax','import nonexistent_ledger_dependency','class Child: pass',SOURCE.replace("research_child_fixture","wrong_key")])
def test_invalid_generated_module_rejected_inside_container(docker,source):
    session=Session(docker,docker.image())
    try:
        with pytest.raises(SandboxError):RemoteStrategy(session,source,'research_child_fixture',{})
    finally:session.close()


def test_owned_orphan_recovery_leaves_other_owner_untouched(docker):
    other=Docker('other-owner-'+str(os.getpid()))
    session=Session(docker,docker.image()); second=Session(other,other.image())
    try:
        docker.cleanup()
        assert not docker.call('ps','-aq','--filter',f'label={LABEL}={docker.owner}')
        assert other.call('ps','-aq','--filter',f'label={LABEL}={other.owner}')
    finally:session.close();second.close();other.close()


def test_process_limit_is_enforced(docker):
    attack='''
import os,time
children=[]
try:
    for _ in range(90):
        try: pid=os.fork()
        except OSError: break
        if pid==0:
            time.sleep(2);os._exit(0)
        children.append(pid)
    assert len(children)<64
finally:
    for pid in children:os.waitpid(pid,0)
'''
    session=Session(docker,docker.image(),seconds=20)
    try:RemoteStrategy(session,attack+SOURCE,'research_child_fixture',{})
    finally:session.close()


def test_backend_eof_triggers_independent_cleanup(docker):
    session=Session(docker,docker.image(),seconds=30)
    try:
        # The same EOF is delivered by the OS when the owning backend process dies.
        session.guardian.stdin.close()
        session.guardian.wait(timeout=10)
        assert not docker.call('ps','-aq','--filter','name=^/'+session.name+'$')
    finally:session.close()


def test_missing_and_finished_container_cleanup_is_idempotent(docker):
    session=Session(docker,docker.image())
    try:
        with pytest.raises(SandboxError):RemoteStrategy(session,'raise SystemExit(0)','research_child_fixture',{})
        session.close();session.close();docker.cleanup();docker.cleanup()
        assert not docker.call('ps','-aq','--filter',f'label={LABEL}={docker.owner}')
    finally:session.close()


def test_canonical_swing_has_no_future_confirmation_inside_container(docker):
    source='''from app.backtesting.strategies.base import Strategy,StrategySpec
class Child(Strategy):
    spec=StrategySpec(key='research_child_fixture',name='Swing',concepts={'swing':{'key':'swing.strict.v1','timeframe':'1m'}})
    def on_bar(self,ctx):
        assert len(ctx._frames['1m'])==3
        assert not ctx.concept('swing')['observations']
        return None
'''
    from tests.test_market_concepts import bars
    ctx=StrategyContext(symbol='QQQ',primary_timeframe='1m',decision_time=pd.Timestamp('2026-01-02T14:33Z'),frames={'1m':bars()},position=None,equity=10000)
    session=Session(docker,docker.image())
    try:
        strategy=RemoteStrategy(session,source,'research_child_fixture',{});strategy.reset()
        assert strategy.on_bar(ctx) is None
    finally:session.close()


def test_forced_backend_process_death_removes_live_container(tmp_path):
    import subprocess,sys
    owner='crash-process-'+str(os.getpid()); runtime=Docker(owner)
    marker=tmp_path/'container-id'
    # This helper is the trusted host coordinator, not generated strategy code.
    helper="""from pathlib import Path
from app.research_agent.sandbox import Docker,Session,RemoteStrategy
import sys
d=Docker(sys.argv[1]);s=Session(d,d.image(),seconds=20)
from tests.test_research_sandbox_docker import SOURCE,context
source=SOURCE.replace("if self.params['enabled']: return None", "while True: pass")
strategy=RemoteStrategy(s,source,'research_child_fixture',{})
strategy.reset()
Path(sys.argv[2]).write_text(s.container_id)
strategy.on_bar(context())
"""
    parent=subprocess.Popen([sys.executable,'-B','-c',helper,owner,str(marker)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+15
        while not marker.exists() and time.monotonic()<deadline:time.sleep(.1)
        assert marker.exists(),'Trusted test coordinator failed to start'
        cid=marker.read_text()
        assert json.loads(runtime.call('inspect',cid))[0]['State']['Running']
        parent.kill();parent.wait(timeout=5)
        deadline=time.monotonic()+12
        while runtime.call('ps','-aq','--filter','id='+cid) and time.monotonic()<deadline:time.sleep(.1)
        assert not runtime.call('ps','-aq','--filter','id='+cid)
    finally:
        if parent.poll() is None:parent.kill();parent.wait(timeout=5)
        runtime.cleanup();runtime.close()
