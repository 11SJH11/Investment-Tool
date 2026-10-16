"""Alpaca PAPER-only transport. No live host, redirects or automatic POST retry."""
from datetime import datetime,timezone
from hashlib import sha256
import hmac
import json
import secrets
import httpx
from app.brokers.base import BrokerHistoryError

HOST='https://paper-api.alpaca.markets'


class PaperClient:
    def __init__(self,key,secret,*,transport=None):
        if not key or not secret:raise BrokerHistoryError('Paper credentials required',category='configuration')
        self._headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}
        self._client=httpx.Client(timeout=15,follow_redirects=False,trust_env=False,transport=transport)
        self._authorization_secret=secrets.token_bytes(32)

    def close(self):self._client.close()

    def _request(self,method,path,*,params=None,body=None,missing=False):
        try:response=self._client.request(method,HOST+path,headers=self._headers,params=params,json=body)
        except httpx.HTTPError:
            raise BrokerHistoryError('Paper request outcome unknown; reconcile before retry',category='network') from None
        if missing and response.status_code==404:return None
        if response.status_code not in (200,201,204):
            retry=response.headers.get('Retry-After','')
            raise BrokerHistoryError('Paper provider rejected request',status_code=response.status_code,
                category='rate_limit' if response.status_code==429 else 'authentication' if response.status_code in (401,403) else 'provider',
                retry_after=int(retry) if retry.isdigit() else None)
        if response.status_code==204:return None
        try:return response.json()
        except ValueError:raise BrokerHistoryError('Invalid paper response',category='data') from None

    def account(self):return self._request('GET','/v2/account')
    def positions(self):return self._request('GET','/v2/positions')
    def clock(self):return self._request('GET','/v2/clock')
    def asset(self):return self._request('GET','/v2/assets/QQQ')
    def open_orders(self):
        rows=self._request('GET','/v2/orders',params={'status':'open','limit':500,'direction':'asc'})
        if not isinstance(rows,list) or len(rows)>=500:raise BrokerHistoryError('Paper order snapshot may be truncated',category='reconciliation')
        return rows
    def find(self,client_order_id):
        return self._request('GET','/v2/orders:by_client_order_id',params={'client_order_id':client_order_id},missing=True)

    def authorize(self,order,expires_at):
        """Internal RiskGateway capability; never returned by an HTTP endpoint."""
        message=json.dumps({'order':order,'expires_at':expires_at},sort_keys=True,allow_nan=False)
        return {'expires_at':expires_at,'signature':hmac.new(self._authorization_secret,message.encode(),sha256).hexdigest()}

    def submit(self,order,approval=None):
        if not approval or approval.get('expires_at',0)<datetime.now(timezone.utc).timestamp():
            raise ValueError('Unexpired paper risk approval required')
        expected=self.authorize(order,approval['expires_at'])
        if not hmac.compare_digest(str(approval.get('signature','')),expected['signature']):
            raise ValueError('Paper order differs from approved risk intent')
        if order.get('symbol')!='QQQ' or order.get('type')!='market' or order.get('time_in_force')!='day' or order.get('extended_hours') is not False:
            raise ValueError('Only regular-session QQQ paper market orders are supported')
        return self._request('POST','/v2/orders',body=order)

    def cancel(self,order_id):
        from uuid import UUID
        identifier=str(UUID(order_id))
        return self._request('DELETE','/v2/orders/'+identifier)
