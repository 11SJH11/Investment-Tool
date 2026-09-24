from contextlib import closing
from types import SimpleNamespace
import sqlite3
import subprocess
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.journal import router
from app.core.config import Settings
from app.services.broker_sync import BrokerSyncService
from app.services.journal import JournalService
from app.storage.database import Database, _SCHEMA
from app.storage.journal_repository import JournalRepository


@pytest.fixture
def journal(tmp_path):
    db = Database(tmp_path / 'journal.db'); db.initialize()
    repo = JournalRepository(db)
    return db, repo, JournalService(repo)


@pytest.fixture
def client(journal, tmp_path):
    db, repo, service = journal
    settings = Settings(_env_file=None, LEDGER_DATA_DIR=tmp_path, OANDA_ACCESS_TOKEN='', OANDA_ACCOUNT_ID='')
    app = FastAPI()
    app.state.services = SimpleNamespace(database=db, journal_repository=repo, journal=service, settings=settings, broker_sync=BrokerSyncService(settings, db))
    app.include_router(router, prefix='/api')
    with TestClient(app) as client:
        yield client


def trade(service, **patch):
    return service.create_trade({'ticker':'XAUUSD','account':'Main','source':'paper_manual','direction':'long',
        'opened_at':'2026-06-01T23:30:00Z','closed_at':'2026-06-03T12:00:00Z',
        'entry_price':100,'exit_price':102,'quantity':1,'stop_loss':99, **patch})


@pytest.mark.parametrize('zone,day,hour', [('UTC','2026-06-01','23:00'),('Europe/London','2026-06-02','00:00'),('America/New_York','2026-06-01','19:00')])
def test_all_journal_views_use_entry_day(journal, zone, day, hour):
    db, repo, service = journal
    trade(service)
    db.set_setting('journal_timezone', zone)
    filters = {'date_from':day,'date_to':day}
    report = repo.report(filters)
    assert report['summary'] == {k:repo.daily(day,'Main')['summary'][k] for k in report['summary']}
    assert report['summary']['trades'] == repo.daily(day,'Main')['summary']['trades'] == 1
    assert report['breakdowns']['entry_hour'][0]['entry_hour'] == hour
    assert repo.calendar('2026-06')[0]['day'] == day
    assert repo.filtered_trades(filters)[0]['journal_date'] == day
    assert repo.daily('2026-06-03','Main')['summary']['trades'] == 0


def test_replay_practised_at_is_separate_from_market_time_and_filterable(journal):
    _, repo, service = journal
    replay = trade(service, source='replay', opened_at='2025-03-14T09:42:00Z', closed_at='2025-03-14T10:03:00Z', practised_at='2026-09-24T15:30:00Z')
    assert replay['opened_at'].startswith('2025-03-14T09:42:00')
    assert replay['practised_at'].startswith('2026-09-24T15:30:00')
    report = repo.report({
        'timezone':'Europe/London',
        'table_filters_json':'{"practised_at":{"kind":"date","operator":"between","min":"2026-09-24","max":"2026-09-24"}}',
    })
    assert [row['id'] for row in report['trades']] == [replay['id']]
    assert report['trades'][0]['journal_date'] == '2025-03-14'
    assert report['trades'][0]['practised_date'] == '2026-09-24'


def test_dst_boundaries_and_mixed_currency_denominators(journal):
    _, repo, service = journal
    for stamp, exit_price, currency in [('2026-03-29T00:30:00Z',102,'USD'),('2026-03-29T01:30:00Z',99,'GBP'),('2026-03-29T02:30:00Z',100,'USD')]:
        trade(service, opened_at=stamp, position_currency=currency, exit_price=exit_price)
    trade(service, opened_at='2026-03-29T02:45:00Z',closed_at=None,exit_price=None)
    r = repo.report({'timezone':'Europe/London'})
    s = r['summary']
    assert s['trades'] == 4 and s['r_trades'] == 3 and s['closed_trades'] == 3
    assert s['win_rate'] == 50 and s['profit_factor_r'] == 2
    assert s['average_r'] == pytest.approx(1/3) and s['total_pnl'] is None
    assert {r['currency']:r['total_pnl'] for r in s['pnl_by_currency']} == {'GBP':-1,'USD':2}
    assert {r['entry_hour'] for r in r['breakdowns']['entry_hour']} == {'00:00','02:00','03:00'}


def test_report_and_calendar_do_not_truncate_at_old_limits(journal):
    db, repo, _ = journal
    with closing(db.connect()) as c, c:
        c.executemany("INSERT INTO journal_trades(source,ticker,opened_at,status,result,r_multiple,pnl_amount) VALUES ('paper_manual','XAUUSD','2026-06-01T12:00:00Z','closed','win',1,1)", [()]*5001)
    assert repo.report()['summary']['trades'] == 5001
    assert repo.calendar('2026-06')[0]['trades'] == 5001
    assert repo.daily('2026-06-01','Main')['summary']['trades'] == 5001


def test_api_manual_review_playbook_daily_and_screenshots(client, journal):
    assert client.get('/api/journal/brokers').json()['status'] == 'not_configured'
    assert client.post('/api/journal/brokers/sync').json()['configured'] is False
    assert client.put('/api/journal/settings',json={'timezone':'not/a-zone'}).status_code == 400
    assert client.put('/api/journal/settings',json={'timezone':'Europe/London'}).status_code == 200
    book = client.post('/api/journal/playbook',json={'title':'Human plan','notes':'Original notes','sections':{'Process':'Wait'},'review_fields':[{'id':'entry','label':'Entry model','type':'multi','options':['Custom model']}]}).json()
    created = client.post('/api/journal/trades',json={'ticker':'XAUUSD','entry_price':100,'exit_price':102,'quantity':1,'opened_at':'2026-06-01T23:30:00Z','closed_at':'2026-06-02T12:00:00Z','stop_loss':99}).json()
    review = {'playbook_id':book['id'],'setup_grade':'A','plan_followed':'Yes','notes':'Keep original freeform','review_data':{'mistakes':['Early'], 'custom':{f"{book['id']}:entry":['Custom model']}}}
    saved = client.patch(f"/api/journal/trades/{created['id']}",json=review)
    assert saved.status_code == 200 and saved.json()['pnl_amount'] == 2
    upload = client.post('/api/journal/attachments',data={'owner_type':'trade','owner_id':created['id'],'slot':'legacy-slot'},files={'file':('old.png',b'image','image/png')})
    assert upload.status_code == 200
    assert client.get(f"/api/journal/trades/{created['id']}").json()['attachments'][0]['slot'] == 'legacy-slot'
    assert client.post('/api/journal/attachments',data={'owner_type':'trade','owner_id':999,'slot':'bad'},files={'file':('bad.png',b'image','image/png')}).status_code == 404
    listing = client.get('/api/journal/trades',params={'playbook_id':book['id'],'setup_grade':'A','limit':1}).json()
    assert listing['total'] == 1 and len(listing['items']) == 1
    assert client.get('/api/journal/options').json()['setup_grade'] == ['A']
    daily = client.get('/api/journal/daily-summary',params={'review_date':'2026-06-02','account':'Main'}).json()
    assert daily['summary']['trades'] == 1 and daily['review'] is None
    for day, account, thoughts in [('2026-06-02','Main','First'),('2026-06-03','Main','Next'),('2026-06-02','Other','Other account')]:
        assert client.post('/api/journal/daily-reviews',json={'review_date':day,'account':account,'thoughts':thoughts}).status_code == 200
    assert client.get('/api/journal/daily-summary',params={'review_date':'2026-06-02','account':'Main'}).json()['review']['thoughts'] == 'First'
    report = client.post('/api/journal/report',json={}).json()
    assert report['breakdowns'][f"playbook_field:{book['id']}:entry"][0]['trades'] == 1
    assert client.delete(f"/api/journal/playbook/{book['id']}").status_code == 200
    after = client.get(f"/api/journal/trades/{created['id']}").json()
    assert after['playbook_id'] is None and after['review_data'] == review['review_data']
    assert after['notes'] == review['notes'] and len(after['attachments']) == 1


def test_broker_api_blocks_facts_and_keeps_supplied_accounting(client,journal):
    _,repo,service = journal
    row = trade(service, source='broker_oanda',external_id='synthetic',external_provider='oanda',pnl_amount=123,pnl_source='broker_reported',r_multiple=None)
    assert row['pnl_amount'] == 123 and row['r_multiple'] is None
    for patch in ({'quantity':9},{'source_metadata':{}},{'source':'paper_manual'},{'pnl_override':5}):
        assert client.patch(f"/api/journal/trades/{row['id']}",json=patch).status_code == 400
    assert client.patch(f"/api/journal/trades/{row['id']}",json={'notes':'Only review'}).status_code == 200
    assert repo.get_trade(row['id'])['pnl_amount'] == 123
    assert client.post('/api/journal/trades',json={'ticker':'XAUUSD','source':'broker_oanda'}).status_code == 400


def test_migration_preserves_all_legacy_rows_and_media(tmp_path):
    path = tmp_path/'legacy.db'
    # Pre-V2 schema, including the original four-source CHECK constraint.
    old_schema = _SCHEMA.replace(" OR source LIKE 'broker_%'", '')
    with closing(sqlite3.connect(path)) as c, c:
        c.executescript(old_schema)
        c.execute("INSERT INTO journal_trades(id,source,ticker,notes,timeframe_notes,source_metadata,external_id) VALUES (41,'replay','XAUUSD','old notes','{\"1H\":\"context\"}','{\"replay\":true}','stable-replay')")
        c.execute("INSERT INTO playbook_entries(id,title,rules,notes) VALUES (31,'Legacy plan','rule','notes')")
        c.execute("INSERT INTO daily_reviews(id,review_date,account,thoughts,pair) VALUES (21,'2026-06-01','Main','old thoughts','Gold')")
        for owner, id in [('trade',41),('playbook',31),('daily_review',21)]:
            c.execute("INSERT INTO media_attachments(owner_type,owner_id,slot,original_name,stored_name,mime_type) VALUES (?,?,'legacy','old.png',?,'image/png')",(owner,id,f'{owner}.png'))
        tables=['journal_trades','playbook_entries','daily_reviews','media_attachments']
        c.row_factory=sqlite3.Row
        original={table:[dict(r) for r in c.execute(f'SELECT * FROM {table}')] for table in tables}
    db=Database(path);db.initialize();db.initialize()
    with closing(db.connect()) as c:
        for table, rows in original.items():
            actual=[dict(r) for r in c.execute(f'SELECT * FROM {table}')]
            assert len(actual)==len(rows)
            for old,new in zip(rows,actual):
                assert {k:new[k] for k in old}==old
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert c.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]==16
    assert JournalRepository(db).get_trade(41)['review_data']=={}


@pytest.mark.parametrize('custom', ['column','index','trigger'])
def test_legacy_migration_stops_before_discarding_unknown_schema(tmp_path,custom):
    path=tmp_path/'unknown.db'
    with closing(sqlite3.connect(path)) as c,c:
        c.executescript(_SCHEMA.replace(" OR source LIKE 'broker_%'",''))
        c.execute("INSERT INTO journal_trades(source,ticker,notes) VALUES ('paper_manual','AAPL','preserve')")
        if custom=='column': c.execute("ALTER TABLE journal_trades ADD COLUMN custom_note TEXT DEFAULT 'preserve'")
        elif custom=='index': c.execute('CREATE INDEX custom_journal_index ON journal_trades(notes)')
        else: c.execute('CREATE TRIGGER custom_journal_trigger AFTER INSERT ON journal_trades BEGIN SELECT 1; END')
    with pytest.raises(RuntimeError,match='migration stopped'):
        Database(path).initialize()
    with closing(sqlite3.connect(path)) as c:
        assert c.execute('SELECT notes FROM journal_trades').fetchone()[0]=='preserve'


@pytest.mark.parametrize('stamp', ['2026-06-01T23:30:00+01:00','2026-06-01T22:30:00Z'])
def test_new_timestamp_storage_is_utc(journal,stamp):
    assert trade(journal[2],opened_at=stamp)['opened_at']=='2026-06-01T22:30:00+00:00'


def test_repositories_import_without_loading_service_container():
    result=subprocess.run([sys.executable,'-c',"from app.storage.broker_sync_repository import BrokerSyncRepository; from app.storage.journal_repository import JournalRepository; import sys; assert 'app.services.container' not in sys.modules"],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
