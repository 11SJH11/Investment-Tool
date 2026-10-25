"""Standalone authenticated loopback MT5 read service. Run with Windows Python.

No Ledger services, database, broker credentials or dynamic dispatch endpoints.
Native call timeout terminates this service, never abandons a parallel MT5 call.
"""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
from threading import Timer
import time
from .mt5_bridge_protocol import CONSTANTS, MAX_REQUEST, MAX_RESPONSE, ProtocolError, encode, validate


class Bridge:
    def __init__(self,module,config):
        if (config.get('environment') not in {'demo','live'} or config.get('allow_initialize') is not True
                or type(config.get('expected_login')) is not int or config['expected_login']<=0
                or not config.get('expected_server') or not config.get('terminal_path')):
            raise ValueError('Explicit environment, identity, terminal path and initialization consent required')
        expected_mode=0 if config['environment']=='demo' else 2
        if config.get('expected_trade_mode',expected_mode)!=expected_mode:
            raise ValueError('Configured trade mode does not match environment')
        if config.get('timestamp_policy','unverified') not in {'unverified','verified_utc'}:raise ValueError('Invalid timestamp policy')
        self.module=module;self.config=config;self.lease=None;self.expires=0;self.initialized=False

    def identity(self):
        terminal=self.module.terminal_info();account=self.module.account_info()
        if terminal is None or not terminal.connected or account is None:raise ProtocolError('disconnected')
        expected_mode=0 if self.config['environment']=='demo' else 2
        if (account.trade_mode!=expected_mode or account.login!=self.config['expected_login']
                or account.server!=self.config['expected_server']):raise ProtocolError('identity_mismatch')
        return account

    def dispatch(self,request):
        if not isinstance(request,dict) or set(request)-{'method','args','kwargs','lease','environment'}:raise ProtocolError('invalid_request')
        # Missing environment is the legacy DEMO-only protocol, never LIVE.
        if request.get('environment','demo')!=self.config['environment']:raise ProtocolError('identity_mismatch')
        method=request.get('method');args=request.get('args',[]);kwargs=request.get('kwargs',{})
        now=time.monotonic()
        if method=='open':
            if args or kwargs or request.get('lease'):raise ProtocolError('invalid_request')
            if self.lease and now<self.expires:raise ProtocolError('busy')
            if not self.initialized:
                # Explicit local configuration only: never pass login/password or switch accounts.
                if not self.module.initialize(self.config['terminal_path'],timeout=30000):raise ProtocolError('connection_failed')
                self.initialized=True
            self.identity();self.lease=secrets.token_hex(32);self.expires=now+60
            constants={n:getattr(self.module,n) for n in CONSTANTS if hasattr(self.module,n)}
            constants.update({n:getattr(self.module,n) for n in dir(self.module) if n.startswith('SYMBOL_CALC_MODE_') and type(getattr(self.module,n)) is int})
            return dict(lease=self.lease,constants=constants,environment=self.config['environment'],timestamp_policy=self.config.get('timestamp_policy','unverified'))
        if not self.lease or not isinstance(request.get('lease'),str) or not hmac.compare_digest(request['lease'],self.lease) or now>=self.expires:raise ProtocolError('session_expired')
        if method=='close':
            if args or kwargs:raise ProtocolError('invalid_request')
            self.lease=None;return True
        args,kwargs=validate(method,args,kwargs)
        self.identity()
        if method.startswith('copy_') and self.config.get('timestamp_policy','unverified')!='verified_utc':raise ProtocolError('timestamp_unverified')
        if method=='copy_rates_range':args[1]=getattr(self.module,args[1])
        if method=='copy_ticks_range':args[3]=self.module.COPY_TICKS_ALL
        if method=='tick_diagnostics':
            receipt_before=time.time_ns()//1000000
            tick=self.module.symbol_info_tick(args[0]);receipt_after=time.time_ns()//1000000
            if tick is None:raise ProtocolError('unavailable')
            result=dict(raw_time_msc=tick.time_msc,receipt_before_utc_ms=receipt_before,receipt_after_utc_ms=receipt_after,
                raw_minus_receipt_ms=tick.time_msc-receipt_after,timestamp_policy=self.config.get('timestamp_policy','unverified'),
                seasonal_rule_verified=False,execution_enabled=False)
        elif method=='account_info':
            account=self.identity()
            result={'record':{n:getattr(account,n) for n in ('login','server','currency','trade_mode','balance','equity','margin','margin_free','margin_level','leverage','trade_allowed','trade_expert') if hasattr(account,n)}}
        elif method=='terminal_info':
            terminal=self.module.terminal_info()
            result={'record':{n:getattr(terminal,n) for n in ('connected','trade_allowed','tradeapi_disabled','build') if hasattr(terminal,n)}}
        else:
            # validate() is the sole fixed method allowlist; no arbitrary RPC.
            value=getattr(self.module,method)(*args,**kwargs)
            if value is None:raise ProtocolError('unavailable')
            result=encode(value)
        self.identity();self.expires=time.monotonic()+60
        return result


def make_server(bridge,token,port):
    if len(token)<32:raise ValueError('Bridge token must contain at least 32 characters')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def setup(self):
            super().setup();self.connection.settimeout(5)
        def do_POST(self):
            code=400;response={'error':'invalid_request'}
            timer=None
            try:
                if self.path!='/v1/read' or self.headers.get('Origin') or self.headers.get('Transfer-Encoding'):raise ProtocolError('invalid_request')
                if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':raise ProtocolError('invalid_request')
                if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                    code=401;raise ProtocolError('unauthorized')
                if self.headers.get('Content-Type')!='application/json':raise ProtocolError('invalid_request')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=MAX_REQUEST:raise ProtocolError('request_limit')
                # Fail the isolated service closed if a native DLL call hangs.
                timer=Timer(35,lambda:os._exit(70));timer.daemon=True;timer.start()
                request=json.loads(self.rfile.read(length))
                response={'result':bridge.dispatch(request)};code=200
                payload=json.dumps(response,allow_nan=False).encode()
                if len(payload)>MAX_RESPONSE:raise ProtocolError('response_limit')
            except ProtocolError as exc:
                code=401 if str(exc)=='unauthorized' else 400;response={'error':str(exc)}
            except Exception:code=400;response={'error':'bridge_failure'}
            finally:
                if timer:timer.cancel()
            payload=json.dumps(response,allow_nan=False).encode()
            try:
                self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
            except (OSError,TimeoutError):pass
    # Single-threaded dispatch serializes every terminal call across all clients.
    return HTTPServer(('127.0.0.1',port),Handler)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);args=parser.parse_args()
    config=json.loads(Path(args.config).read_text(encoding='utf-8'))
    token=Path(config['token_file']).read_text(encoding='utf-8').strip()
    import MetaTrader5
    make_server(Bridge(MetaTrader5,config),token,int(config.get('port',18765))).serve_forever()


if __name__=='__main__':main()
