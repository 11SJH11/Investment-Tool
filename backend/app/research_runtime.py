"""CPU-only child simulation runtime. Workers never receive providers or repositories."""
import ctypes
import os
import pickle
from time import process_time

_inputs = None
_cancel = None


def memory_info():
    if os.name == 'nt':
        class Memory(ctypes.Structure):
            _fields_ = [('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        m=Memory();m.length=ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        class Counters(ctypes.Structure):
            _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in ('peak','current','pool_peak','pool','nonpage_peak','nonpage','page','page_peak')]
        c=Counters();c.cb=ctypes.sizeof(c)
        kernel=ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype=ctypes.c_void_p
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(kernel.GetCurrentProcess()),ctypes.byref(c),c.cb)
        return {'available_bytes':m.available,'peak_rss_bytes':c.peak,'rss_bytes':c.current}
    try:
        import resource
        peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if os.uname().sysname=='Darwin' else 1024)
        available=os.sysconf('SC_AVPHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')
        return {'available_bytes':available,'peak_rss_bytes':peak,'rss_bytes':peak}
    except (ImportError,ValueError,OSError):
        return {'available_bytes':0,'peak_rss_bytes':None,'rss_bytes':None}


def worker_count(requested, input_bytes=0):
    """Resolve a bounded CPU worker request.

    Conservative mode intentionally tops out at two processes; performance mode
    may use up to four when CPU/RAM permit. Explicit values are still capped by
    the same resource ceiling. One causal simulation remains single-process.
    """
    cpus=os.cpu_count() or 1
    memory=memory_info()['available_bytes']
    # Reserve at least half available RAM; allow overhead and per-run frame copies.
    memory_cap=max(1,int(memory//max(512*1024**2,input_bytes*6))) if memory else 1
    ceiling=max(1,min(8,max(1,cpus-2),memory_cap//2 or 1))
    mode='auto_conservative' if requested in (None,'auto') else str(requested)
    if mode=='auto_conservative':
        return min(2,ceiling)
    if mode=='auto_performance':
        return min(4,ceiling)
    value=int(mode)
    if not 1<=value<=8:
        raise ValueError('Workers must be Auto conservative, Auto performance or 1–8')
    return min(value,ceiling)


def initialize_worker(path, cancel):
    global _inputs,_cancel
    # App-owned, private temporary snapshot; never an uploaded pickle.
    with open(path,'rb') as stream:_inputs=pickle.load(stream)
    _cancel=cancel


def execute_cell(payload, inputs=None, cancel=None):
    from app.services.backtest import BacktestService
    from app.performance import Profile
    inputs=_inputs if inputs is None else inputs
    cancel=_cancel if cancel is None else cancel
    def progress(*args):
        if cancel is not None and cancel.is_set():
            raise InterruptedError('Research cancelled')
    start=process_time()
    with Profile() as profile:
        try:
            result=BacktestService(None).run({**payload,'save_run':False},prepared=inputs,progress=progress)
            return {'result':result,'performance':profile.snapshot(),'cpu_seconds':process_time()-start,
                    'memory':memory_info(),'pid':os.getpid()}
        except InterruptedError:
            return {'cancelled':True}
        except Exception:
            # Strategy/plugin exceptions can contain arbitrary data. Do not persist them.
            return {'error':'Cell simulation failed; check the exact configuration and data.'}
