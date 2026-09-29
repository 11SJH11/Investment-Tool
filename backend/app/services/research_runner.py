"""One parent coordinates exact simulations; all persistence stays in the parent."""
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from hashlib import sha256
import json
import multiprocessing
from pathlib import Path
import pickle
import tempfile
from time import perf_counter, process_time

from app.frame_cache import fingerprint
from app.performance import Profile, measure
from app.research_runtime import execute_cell, initialize_worker, worker_count, memory_info
from app.services.backtest import _snapshot_config
from app.backtesting.strategies import strategy_registry


def input_identity(inputs):
    hashes={symbol:{tf:fingerprint(f) for tf,f in frames.items()} for symbol,frames in inputs['frames_by_symbol'].items()}
    warmup={symbol:fingerprint(f) for symbol,f in inputs['diagnostic_history'].items()}
    return sha256(json.dumps([hashes,warmup,inputs['providers'],inputs['source_namespaces']],sort_keys=True,default=str).encode()).hexdigest()


def run_experiment(service, repository, payload, *, progress, cancelled, commit):
    """Callbacks serialize cancellation and commits with the owning queue."""
    children=payload['research_children'];group=payload['experiment_group']
    document=repository.get(group) or {
        'experiment_group':group,'experiment_id':group,'experiment_type':payload['experiment_type'],
        'name':payload['run_name'],'test_role':payload['test_role'],'notes':payload.get('run_notes',''),
        'tags':payload.get('run_tags',[]),'plan':payload['research_plan'],'base_configuration':payload['research_base'],
        'cells':[{'index':i,'values':c['research_experiment']['cell'],'status':'queued'} for i,c in enumerate(children)]}
    document['status']='preparing shared data';repository.save(document)
    # Recover the tiny crash window between immutable run save and cell-reference save.
    for run in service.runs.list_by_experiment(group):
        index=run['config'].get('research_experiment',{}).get('cell_index')
        if run['config'].get('research_parent_id')==group and isinstance(index,int) and 0<=index<len(children):
            document['cells'][index].update(status='completed',run_id=run['id'])
    started=perf_counter();cpu_started=process_time()
    with Profile() as preparation:
        inputs=service.prepare(children[0],progress=lambda *args:progress('preparing shared data',0,len(children)))
    identity=input_identity(inputs)
    if document.get('market_data_fingerprint') not in (None,identity):
        raise ValueError('Research input changed; create a new experiment instead of mixing snapshots')
    document['market_data_fingerprint']=identity
    input_bytes=sum(int(f.memory_usage(deep=True).sum()) for fs in inputs['frames_by_symbol'].values() for f in fs.values())
    input_bytes+=sum(int(f.memory_usage(deep=True).sum()) for f in inputs['diagnostic_history'].values())
    requested=payload.get('research_workers','auto')
    workers=worker_count(requested,input_bytes)
    strategy=strategy_registry.create(inputs['strategy_key'],**children[0].get('strategy_params',{}))
    if getattr(strategy,'workspace_provenance',None):workers=1
    document['performance']={'preparation':preparation.snapshot(),'input_bytes':input_bytes,
                             'requested_workers':requested,'workers':workers,'cells':document.get('performance',{}).get('cells',{})}
    repository.save(document)
    context=multiprocessing.get_context('spawn');event=context.Event()
    remaining=[i for i,c in enumerate(document['cells']) if c['status']!='completed']
    done=len(children)-len(remaining)
    def save_cell(index,outcome):
        nonlocal done
        cell=document['cells'][index]
        if outcome.get('cancelled'):return
        if outcome.get('error'):
            cell.update(status='failed',error=outcome['error'])
        else:
            child=children[index];result=outcome['result']
            effective={**child,'strategy_params':result['strategy']['params'],
                       'research_parent_id':group,'market_data_fingerprint':identity}
            if result.get('workspace'):effective['workspace']=result['workspace']
            persistence_start=perf_counter()
            with measure('research_persistence'):
                saved=commit(lambda:service.runs.create(config=_snapshot_config(effective,strategy_key=inputs['strategy_key'],symbols=inputs['symbols']),
                    result=result,name=child['run_name'],notes=child.get('run_notes',''),test_role=child['test_role'],
                    experiment_group=group,tags=child.get('run_tags',[])))
            document['performance']['persistence_seconds']=document['performance'].get('persistence_seconds',0)+perf_counter()-persistence_start
            cell.update(status='completed',run_id=saved['id']);cell.pop('error',None)
            document['performance']['cells'][str(index)]={k:v for k,v in outcome.items() if k!='result'}
        done+=1
        document['status']='running';repository.save(document)
        progress('running',done,len(children))
    try:
        progress('running',done,len(children))
        if workers==1:
            for i in remaining:
                cancelled()
                document['cells'][i]['status']='running';repository.save(document)
                # The same cancellation contract as engine progress, including every 64 bars.
                class Check:
                    def is_set(self):
                        try:cancelled();return False
                        except Exception:return True
                save_cell(i,execute_cell(children[i],inputs,Check()))
                cancelled()
        else:
            with tempfile.TemporaryDirectory(prefix='ledger-research-input-') as directory:
                path=Path(directory)/'prepared.pkl'
                with path.open('wb') as stream:pickle.dump(inputs,stream,protocol=pickle.HIGHEST_PROTOCOL)
                # One snapshot read per worker, not a DataFrame serialized for each cell.
                with ProcessPoolExecutor(max_workers=workers,mp_context=context,initializer=initialize_worker,initargs=(str(path),event)) as pool:
                    pending={}
                    iterator=iter(remaining)
                    def fill():
                        while len(pending)<workers:
                            i=next(iterator,None)
                            if i is None:break
                            document['cells'][i]['status']='running';repository.save(document)
                            pending[pool.submit(execute_cell,children[i])]=i
                    fill()
                    try:
                        while pending:
                            cancelled()
                            completed,_=wait(pending,timeout=.1,return_when=FIRST_COMPLETED)
                            for future in completed:
                                i=pending.pop(future)
                                try:outcome=future.result()
                                except Exception:outcome={'error':'Research worker failed; this cell can be retried.'}
                                save_cell(i,outcome)
                            fill()
                    finally:
                        event.set()
                        for future in pending:future.cancel()
        progress('analysing results',done,len(children))
        document['status']='completed' if all(c['status']=='completed' for c in document['cells']) else 'failed'
        progress('saving',done,len(children))
    except BaseException as exc:
        from app.services.backtest_jobs import JobCancelled
        event.set();document['status']='cancelled' if isinstance(exc,JobCancelled) else 'failed'
        for cell in document['cells']:
            if cell['status']!='completed':cell['status']=document['status']
        raise
    finally:
        document['performance']['wall_seconds']=perf_counter()-started
        document['performance']['parent_cpu_seconds']=process_time()-cpu_started
        document['performance']['parent_memory']=memory_info()
        repository.save(document)
    return document
