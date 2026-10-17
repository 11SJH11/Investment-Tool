"""Descriptive metrics for one independent shadow account; no portfolio pooling."""
from zoneinfo import ZoneInfo
from .bars import stamp


def summarize(trades, starting_balance, current_equity, observations):
    pnl = [t['net_pnl'] for t in trades]
    rs = [t['r_multiple'] for t in trades if t.get('r_multiple') is not None]
    wins = [v for v in pnl if v>1e-9]
    losses = [v for v in pnl if v< -1e-9]
    def pf(values):
        profit = sum(max(0,v) for v in values)
        loss = -sum(min(0,v) for v in values)
        return profit/loss if loss else None
    peak = starting_balance
    dd_cash = dd_pct = 0
    days = set()
    for timestamp, equity in observations:
        days.add(stamp(timestamp).astimezone(ZoneInfo('America/New_York')).date())
        peak = max(peak,equity)
        dd_cash = max(dd_cash,peak-equity)
        dd_pct = max(dd_pct,100*(peak-equity)/peak if peak else 0)
    return dict(n=len(trades),low_sample=len(trades)<30,observed_sessions=len(days),
                wins=len(wins),losses=len(losses),breakeven=len(pnl)-len(wins)-len(losses),
                win_rate_pct=100*len(wins)/len(pnl) if pnl else None,
                profit_factor=pf(pnl),r_sample_size=len(rs),average_r=sum(rs)/len(rs) if rs else None,
                total_r=sum(rs) if rs else None,
                return_pct=100*(current_equity/starting_balance-1) if starting_balance else None,
                max_drawdown_cash=dd_cash if days else None,max_drawdown_pct=dd_pct if days else None,
                long_profit_factor=pf([t['net_pnl'] for t in trades if t['direction']=='long']),
                short_profit_factor=pf([t['net_pnl'] for t in trades if t['direction']=='short']),
                average_winner=sum(wins)/len(wins) if wins else None,
                average_loser=sum(losses)/len(losses) if losses else None,
                largest_winner=max(wins) if wins else None,largest_loser=min(losses) if losses else None,
                session_close_winners=sum(t['net_pnl']>1e-9 and t.get('exit_reason')=='session_close' for t in trades),
                note='Closed-trade statistics; return and drawdown use recorded marked equity. PF unavailable without losses. Observed sessions are sessions with checkpoints, not elapsed calendar days. Low sample means fewer than 30 closed trades, not a confidence test.')


def deployment_metrics(connection, deployment):
    observations = connection.execute("""SELECT decision_at,
        json_extract(evidence_json,'$.equity_point.equity')
        FROM forward_checkpoints WHERE deployment_id=? ORDER BY decision_at""", (deployment['id'],))
    return summarize(deployment['state']['trade_history'],
                     deployment['definition']['engine']['starting_balance'],
                     deployment['state']['equity'], observations)
