from datetime import datetime, timezone

from app.services.portfolio import PortfolioService


class Repo:
    def __init__(self): self.rows=[]; self.next=1
    def list_transactions(self, account=None): return [dict(x) for x in self.rows if not account or x["account"]==account]
    def add_transaction(self,p): row={**p,"id":self.next,"account":p.get("account","Main")}; self.next+=1; self.rows.append(row); return row
    def get_transaction(self,i): return next((x for x in self.rows if x["id"]==i),None)
    def delete_transaction(self,i): return False
    def accounts(self): return ["Main"]
class Prices:
    def resolve(self,ticker,when,override=None): return {"price":100.0,"source":"test","timestamp":when.isoformat(),"overridden":False}
class FX:
    def rate(self,a,b,when): return {"rate":2.0,"source":"test"}
    def latest(self,a,b): return {"rate":2.0,"source":"test","date":"2026-01-01"}
class ScreenerRepo:
    def get_metrics(self,t): return {"price":100}
class Screener:
    def refresh_one_price(self,t): pass


def test_sell_can_be_entered_by_base_currency_amount():
    svc=PortfolioService(Repo(),ScreenerRepo(),Screener(),Prices(),FX())
    when="2026-01-02T15:00:00+00:00"
    svc.add_transaction({"ticker":"AAPL","action":"BUY","occurred_at":when,"input_mode":"amount","amount":1000,"base_currency":"GBP","asset_currency":"USD","account":"Main"})
    sell=svc.add_transaction({"ticker":"AAPL","action":"SELL","occurred_at":when,"input_mode":"amount","amount":250,"base_currency":"GBP","asset_currency":"USD","account":"Main"})
    assert sell["quantity"] == 5.0
    assert sell["input_amount"] == 250
