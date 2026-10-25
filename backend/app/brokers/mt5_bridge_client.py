"""Lazy read-only module facade for the existing MT5 adapter. No native import."""
from datetime import datetime
import http.client
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from .base import BrokerHistoryError
from .mt5_bridge_protocol import METHODS, MAX_REQUEST, MAX_RESPONSE


def decode(value):
    if isinstance(value,dict):
        if set(value)=={'record'}:return SimpleNamespace(**{k:decode(v) for k,v in value['record'].items()})
        return {k:decode(v) for k,v in value.items()}
    if isinstance(value,list):return [decode(v) for v in value]
    return value


class BridgeClient:
    def __init__(self,url,token_file,environment):
        parsed=urlsplit(url)
        if (parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.username or parsed.password
                or parsed.path not in ('','/') or parsed.query or parsed.fragment or not parsed.port):
            raise BrokerHistoryError('MT5 bridge requires an explicit IPv4 loopback HTTP port',category='configuration')
        if environment not in {'demo','live'}:raise BrokerHistoryError('MT5 bridge requires an explicit demo/live profile',category='configuration')
        self.environment=environment
        self.port=parsed.port;self.token_file=token_file;self.lease=None;self.constants={};self.timestamp_policy='unverified'

    def _call(self,method,args=(),kwargs=None):
        connection=None
        try:
            token=Path(self.token_file).read_text(encoding='utf-8').strip()
            if len(token)<32:raise ValueError()
            request=dict(method=method,args=list(args),kwargs=kwargs or {},lease=self.lease)
            if self.environment=='live':request['environment']='live'
            body=json.dumps(request,allow_nan=False).encode()
            if len(body)>MAX_REQUEST:raise ValueError()
            connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=40)
            connection.request('POST','/v1/read',body,{'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            response=connection.getresponse();raw=response.read(MAX_RESPONSE+1)
            if len(raw)>MAX_RESPONSE:raise ValueError()
            value=json.loads(raw)
            if response.status!=200 or 'error' in value:
                safe={'busy','disconnected','identity_mismatch','connection_failed','session_expired','unsupported','timestamp_unverified','unavailable','response_limit','unauthorized'}
                code=value.get('error');code=code if code in safe else 'bridge_failure'
                raise BrokerHistoryError('MT5 read-only bridge: '+code,category='connection')
            return decode(value['result'])
        except BrokerHistoryError:raise
        except Exception:raise BrokerHistoryError('MT5 read-only bridge unavailable or invalid response; existing data retained',category='connection') from None
        finally:
            if connection:connection.close()

    def initialize(self,*args,**kwargs):
        # Native paths/login/password belong only to the explicitly configured
        # service; never transmit credentials or let a profile switch accounts.
        if any(kwargs.get(k) for k in ('login','password','server')):
            raise BrokerHistoryError('Bridge profiles must not supply login credentials; pin identity in the service',category='configuration')
        opened=self._call('open')
        if opened.get('environment','demo')!=self.environment:
            raise BrokerHistoryError('MT5 bridge environment mismatch',category='configuration')
        self.lease=opened['lease'];self.constants=opened['constants'];self.timestamp_policy=opened['timestamp_policy'];return True

    def shutdown(self):
        try:
            if self.lease:self._call('close')
        finally:self.lease=None

    def __getattr__(self,name):
        if name in self.constants:return self.constants[name]
        if name not in METHODS:raise AttributeError('Unsupported read-only MT5 bridge operation')
        def call(*args,**kwargs):
            args=list(args)
            if name=='copy_rates_range':
                args[1]=next((k for k,v in self.constants.items() if k.startswith('TIMEFRAME_') and v==args[1]),None)
            elif name=='copy_ticks_range':args[3]='COPY_TICKS_ALL' if args[3]==self.constants.get('COPY_TICKS_ALL') else None
            for i,value in enumerate(args):
                if isinstance(value,datetime):
                    if value.utcoffset() is None:raise BrokerHistoryError('MT5 bridge timestamps require a timezone',category='configuration')
                    args[i]=value.timestamp()
            return self._call(name,args,kwargs)
        return call
