import json
import pytest
from app.core.journal_analytics import filter_trades,report,table_rules

@pytest.fixture
def rows():
    return [dict(id=i,ticker='AAPL' if i!=2 else 'MSFT',status='closed',opened_at=f'2026-09-0{i}T23:40:00Z',closed_at=f'2026-09-0{i}T23:50:00Z',r_multiple=r,pnl_amount=p,position_currency=c,result=result,source='paper_manual',review_data={'confluences':['trend']},source_metadata={},notes='keep',quantity=1) for i,r,p,c,result in [(1,2,20,'USD','win'),(2,-1,-10,'GBP','loss'),(3,0,0,'USD','breakeven')]]

def test_header_filters_summary_currency_and_zero_bounds(rows):
    filters={'timezone':'UTC','table_filters_json':json.dumps({'r_multiple':{'kind':'number','operator':'greater','min':'0'}})}
    selected=filter_trades(rows,filters);assert [t['id'] for t in selected]==[1]
    totals=report(selected,filters)['summary'];assert totals['trades']==1 and totals['total_r']==2 and totals['win_rate']==100
    all_rows=report(rows,filters)['summary'];assert all_rows['total_pnl'] is None and len(all_rows['pnl_by_currency'])==2
    filters['table_filters_json']=json.dumps({'r_multiple':{'kind':'number','operator':'between','min':'0','max':'0'}})
    assert [t['id'] for t in filter_trades(rows,filters)]==[3]

def test_header_date_uses_journal_timezone_and_combines_with_dimensions(rows):
    filters={'timezone':'Europe/London','table_filters_json':json.dumps({'opened_at':{'kind':'date','min':'2026-09-02','max':'2026-09-02'}}),'dimensions_json':json.dumps({'ticker':['AAPL','MSFT']})}
    assert [t['id'] for t in filter_trades(rows,filters)]==[1]
    filters['search']='does not exist';assert filter_trades(rows,filters)==[]

def test_sort_missing_numeric_last_and_does_not_mutate(rows):
    rows.append({**rows[0],'id':4,'r_multiple':None})
    selected=filter_trades(rows,{'timezone':'UTC','table_sort_json':json.dumps({'key':'r_multiple','direction':'desc'})})
    assert [t['id'] for t in selected]==[1,3,2,4]
    assert [t['id'] for t in rows]==[1,2,3,4]

def test_descriptive_buckets_curves_and_sample_counts(rows):
    r=report(rows,{'timezone':'Europe/London'})
    assert r['breakdowns']['entry_10min'][0]['entry_10min']=='00:40'
    assert r['breakdowns']['entry_30min'][0]['entry_30min']=='00:30'
    assert r['breakdowns']['confluence'][0]['trades']==3
    assert [p['cumulative_r'] for p in r['r_curve']]==[2,1,1]
    assert [p['drawdown_r'] for p in r['r_curve']]==[0,-1,-1]
    assert r['r_curve'][-1]['rolling_expectancy']==pytest.approx(1/3)
    assert r['r_curve'][-1]['n']==3

@pytest.mark.parametrize('rule',[{'bad':[]},{'quantity':{'kind':'number','min':'NaN'}},{'opened_at':{'kind':'date','min':'bad'}},{'ticker':[1]},{'quantity':{'kind':'number','operator':'sql'}}])
def test_invalid_table_filters_rejected(rule):
    with pytest.raises(ValueError,match='table filter'):table_rules({'table_filters_json':json.dumps(rule)})


def test_same_day_sort_uses_timestamp_and_full_options_remain_available(rows):
    from app.core.journal_analytics import filter_options
    rows[1]['opened_at']='2026-09-01T10:00:00Z'
    selected=filter_trades(rows,{'timezone':'UTC','table_sort_json':json.dumps({'key':'opened_at','direction':'asc'})})
    assert [t['id'] for t in selected]==[2,1,3]
    assert filter_options(rows,'UTC')['currency']==['GBP','USD']


def test_text_zero_matches_frontend_semantics():
    from app.core.journal_analytics import table_match
    assert table_match(0,'0')
    assert not table_match(None,'0')
