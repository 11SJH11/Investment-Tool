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
