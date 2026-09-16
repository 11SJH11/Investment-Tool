import sqlite3
from pathlib import Path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS securities (
    ticker TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    asset_type TEXT NOT NULL DEFAULT 'equity',
    security_type TEXT NOT NULL DEFAULT 'common_stock',
    exchange TEXT,
    status TEXT,
    tradable INTEGER,
    fractionable INTEGER,
    shortable INTEGER,
    provider TEXT NOT NULL,
    provider_id TEXT,
    cik TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_securities_name ON securities(name);
CREATE INDEX IF NOT EXISTS idx_securities_exchange ON securities(exchange);
CREATE INDEX IF NOT EXISTS idx_securities_cik ON securities(cik);

CREATE TABLE IF NOT EXISTS market_cache_coverage (
    namespace TEXT NOT NULL,
    ticker TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    covered_start TEXT NOT NULL,
    covered_end TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(namespace, ticker, timeframe)
);

CREATE TABLE IF NOT EXISTS json_cache (
    namespace TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    payload TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(namespace, cache_key)
);

-- Phase 3: locally queryable screener snapshots. Fundamental values are sourced
-- from SEC filings; price snapshots are sourced from the configured market feed.
CREATE TABLE IF NOT EXISTS fundamental_metrics (
    ticker TEXT PRIMARY KEY REFERENCES securities(ticker) ON DELETE CASCADE,
    cik TEXT,
    company_name TEXT,
    fiscal_year INTEGER,
    period_end TEXT,
    revenue REAL,
    revenue_growth_yoy REAL,
    net_income REAL,
    net_margin REAL,
    operating_income REAL,
    operating_margin REAL,
    assets REAL,
    liabilities REAL,
    equity REAL,
    cash REAL,
    operating_cash_flow REAL,
    capital_expenditure REAL,
    free_cash_flow REAL,
    eps_diluted REAL,
    shares_outstanding REAL,
    return_on_equity REAL,
    source TEXT NOT NULL DEFAULT 'sec',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fundamental_revenue_growth ON fundamental_metrics(revenue_growth_yoy);
CREATE INDEX IF NOT EXISTS idx_fundamental_net_margin ON fundamental_metrics(net_margin);
CREATE INDEX IF NOT EXISTS idx_fundamental_roe ON fundamental_metrics(return_on_equity);

CREATE TABLE IF NOT EXISTS market_snapshots (
    ticker TEXT PRIMARY KEY REFERENCES securities(ticker) ON DELETE CASCADE,
    price REAL NOT NULL,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_market_snapshots_price ON market_snapshots(price);


-- Phase 4: portfolio transaction ledger. Holdings are derived from this event log.
CREATE TABLE IF NOT EXISTS portfolio_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL DEFAULT 'Main',
    ticker TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('BUY','SELL')),
    occurred_at TEXT NOT NULL,
    quantity REAL NOT NULL CHECK(quantity > 0),
    price REAL NOT NULL CHECK(price >= 0),
    fees REAL NOT NULL DEFAULT 0 CHECK(fees >= 0),
    note TEXT NOT NULL DEFAULT '',
    input_mode TEXT NOT NULL DEFAULT 'quantity',
    input_amount REAL,
    base_currency TEXT NOT NULL DEFAULT 'GBP',
    asset_currency TEXT NOT NULL DEFAULT 'USD',
    fx_rate REAL,
    fx_source TEXT,
    price_source TEXT,
    price_timestamp TEXT,
    price_overridden INTEGER NOT NULL DEFAULT 0,
    fees_currency TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_portfolio_tx_ticker ON portfolio_transactions(ticker);
CREATE INDEX IF NOT EXISTS idx_portfolio_tx_account ON portfolio_transactions(account);
CREATE INDEX IF NOT EXISTS idx_portfolio_tx_time ON portfolio_transactions(occurred_at);

-- Phase 4: unified journal trade model. Execution facts are user/broker supplied;
-- objective result/P&L/R values are derived consistently by the service.
CREATE TABLE IF NOT EXISTS journal_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL CHECK(source IN ('live_manual','paper_manual','replay','backtest') OR source LIKE 'broker_%'),
    name TEXT NOT NULL DEFAULT 'Trade',
    account TEXT NOT NULL DEFAULT 'Main',
    ticker TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'long' CHECK(direction IN ('long','short')),
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed')),
    opened_at TEXT,
    closed_at TEXT,
    entry_price REAL,
    exit_price REAL,
    quantity REAL,
    position_amount REAL,
    position_currency TEXT NOT NULL DEFAULT 'USD',
    stop_loss REAL,
    take_profit REAL,
    fees REAL NOT NULL DEFAULT 0,
    result TEXT CHECK(result IN ('win','loss','breakeven') OR result IS NULL),
    result_source TEXT CHECK(result_source IN ('manual','computed') OR result_source IS NULL),
    pnl_amount REAL,
    pnl_pct REAL,
    r_multiple REAL,
    planned_rr REAL,
    pnl_override REAL,
    override_reason TEXT NOT NULL DEFAULT '',
    pnl_source TEXT,
    trade_type TEXT NOT NULL DEFAULT '',
    setup TEXT NOT NULL DEFAULT '',
    market_condition TEXT NOT NULL DEFAULT '',
    entry_timeframe TEXT NOT NULL DEFAULT '',
    timeframe_alignment TEXT NOT NULL DEFAULT '',
    dxy TEXT NOT NULL DEFAULT '',
    session_time TEXT NOT NULL DEFAULT '',
    tf_type TEXT NOT NULL DEFAULT '',
    wick TEXT NOT NULL DEFAULT '',
    analysis TEXT NOT NULL DEFAULT '',
    entry_notes TEXT NOT NULL DEFAULT '',
    management TEXT NOT NULL DEFAULT '',
    learning TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    timeframe_notes TEXT NOT NULL DEFAULT '{}',
    external_provider TEXT NOT NULL DEFAULT '',
    external_id TEXT,
    external_order_id TEXT,
    source_metadata TEXT NOT NULL DEFAULT '{}',
    imported_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_journal_trades_ticker ON journal_trades(ticker);
CREATE INDEX IF NOT EXISTS idx_journal_trades_source ON journal_trades(source);
CREATE INDEX IF NOT EXISTS idx_journal_trades_opened ON journal_trades(opened_at);
CREATE INDEX IF NOT EXISTS idx_journal_trades_setup ON journal_trades(setup);

-- Phase 6.3: normalised research/source records. External providers can be added
-- without creating provider-specific UI/storage tables. The source-specific raw
-- fields live in metadata_json; common fields remain queryable.
CREATE TABLE IF NOT EXISTS research_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_item_id TEXT NOT NULL DEFAULT '',
    item_type TEXT NOT NULL DEFAULT 'note',
    instrument TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL DEFAULT 'neutral' CHECK(direction IN ('bullish','bearish','neutral','mixed','unknown')),
    confidence REAL,
    url TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_research_items_instrument ON research_items(instrument);
CREATE INDEX IF NOT EXISTS idx_research_items_source ON research_items(source);
CREATE INDEX IF NOT EXISTS idx_research_items_published ON research_items(published_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_research_items_external ON research_items(source, source_item_id) WHERE source_item_id != '';

CREATE TABLE IF NOT EXISTS daily_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_date TEXT NOT NULL,
    account TEXT NOT NULL DEFAULT 'Main',
    focus_goal TEXT NOT NULL DEFAULT '',
    market_condition TEXT NOT NULL DEFAULT '',
    emotional_state TEXT NOT NULL DEFAULT '',
    process TEXT NOT NULL DEFAULT '',
    pair TEXT NOT NULL DEFAULT '',
    session TEXT NOT NULL DEFAULT '',
    setups TEXT NOT NULL DEFAULT '',
    learnings TEXT NOT NULL DEFAULT '',
    psychology TEXT NOT NULL DEFAULT '',
    mistakes TEXT NOT NULL DEFAULT '',
    did_well TEXT NOT NULL DEFAULT '',
    improve TEXT NOT NULL DEFAULT '',
    actionable_steps TEXT NOT NULL DEFAULT '',
    thoughts TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(review_date, account)
);
CREATE INDEX IF NOT EXISTS idx_daily_reviews_date ON daily_reviews(review_date);

CREATE TABLE IF NOT EXISTS playbook_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Entry Model',
    description TEXT NOT NULL DEFAULT '',
    rules TEXT NOT NULL DEFAULT '',
    checklist TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS media_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_type TEXT NOT NULL CHECK(owner_type IN ('trade','daily_review','playbook')),
    owner_id INTEGER NOT NULL,
    slot TEXT NOT NULL DEFAULT '',
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL UNIQUE,
    mime_type TEXT NOT NULL,
    caption TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_media_owner ON media_attachments(owner_type, owner_id);

-- Phase 5.2: persistent Strategy Lab run history. The full configuration and
-- deterministic result snapshot are stored so a historical run can be opened
-- and compared without silently re-running it against changed data/code.
CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    test_role TEXT NOT NULL DEFAULT 'development' CHECK(test_role IN ('development','validation','out_of_sample','unclassified')),
    experiment_group TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    strategy_key TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    symbols TEXT NOT NULL DEFAULT '[]',
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    primary_timeframe TEXT NOT NULL,
    session TEXT NOT NULL,
    config_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    trades INTEGER NOT NULL DEFAULT 0,
    expectancy_r REAL,
    total_r REAL,
    net_pnl REAL,
    return_pct REAL,
    max_drawdown_pct REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_created ON backtest_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy ON backtest_runs(strategy_key);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_role ON backtest_runs(test_role);
"""


def _migrate_schema(connection: sqlite3.Connection) -> None:
    """Apply additive migrations needed by existing local Ledger databases."""
    columns = {row[1] for row in connection.execute("PRAGMA table_info(securities)").fetchall()}
    added_security_type = "security_type" not in columns
    if added_security_type:
        connection.execute(
            "ALTER TABLE securities ADD COLUMN security_type TEXT NOT NULL DEFAULT 'common_stock'"
        )

        # Phase 3.1: classify the rows that already existed before this column.
        # Future symbol refreshes set security_type through the provider instead.
        connection.execute(
            """
            UPDATE securities
            SET security_type = CASE
                WHEN UPPER(name) LIKE '%WARRANT%' THEN 'warrant'
                WHEN UPPER(name) LIKE '% UNITS%' OR UPPER(name) LIKE '% UNIT %' THEN 'unit'
                WHEN UPPER(name) LIKE '% RIGHTS%' OR UPPER(name) LIKE '% RIGHT %' THEN 'right'
                WHEN UPPER(name) LIKE '% PREFERRED%' OR UPPER(name) LIKE '% PREFERENCE%' THEN 'preferred'
                WHEN UPPER(name) LIKE '%ACQUISITION CORP%' OR UPPER(name) LIKE '%ACQUISITION CO%'
                     OR UPPER(name) LIKE '%BLANK CHECK%' THEN 'spac'
                WHEN UPPER(name) LIKE '%AMERICAN DEPOSITARY%' OR UPPER(name) LIKE '%AMERICAN DEPOSITORY%'
                     OR UPPER(name) LIKE '% ADR %' THEN 'adr'
                WHEN UPPER(name) LIKE '%REAL ESTATE INVESTMENT TRUST%' OR UPPER(name) LIKE '% REIT %' THEN 'reit'
                WHEN UPPER(name) LIKE '% ETF%' OR UPPER(name) LIKE '%EXCHANGE TRADED FUND%' THEN 'etf'
                WHEN UPPER(name) LIKE '% ETN%' OR UPPER(name) LIKE '%EXCHANGE TRADED NOTE%' THEN 'etn'
                WHEN UPPER(name) LIKE '% FUND %' OR UPPER(name) LIKE '% FUNDS %' THEN 'fund'
                ELSE 'common_stock'
            END
            """
        )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_securities_security_type ON securities(security_type)"
    )

    # Phase 4.1 additive portfolio migration. Existing quantity/price transactions stay valid.
    portfolio_columns = {row[1] for row in connection.execute("PRAGMA table_info(portfolio_transactions)").fetchall()}
    portfolio_additions = {
        "input_mode": "TEXT NOT NULL DEFAULT 'quantity'",
        "input_amount": "REAL",
        "base_currency": "TEXT NOT NULL DEFAULT 'GBP'",
        "asset_currency": "TEXT NOT NULL DEFAULT 'USD'",
        "fx_rate": "REAL",
        "fx_source": "TEXT",
        "price_source": "TEXT",
        "price_timestamp": "TEXT",
        "price_overridden": "INTEGER NOT NULL DEFAULT 0",
        "fees_currency": "TEXT",
    }
    for column, ddl in portfolio_additions.items():
        if column not in portfolio_columns:
            connection.execute(f"ALTER TABLE portfolio_transactions ADD COLUMN {column} {ddl}")

    # Phase 4.1 journal calculation/override metadata.
    journal_columns = {row[1] for row in connection.execute("PRAGMA table_info(journal_trades)").fetchall()}
    journal_additions = {
        "pnl_override": "REAL",
        "override_reason": "TEXT NOT NULL DEFAULT ''",
        "pnl_source": "TEXT",
        "position_amount": "REAL",
        "position_currency": "TEXT NOT NULL DEFAULT 'USD'",
        "planned_rr": "REAL",
        "external_provider": "TEXT NOT NULL DEFAULT ''",
        "external_id": "TEXT",
        "external_order_id": "TEXT",
        "source_metadata": "TEXT NOT NULL DEFAULT '{}'",
        "imported_at": "TEXT",
    }
    for column, ddl in journal_additions.items():
        if column not in journal_columns:
            connection.execute(f"ALTER TABLE journal_trades ADD COLUMN {column} {ddl}")

    # Phase 6.3: old databases restricted journal source values to the original
    # four literals. Rebuild only when that old CHECK is present so future
    # broker_* sources can be added without another SQLite table migration.
    table_sql_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='journal_trades'"
    ).fetchone()
    table_sql = str(table_sql_row[0] or "") if table_sql_row else ""
    if "source LIKE 'broker_%'" not in table_sql:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(journal_trades)").fetchall()]
        connection.execute("""
            CREATE TABLE journal_trades_v63 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL CHECK(source IN ('live_manual','paper_manual','replay','backtest') OR source LIKE 'broker_%'),
                name TEXT NOT NULL DEFAULT 'Trade', account TEXT NOT NULL DEFAULT 'Main', ticker TEXT NOT NULL,
                direction TEXT NOT NULL DEFAULT 'long' CHECK(direction IN ('long','short')),
                status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed')), opened_at TEXT, closed_at TEXT,
                entry_price REAL, exit_price REAL, quantity REAL, position_amount REAL, position_currency TEXT NOT NULL DEFAULT 'USD',
                stop_loss REAL, take_profit REAL, fees REAL NOT NULL DEFAULT 0,
                result TEXT CHECK(result IN ('win','loss','breakeven') OR result IS NULL),
                result_source TEXT CHECK(result_source IN ('manual','computed') OR result_source IS NULL),
                pnl_amount REAL, pnl_pct REAL, r_multiple REAL, planned_rr REAL, pnl_override REAL,
                override_reason TEXT NOT NULL DEFAULT '', pnl_source TEXT, trade_type TEXT NOT NULL DEFAULT '',
                setup TEXT NOT NULL DEFAULT '', market_condition TEXT NOT NULL DEFAULT '', entry_timeframe TEXT NOT NULL DEFAULT '',
                timeframe_alignment TEXT NOT NULL DEFAULT '', dxy TEXT NOT NULL DEFAULT '', session_time TEXT NOT NULL DEFAULT '',
                tf_type TEXT NOT NULL DEFAULT '', wick TEXT NOT NULL DEFAULT '', analysis TEXT NOT NULL DEFAULT '',
                entry_notes TEXT NOT NULL DEFAULT '', management TEXT NOT NULL DEFAULT '', learning TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '', timeframe_notes TEXT NOT NULL DEFAULT '{}', external_provider TEXT NOT NULL DEFAULT '',
                external_id TEXT, external_order_id TEXT, source_metadata TEXT NOT NULL DEFAULT '{}', imported_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        target = [row[1] for row in connection.execute("PRAGMA table_info(journal_trades_v63)").fetchall()]
        if set(columns) - set(target):
            raise RuntimeError("Journal migration stopped: unrecognised columns must be preserved before upgrading")
        custom_objects = connection.execute("SELECT name FROM sqlite_master WHERE tbl_name='journal_trades' AND (type='trigger' OR (type='index' AND sql IS NOT NULL AND name NOT IN ('idx_journal_trades_ticker','idx_journal_trades_source','idx_journal_trades_opened','idx_journal_trades_setup','idx_journal_trades_external')))").fetchall()
        if custom_objects:
            raise RuntimeError("Journal migration stopped: custom indexes or triggers require a preserving migration")
        shared = [column for column in target if column in columns]
        names = ",".join(shared)
        connection.execute(f"INSERT INTO journal_trades_v63({names}) SELECT {names} FROM journal_trades")
        old_count = connection.execute("SELECT COUNT(*) FROM journal_trades").fetchone()[0]
        new_count = connection.execute("SELECT COUNT(*) FROM journal_trades_v63").fetchone()[0]
        if old_count != new_count or connection.execute(f"SELECT {names} FROM journal_trades EXCEPT SELECT {names} FROM journal_trades_v63").fetchone():
            raise RuntimeError("Journal migration stopped: copied data did not match existing records")
        connection.execute("DROP TABLE journal_trades")
        connection.execute("ALTER TABLE journal_trades_v63 RENAME TO journal_trades")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_journal_trades_ticker ON journal_trades(ticker)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_journal_trades_source ON journal_trades(source)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_journal_trades_opened ON journal_trades(opened_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_journal_trades_setup ON journal_trades(setup)")

    # Create this after any old-table migration. Creating it in the base schema
    # would fail when SQLite opens a pre-6.3 journal_trades table before the
    # new external_* columns have been added.
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_journal_trades_external ON journal_trades(source, external_provider, external_id) WHERE external_id IS NOT NULL AND external_id != ''")

    # Phase 5.4: group development/validation/OOS runs and add lightweight tags.
    run_columns = {row[1] for row in connection.execute("PRAGMA table_info(backtest_runs)").fetchall()}
    if "experiment_group" not in run_columns:
        connection.execute("ALTER TABLE backtest_runs ADD COLUMN experiment_group TEXT NOT NULL DEFAULT ''")
    if "tags" not in run_columns:
        connection.execute("ALTER TABLE backtest_runs ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_backtest_runs_experiment ON backtest_runs(experiment_group)")

    # Journal V2: all additions follow the legacy source-constraint migration.
    additions = {
        "journal_trades": {
            "playbook_id": "INTEGER REFERENCES playbook_entries(id) ON DELETE SET NULL",
            "setup_grade": "TEXT NOT NULL DEFAULT ''", "plan_followed": "TEXT NOT NULL DEFAULT ''",
            "review_data": "TEXT NOT NULL DEFAULT '{}'",
            "external_account_key": "TEXT NOT NULL DEFAULT ''", "account_currency": "TEXT",
            "broker_realized_pnl": "REAL", "financing": "REAL", "commission": "REAL",
            "guaranteed_execution_fee": "REAL", "dividend_adjustment": "REAL",
            "initial_risk_amount": "REAL", "risk_source": "TEXT", "costs_complete": "INTEGER",
        },
        "playbook_entries": {"sections": "TEXT NOT NULL DEFAULT '{}'", "review_fields": "TEXT NOT NULL DEFAULT '[]'"},
    }
    for table, fields in additions.items():
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for column, ddl in fields.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_journal_playbook ON journal_trades(playbook_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_journal_account ON journal_trades(external_account_key)")
    connection.execute("""CREATE TABLE IF NOT EXISTS broker_sync_state (
        provider TEXT NOT NULL, account_key TEXT NOT NULL, environment TEXT NOT NULL,
        cursor TEXT, last_success_at TEXT, status TEXT NOT NULL DEFAULT 'never_synced',
        error TEXT, PRIMARY KEY(provider, account_key)
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS portfolio_broker_accounts (
        provider TEXT NOT NULL, account_key TEXT NOT NULL, environment TEXT NOT NULL,
        label TEXT NOT NULL, summary TEXT NOT NULL, synced_at TEXT NOT NULL,
        PRIMARY KEY(provider, account_key)
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS portfolio_broker_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL, account_key TEXT NOT NULL,
        kind TEXT NOT NULL, external_id TEXT NOT NULL, facts TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1, note TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
        UNIQUE(provider, account_key, kind, external_id),
        FOREIGN KEY(provider, account_key) REFERENCES portfolio_broker_accounts(provider, account_key)
    )""")


class Database:
    """Small SQLite wrapper for Ledger-owned application state."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(_SCHEMA)
            _migrate_schema(connection)
            # Phase 4.3 adds planned risk:reward metadata.
            # Existing rows are backfilled where entry/stop/target are directionally valid.
            connection.execute("""
                UPDATE journal_trades
                SET planned_rr = CASE
                    WHEN planned_rr IS NOT NULL THEN planned_rr
                    WHEN direction='long' AND entry_price IS NOT NULL AND stop_loss < entry_price AND take_profit > entry_price
                      THEN (take_profit-entry_price)/(entry_price-stop_loss)
                    WHEN direction='short' AND entry_price IS NOT NULL AND stop_loss > entry_price AND take_profit < entry_price
                      THEN (entry_price-take_profit)/(stop_loss-entry_price)
                    ELSE NULL
                END
            """)
            for version in range(1, 17):
                connection.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (?)", (version,))

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO app_settings(key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )

    def get_setting(self, key: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None
