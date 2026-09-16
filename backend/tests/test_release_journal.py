import json

import pytest

from app.core.journal_analytics import DIMENSIONS, filter_options, filter_trades, summary
from tests.test_journal_v2 import client, journal, trade


def filters(**dimensions):
    return {'dimensions_json': json.dumps(dimensions), 'timezone': 'Europe/London'}


@pytest.mark.parametrize('dimension', DIMENSIONS)
def test_every_dimension_matches_values_without_splitting_labels(dimension):
    row = dict(id=1, opened_at='2026-06-01T23:30:00Z', source_metadata={}, review_data={})
    if dimension == 'environment':
        row['source_metadata']['environment'] = 'demo'
    elif dimension in ('structure_alignment','entry_relativity','shift','confluences','mistakes','emotions'):
        row['review_data'][dimension] = ['A / B', 'C']
    elif dimension not in ('weekday','entry_hour','month'):
        row[dimension] = 'A / B'
    values = filter_options([row], 'Europe/London')[dimension]
    assert len(filter_trades([row], filters(**{dimension: values}))) == 1
    assert filter_trades([row], filters(**{dimension: ['absent']})) == []


def test_or_within_and_across_dimensions_and_timezone(journal):
    _, repo, service = journal
    a = trade(service, ticker='AAPL', account='One', review_data={'mistakes':['Early','Late']})
    b = trade(service, ticker='MSFT', account='One', review_data={'mistakes':['Early']})
    trade(service, ticker='AAPL', account='Two')
    f = {**filters(ticker=['AAPL','MSFT'], account=['One'], mistakes=['Early','Unknown'], weekday=['Tuesday'],entry_hour=['00:00'],month=['2026-06']), 'date_from':'2026-06-02','date_to':'2026-06-02'}
    assert {t['id'] for t in repo.filtered_trades(f)} == {a['id'],b['id']}
    assert repo.report(f)['summary']['trades'] == 2
    assert repo.calendar('2026-06',filters=f)[0]['trades'] == 2


def test_metrics_denominators_missing_excursions_and_separate_currencies(journal):
    _, repo, service = journal
    trade(service, setup_grade='A', plan_followed='Yes', source_metadata={'mfe_per_share':3,'mae_per_share':0.5})
    trade(service, exit_price=99, position_currency='GBP', setup_grade='B', plan_followed='No',source_metadata={'mfe_r':0.25,'mae_r':1})
    trade(service, exit_price=100, source_metadata={'mfe_per_share':'legacy unknown','mae_r':'NaN'})
    trade(service, exit_price=None,closed_at=None)
    s = repo.report()['summary']
    assert (s['trades'],s['closed_trades'],s['wins'],s['losses'],s['breakevens']) == (4,3,1,1,1)
    assert s['average_winner_r'] == 2 and s['average_loser_r'] == -1
    assert s['average_mfe_r'] == 1.625 and s['average_mae_r'] == .75
    assert s['mfe_trades'] == s['mae_trades'] == s['plan_trades'] == 2
    assert s['plan_followed_pct'] == 50 and s['duration_trades'] == 3
    assert s['grade_distribution'] == {'A':1,'B':1,'Unlabelled':2}
    assert s['total_pnl'] is None
    assert {v['currency']:v['total_pnl'] for v in s['pnl_by_currency']} == {'USD':2,'GBP':-1}
    empty = summary([])
    assert empty['trades'] == 0 and empty['average_mfe_r'] is None


def test_api_filters_and_options_share_timezone(client, journal):
    _, _, service = journal
    trade(service,ticker='AAPL'); trade(service,ticker='MSFT')
    f = filters(ticker=['AAPL'],entry_hour=['00:00'])
    assert client.get('/api/journal/trades',params=f).json()['total'] == 1
    assert client.post('/api/journal/report',json=f).json()['summary']['trades'] == 1
    assert client.get('/api/journal/options',params={'timezone':'Europe/London'}).json()['entry_hour'] == ['00:00']
    for invalid in ('[1]', '{', '{"ticker":"AAPL"}', '{"unknown":[]}'):
        assert client.get('/api/journal/trades',params={'dimensions_json':invalid}).status_code == 400
        assert client.post('/api/journal/report',json={'dimensions_json':invalid}).status_code == 400


def test_option_reorder_removal_preserves_field_id_answers_and_legacy_label(client):
    book = client.post('/api/journal/playbook',json={'title':'Plan','review_fields':[{'id':'stable','label':'Question','type':'select','options':['A / B','C']}]}).json()
    saved = client.post('/api/journal/trades',json={'ticker':'AAPL','playbook_id':book['id'],'review_data':{'custom':{f"{book['id']}:stable":'A / B'}}}).json()
    for options in (['C','A / B','D'],['D','C']):
        response=client.patch(f"/api/journal/playbook/{book['id']}",json={'title':'Plan','review_fields':[{'id':'stable','label':'Renamed','type':'select','options':options}]})
        assert response.status_code == 200
        assert response.json()['review_fields'][0]['options'] == options
        assert client.get(f"/api/journal/trades/{saved['id']}").json()['review_data'] == saved['review_data']
