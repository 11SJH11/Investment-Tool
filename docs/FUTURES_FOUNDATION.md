# Futures foundation — Checkpoint 3

Implemented 2026-09-17. This is a contract-accounting and data-provenance
foundation, not a broker execution or continuous-contract trading simulator.
Gold and Momentum strategy source files and market-data routing are unchanged.

## Contract model

All families use USD. Point value equals the contract multiplier; tick value is
tick size times point value. Quantities are whole contracts.

| Root | Exchange | Tick size | USD/point | USD/tick |
|---|---|---:|---:|---:|
| NQ | CME | 0.25 | 20 | 5 |
| MNQ | CME | 0.25 | 2 | 0.50 |
| ES | CME | 0.25 | 50 | 12.50 |
| MES | CME | 0.25 | 5 | 1.25 |
| YM | CBOT | 1 | 5 | 5 |
| MYM | CBOT | 1 | 0.50 | 0.50 |
| RTY | CME | 0.10 | 50 | 5 |
| M2K | CME | 0.10 | 5 | 0.50 |
| GC | COMEX | 0.10 | 100 | 10 |
| MGC | COMEX | 0.10 | 10 | 1 |
| CL | NYMEX | 0.01 | 1,000 | 10 |
| MCL | NYMEX | 0.01 | 100 | 1 |

Every root has a `ROOT1!` chart alias. Dated symbols such as `NQU6`, `MESZ26`
and `M2KZ6` use the same economics. Bare roots are not reinterpreted as futures:
they can collide with equity tickers. SI is deferred pending verified coverage.

The family model includes description, currency, exchange, session, expiry
convention, provider product code and specification version `cme-economics-v1`.
Instrument responses also retain the canonical ticker and provider symbol.
Coverage is explicitly subject to Massive entitlement and returned contracts;
no live credentialed coverage probe was performed for any family.

Specifications were checked against primary sources:

- [CME micro equity index overview](https://www.cmegroup.com/education/courses/micro-e-mini-futures/micro-e-mini-futures-products-overview)
  and [contract fact card](https://www.cmegroup.com/trading/equity-index/files/cme-micro-e-mini-futures-fact-card.pdf).
- [CME Micro Gold overview](https://www.cmegroup.com/education/lessons/micro-gold-and-micro-silver-futures-product-overview).
- [CME Micro WTI FAQ](https://www.cmegroup.com/education/articles-and-reports/micro-wti-crude-oil-futures-faq).
- [Massive contracts reference](https://massive.com/docs/rest/futures/contracts).

## Accounting and fills

For direction sign `s` (+1 long, -1 short), quantity `q`, multiplier `m`:

- Gross P&L = `(exit - entry) * s * q * m`.
- Initial dollar risk = `abs(entry - initial stop) * q * m`.
- Notional exposure = `abs(entry * q * m)`.
- Net P&L subtracts the existing per-order fees; R = net P&L / initial risk.
- Risk sizing divides the configured dollar risk by `abs(entry-stop) * m`.
  Position-value sizing divides by `entry * m`. The existing leverage/notional
  cap applies, then quantity rounds down to whole contracts.
- Partial exits also round down. A reduction below one contract does nothing
  and incurs no commission. Realized, unrealized and final accounting all use m.
- Requested stop, target and explicit entry prices must be on tick. Off-tick
  orders are rejected; managed off-tick protection changes raise validation errors.
  Existing spread/slippage costs are applied, then market fills round adversely
  to a tick. Existing same-bar stop/target policy remains in force.

No exchange margin or special futures leverage is invented. At 25,000, one NQ
contract consumes $500,000 notional under the existing cap. Small accounts may
therefore get `position_size_zero`. Commission remains per order, not per contract.
Replay retains its existing zero-cost practice model and now accepts a contract
count. Manual Journal can accept whole quantity or full notional value; futures
currency is USD only. Weighted actual Journal fills need not lie on one tick.
Broker imports retain adapter-owned accounting.

## Continuous history and no-lookahead boundary

Execution requires a known dated contract, directly selected or resolved from a
continuous alias with valid raw provenance. Front aliases support Backtest and
Replay; Journal retains alias and actual source/executed contract. Adjusted bars
never become fills. Pending entries cancel at a roll; open-position transfers
across contracts fail explicitly before any artificial gap P&L.

Current schedule, daily-close adjustment, cache versioning, real NQ evidence and
provider limitations are documented in CONTINUOUS_FUTURES_RESEARCH.md. Calendar
front selection remains a supported explicit legacy policy, not the default.
TradingView roll/data parity is unverified. Old Journal data remains readable;
legacy Replay positions without economics require a new session. No automatic
historical futures P&L correction is performed.

Replay still clips canonical minutes before aggregation and indicators. Futures
chart buckets anchor at 18:00 America/New_York; winter/summer anchors are tested.
Provider bars remain authoritative for holidays, maintenance gaps and expiry.
Existing engine weekday/daily guardrails still use the configured local civil
date, not a new exchange trading-date calendar. Automatic no-overnight boundaries
are likewise the existing generic model; use explicit entry/force-close windows
for intraday studies. Full exchange calendars, delivery/margin and multi-expiry
execution remain follow-up work.

## Storage and changed files

No SQLite schema migration or user-data rewrite. Economics live in existing
Journal/run JSON metadata; market-cache provenance is additive. The user's real
database, credentials, attachments and saved runs were not touched.

Changed implementation files:

- `backend/app/backtesting/engine.py`
- `backend/app/backtesting/models.py`
- `backend/app/data/instruments.py`
- `backend/app/data/providers/massive_futures.py`
- `backend/app/services/backtest.py`
- `backend/app/services/chart_data.py`
- `backend/app/services/journal.py`
- `backend/app/services/market_data.py`
- `backend/app/storage/market_store.py`
- `frontend/src/features/strategy-lab/ReplayPanel.jsx`
- `docs/RELEASE_CHECKPOINTS.md`

New files:

- `backend/app/data/futures.py`
- `backend/tests/test_futures_foundation.py`
- `frontend/src/features/strategy-lab/futures-utils.js`
- `frontend/tests/futures.test.js`
- `docs/FUTURES_FOUNDATION.md`

## Verification

Commands ran with the backend virtualenv, unique temporary pytest directories
and `-p no:cacheprovider`. Frontend build output went to a unique temp directory.

- Initial compatibility: `pytest -q tests/test_phase5_engine.py
  tests/test_phase62_multi_asset.py tests/test_journal_v2.py`: **27 passed**.
- Focused `pytest -q tests/test_futures_foundation.py`: **33 passed**, 1.38 seconds,
  also passed within the full suite. The first
  focused run was 32 pass/1 fail because the new direct-repository legacy fixture
  omitted required fees; the fixture was corrected before the full run.
- Full backend: `pytest -q`: **293 passed**, 2 existing deprecation warnings,
  27.29 seconds. Includes engine, frozen XAU, Momentum, Replay, OANDA, Trading 212,
  Journal and migration/preservation regressions.
- Frontend: `node --test tests/*.test.js`: **10 passed**, including 3 new futures
  cases and the existing 7 Journal utility/preference cases.
- Production: `npm.cmd run build -- --outDir <unique-temp>`: **passed**, 66
  modules, 7.98 seconds. Existing large-chunk warning remains.
- `git diff --check`: passed.
- Isolated headless Chrome with synthetic prices and blocked outbound provider
  calls: dated NQ order, next-minute fill, $365 initial risk, next-minute close,
  one-contract 0.25-point gain saved as **$5** in Journal; continuous-alias warning
  and rejected order; no horizontal overflow at 1024px or observed runtime
  exceptions during the completed checks. API requests were redirected to the
  isolated server in the smoke harness only. Screenshot and scripts reside under
  temporary `ledger-cp3-smoke-0xrpz2zu`, not repository source.

## Manual acceptance

1. With Massive entitlement, search each continuous alias and inspect source
   contracts around an expiry. Empty provider coverage must remain an explicit
   error, never synthetic candles.
2. Load an available dated NQ/MNQ contract in Replay. Enter one contract and
   tick-aligned protection. Confirm a 20-point move is $400/$40 respectively.
3. Close and inspect the common Journal; edit review notes and confirm execution
   values and contract metadata remain unchanged. Reopen an old futures record.
4. Attempt a fractional contract, off-tick stop and continuous-alias order;
   confirm explicit rejection. Switch timeframes mid-bucket and check causality.
5. Backtest a dated contract with sufficient full-notional capacity. Inspect
   sizing, dollar risk, fees and same-bar outcomes. Do not interpret this as a
   futures-margin or cross-contract portfolio simulator.

Checkpoint 4 (Strategy Workspace), 5 (ORB/VWAP), 6 (Gold variants/comparison) and
7 (release-wide final verification/report) remain pending.
