"""Read-only IEX forward data. Fixed hosts, raw prices, explicit calendar.

Kept separate from configurable historical routing: a forward experiment cannot
silently combine delayed SIP/split-adjusted warmup with live IEX/raw bars.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import httpx
from app.brokers.base import BrokerHistoryError
from .bars import stamp


class AlpacaForwardData:
    provider='alpaca'
    feed='iex'
    def __init__(self,key,secret,*,transport=None):
        if not key or not secret:
            raise BrokerHistoryError('Alpaca credentials are required',category='configuration')
        self._headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}
        self._client=httpx.Client(timeout=20,follow_redirects=False,trust_env=False,transport=transport)

    def close(self):self._client.close()

    def _get(self,host,path,params):
        try:
            response=self._client.get(host+path,params=params,headers=self._headers)
        except httpx.HTTPError:
            raise BrokerHistoryError('Forward data request failed',category='network') from None
        if response.status_code!=200:
            category='rate_limit' if response.status_code==429 else 'authentication' if response.status_code in (401,403) else 'provider'
            retry=response.headers.get('Retry-After','')
            raise BrokerHistoryError('Forward data provider rejected the request',category=category,
                                     status_code=response.status_code,retry_after=int(retry) if retry.isdigit() else None)
        try:return response.json()
        except ValueError:raise BrokerHistoryError('Invalid forward data response',category='provider') from None

    def calendar(self,start,end):
        payload=self._get('https://paper-api.alpaca.markets','/v2/calendar',
                          {'start':str(start),'end':str(end),'date_type':'TRADING'})
        try:
            if not isinstance(payload,list):raise ValueError()
            zone=ZoneInfo('America/New_York')
            return [dict(open=stamp(datetime.fromisoformat(r['date']+'T'+r['open']).replace(tzinfo=zone)).isoformat(),
                         close=stamp(datetime.fromisoformat(r['date']+'T'+r['close']).replace(tzinfo=zone)).isoformat()) for r in payload]
        except (KeyError,TypeError,ValueError):
            raise BrokerHistoryError('Invalid provider session calendar',category='data') from None

    def bars(self,start,end):
        start,end=stamp(start),stamp(end)
        if start>=end:raise ValueError('Ordered forward data period required')
        token=None;seen=set();result=[]
        for _ in range(20):
            params=dict(timeframe='1Min',start=start.isoformat(),end=end.isoformat(),
                        limit=10000,feed='iex',adjustment='raw',sort='asc')
            if token:params['page_token']=token
            payload=self._get('https://data.alpaca.markets','/v2/stocks/QQQ/bars',params)
            try:
                for r in payload.get('bars') or []:
                    at=stamp(r['t'])
                    if not start<=at<end:continue
                    available=at+timedelta(minutes=1)
                    if available>end:continue
                    result.append(dict(timestamp=at.isoformat(),available_at=available.isoformat(),
                                       **{k:r[v] for k,v in [('open','o'),('high','h'),('low','l'),('close','c'),('volume','v')]}))
                token=payload.get('next_page_token')
            except (KeyError,TypeError,ValueError,AttributeError):
                raise BrokerHistoryError('Invalid forward bar response',category='data') from None
            if not token:return result
            if token in seen:break
            seen.add(token)
        raise BrokerHistoryError('Forward data pagination did not complete',category='data')
