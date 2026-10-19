from types import SimpleNamespace as NS
from datetime import datetime, timezone

import pytest

from app.data.providers.mt5_spot_metal import GoldDataRoute, eligible_gold
from app.core.safe_errors import ProviderConfigurationError, MissingHistoryError
from tests.test_mt5_symbol_catalog import setup
from tests.test_mt5_history_hub import wire


def configure(terminal):
    wire(terminal)
    info=NS(name='XAUUSDs',description='Gold spot',currency_base='XAU',currency_profit='USD',
        trade_calc_mode=3,chart_mode=0,expiration_time=0,trade_contract_size=100,
        trade_tick_size=.01,volume_min=.01,volume_step=.01,point=.01,custom=False)
    terminal.rows=[info]
    terminal.symbol_info=lambda name:info if name==info.name else None
    return info


def bounds():
    return datetime(2026,1,2,10,tzinfo=timezone.utc),datetime(2026,1,2,10,3,tzinfo=timezone.utc)


def test_oanda_kept_without_terminal_discovery(setup):
    service,terminal,_=setup
    previous=list(terminal.calls);oanda=object()
    assert GoldDataRoute(oanda,service).resolve() is oanda
    assert terminal.calls==previous


def test_verified_gold_resolves_once_and_keeps_bid_volume_and_account_provenance(setup):
    service,terminal,_=setup;configure(terminal)
    route=GoldDataRoute(None,service);provider=route.resolve()
    before=list(terminal.calls)
    assert route.resolve() is provider and terminal.calls==before
    frame=provider.get_bars('XAUUSD','1m',*bounds())
    assert len(frame)==3
    assert set(frame.broker_symbol)=={'XAUUSDs'} and set(frame.price_basis)=={'bid'}
    assert frame.volume.tolist()==frame.tick_volume.tolist()==[10]*3
    assert provider.research_provenance['broker_execution_parity'] is False
    before=list(terminal.calls)
    assert provider.get_bars('XAUUSD','1m',*bounds()).equals(frame)
    assert terminal.calls==before
    assert provider.cache_namespace.startswith('mt5-gold-bid-v1-')
    assert '123' not in str(provider.research_provenance)


@pytest.mark.parametrize('change',[{'currency_base':'USD'},{'chart_mode':1},{'expiration_time':10},
    {'trade_contract_size':0},{'volume_step':float('nan')},{'custom':True}])
def test_unverified_or_wrong_instrument_never_selected(setup,change):
    service,terminal,_=setup;info=configure(terminal)
    for k,v in change.items():setattr(info,k,v)
    with pytest.raises(ProviderConfigurationError):GoldDataRoute(None,service).resolve()
    assert 'bars' not in terminal.calls


def test_ambiguous_gold_candidates_are_not_ranked_by_name(setup):
    service,terminal,_=setup;info=configure(terminal)
    terminal.rows.append(NS(**{**vars(info),'name':'GOLD247'}))
    with pytest.raises(ProviderConfigurationError,match='exactly one'):GoldDataRoute(None,service).resolve()


def test_selected_account_change_cannot_reuse_pinned_source(setup):
    service,terminal,_=setup;configure(terminal)
    provider=GoldDataRoute(None,service).resolve()
    terminal.login=456
    key=service.discover('mt5-default')['items'][0]['account_key']
    service.select_account('mt5-default',key)
    with pytest.raises(ProviderConfigurationError,match='account changed'):provider.get_bars('XAUUSD','1m',*bounds())


def test_changed_contract_specs_fail_before_market_cache_publication(setup):
    service,terminal,_=setup;info=configure(terminal)
    provider=GoldDataRoute(None,service).resolve();info.trade_contract_size=10
    with pytest.raises(ProviderConfigurationError,match='specifications changed'):provider.get_bars('XAUUSD','1m',*bounds())


def test_daily_and_futures_are_not_silently_reinterpreted(setup):
    service,terminal,_=setup;configure(terminal)
    provider=GoldDataRoute(None,service).resolve()
    for ticker,tf in [('NQ1!','1m'),('XAUUSD','1d')]:
        with pytest.raises(MissingHistoryError):provider.get_bars(ticker,tf,*bounds())
    with pytest.raises(MissingHistoryError):provider.get_quote('XAUUSD')


def test_market_cache_preserves_broker_price_and_volume_semantics(setup,tmp_path):
    from app.services.market_data import MarketDataService
    from app.storage.market_store import MarketStore
    from app.storage.market_cache_repository import MarketCacheRepository
    service,terminal,db=setup;configure(terminal)
    provider=GoldDataRoute(None,service).resolve()
    store=MarketStore(tmp_path/'canonical')
    frame=provider.get_bars('XAUUSD','1m',*bounds())
    store.write_bars(provider.cache_namespace,'XAUUSD','1m',frame)
    cached=store.read_bars(provider.cache_namespace,'XAUUSD','1m')
    assert set(cached.broker_symbol)=={'XAUUSDs'}
    assert set(cached.price_basis)=={'bid'}
    assert set(cached.volume_semantics)=={'tick_count_not_exchange_volume'}
    market=MarketDataService(provider,store,MarketCacheRepository(db))
    spec=market.instrument_info('XAUUSD')
    assert spec.provider_key==provider.key and spec.provider_symbol=='XAUUSDs'
    assert 'OANDA' not in spec.name
