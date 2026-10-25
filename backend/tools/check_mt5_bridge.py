"""Opt-in DEMO or LIVE read-only discovery and Journal sync into a NEW temporary DB.

Never opens the user's Ledger database, submits orders or switches accounts.
Run from backend. Credentials are not accepted, returned or printed.
"""
import argparse
import json
from pathlib import Path
import sys
import time
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.brokers.metatrader5 import MetaTrader5History
from app.core.config import Settings
from app.services.broker_connections import BrokerConnections
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository
from app.brokers.mt5_clock_diagnostic import summarize_bridge_samples


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--bridge-url',default='http://127.0.0.1:18765')
    parser.add_argument('--token-file',required=True)
    parser.add_argument('--symbol',default='XAUUSDs')
    confirmation=parser.add_mutually_exclusive_group(required=True)
    confirmation.add_argument('--confirm-demo',action='store_true')
    confirmation.add_argument('--confirm-live-read-only',action='store_true')
    args=parser.parse_args()
    environment='live' if args.confirm_live_read_only else 'demo'
    settings=Settings(_env_file=None,MT5_ENABLED=True,MT5_ENVIRONMENT=environment,MT5_LOGIN='',MT5_PASSWORD='',MT5_SERVER='',MT5_TERMINAL_PATH='',
        MT5_BRIDGE_URL=args.bridge_url,MT5_BRIDGE_TOKEN_FILE=args.token_file,BROKER_PROFILES_JSON='[]',BROKER_PROFILES_FILE='')
    with TemporaryDirectory(prefix='ledger-mt5-bridge-acceptance-') as folder:
        database=Database(Path(folder)/'isolated.db');database.initialize()
        connections=BrokerConnections(settings,database)
        discovery=connections.discover('mt5-default')
        if len(discovery['items'])!=1 or discovery['items'][0]['environment']!=environment:raise RuntimeError('Pinned environment identity required')
        key=discovery['items'][0]['account_key'];connections.select_account('mt5-default',key)
        first=connections.sync('mt5-default');second=connections.sync('mt5-default')
        if second['created']!=0:raise RuntimeError('Repeat sync unexpectedly created trades; inspect ongoing broker changes')
        adapter=MetaTrader5History({'bridge_url':args.bridge_url,'bridge_token_file':args.token_file},environment)
        try:
            adapter.connect(key)
            clock_samples=[]
            for index in range(5):
                clock_samples.append(adapter._module.tick_diagnostics(args.symbol))
                if index<4:time.sleep(1)
            diagnostics=clock_samples[-1]
        finally:adapter.close()
        safe=lambda value:{k:value.get(k) for k in ('created','executions_changed','deals_retrieved','positions_processed','closed_trades_imported') if k in value}
        print(json.dumps(dict(environment=environment,account_key=key,first_sync=safe(first),repeat_sync=safe(second),
            journal_trades=len(JournalRepository(database).list_trades()),tick_diagnostics=diagnostics,
            clock_samples=clock_samples,clock_summary=summarize_bridge_samples(clock_samples),
            orders_sent=False,existing_database_touched=False),indent=2))


if __name__=='__main__':main()
