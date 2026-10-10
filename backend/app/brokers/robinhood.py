"""Official Robinhood Trading MCP, strict read allowlist and sanitized failures.
OAuth token is backend-only. No password automation, private endpoints or orders.
"""
import json
import math
import httpx
from app.brokers.base import BrokerHistoryError
from app.brokers.executions import account_key
from app.brokers.trading212 import PortfolioSnapshot

ENDPOINT='https://agent.robinhood.com/mcp/trading'
READ_TOOLS={'get_accounts','get_portfolio','get_equity_positions','get_option_positions','get_crypto_positions'}

def error(message,category='capability'):
    return BrokerHistoryError(message,category=category)

class RobinhoodMCP:
    def __init__(self,token,client=None):
        if not token:raise error('Authorize the official Robinhood Trading MCP; configure a backend OAuth access token','authentication')
        self.client=client or httpx.Client(timeout=30,follow_redirects=False)
        self.headers={'Authorization':'Bearer '+token,'Accept':'application/json, text/event-stream'}
        self.sequence=0;self.tools={}
    def close(self):self.headers.clear();self.client.close()
    def rpc(self,method,params=None,notification=False):
        self.sequence+=1;body={'jsonrpc':'2.0','method':method,'params':params or {}}
        if not notification:body['id']=self.sequence
        try:
            response=self.client.post(ENDPOINT,json=body,headers=self.headers)
            if response.status_code in (401,403):raise error('Robinhood authorization expired or lacks permission; reconnect using official OAuth','authentication')
            if response.status_code==429:raise BrokerHistoryError('Robinhood rate limited; last snapshot preserved',category='rate_limited',status_code=429,retry_after=response.headers.get('Retry-After'))
            if response.status_code>=300:raise error('Robinhood MCP request failed; last snapshot preserved','provider')
            if response.headers.get('mcp-session-id'):self.headers['Mcp-Session-Id']=response.headers['mcp-session-id']
            if notification:return {}
            if len(response.content)>20000000:raise ValueError()
            if 'text/event-stream' in response.headers.get('content-type',''):
                messages=[json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith('data:') and line[5:].strip()]
                payload=next(m for m in messages if m.get('id')==body['id'])
            else:payload=response.json()
            if payload.get('id')!=body['id'] or 'error' in payload:raise ValueError()
            return payload['result']
        except BrokerHistoryError:raise
        except Exception:raise error('Robinhood MCP response/connection unavailable; previous data preserved','provider') from None
    def discover(self):
        if self.tools:return self.tools
        result=self.rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'Ledger read-only portfolio','version':'1'}})
        version=result.get('protocolVersion')
        if version not in {'2024-11-05','2025-03-26','2025-06-18'}:raise error('Unsupported Robinhood MCP protocol version')
        self.headers['MCP-Protocol-Version']=version;self.rpc('notifications/initialized',notification=True)
        cursor=None;seen=set();tools={}
        for _ in range(30):
            page=self.rpc('tools/list',{'cursor':cursor} if cursor else {})
            for tool in page.get('tools',[]):tools[tool['name']]=tool
            cursor=page.get('nextCursor')
            if not cursor:self.tools=tools;return tools
            if cursor in seen:break
            seen.add(cursor)
        raise error('Robinhood tool pagination did not finish','provider')
    def call(self,name,arguments):
        if name not in READ_TOOLS:raise error('Ledger Robinhood connection is read-only')
        self.discover()
        if name not in self.tools:raise error('Required Robinhood read capability is unavailable')
        schema=self.tools[name].get('inputSchema',{})
        if set(schema.get('required',[]))-arguments.keys():raise error('Robinhood tool requires unsupported arguments; adapter update required')
        result=self.rpc('tools/call',{'name':name,'arguments':arguments})
        if result.get('isError'):raise error('Robinhood read tool failed; previous data retained','provider')
        if isinstance(result.get('structuredContent'),(dict,list)):return result['structuredContent']
        try:return json.loads(''.join(block['text'] for block in result.get('content',[]) if block.get('type')=='text'))
        except Exception:raise error('Robinhood did not return structured portfolio facts; adapter update required') from None

def collection(payload,key):
    if isinstance(payload,list):return payload
    if isinstance(payload,dict):
        for candidate in (payload.get(key),payload.get('results'),payload.get('data')):
            if isinstance(candidate,list):return candidate
            if isinstance(candidate,dict) and isinstance(candidate.get(key),list):return candidate[key]
    raise error('Robinhood collection schema unavailable; previous snapshot retained')

def numeric(value):
    if value is None:return None
    try:
        if isinstance(value,bool):raise ValueError()
        value=float(value)
        if not math.isfinite(value):raise ValueError()
        return value
    except Exception:raise error('Robinhood returned invalid numeric facts','provider') from None

class RobinhoodPortfolio:
    provider='robinhood'
    def __init__(self,credentials,environment='live',*,transport=None):
        if environment!='live':raise error('Robinhood MCP requires live account discovery','configuration')
        self.environment=environment;self.transport=transport or RobinhoodMCP(credentials.get('access_token',''))
        self.account_key=None;self.account_label=None;self.selected=credentials.get('account_id','');self._accounts=[];self.account=None
    def close(self):self.transport.close()
    @staticmethod
    def capability_report():
        return dict(provider='robinhood',destination='portfolio',supported=True,read_only=True,execution=False,account_discovery=True,supports_futures=False,
            reason='Official Trading MCP read adapter. Backend OAuth token required; live schema/permission validation required on connection. Normal and agentic accounts remain separate. Ledger execution is disabled.')
    def accounts(self):
        self.transport.discover();payload=self.transport.call('get_accounts',{})
        if isinstance(payload,dict) and any(payload.get(k) for k in ('next','next_cursor','nextCursor','next_page_token')):raise error('Robinhood account discovery is incomplete; snapshot unchanged')
        self._accounts=collection(payload,'accounts');output=[]
        for account in self._accounts:
            external=account.get('account_number') or account.get('id')
            if not isinstance(external,(str,int)):raise error('Robinhood account lacks a stable identity')
            key=account_key(self.provider,'live','official-mcp',str(external))
            output.append(dict(account_key=key,label='Robinhood / '+key[:8],environment='live',currency=account.get('currency'),account_type=account.get('account_type','unknown')))
        return output
    def read_account(self,selected_key=None):
        discovered=self.accounts()
        for account,public in zip(self._accounts,discovered):
            external=str(account.get('account_number') or account.get('id'))
            if (selected_key and public['account_key']==selected_key) or (not selected_key and self.selected and external==self.selected) or (not selected_key and not self.selected and len(discovered)==1):
                self.account=account;self.account_key=public['account_key'];self.account_label=public['label'];return public
        raise error('Select an available Robinhood account before syncing','configuration')
    def arguments(self,name):
        properties=self.transport.tools.get(name,{}).get('inputSchema',{}).get('properties',{})
        for key in ('account_number','account_id'):
            if key in properties:
                value=self.account.get(key) or self.account.get('id')
                if value is None:raise error('Robinhood account does not match discovered tool schema')
                return {key:str(value)}
        raise error('Robinhood tool has no supported account-scoped contract; refusing to mix accounts')
    def verify_scope(self,payload):
        if not isinstance(payload,dict):return
        for key in ('account_number','account_id'):
            if payload.get(key) is not None:
                expected=self.account.get(key) or self.account.get('id')
                if expected is None or str(payload[key])!=str(expected):
                    raise error('Robinhood returned facts for a different account; snapshot unchanged')

    def fetch_snapshot(self,summary):
        positions=[]
        for tool,asset in [('get_equity_positions','equity'),('get_option_positions','option'),('get_crypto_positions','crypto')]:
            if tool not in self.transport.tools:continue
            args=self.arguments(tool);seen=set()
            for _ in range(100):
                payload=self.transport.call(tool,args)
                self.verify_scope(payload)
                for item in collection(payload,'positions'):
                    self.verify_scope(item)
                    instrument=item.get('instrument') if isinstance(item.get('instrument'),dict) else {}
                    identifier=item.get('id') or item.get('instrument_id') or instrument.get('id')
                    symbol=item.get('symbol') or instrument.get('symbol');quantity=numeric(item.get('quantity'))
                    if not identifier or not symbol or quantity is None:raise error('Robinhood position lacks supported identity, symbol or quantity fields; snapshot unchanged')
                    facts={'instrument':{'ticker':str(symbol),'name':item.get('name') or instrument.get('name') or str(symbol),'currency':item.get('currency') or self.account.get('currency')},'quantity':quantity,'averagePricePaid':numeric(item.get('average_buy_price',item.get('average_cost'))),'currentPrice':numeric(item.get('current_price')),'walletImpact':{'currency':item.get('currency') or self.account.get('currency'),'currentValue':numeric(item.get('market_value')),'totalCost':numeric(item.get('cost_basis')),'unrealizedProfitLoss':numeric(item.get('unrealized_pnl'))},'asset_class':asset,'account_type':self.account.get('account_type','unknown')}
                    positions.append({'kind':'position','external_id':asset+':'+str(identifier),'facts':facts})
                cursor=payload.get('next_cursor') if isinstance(payload,dict) else None
                if isinstance(payload,dict) and any(payload.get(k) for k in ('next','next_page_token','nextCursor')):raise error('Unsupported Robinhood pagination contract; snapshot unchanged')
                if not cursor:break
                if cursor in seen or 'cursor' not in self.transport.tools[tool].get('inputSchema',{}).get('properties',{}):raise error('Robinhood pagination cannot advance safely')
                seen.add(cursor);args={**args,'cursor':cursor}
            else:raise error('Robinhood pagination exceeded safe budget','provider')
        if 'get_equity_positions' not in self.transport.tools:raise error('Robinhood equity holdings permission unavailable')
        portfolio=self.transport.call('get_portfolio',self.arguments('get_portfolio'))
        if not isinstance(portfolio,dict):raise error('Robinhood portfolio summary schema unavailable')
        self.verify_scope(portfolio)
        if not any(key in portfolio for key in ('total_value','cash','cost_basis','unrealized_pnl','realized_pnl')):
            raise error('Robinhood portfolio facts do not match the supported schema; snapshot unchanged')
        summary={'currency':portfolio.get('currency') or self.account.get('currency'),'totalValue':numeric(portfolio.get('total_value')),'cash':{'availableToTrade':numeric(portfolio.get('cash'))},'investments':{'totalCost':numeric(portfolio.get('cost_basis')),'unrealizedProfitLoss':numeric(portfolio.get('unrealized_pnl')),'realizedProfitLoss':numeric(portfolio.get('realized_pnl'))},'account_type':self.account.get('account_type','unknown'),'provider':'robinhood','capabilities':self.discovered_capabilities()}
        return PortfolioSnapshot(summary,positions,[])
    def discovered_capabilities(self):
        tools=self.transport.tools
        return {**{asset+'_read':name in tools for asset,name in [('portfolio','get_portfolio'),('equities','get_equity_positions'),('options','get_option_positions'),('crypto','get_crypto_positions')]},
            **{'provider_'+asset+'_execution':name in tools for asset,name in [('equities','place_equity_order'),('options','place_option_order'),('crypto','place_crypto_order')]},'ledger_execution':False,'futures_execution':False}
