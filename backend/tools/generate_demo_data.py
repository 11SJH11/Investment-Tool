"""Generate deterministic, synthetic Ledger data for UI/load testing.

This never touches the normal ./data/ledger.db unless an explicit --target points
there. The default target is ./data/demo/ledger.db.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import math
from pathlib import Path
import random
import sys

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository

SEED = 20260922
KNOWN = [
    ("AAPL", "Apple (demo metrics)"), ("MSFT", "Microsoft (demo metrics)"),
    ("NVDA", "NVIDIA (demo metrics)"), ("AMD", "AMD (demo metrics)"),
    ("AMZN", "Amazon (demo metrics)"), ("META", "Meta (demo metrics)"),
    ("TSLA", "Tesla (demo metrics)"), ("SPY", "SPY ETF (demo metrics)"),
    ("QQQ", "QQQ ETF (demo metrics)"), ("GOOGL", "Alphabet (demo metrics)"),
]
TRADE_SYMBOLS = ["XAUUSD", "NQ1!", "AAPL", "NVDA", "AMD", "SPY"]
SETUPS = ["Liquidity sweep + Type 3", "Opening range breakout", "VWAP mean reversion", "Momentum pullback", "VCP breakout"]
SESSIONS = ["London", "New York", "Asia", "London/New York overlap"]
REGIMES = ["Trending", "Range", "High volatility", "Low volatility", "News-driven"]
MISTAKES = ["Early entry", "Late entry", "Moved stop", "Overtraded", "Chased price", "Ignored higher timeframe"]
CONFLUENCES = ["Liquidity sweep", "FVG", "HTF trend", "VWAP", "Volume expansion", "Session level", "Structure shift"]
EMOTIONS = ["Calm", "Confident", "Impatient", "Hesitant", "Frustrated"]


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def business_days(start: date, end: date):
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += timedelta(days=1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=ROOT / "data" / "demo" / "ledger.db")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--years", type=int, default=3)
    args = parser.parse_args()
    db_path = args.target.resolve()
    if db_path.exists():
        if not args.force:
            raise SystemExit(f"Refusing to overwrite {db_path}; pass --force")
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(SEED)
    db = Database(db_path)
    db.initialize()
    db.set_setting("journal_timezone", "America/New_York")
    db.set_setting("demo_mode", "true")
    db.set_setting("demo_seed", str(SEED))

    end_day = date(2026, 9, 21)
    start_day = end_day - timedelta(days=365 * args.years)
    now = datetime(2026, 9, 21, 20, 0, tzinfo=timezone.utc)

    # 1) Discovery universe + persistent screener snapshots.
    synthetic = [(f"D{n:03d}", f"Demo Company {n:03d}") for n in range(1, 291)]
    securities = KNOWN + synthetic
    with db.connect() as con:
        for i, (ticker, name) in enumerate(securities):
            security_type = "etf" if ticker in {"SPY", "QQQ"} or i % 29 == 0 else ("reit" if i % 31 == 0 else "common_stock")
            exchange = ["NASDAQ", "NYSE", "ARCA"][i % 3]
            con.execute(
                "INSERT INTO securities(ticker,name,asset_type,security_type,exchange,status,tradable,fractionable,shortable,provider,provider_id,cik) VALUES(?,?,?,?,?,'active',1,1,1,'demo',?,?)",
                (ticker, name, "equity", security_type, exchange, f"demo-{ticker}", f"{1000000+i:010d}"),
            )
            price = round(rng.uniform(8, 720), 2)
            shares = rng.uniform(20_000_000, 4_000_000_000)
            eps = rng.uniform(0.4, 24.0)
            con.execute("INSERT INTO market_snapshots(ticker,price,timestamp,source,updated_at) VALUES(?,?,?,?,?)", (ticker, price, iso(now), "demo", iso(now)))
            con.execute(
                """INSERT INTO fundamental_metrics(ticker,cik,company_name,fiscal_year,period_end,revenue,revenue_growth_yoy,net_income,net_margin,operating_income,operating_margin,assets,liabilities,equity,cash,operating_cash_flow,capital_expenditure,free_cash_flow,eps_diluted,shares_outstanding,return_on_equity,source,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ticker, f"{1000000+i:010d}", name, 2025, "2025-12-31", rng.uniform(1e8, 4e11), rng.uniform(-0.15, 0.45), rng.uniform(-5e9, 4e10), rng.uniform(-0.12, 0.35), rng.uniform(-3e9, 5e10), rng.uniform(-0.08, 0.30), rng.uniform(2e8, 8e11), rng.uniform(5e7, 4e11), rng.uniform(1e8, 5e11), rng.uniform(1e7, 1e11), rng.uniform(-2e9, 6e10), -rng.uniform(1e7, 1e10), rng.uniform(-1e9, 5e10), eps, shares, rng.uniform(-0.2, 0.55), "demo", iso(now)),
            )
            ema20 = price * rng.uniform(0.94, 1.04); ema50 = price * rng.uniform(0.90, 1.05); sma200 = price * rng.uniform(0.78, 1.08)
            payload = {
                "close": price, "ema20": ema20, "ema50": ema50, "sma200": sma200,
                "rsi14": rng.uniform(28, 76), "atr": price*rng.uniform(.008,.045), "atr_pct": rng.uniform(.8,4.5),
                "return_5d": rng.uniform(-12,14), "return_20d": rng.uniform(-24,30), "return_60d": rng.uniform(-38,55),
                "relative_volume": rng.uniform(.45,3.8), "average_volume": rng.uniform(150_000,25_000_000),
                "average_dollar_volume": rng.uniform(2e6,4e9), "distance_20d_high": rng.uniform(0,18),
                "distance_52w_high": rng.uniform(0,42), "volatility": rng.uniform(12,90), "gap_pct": rng.uniform(-8,8),
                "trend_aligned": float(price > ema20 > ema50 > sma200), "volume": rng.uniform(80_000,35_000_000), "history_bars": 520,
            }
            con.execute("INSERT INTO technical_snapshots(ticker,payload,source,snapshot_at,updated_at) VALUES(?,?,?,?,?)", (ticker, json.dumps(payload), "demo", iso(now - timedelta(days=1)), iso(now)))

    # 2) Playbooks and review fields.
    playbooks = [
        ("Gold Type 3", "Entry Model"), ("ORB", "Entry Model"), ("VWAP Reversion", "Mean Reversion"), ("Momentum / VCP", "Swing"),
    ]
    playbook_ids = []
    with db.connect() as con:
        for title, category in playbooks:
            review_fields = [
                {"id": "quality", "label": "Setup quality", "type": "choice", "options": ["A", "B", "C"]},
                {"id": "news", "label": "News catalyst", "type": "boolean"},
            ]
            cur = con.execute("INSERT INTO playbook_entries(title,category,description,rules,checklist,notes,sections,review_fields) VALUES(?,?,?,?,?,?,?,?)",
                              (title, category, "Synthetic playbook for UI testing.", "Wait for confirmation; define risk before entry.", "Context\nTrigger\nRisk", "Demo only", json.dumps({"Context":"Use higher-timeframe context"}), json.dumps(review_fields)))
            playbook_ids.append(cur.lastrowid)

    # 3) Dense Journal history: at least one trade every weekday for ~3 years.
    trade_rows = []
    daily_review_rows = []
    trade_id = 0
    for day_index, day in enumerate(business_days(start_day, end_day)):
        trades_today = 1 + (1 if rng.random() < .42 else 0) + (1 if rng.random() < .10 else 0)
        day_rs = []
        for j in range(trades_today):
            trade_id += 1
            symbol = rng.choice(TRADE_SYMBOLS)
            setup = rng.choice(SETUPS)
            session = rng.choices(SESSIONS, [24, 42, 14, 20])[0]
            direction = rng.choice(["long", "short"])
            hour = {"Asia": 1, "London": 8, "New York": 14, "London/New York overlap": 13}[session]
            minute = rng.choice([0, 5, 10, 15, 20, 30, 40, 45, 50])
            opened = datetime.combine(day, time(hour, minute), tzinfo=timezone.utc)
            duration = rng.choice([8, 12, 18, 25, 35, 50, 75, 120])
            closed = opened + timedelta(minutes=duration)
            # Add clustered rough periods so charts contain streaks/drawdowns instead of a smooth synthetic edge.
            rough = (day_index // 55) % 6 == 3
            r_choices = [-1.0, -0.75, -0.5, 0.0, 0.45, 0.8, 1.0, 1.5, 2.0, 2.5, 3.0]
            weights = [30, 8, 4, 3, 5, 7, 9, 12, 13, 5, 4] if rough else [24, 5, 3, 2, 5, 8, 11, 15, 17, 6, 4]
            r_mult = rng.choices(r_choices, weights)[0]
            day_rs.append(r_mult)
            base = {"XAUUSD": 2400, "NQ1!": 20500, "AAPL": 220, "NVDA": 170, "AMD": 155, "SPY": 640}[symbol]
            entry = base * rng.uniform(.85, 1.15)
            risk = max(entry * rng.uniform(.0025, .008), .1)
            sign = 1 if direction == "long" else -1
            stop = entry - sign*risk
            target = entry + sign*risk*2
            exit_price = entry + sign*risk*r_mult
            pnl = round(r_mult * rng.uniform(65, 180), 2)
            result = "win" if r_mult > 0 else "loss" if r_mult < 0 else "breakeven"
            plan = rng.choices(["Yes", "Partially", "No"], [72, 19, 9])[0]
            grade = rng.choices(["A", "B", "C", ""], [32, 42, 18, 8])[0]
            mistakes = [] if result == "win" and rng.random() < .72 else rng.sample(MISTAKES, rng.choice([0,1,1,1,2]))
            confluences = rng.sample(CONFLUENCES, rng.randint(1, min(4, len(CONFLUENCES))))
            review = {
                "mistakes": mistakes, "confluences": confluences, "emotions": rng.sample(EMOTIONS, 1),
                "structure_alignment": rng.choice(["Aligned", "Mixed", "Counter-trend"]),
                "entry_relativity": rng.choice(["Discount", "Equilibrium", "Premium"]),
                "shift": rng.choice(["Confirmed", "Early", "None"]),
                "went_well": "Risk was defined before entry." if plan == "Yes" else "Entry thesis was documented.",
                "went_wrong": rng.choice(["", "Entry was a little early.", "Management reduced the planned reward."]),
                "do_differently": rng.choice(["Keep the same process.", "Wait for a cleaner close.", "Reduce low-quality trades."]),
                "custom": {}, "custom_labels": {},
            }
            pb = rng.choice(playbook_ids)
            review["custom"][f"{pb}:quality"] = grade or "C"
            review["custom"][f"{pb}:news"] = rng.random() < .18
            review["custom_labels"][f"{pb}:quality"] = "Setup quality"
            review["custom_labels"][f"{pb}:news"] = "News catalyst"
            source = rng.choices(["live_manual", "paper_manual", "replay", "backtest"], [55, 12, 18, 15])[0]
            account_currency = "GBP" if rng.random() < .18 else "USD"
            source_meta = {"exit_reason": rng.choice(["target", "stop", "manual", "session_close", "trailing_stop"]), "mfe_r": max(r_mult, 0)+rng.uniform(.05,1.2), "mae_r": -rng.uniform(.05,1.1), "environment":"demo"}
            trade_rows.append((source, f"Demo trade {trade_id}", "Demo", symbol, direction, "closed", iso(opened), iso(closed), entry, exit_price, 1.0, entry, "USD", stop, target, 0.0, result, "computed", pnl, (exit_price-entry)*sign/entry*100, r_mult, 2.0, None, "", "computed", "day_trade", setup, rng.choice(REGIMES), rng.choice(["1m","5m","15m"]), rng.choice(["Aligned","Mixed"]), "", session, "intraday", "", "Synthetic demo trade", "Synthetic entry note", "Synthetic management note", "Synthetic learning note", "Demo data", "{}", "", None, None, json.dumps(source_meta), None, pb, grade, plan, json.dumps(review), "demo-account", account_currency, None, 0.0, 0.0, 0.0, 0.0, abs(pnl/max(abs(r_mult),.25)), "demo", 1))
        if rng.random() < .72:
            daily_review_rows.append((day.isoformat(), "Demo", "Execute only the planned setup", rng.choice(REGIMES), rng.choice(["Calm", "Focused", "Tired", "Confident"]), "Reviewed plan before session", rng.choice(TRADE_SYMBOLS), rng.choice(SESSIONS), ", ".join(rng.sample(SETUPS, 2)), f"Daily result around {sum(day_rs):+.2f}R; process over outcome.", "Stayed aware of pace and risk.", rng.choice(["", "Early entry", "Overtraded once"]), "Defined risk consistently.", "Wait for cleaner confirmation when uncertain.", "Keep screenshots and tag every trade.", "Synthetic review for load testing."))

    trade_cols = ["source","name","account","ticker","direction","status","opened_at","closed_at","entry_price","exit_price","quantity","position_amount","position_currency","stop_loss","take_profit","fees","result","result_source","pnl_amount","pnl_pct","r_multiple","planned_rr","pnl_override","override_reason","pnl_source","trade_type","setup","market_condition","entry_timeframe","timeframe_alignment","dxy","session_time","tf_type","wick","analysis","entry_notes","management","learning","notes","timeframe_notes","external_provider","external_id","external_order_id","source_metadata","imported_at","playbook_id","setup_grade","plan_followed","review_data","external_account_key","account_currency","broker_realized_pnl","financing","commission","guaranteed_execution_fee","dividend_adjustment","initial_risk_amount","risk_source","costs_complete"]
    with db.connect() as con:
        con.executemany(f"INSERT INTO journal_trades({','.join(trade_cols)}) VALUES({','.join('?' for _ in trade_cols)})", trade_rows)
        review_cols = ["review_date","account","focus_goal","market_condition","emotional_state","process","pair","session","setups","learnings","psychology","mistakes","did_well","improve","actionable_steps","thoughts"]
        con.executemany(f"INSERT INTO daily_reviews({','.join(review_cols)}) VALUES({','.join('?' for _ in review_cols)})", daily_review_rows)

    # 4) Portfolio transactions and a broker snapshot for Overview.
    invest = ["AAPL","MSFT","NVDA","AMD","AMZN","META","SPY","QQQ"]
    with db.connect() as con:
        for n in range(96):
            ticker = invest[n % len(invest)]
            occurred = datetime(2023, 10, 1, tzinfo=timezone.utc) + timedelta(days=n*11)
            if occurred.date() > end_day: break
            price = 40 + (n % 17)*7 + rng.uniform(-8, 10)
            qty = rng.uniform(.2, 4.5)
            con.execute("INSERT INTO portfolio_transactions(account,ticker,action,occurred_at,quantity,price,fees,note,input_mode,input_amount,base_currency,asset_currency,fx_rate,fx_source,price_source,price_timestamp,price_overridden,fees_currency) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        ("Demo Investments", ticker, "BUY", iso(occurred), qty, max(1, price), .5, "Synthetic monthly investment", "amount", round(qty*price,2), "GBP", "USD", .78, "demo", "demo", iso(occurred), 0, "GBP"))
        summary = {"currency":"GBP","totalValue":18425.36,"investments":{"unrealizedProfitLoss":1267.42},"cash":{"availableToTrade":913.28}}
        con.execute("INSERT INTO portfolio_broker_accounts(provider,account_key,environment,label,summary,synced_at) VALUES(?,?,?,?,?,?)", ("trading212","demo-t212","demo","Trading 212 demo / synthetic",json.dumps(summary),iso(now)))
        for i,ticker in enumerate(invest):
            facts={"ticker":ticker,"name":ticker,"quantity":round(rng.uniform(1,35),5),"currentPrice":round(rng.uniform(40,700),2),"averagePrice":round(rng.uniform(35,650),2),"currency":"USD"}
            con.execute("INSERT INTO portfolio_broker_records(provider,account_key,kind,external_id,facts,active,note,tags) VALUES(?,?,?,?,?,1,'',?)",("trading212","demo-t212","position",f"pos-{ticker}",json.dumps(facts),json.dumps(["demo"])))

    # 5) Research notes.
    with db.connect() as con:
        for n in range(160):
            published = now - timedelta(days=n*4 + rng.randint(0,3))
            symbol = rng.choice(TRADE_SYMBOLS + invest)
            con.execute("INSERT INTO research_items(source,source_item_id,item_type,instrument,published_at,title,summary,direction,confidence,url,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (rng.choice(["manual","demo-news","demo-research"]), f"demo-{n}", rng.choice(["note","news","thesis"]), symbol, iso(published), f"Demo research note {n+1}: {symbol}", "Synthetic research content used to stress-test layouts and filters.", rng.choice(["bullish","bearish","neutral","mixed"]), round(rng.uniform(.45,.92),2), "", json.dumps({"demo":True,"tags":rng.sample(["macro","earnings","technical","risk"],2)})))

    # 6) Saved backtest research across strategies/roles.
    repo = BacktestRunRepository(db)
    strategies = [
        ("xau_liquidity_type3_baseline_v1", "XAUUSD Liquidity Sweep + Type 3 + 50% · baseline v1.1", "XAUUSD", "1m"),
        ("opening_range_breakout_baseline_v1", "Opening Range Breakout · baseline v1.0", "AAPL", "5m"),
        ("vwap_mean_reversion_baseline_v1", "VWAP Mean Reversion · baseline v1.0", "AAPL", "5m"),
        ("momentum_vcp_breakout_baseline_v1", "Momentum / VCP Breakout · baseline v1.0", "AAPL", "1d"),
    ]
    for n in range(90):
        key, sname, symbol, tf = strategies[n % len(strategies)]
        period_start = start_day + timedelta(days=(n*11) % max(1,(end_day-start_day).days-90))
        period_end = min(end_day, period_start + timedelta(days=rng.randint(45,150)))
        role = "development" if n < 60 else "validation" if n < 80 else "out_of_sample"
        group = f"demo-validation-{(n-60)//2:02d}" if n >= 60 else ""
        trades = rng.randint(18, 240) if tf != "1d" else rng.randint(8, 70)
        expectancy = rng.uniform(-.18,.42)
        total_r = expectancy * trades
        win_rate = rng.uniform(36,68)
        pf = max(.45, rng.uniform(.7,1.8) + expectancy)
        ret = total_r * rng.uniform(.08,.18)
        dd = -abs(rng.uniform(1.2,14.0))
        start_balance=10000.0; ending=start_balance*(1+ret/100); net=ending-start_balance
        eq=[];balance=start_balance;cumr=0.0;peak=start_balance
        sample_trades=[]
        points=max(12,min(60,trades))
        for i in range(points):
            rr=rng.gauss(expectancy,.9);cumr+=rr;balance+=rr*75;peak=max(peak,balance)
            stamp=datetime.combine(period_start + timedelta(days=int((period_end-period_start).days*i/max(1,points-1))), time(16), tzinfo=timezone.utc)
            eq.append({"timestamp":iso(stamp),"equity":round(balance,2),"return_pct":round((balance/start_balance-1)*100,2),"cumulative_r":round(cumr,2),"drawdown_pct":round((balance/peak-1)*100,2),"realized_pnl":round(rr*75,2),"closed_trades":[]})
            if i<20:
                sample_trades.append({"symbol":symbol,"direction":"long" if i%2==0 else "short","entry_time":iso(stamp-timedelta(minutes=30)),"entry_price":100+i,"stop_loss":99+i,"take_profit":102+i,"exit_time":iso(stamp),"exit_price":100+i+rr,"exit_reason":"target" if rr>0 else "stop","planned_rr":2.0,"r_multiple":round(rr,2),"net_pnl":round(rr*75,2),"result":"win" if rr>0 else "loss"})
        metrics={"starting_balance":start_balance,"ending_balance":round(ending,2),"net_pnl":round(net,2),"return_pct":round(ret,2),"trades":trades,"win_rate_pct":round(win_rate,2),"expectancy_r":round(expectancy,3),"total_r":round(total_r,2),"average_planned_rr":2.0,"profit_factor_r":round(pf,2),"max_drawdown_pct":round(dd,2),"longest_losing_streak":rng.randint(2,8)}
        config={"strategy_key":key,"symbols":[symbol],"start_date":period_start.isoformat(),"end_date":period_end.isoformat(),"primary_timeframe":tf,"session":"24h" if symbol=="XAUUSD" else "regular","starting_balance":start_balance}
        result={"strategy":{"key":key,"name":sname},"symbols":[symbol],"primary_timeframe":tf,"session":config["session"],"metrics":metrics,"equity_curve":eq,"trades":sample_trades,"analysis":{"breakdowns":{},"observations":[],"largest_losses":[],"note":"Synthetic demo run; descriptive only."},"data":{"feed":"demo","adjustment":"none","warnings":["Synthetic demo data: do not use for strategy conclusions."]}}
        repo.create(config=config,result=result,name=f"Demo experiment {n+1:02d}",notes="Synthetic run generated for UI/load testing.",test_role=role,experiment_group=group,tags=["demo",key.split('_')[0]])

    counts = {}
    with db.connect() as con:
        for table in ["securities","technical_snapshots","fundamental_metrics","journal_trades","daily_reviews","playbook_entries","portfolio_transactions","research_items","backtest_runs"]:
            counts[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    manifest = {"generated_at": iso(now), "seed": SEED, "years": args.years, "database": str(db_path), "counts": counts, "warning": "All records are synthetic and are only for UI/load testing."}
    (db_path.parent / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
