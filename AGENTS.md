# Ledger engineering rules for Codex and other coding agents

This file is the default engineering contract for this repository. Read it before making changes.

## 1. Product goal and priority order

Ledger is a trading research, strategy-development, backtesting, replay, journaling and analysis application. The intended loop is:

`Research -> Strategy -> Backtest -> Replay -> Trade -> Journal -> Analyse`

When priorities conflict, use this order:

1. Backtesting / execution correctness
2. Market-data correctness and no look-ahead leakage
3. Replay integrity and reliability
4. Preservation of user data
5. Maintainability and explicit architecture boundaries
6. Useful UX
7. Visual polish / TradingView parity

Do not make the app look better by making the research or execution model less correct.

## 2. Current stack

Frontend:
- React + Vite
- JavaScript / JSX
- TradingView Lightweight Charts
- Tailwind CSS

Backend:
- Python
- FastAPI + Uvicorn
- Pydantic Settings
- pandas
- SQLite for Ledger-owned application state
- DuckDB / local analytical data where already used
- local market-data cache
- httpx for provider HTTP requests
- pytest

Do not introduce a new framework, database, state library, queue, cache service or major dependency unless the task genuinely requires it and the user has agreed to the architectural change.

## 3. Required workflow for every coding task

Before editing:
1. Inspect the relevant implementation, interfaces and existing tests.
2. Trace the current data flow instead of guessing filenames or architecture.
3. Identify the smallest set of files that should change.
4. For broad or risky work, state the plan before modifying code.

While editing:
5. Make the smallest coherent change that fits the existing architecture.
6. Do not refactor unrelated code "while you are here".
7. Preserve public API behaviour unless the task explicitly changes it.
8. Add or update deterministic tests for changed behaviour.

Before finishing:
9. Run the relevant tests, then the broad regression suite when practical.
10. For backend changes, normally run `cd backend && pytest -q`.
11. For frontend changes, normally run `cd frontend && npm run build` after dependencies are installed.
12. Review the final diff for accidental changes, secrets, generated files and unrelated formatting churn.
13. Report changed files, tests run, failures/limitations and any assumptions.

Never say a test or build passed unless it was actually run successfully.

## 4. Stop conditions: ask before proceeding

Stop and ask for a decision instead of guessing if a requested change would:
- alter the frozen XAUUSD baseline strategy rules or parameters;
- tune a strategy specifically to make historical results greener;
- introduce a destructive or data-losing database migration;
- place, modify or cancel a real/demo broker order;
- require storing, logging or exposing API secrets;
- scrape or reverse-engineer a paywalled/licensed broker or research portal;
- change the market-data provider used for an existing instrument;
- revive or redesign the deferred NQ/Massive continuous-futures work;
- weaken replay anti-look-ahead behaviour;
- make a large architectural change that is not necessary for the task;
- be materially ambiguous about trading semantics, fills, stops, targets or timestamps.

## 5. Market-data boundaries

Use the existing `MarketDataService` / provider-routing architecture. Feature code should not bypass it and make provider calls directly unless the provider abstraction explicitly requires that work.

Current routing intent:
- US equities: Alpaca
- XAUUSD: OANDA (`XAU_USD` at the provider boundary)
- NQ1! / futures: Massive work is experimental/deferred

Rules:
- Keep Ledger's canonical instrument aliases separate from provider-specific symbols.
- Preserve UTC internally; convert only for presentation/session logic.
- Preserve provider metadata and session profiles.
- OANDA candle volume is activity/tick volume, not exchange volume. Do not label it as true traded volume.
- Do not silently fabricate missing bars or provider data.
- Historical caches must be deterministic and reusable for long backtests.
- If provider freshness or market closure is uncertain, prefer the provider's actual latest completed bar boundary rather than the local wall clock.

## 6. OANDA safety and future broker imports

The existing OANDA integration is a market-data integration. Future journal synchronisation may read broker/account history.

Unless a task explicitly and separately authorises execution:
- OANDA account integration must be READ-ONLY.
- Do not create, modify, close or cancel orders or positions.
- Do not add order-placement endpoints "for completeness".
- Never expose access tokens in responses, logs, exceptions or committed files.

Broker-imported journal trades must use the common Journal model, not a separate OANDA journal.
Use stable provider identities for idempotency:
- `source = "broker_<provider>"`
- `external_provider`
- `external_id`
- optional `external_order_id`
- `source_metadata` for provider-specific non-core fields

Repeated syncs must not duplicate trades.

## 7. Journal invariants

There is ONE Journal data model for:
- manual trades;
- Replay trades;
- backtest-related records where applicable;
- future broker imports.

Do not fork journal schemas or UIs by source.

Replay closed trades are automatically written to the Journal. This write is intended to be idempotent via a deterministic external ID. Preserve this behaviour unless explicitly asked to change it.

Objective fields such as entry/exit/quantity/P&L should remain separable from discretionary fields such as setup, reasoning, notes and screenshots.

## 8. Replay integrity

Replay is a research tool, so hidden future data must stay hidden.

Rules:
- Never expose unrevealed future bars to entry logic or the UI.
- Keep the canonical intraday replay source behaviour unless explicitly redesigned and tested.
- Preserve deterministic behaviour across timeframe switches.
- If the user rewinds after revealing bars, preserve/mark the existing integrity-compromised state rather than pretending the run remained clean.
- Weekend/holiday starts may advance to the first available provider session rather than failing.
- XAUUSD should support the 24h/full-provider-session workflow.

Any change to replay fill semantics, same-bar stop/target ordering, gap handling or reveal timing requires tests.

## 9. Backtesting architecture

Strategy plugins describe signals. The common backtest engine owns execution mechanics.

Strategy plugins should NOT independently reimplement:
- fills;
- position sizing;
- commissions/spread/slippage;
- stop/target lifecycle;
- generic trade accounting;
- portfolio/equity accounting.

Use the common `EntrySignal`/engine path. Keep limit orders persistent according to their configured wait and preserve setup-vs-fill accounting.

No look-ahead:
- pivots must be confirmed using bars that are already completed at the decision point;
- higher-timeframe context must not contain data unavailable at that timestamp;
- do not centre indicators/windows on future samples;
- audit metadata must describe information available when the signal occurred.

## 10. Frozen XAUUSD baseline

The current baseline is intentionally a research baseline, not a profit-optimised strategy.

Stable strategy key:
`xau_liquidity_type3_baseline_v1`

Current implementation/version label:
`xau_liquidity_type3_baseline_v1_1`

Core behaviour:
- market: XAUUSD
- context: 1H
- execution: 1m
- higher-timeframe liquidity: most recent confirmed 1H 2-left / 2-right pivot by default
- sweep below a liquidity low for longs / above a liquidity high for shorts
- Type 3 confirmation: completed 1m close through a stronger opposing swing selected from bounded pre-sweep structure
- `structure_lookback_bars = 40`
- `minimum_structure_bars = 3`
- `max_type3_wait_bars = 120`
- persistent 50% retracement limit entry
- `limit_wait_bars = 120`
- stop at the structural sweep extreme
- target = 1.5R
- long/short are mirrors
- sessions are tagged for analysis; session does NOT determine baseline validity

The baseline intentionally does NOT include:
- DXY confirmation
- session filter
- minimum sweep size
- FVG / order-block / POI filter
- news filter
- 20-minute overextension rule
- extra higher-timeframe directional bias
- discretionary visual selection

Do not change these baseline rules because a test period loses money. Confluences must be separate experiments so their incremental effect can be measured.

## 11. Strategy research / anti-overfitting rules

For confluence experiments:
- freeze the baseline first;
- add one conceptual variable at a time where possible;
- retain the unmodified baseline for comparison;
- record trade count as well as win rate/expectancy;
- prefer objective measurements over discretionary labels;
- use development, validation and out-of-sample periods;
- later add sensitivity/walk-forward testing rather than selecting one lucky parameter;
- do not select a parameter solely because it maximises one historical window.

If a requested strategy rule is subjective (for example "strong rejection"), ask for a deterministic definition before coding it.

## 12. Strategy audit requirements

Auditability matters as much as aggregate metrics. XAU strategy metadata is designed to make a detected setup inspectable.

Preserve/extend visualisation of:
- 1H liquidity level
- sweep point/time
- Type 3 swing level/time
- Type 3 confirmation
- impulse high/low
- 50% entry
- stop
- target
- exit

Do not use annotations to alter strategy eligibility. They are diagnostics.

## 13. Research-source architecture

Research uses a normalised common model. New sources should map into the existing research item fields instead of creating a source-specific table/UI unless a genuinely incompatible data type requires it.

Common concepts include:
- source
- source item ID
- item type
- instrument
- publication time
- title
- summary
- direction
- confidence
- URL
- metadata for source-specific fields

Examples of future sources:
- Financial Times
- Autochartist
- OANDA research/news where licensed/API-accessible
- economic calendar feeds
- other news providers

Respect access/licensing boundaries:
- Do not scrape Financial Times article content.
- Do not scrape OANDA/Autochartist portals.
- A user being able to view a portal does not imply reusable API rights.
- Prefer official/licensed APIs or manual links/notes.
- Keep externally supplied confidence/probability under its original label; never relabel an Autochartist probability as "chance of profit" without evidence.

## 14. Autochartist is scaffold-only

Autochartist configuration/provider code currently exists only as safe readiness scaffolding.

Until the user obtains confirmed developer/API entitlement:
- do not make remote Autochartist calls;
- do not reuse browser/portal session URLs or short-lived tokens;
- do not reverse-engineer the MT4/MT5 LaunchPad plugin;
- do not guess signing/authentication algorithms;
- do not claim the connection is validated merely because fields are present.

The capability endpoint should remain explicit about whether a remote probe was performed.

## 15. Database and user-data safety

The local SQLite database contains user-owned app state (journal, saved backtests, research, settings, etc.). Treat it as irreplaceable.

Rules:
- migrations should be additive/preserving whenever possible;
- migration tests must cover important existing rows;
- never delete/recreate a table without copying and validating shared data first;
- never silently reset the database on migration failure;
- do not ship or overwrite a stale `backend/data/ledger.db` as part of an update;
- do not edit the user's real `backend/data` during ordinary code tasks;
- preserve stable IDs where possible;
- use unique external IDs for idempotent imports.

If a destructive migration is actually necessary, stop and request explicit approval plus a backup plan.

## 16. Chart/drawing invariants

Drawings are market objects anchored to timestamp + price, not to a candle index or a timeframe-specific x-coordinate.

Therefore:
- drawings should persist across timeframe switches where their timestamps/prices remain meaningful;
- viewport restoration must map to valid bars/logical positions rather than assuming every lower-timeframe timestamp exists on a higher timeframe;
- do not reintroduce chart behaviour that can blank the chart during 1m/5m/timeframe transitions;
- chart polish is lower priority than replay/backtesting correctness.

## 17. Secrets and repository hygiene

Never commit or package:
- `.env`
- API keys/tokens/secrets
- broker account credentials
- browser session tokens
- short-lived Autochartist/OANDA portal URLs
- virtual environments
- `node_modules`
- `__pycache__`
- `.pytest_cache`
- generated local user databases

Only `.env.example` should contain blank/example configuration.

If a secret appears in a traceback/chat/file, do not repeat it. Recommend rotation if exposure is plausible.

## 18. Packaging / handoff

When producing an update bundle:
- preserve source structure;
- exclude user databases and secrets;
- exclude dependency/cache directories;
- include migration/update notes if the user's current `backend/data` must be retained;
- include a concise test checklist;
- state exact regression results.

## 19. Current intentionally deferred work

Do not casually revive these items:
- NQ1! / Massive continuous-futures reliability work
- live broker execution from Ledger
- Autochartist network integration
- true order-flow/delta without an appropriate data source
- large TradingView-parity drawing/UI projects

They can be planned later in the discussion/planning workflow.

## 20. Definition of done

A task is not done merely because the code was written. It is done when:
- behaviour matches the requested semantics;
- important edge cases have deterministic tests;
- existing tests still pass or failures are explicitly explained;
- data and secret safety are preserved;
- no unrelated feature regressed knowingly;
- the final response says exactly what changed and what still needs manual validation.
