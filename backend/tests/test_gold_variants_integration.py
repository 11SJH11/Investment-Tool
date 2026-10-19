"""Acceptance for user-owned Gold variants preserved during worktree integration."""
import pandas as pd
import pytest

from app.backtesting.engine import BacktestEngine
from app.backtesting.models import BacktestConfig
from app.backtesting.strategies import strategy_registry
from app.backtesting.strategies.gold_asia_15m_ifvg_research_v1 import GoldAsia15mIfvgResearchV1
from app.backtesting.strategies.gold_asia_15m_ifvg_loss_tests_v2 import GoldIfvgSkip23ETV2
from app.data.instruments import default_trading_weekdays
from tests.test_gold_ifvg_acceptance import fixture


def run(strategy,frames):
    return BacktestEngine(BacktestConfig(trading_weekdays=default_trading_weekdays(['XAUUSD']))).run(
        symbol_frames={'XAUUSD':frames},strategies={'XAUUSD':strategy},primary_timeframe='1m')


def test_all_preserved_gold_variants_are_discoverable():
    keys={s.key for s in strategy_registry.specs()}
    assert {'gold_asia_15m_ifvg_research_v1','gold_ifvg_v2_skip_23et',
        'gold_ifvg_v2_fvg_ratio_020','gold_ifvg_v2_be_050','gold_ifvg_v2_be_080',
        'gold_ifvg_v2_no_be','gold_ifvg_v2_reclaim_exit'}<=keys


@pytest.mark.parametrize('day',['2026-01-04','2026-03-08','2026-11-01'])
def test_t01_preserves_sunday_entry_and_068r_management(day):
    frames=fixture(day,'breakeven')
    baseline=run(GoldAsia15mIfvgResearchV1(),frames)['trades']
    child=run(GoldIfvgSkip23ETV2(),frames)['trades']
    assert len(baseline)==len(child)==1
    for field in ['entry_time','exit_time','entry_price','exit_price','stop_loss','take_profit','r_multiple','quantity']:
        assert child[0][field]==baseline[0][field],field
    assert child[0]['r_multiple']==0
    assert child[0]['metadata']['final_stop_loss']==child[0]['entry_price']


@pytest.mark.parametrize('day',['2026-01-04','2026-03-08','2026-11-01'])
def test_t01_rejects_23et_confirmation_without_altering_v1(day):
    frames=fixture(day)
    for frame in frames.values():frame['timestamp']+=pd.Timedelta(hours=2)
    assert len(run(GoldAsia15mIfvgResearchV1(),frames)['trades'])==1
    assert run(GoldIfvgSkip23ETV2(),frames)['trades']==[]
