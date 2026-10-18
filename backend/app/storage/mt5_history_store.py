"""Content-addressed Parquet snapshots, with SQLite publishing the manifest last."""
from hashlib import sha256
import json

from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_symbols import fingerprint
from app.storage.market_store import MarketStore


class MT5HistoryStore:
    def __init__(self, database):
        self.database = database
        self.root = database.path.parent / 'market' / 'mt5-hub'

    def key(self, account_key, request):
        return 'mt5_history:' + account_key + ':' + fingerprint(request)

    def cached(self, account_key, request):
        value = self.database.get_setting(self.key(account_key, request))
        if not value:
            return None
        manifest = json.loads(value)
        path = self.root / (manifest['data_fingerprint'] + '.parquet')
        if not path.exists() or self.digest(path) != manifest['data_fingerprint']:
            raise BrokerHistoryError('MT5 history cache failed integrity verification', category='history')
        return manifest

    @staticmethod
    def digest(path):
        digest = sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()

    def save(self, account_key, request, frame, manifest):
        import uuid
        temporary = self.root / (uuid.uuid4().hex + '.parquet')
        try:
            MarketStore(self.root)._atomic_write(temporary, frame)
            digest = self.digest(temporary)
            target = self.root / (digest + '.parquet')
            if not target.exists():
                temporary.replace(target)
            elif self.digest(target) != digest:
                raise BrokerHistoryError('MT5 history cache integrity conflict', category='history')
            manifest = {**manifest, 'data_fingerprint': digest, 'storage_format': 'parquet',
                        'fingerprint_basis': 'sha256_parquet_bytes'}
            self.database.set_setting(self.key(account_key, request), json.dumps(manifest, allow_nan=False))
            return manifest
        finally:
            temporary.unlink(missing_ok=True)

    def coverage(self, account_key):
        with self.database.connect() as connection:
            rows = connection.execute('SELECT value FROM app_settings WHERE key LIKE ? ORDER BY updated_at DESC',
                                      ('mt5_history:' + account_key + ':%',)).fetchall()
        return {'items': [json.loads(row[0]) for row in rows],
                'coverage_basis': 'individual_observed_windows; gaps_not_inferred_filled'}
