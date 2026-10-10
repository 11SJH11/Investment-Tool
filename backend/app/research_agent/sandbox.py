"""Fail-closed Docker RPC. Generated source is data here, never imported/executed."""
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
from queue import Queue, Empty
import re
import shutil
import subprocess
import sys
import tempfile
from threading import Thread, Event
import time
from uuid import uuid4
from app.backtesting.strategies.base import Strategy, StrategySpec
from .sandbox_wire import encode, decode, signal_from_json, MAX_REPLY, MAX_MESSAGE
from .sandbox_image import TAG

LABEL = 'com.ledger.research.sandbox'


class SandboxError(ValueError): pass


class Docker:
    def __init__(self, owner='manual'):
        self.owner = sha256(str(owner).encode()).hexdigest()[:24]
        self.exe = shutil.which('docker') or (r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name=='nt' else 'docker')
        # Do not load the user's registry credentials or inherit DOCKER_HOST/TLS settings.
        self.config = tempfile.TemporaryDirectory(prefix='ledger-docker-cli-')
        self.command = [self.exe, '--config', self.config.name]
        if os.name=='nt': self.command += ['--host','npipe:////./pipe/dockerDesktopLinuxEngine']
        self.env = {k:v for k,v in os.environ.items() if k in {'PATH','SystemRoot','SYSTEMROOT','TEMP','TMP','WINDIR'}}

    def call(self, *args, timeout=30):
        try:
            result = subprocess.run([*self.command,*args],env=self.env,capture_output=True,timeout=timeout)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise SandboxError('DOCKER_UNAVAILABLE_OR_TIMEOUT') from None
        if result.returncode: raise SandboxError('DOCKER_COMMAND_FAILED')
        return result.stdout.decode('utf-8').strip()

    def image(self):
        server = json.loads(self.call('info','--format','{{json .}}'))
        if server.get('OSType')!='linux' or server.get('CgroupVersion')!='2' or not any('seccomp' in s for s in server.get('SecurityOptions',[])):
            raise SandboxError('DOCKER_SECURITY_PREREQUISITES_MISSING')
        image = json.loads(self.call('image','inspect',TAG))[0]
        if image.get('Os')!='linux' or image.get('Architecture')!='amd64': raise SandboxError('SANDBOX_IMAGE_PLATFORM_MISMATCH')
        from .sandbox_image import stage
        with tempfile.TemporaryDirectory(prefix='ledger-image-check-') as folder:
            expected=stage(folder)['sha256']
        if image.get('Config',{}).get('Labels',{}).get('com.ledger.research.build')!=expected:
            raise SandboxError('SANDBOX_IMAGE_STALE_REBUILD_REQUIRED')
        return image['Id']

    def cleanup(self):
        # Only this Ledger database's labelled containers. No global Docker prune.
        ids = self.call('ps','-aq','--filter',f'label={LABEL}={self.owner}').split()
        for cid in ids: self.remove(cid)

    def remove(self,name):
        # Watchdog and cancellation can race. Only confirmed absence is success.
        for _ in range(30):
            try:self.call('rm','-f',name,timeout=10);return
            except SandboxError:
                remaining=self.call('ps','-aq','--filter',('id='+name if re.fullmatch('[a-f0-9]{12,64}',name) else 'name=^/'+name+'$'))
                if not remaining:return
                time.sleep(.1)
        raise SandboxError('SANDBOX_CLEANUP_FAILED')

    def close(self): self.config.cleanup()


class Session:
    def __init__(self, docker, image, *, seconds=120, cancel=None):
        if not re.fullmatch(r'sha256:[a-f0-9]{64}',image): raise SandboxError('Immutable image ID required')
        self.docker=docker; self.cancel=cancel or Event(); self.deadline=time.monotonic()+seconds
        self.name='ledger-research-'+uuid4().hex; self.container_id=None; self.process=None; self.guardian=None; self.stopped=Event(); self.replies=Queue(maxsize=2)
        self.provenance={'image_id':image,'network':'none','user':'65532:65532','memory_bytes':536870912,
                         'cpus':1,'pids':64,'read_only':True,'mounts':[],'protocol':'completed-bars-json-v1',
                         'timeout_seconds':seconds,'source_sha256':None}
        try:
            docker.call('create','--name',self.name,'--label',f'{LABEL}={docker.owner}',
                '--network','none','--read-only','--user','65532:65532','--cap-drop','ALL',
                '--security-opt','no-new-privileges:true','--memory','512m','--memory-swap','512m',
                '--cpus','1','--pids-limit','64','--ulimit','nofile=128:128','--ulimit','core=0:0',
                '--tmpfs','/scratch:rw,noexec,nosuid,nodev,size=33554432,mode=1777',
                '--ipc','none','--log-driver','none','--restart','no','-i',image)
            info=json.loads(docker.call('inspect',self.name))[0]; h=info['HostConfig']
            self.container_id=info['Id']
            if (h['NetworkMode']!='none' or h['Privileged'] or not h['ReadonlyRootfs'] or h['Binds'] or info['Mounts']
                or h['Memory']!=536870912 or h['MemorySwap']!=536870912 or h['NanoCpus']!=1000000000
                or h['PidsLimit']!=64 or h['CapDrop']!=['ALL'] or info['Config']['User']!='65532:65532'
                or not any('no-new-privileges' in s for s in h['SecurityOpt'])):
                raise SandboxError('CONTAINER_POLICY_MISMATCH')
            self.guardian=subprocess.Popen([sys.executable,'-I',str(Path(__file__).with_name('sandbox_guardian.py')),
                *docker.command,self.container_id,str(min(600,max(.1,self.deadline-time.monotonic())))],env=docker.env,
                stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.process=subprocess.Popen([*docker.command,'start','-ai',self.name],env=docker.env,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
            Thread(target=self._read,daemon=True).start()
            Thread(target=self._watch,daemon=True).start()
        except BaseException:
            self.close(); raise

    def _read(self):
        try:
            while not self.stopped.is_set():
                raw=self.process.stdout.readline(MAX_REPLY+1)
                if not raw or len(raw)>MAX_REPLY:
                    self.replies.put_nowait(None); return
                self.replies.put_nowait(raw)
        except Exception:
            try:self.replies.put_nowait(None)
            except Exception:pass

    def _watch(self):
        while not self.stopped.wait(.1):
            if self.cancel.is_set() or time.monotonic()>=self.deadline:
                try:self.docker.remove(self.container_id or self.name)
                except SandboxError:pass
                return

    def request(self, message):
        if self.cancel.is_set(): raise SandboxError('CANCELLED')
        if time.monotonic()>=self.deadline: raise SandboxError('SANDBOX_TIMEOUT')
        raw=encode(message)
        if len(raw)>MAX_MESSAGE: raise SandboxError('SANDBOX_INPUT_LIMIT')
        try:
            # Writer can block if a hostile process stops reading; watchdog kills the container.
            view=memoryview(raw)
            while view:
                written=self.process.stdin.write(view)
                if not written:raise SandboxError('SANDBOX_PIPE_CLOSED')
                view=view[written:]
            self.process.stdin.flush()
            while True:
                if self.cancel.is_set(): raise SandboxError('CANCELLED')
                if time.monotonic()>=self.deadline: raise SandboxError('SANDBOX_TIMEOUT')
                try:reply=self.replies.get(timeout=.1);break
                except Empty:continue
            if reply is None: raise SandboxError('SANDBOX_EXIT_OR_OUTPUT_LIMIT')
            result=decode(reply)
            if not isinstance(result,dict) or result.get('ok') is not True or set(result)!={'ok','result'}:
                raise SandboxError('STRATEGY_VALIDATION_OR_EXECUTION_FAILED')
            return result['result']
        except (BrokenPipeError,OSError,TypeError,KeyError,RecursionError,json.JSONDecodeError):
            raise SandboxError('INVALID_SANDBOX_RESPONSE') from None

    def close(self):
        self.stopped.set()
        removed=False
        try:self.docker.remove(self.container_id or self.name);removed=True
        except SandboxError:
            # Failed cleanup must surface; startup recovery retries owned containers.
            raise SandboxError('SANDBOX_CLEANUP_FAILED') from None
        finally:
            if self.guardian:
                self.guardian.stdin.close()
                if removed and self.guardian.poll() is None:self.guardian.terminate()
                try:self.guardian.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    if removed:self.guardian.kill();self.guardian.wait(timeout=5)
            if self.process:
                if self.process.poll() is None:self.process.kill()
                self.process.wait(timeout=5)
                for stream in (self.process.stdin,self.process.stdout):
                    if stream:
                        try:stream.close()
                        except OSError:pass

    def usage(self):
        # Measured by Docker, never trusted strategy output. Stats are a terminal
        # sample (not a claimed peak) and may be unavailable after a killed task.
        try:
            result=json.loads(self.docker.call('stats','--no-stream','--format','{{json .}}',self.name,timeout=5))
            return {k:result.get(k) for k in ('CPUPerc','MemUsage','MemPerc','PIDs','BlockIO','NetIO')}
        except (SandboxError,ValueError):return None


def context_message(ctx):
    # _frames is used for its timeframe names only. Future rows never cross IPC.
    frames={}
    from app.data.futures import PROVENANCE_COLUMNS
    allowed={'timestamp','available_at','open','high','low','close','volume',*PROVENANCE_COLUMNS}
    for timeframe in ctx._frames:
        frame=ctx.bars(timeframe)
        frame=frame[[column for column in frame.columns if column in allowed]]
        frames[timeframe]={'columns':list(frame.columns),'rows':json.loads(frame.to_json(orient='values',date_format='iso',date_unit='ns',double_precision=15))}
    return {'symbol':ctx.symbol,'primary_timeframe':ctx.primary_timeframe,'decision_time':ctx.decision_time,
            'frames':frames,'position':asdict(ctx.position) if ctx.position else None,'equity':ctx.equity}


class RemoteStrategy(Strategy):
    def __init__(self,session,source,key,params):
        self.session=session; self.params=params; self.trace=[]
        session.provenance['source_sha256']=sha256(source.encode()).hexdigest()
        response=session.request({'op':'init','source':source,'key':key,'params':params})
        if not isinstance(response,dict) or set(response)!={'spec'} or response['spec'].get('key')!=key:
            raise SandboxError('INVALID_STRATEGY_SPEC')
        # Only presentation fields are accepted. Container declarations confer no host permissions.
        self.spec=StrategySpec(key=key,name=str(response['spec'].get('name',key))[:200])

    def reset(self): self.session.request({'op':'reset'})

    def on_bar(self,ctx):
        message={'op':'bar','context':context_message(ctx)}
        result=self.session.request(message)
        self.trace.append(sha256(encode(result)).hexdigest())
        try:return signal_from_json(result)
        except (ValueError,TypeError,KeyError,OverflowError):raise SandboxError('INVALID_STRATEGY_SIGNAL') from None
