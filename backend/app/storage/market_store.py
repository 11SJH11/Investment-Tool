from datetime import datetime
from pathlib import Path

import pandas as pd
from app.data.futures import PROVENANCE_COLUMNS


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
            return connection.execute(query, params).df()
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
