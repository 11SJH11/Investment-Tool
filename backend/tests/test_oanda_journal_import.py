import json
from uuid import uuid4

import httpx
import pytest

from app.brokers.base import BrokerHistoryError
from app.brokers.oanda import OandaHistory


def history():
    opened = {"id": "10", "type": "ORDER_FILL", "batchID": "9", "orderID": "9", "time": "2026-06-01T23:30:00Z", "commission": "0.1", "tradeOpened": {"tradeID": "10", "units": "100", "price": "1.10", "halfSpreadCost": "0.3"}}
    first = {"id": "20", "type": "ORDER_FILL", "orderID": "19", "time": "2026-06-02T10:00:00Z", "commission": "0.1", "tradeReduced": {"tradeID": "10", "units": "40", "price": "1.12", "realizedPL": "0.8", "halfSpreadCost": "0.2"}}
    last = {"id": "30", "type": "ORDER_FILL", "orderID": "29", "time": "2026-06-03T10:00:00Z", "commission": "0.1", "tradesClosed": [{"tradeID": "10", "units": "60", "price": "1.13", "realizedPL": "1.8", "halfSpreadCost": "0.3"}]}
    stop = {"id": "11", "type": "STOP_LOSS_ORDER", "batchID": "9", "tradeID": "10", "reason": "ON_FILL", "price": "1.09", "accountID": "private-account"}
    target = {"id": "12", "type": "TAKE_PROFIT_ORDER", "batchID": "9", "tradeID": "10", "reason": "ON_FILL", "price": "1.14"}
    trade = {"id": "10", "instrument": "EUR_USD", "initialUnits": "100", "currentUnits": "0", "price": "1.10", "openTime": opened["time"], "closeTime": last["time"], "state": "CLOSED", "realizedPL": "2.6", "financing": "-0.2", "averageClosePrice": "1.126", "closingTransactionIDs": ["20", "30"], "stopLossOrder": {"price": "1.115"}}
    return trade, opened, [first, last], [stop, target]


def adapter(handler=None, account="synthetic-account", environment="practice"):
    return OandaHistory(uuid4().hex, account, environment, client=httpx.Client(transport=httpx.MockTransport(handler or (lambda r: httpx.Response(500)))))


def test_partial_closes_costs_and_initial_protection():
    trade, opening, closing, protection = history()
    broker = adapter()
    mapped = broker._map(trade, opening, closing, protection, "USD")
    assert mapped["exit_price"] == pytest.approx(1.126)
    assert mapped["pnl_amount"] == pytest.approx(2.1)  # financing + commissions, no second spread charge
    assert mapped["r_multiple"] == pytest.approx(2.1)
    assert mapped["planned_rr"] == pytest.approx(4)
    assert mapped["stop_loss"] == 1.09
    assert mapped["source_metadata"]["closing_transaction_ids"] == ["20", "30"]
    assert "private-account" not in json.dumps(mapped)
    broker.close()


def test_unknown_risk_and_unallocatable_commission_are_not_invented():
    trade, opening, closing, _ = history()
    broker = adapter()
    mapped = broker._map(trade, opening, closing, [], "GBP")
    assert mapped["stop_loss"] is None and mapped["r_multiple"] is None
    opening["tradesClosed"] = [{"tradeID": "8", "units": "1"}]
    mapped = broker._map(trade, opening, closing, [], "GBP")
    assert not mapped["costs_complete"]
    assert mapped["pnl_amount"] is None and mapped["result"] is None
    assert mapped["broker_realized_pnl"] == 2.6
    broker.close()


def test_short_and_historical_home_conversion():
    trade, opening, closing, protection = history()
    trade["initialUnits"] = "-100"
    opening["tradeOpened"]["units"] = "-100"
    protection[0]["price"] = "1.11"
    protection[1]["price"] = "1.08"
    opening["homeConversionFactors"] = {"lossQuoteHome": {"factor": "0.8"}}
    broker = adapter()
    mapped = broker._map(trade, opening, closing, protection, "GBP")
    assert mapped["direction"] == "short"
    assert mapped["initial_risk_amount"] == pytest.approx(.8)
    assert mapped["r_multiple"] == pytest.approx(2.1 / .8)
    broker.close()


def test_bad_reduction_rejects_entire_trade():
    trade, opening, closing, protection = history()
    closing[0]["tradeReduced"]["units"] = "39"
    broker = adapter()
    with pytest.raises(BrokerHistoryError, match="units"):
        broker._map(trade, opening, closing, protection, "USD")
    broker.close()


def test_get_only_history_and_incremental_hydration():
    trade, opening, closing, protection = history()
    transactions = [opening, *protection, *closing]
    calls = []
    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        suffix = request.url.path.split('/synthetic-account/')[1]
        if suffix == 'summary':
            return httpx.Response(200, json={"account": {"currency": "USD", "lastTransactionID": "30"}})
        if suffix == 'transactions/idrange':
            lo, hi = int(request.url.params['from']), int(request.url.params['to'])
            return httpx.Response(200, json={"transactions": [t for t in transactions if lo <= int(t['id']) <= hi]})
        if suffix.startswith('transactions/'):
            return httpx.Response(200, json={"transaction": next(t for t in transactions if t['id'] == suffix.split('/')[-1])})
        if suffix == 'trades/10':
            return httpx.Response(200, json={"trade": trade})
        if suffix == 'trades':
            assert request.url.params['state'] == 'CLOSED'
            return httpx.Response(200, json={"trades": [trade]})
        raise AssertionError(suffix)
    broker = adapter(handler)
    first = broker.fetch_closed(None)
    second = broker.fetch_closed('20')
    assert first.trades[0]['external_id'] == second.trades[0]['external_id']
    assert first.trades[0]['pnl_amount'] == second.trades[0]['pnl_amount']
    assert second.cursor == '30'
    assert broker.fetch_closed('30').trades == []
    broker.close()


def test_provider_errors_do_not_echo_body_account_or_authorization():
    broker = adapter(lambda request: httpx.Response(401, json={"message": str(request.headers), "url": str(request.url)}))
    with pytest.raises(BrokerHistoryError) as raised:
        broker.fetch_closed(None)
    assert str(raised.value) == "OANDA history request failed (HTTP 401)"
    broker.close()


def test_closed_trade_pagination_and_high_water_mark():
    pages=[]
    def handler(r):
        assert r.method=='GET'
        if r.url.path.endswith('/summary'):
            return httpx.Response(200,json={'account':{'currency':'USD','lastTransactionID':'600'}})
        if r.url.path.endswith('/transactions/idrange'):
            return httpx.Response(200,json={'transactions':[]})
        if r.url.path.endswith('/trades'):
            pages.append(dict(r.url.params))
            # Trades closed after the captured high-water mark are deferred.
            ids=range(600,100,-1) if len(pages)==1 else [100]
            return httpx.Response(200,json={'trades':[{'id':str(i),'state':'CLOSED','closingTransactionIDs':['601']} for i in ids]})
        pytest.fail('Deferred trades must not fetch newer fills')
    broker=adapter(handler)
    result=broker.fetch_closed(None)
    assert result.trades==[] and result.cursor=='600'
    assert pages[1]['beforeID']=='100'
    broker.close()


def test_missing_history_array_cannot_advance_cursor():
    def handler(r):
        if r.url.path.endswith('/summary'):
            return httpx.Response(200,json={'account':{'currency':'USD','lastTransactionID':'31'}})
        return httpx.Response(200,json={})
    broker=adapter(handler)
    with pytest.raises(BrokerHistoryError,match='incomplete history'):
        broker.fetch_closed('30')
    broker.close()


def test_retryable_error_retries_get_without_following_redirects(monkeypatch):
    monkeypatch.setattr('app.brokers.oanda.time.sleep',lambda seconds:None)
    calls=[]
    def handler(r):
        calls.append(r)
        assert r.method=='GET'
        return httpx.Response(429 if len(calls)<3 else 200,json={'ok':True})
    broker=adapter(handler,environment='live')
    assert broker._get('summary')=={'ok':True} and len(calls)==3
    assert all(r.url.host=='api-fxtrade.oanda.com' for r in calls)
    broker.close()


def test_open_trades_are_ignored_and_environments_have_distinct_identity():
    def handler(r):
        if r.url.path.endswith('/summary'):
            return httpx.Response(200,json={'account':{'currency':'USD','lastTransactionID':'1'}})
        return httpx.Response(200,json={'transactions':[],'trades':[{'id':'1','state':'OPEN'}]})
    practice=adapter(handler);live=adapter(handler,environment='live')
    assert practice.fetch_closed(None).trades==[]
    assert practice.account_key!=live.account_key
    practice.close();live.close()


def test_legacy_conversion_and_invalid_timestamp():
    t,o,c,p=history();broker=adapter()
    o['lossQuoteHomeConversionFactor']='0.8'
    assert broker._map(t,o,c,p,'GBP')['initial_risk_amount']==pytest.approx(.8)
    t['openTime']='2026-06-01T23:30:00'
    with pytest.raises(BrokerHistoryError,match='timestamp'):
        broker._map(t,o,c,p,'GBP')
    broker.close()
