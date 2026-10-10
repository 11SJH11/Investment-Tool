from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import inspect
import math
import json
from pathlib import Path
from threading import RLock
import pandas as pd
from .base import ConceptRequest, Observation

@dataclass(frozen=True)
class Definition:
    key: str
    description: str
    calculate: object
    parameters: object
    dependencies: tuple[str,...]=()
    status: str='EXPERIMENTAL'
    limitations: str='Descriptive definition; not evidence of profitability.'
    implementation_files: tuple[str,...]=()

class ConceptRegistry:
    def __init__(self):
        self.items={};self.cache=OrderedDict();self.lock=RLock()
    def register(self,definition):
        ConceptRequest(key=definition.key)
        if definition.key in self.items:raise ValueError('Concept version already registered; create a new version')
        self.items[definition.key]=definition
        try:self._graph(definition.key,(),allow_missing=True)
        except Exception:
            del self.items[definition.key];raise
    def _graph(self,key,path,allow_missing=False):
        if key in path:raise ValueError('Circular concept dependency')
        if key not in self.items:
            if allow_missing:return
            raise ValueError('Unknown exact concept version: '+key)
        for dependency in self.items[key].dependencies:self._graph(dependency,(*path,key),allow_missing)
    def provenance(self,request):
        request=ConceptRequest.model_validate(request);self._graph(request.key,())
        definition=self.items[request.key]
        params=definition.parameters.model_validate(request.params).model_dump()
        files={inspect.getsourcefile(definition.calculate),inspect.getsourcefile(definition.parameters),inspect.getsourcefile(type(self)),inspect.getsourcefile(Observation),*definition.implementation_files}
        source=sha256(b''.join(Path(p).read_bytes() for p in sorted(x for x in files if x))).hexdigest()
        return {'key':request.key,'timeframe':request.timeframe,'params':params,'source_sha':source,
                'scope':'strategy-local' if request.key.startswith('strategy-local:') else 'canonical',
                'dependencies':[self.provenance({'key':k,'timeframe':request.timeframe}) for k in definition.dependencies]}
    def declarations(self,requests):
        return {alias:self.provenance(request) for alias,request in requests.items()}
    def describe(self):
        return [{**self.provenance({'key':d.key}),'description':d.description,'status':d.status,
                 'limitations':d.limitations,'parameter_schema':d.parameters.model_json_schema()} for d in self.items.values()]
    def evaluate(self,request,bars,*,symbol,decision_time):
        request=ConceptRequest.model_validate(request);provenance=self.provenance(request)
        from app.backtesting.context import _completed_bars, timeframe_delta
        frame=_completed_bars(bars,request.timeframe,decision_time)
        if not frame.empty:
            required={'timestamp','open','high','low','close','volume'}
            if not required.issubset(frame):raise ValueError('Concept input requires OHLCV bars')
            if not frame[['open','high','low','close','volume']].map(lambda v:isinstance(v,(int,float)) and math.isfinite(v)).all().all():raise ValueError('Concept input has non-finite OHLCV')
            stamps=pd.to_datetime(frame.timestamp,utc=True)
            if stamps.duplicated().any() or not stamps.is_monotonic_increasing:raise ValueError('Concept bars must be ordered and unique')
        # Include every supplied column: provider, adjustment and source-contract changes invalidate.
        data=sha256(pd.util.hash_pandas_object(frame,index=False).values.tobytes()+str(list(zip(frame.columns,map(str,frame.dtypes)))).encode()).hexdigest()
        key=sha256(json.dumps([symbol,provenance,data],sort_keys=True,allow_nan=False).encode()).hexdigest()
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key);return deepcopy(self.cache[key])
        definition=self.items[request.key]
        dependencies={k:self.evaluate({'key':k,'timeframe':request.timeframe},frame,symbol=symbol,decision_time=decision_time)['observations'] for k in definition.dependencies}
        if 'available_at' not in frame:frame=frame.assign(available_at=pd.to_datetime(frame.timestamp,utc=True)+timeframe_delta(request.timeframe))
        observations=tuple(Observation.model_validate(o) for o in definition.calculate(frame,provenance['params'],dependencies))
        if any(o.confirmed_at>pd.Timestamp(decision_time) for o in observations):raise ValueError('Concept exposed unconfirmed evidence')
        output={'observations':observations,'provenance':provenance,'data_fingerprint':data,'cache_key':key}
        # Bound both entry count and per-entry retained evidence. Large results are uncached.
        if len(observations)<=10000:
            with self.lock:
                self.cache[key]=deepcopy(output)
                while len(self.cache)>64:self.cache.popitem(last=False)
        return output

registry=ConceptRegistry()
