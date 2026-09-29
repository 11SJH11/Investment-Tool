from app.performance import timed, profiled, measure
from datetime import datetime
from pathlib import Path
import json
import os

import pandas as pd
from app.data.futures import PROVENANCE_COLUMNS
from app.frame_cache import frames
from app.performance import count


_REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
_OPTIONAL_COLUMNS = PROVENANCE_COLUMNS


class MarketStore:
    """Local OHLCV cache: Parquet files namespaced by provider/feed/adjustment."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, namespace: str, ticker: str, timeframe: str) -> Path:
        safe_namespace = namespace.replace("/", "-")
        safe_ticker = ticker.upper().replace("/", "-")
        return self.root / "bars" / safe_namespace / timeframe / f"{safe_ticker}.parquet"

    def write_bars(self, namespace: str, ticker: str, timeframe: str, bars: pd.DataFrame) -> Path:
        import duckdb

        frame = self._normalize(bars)
        path = self._path(namespace, ticker, timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            existing = self.read_bars(namespace, ticker, timeframe)
            frame = self._normalize(pd.concat([existing, frame], ignore_index=True))

        connection = duckdb.connect()
        try:
            connection.register("bars_df", frame)
            target = str(path).replace("'", "''")
            connection.execute(f"COPY bars_df TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        finally:
            connection.close()
        return path

    def replace_bars(self, namespace: str, ticker: str, timeframe: str, bars: pd.DataFrame) -> Path:
        """Atomically replace a derived cache file without merging stale rows."""
        import duckdb
        frame = self._normalize(bars)
        path = self._path(namespace, ticker, timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        connection = duckdb.connect()
        try:
            connection.register('bars_df', frame)
            target = str(tmp).replace("'", "''")
            connection.execute(f"COPY bars_df TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        finally:
            connection.close()
        os.replace(tmp, path)
        frames.clear()
        return path

    def metadata_path(self, category: str, namespace: str, ticker: str, timeframe: str) -> Path:
        safe_namespace = namespace.replace('/', '-')
        safe_ticker = ticker.upper().replace('/', '-')
        return self.root / 'metadata' / category / safe_namespace / timeframe / f'{safe_ticker}.json'

    def read_metadata(self, category: str, namespace: str, ticker: str, timeframe: str):
        path = self.metadata_path(category, namespace, ticker, timeframe)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def write_metadata(self, category: str, namespace: str, ticker: str, timeframe: str, document: dict) -> Path:
        path = self.metadata_path(category, namespace, ticker, timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(document, sort_keys=True, default=str), encoding='utf-8')
        os.replace(tmp, path)
        return path

    def list_metadata(self, category: str) -> list[dict]:
        """Return readable metadata documents without exposing filesystem paths.

        Metadata is deliberately separate from OHLCV payloads, so diagnostics can
        describe durable continuous-futures snapshots without opening Parquet.
        Malformed/stale documents are ignored rather than breaking Settings.
        """
        root = self.root / 'metadata' / category
        if not root.exists():
            return []
        documents: list[dict] = []
        for path in sorted(root.rglob('*.json')):
            try:
                value = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if isinstance(value, dict):
                documents.append(value)
        return documents

    @timed('parquet_read')
    def read_bars(
        self,
        namespace: str,
        ticker: str,
        timeframe: str,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
    ) -> pd.DataFrame:
        import duckdb

        path = self._path(namespace, ticker, timeframe)
        if not path.exists():
            return pd.DataFrame(columns=_REQUIRED_COLUMNS)

        stat = path.stat()
        identity = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        begin = pd.Timestamp(start) if start is not None else pd.Timestamp.min.tz_localize('UTC')
        finish = pd.Timestamp(end) if end is not None else pd.Timestamp.max.tz_localize('UTC')
        begin = begin.tz_localize('UTC') if begin.tzinfo is None else begin.tz_convert('UTC')
        finish = finish.tz_localize('UTC') if finish.tzinfo is None else finish.tz_convert('UTC')
        cached = frames.range_get(identity, begin, finish)
        if cached is not None:
            return cached

        clauses: list[str] = []
        params: list = [str(path)]
        if start is not None:
            clauses.append("timestamp >= ?")
            params.append(str(start))
        if end is not None:
            clauses.append("timestamp <= ?")
            params.append(str(end))

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM read_parquet(?) {where} ORDER BY timestamp"
        connection = duckdb.connect()
        try:
            count('parquet_physical_read')
            result = connection.execute(query, params).df()
            frames.put(('range', identity, begin, finish), result)
            return result
        finally:
            connection.close()

    @staticmethod
    def _normalize(bars: pd.DataFrame) -> pd.DataFrame:
        frame = bars.copy()
        if "timestamp" not in frame.columns and isinstance(frame.index, pd.DatetimeIndex):
            index_name = frame.index.name or "index"
            frame = frame.reset_index().rename(columns={index_name: "timestamp"})

        missing = [column for column in _REQUIRED_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"Missing OHLCV columns: {', '.join(missing)}")

        columns = _REQUIRED_COLUMNS + [column for column in _OPTIONAL_COLUMNS if column in frame.columns]
        frame = frame[columns]
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.drop_duplicates("timestamp", keep="last")
        return frame.sort_values("timestamp").reset_index(drop=True)
