from types import SimpleNamespace
from contextlib import closing
import json

import httpx
import pytest

from app.data.http import JsonHttpClient, ProviderHttpError, _redact_text, _redact_url
from app.services.screener import ScreenerService
from app.storage.database import Database


def test_provider_error_redacts_bearer_json_and_account_path():
    for text in ['Authorization: Bearer synthetic-credential', '{"access_token":"synthetic-credential"}', "{'api_key': 'synthetic-credential'}"]:
        assert 'synthetic-credential' not in _redact_text(text)
    assert 'private-account' not in _redact_url('https://example.test/v3/accounts/private-account/trades')
    client=JsonHttpClient(max_attempts=1)
    client._client.close()
    def handler(request):
        raise httpx.ConnectError('Authorization: Bearer synthetic-credential',request=request)
    client._client=httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderHttpError) as raised:
        client.get_json('https://example.test/v3/accounts/private-account/trades')
    assert 'synthetic-credential' not in str(raised.value) and 'private-account' not in str(raised.value)
    client.close()


def test_screener_partial_failures_remain_visible_without_echoing_secrets(tmp_path,caplog):
    db=Database(tmp_path/'db');db.initialize()
    with closing(db.connect()) as c,c:
        c.executemany("INSERT INTO securities(ticker,name,provider,tradable) VALUES (?,?,'alpaca',1)",[('A','A'),('B','B'),('C','C')])
    class Provider:
        live_feed='iex'
        def get_latest_bars(self,symbols):
            if symbols==['A','B']:
                return [{'ticker':'A'}]
            raise RuntimeError('Bearer synthetic-credential')
    repo=SimpleNamespace(upsert_snapshots=lambda rows,source:len(rows))
    result=ScreenerService(repo,SimpleNamespace(database=db),alpaca=Provider()).refresh_price_snapshots(chunk_size=2)
    assert result['requested']==3 and result['stored']==1 and result['failed']==2
    assert result['diagnostics']==[{'batch':1,'symbols':['B'],'reason':'No usable bar returned'},{'batch':2,'symbols':['C'],'reason':'RuntimeError'}]
    assert 'synthetic-credential' not in json.dumps(result)+caplog.text
