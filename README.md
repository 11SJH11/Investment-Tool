# Ledger v2

## Phase 6.3.0 — handoff / integration foundation

Phase 6.3 is the final broad app update before day-to-day implementation moves to Codex. It keeps the Phase 6.2.4 reliability work intact and adds narrow integration foundations rather than another large UI rewrite.

### What changed

- **Unified Journal ingestion readiness**
  - Replay still auto-saves a closed trade to the normal Journal.
  - Replay saves now carry a deterministic external ID so repeated saves are idempotent.
  - Journal records support `external_provider`, `external_id`, `external_order_id`, `source_metadata` and `imported_at`.
  - `broker_*` sources are supported for future read-only broker synchronisation without creating a separate broker journal.
  - No OANDA order-placement/execution code was added.

- **Research workspace / common source model**
  - Research records now have a provider-neutral storage model for future FT, Autochartist, OANDA/news/calendar and other sources.
  - Research UI can save a source, external link, instrument, bias and the user's own thesis/summary.
  - Ledger does **not** scrape Financial Times, OANDA or Autochartist content.

- **Autochartist readiness only**
  - Optional blank configuration and a capability/status scaffold were added.
  - No remote Autochartist requests are made.
  - Portal/MT4/MT5 access is not treated as developer API entitlement.

- **XAUUSD strategy audit**
  - Audit charts can show the 1H liquidity level, sweep, Type 3 swing/confirmation, impulse high/low, entry/50% level, stop, target and exit when strategy metadata is present.

- **XAUUSD baseline v1.1 included**
  - Stable plugin key remains `xau_liquidity_type3_baseline_v1` for compatibility.
  - Version metadata is `xau_liquidity_type3_baseline_v1_1`.
  - Stronger pre-sweep Type 3 structure selection uses a 40-bar lookback and 3-bar minimum separation by default.
  - Baseline remains confluence-free and session-neutral.

- **Codex guardrails**
  - Root `AGENTS.md` defines the repository engineering contract, data/broker safety boundaries, frozen XAU baseline, anti-overfitting rules, test requirements and stop conditions.
  - `CODEX_WORKFLOW.md` gives a concise task-writing workflow.

### Regression status

Backend: **113 passed, 1 skipped**.

Frontend modified JSX/JS files were syntax-parsed successfully with the TypeScript parser in the build environment. A full Vite production build could not be run in the artifact environment because frontend dependencies were not present and package installation had no network access. Run `npm install` once locally if needed, then `npm run build` as part of the upgrade checklist.

### Upgrade safety

The update bundle intentionally does **not** contain a `backend/data/ledger.db` or `.env`.

Keep your current:
- `backend/.env`
- `backend/data/ledger.db`
- any existing `backend/data/market/` cache you want to retain

See `UPGRADING_TO_6.3.md` before replacing your current project folder.

NQ1!/Massive remains deferred. Autochartist network integration remains deferred until proper API entitlement/credentials are confirmed.
