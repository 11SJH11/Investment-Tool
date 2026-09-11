# Ledger Phase 6.3 final handoff checklist

Run these checks after copying your existing `.env` and `backend/data` into the Phase 6.3 folder.

## 1. Automated checks

Backend:

```powershell
cd backend
pytest -q
```

Release regression result: **113 passed, 1 skipped**.

Frontend:

```powershell
cd frontend
npm run build
```

Then start both frontend and backend normally.

## 2. Existing data migration

- Open Journal and confirm existing trades are still present.
- Open saved Strategy Lab runs and confirm historical saved runs are still present.
- Restart Ledger once and confirm the same data remains.

The migration adds broker/source identity columns to Journal records and the generic `research_items` table. It must not reset existing Journal rows.

## 3. Replay -> Journal

- Start a Replay session.
- Open and close one replay trade.
- Confirm the UI reports that the closed trade was saved to Journal.
- Open Journal and confirm entry/exit time, price, direction, size, stop/target and replay notes are present.
- Repeat/retrigger the same save path if practical and confirm it does not create a duplicate record for the same deterministic Replay identity.

Expected source: `replay`; external provider: `ledger_replay`.

## 4. Research workspace

- Open Research for AAPL or XAUUSD.
- Add a manual Financial Times research note with a title, link, bias and your own summary.
- Confirm it appears only under the selected instrument.
- Refresh/restart and confirm the note persists.
- Open its link and confirm Ledger only navigates to the external source; Ledger must not scrape article text.
- Delete a test note and confirm it disappears.

## 5. Autochartist safety scaffold

- Open Settings -> Data & providers.
- With no Autochartist developer credentials, Autochartist should show **Not configured**.
- `GET /api/data/providers/autochartist/capabilities` should say `remote_probe_performed: false`.
- Do not paste OANDA Research Portal URLs/session tokens into `.env`.

No Autochartist network integration is enabled in this release.

## 6. XAU baseline v1.1

In Strategy Lab confirm the strategy is shown as:

`XAUUSD Liquidity Sweep + Type 3 + 50% · baseline v1.1`

Important defaults:
- 1H liquidity pivots: 2 left / 2 right
- 1m execution pivots: 2 left / 2 right
- Type 3 structure lookback: 40 bars
- minimum swing -> sweep structure separation: 3 bars
- sweep -> Type 3 expiry: 120 bars
- 50% limit expiry: 120 bars
- entry retracement: 50%
- target: 1.5R
- all sessions eligible; sessions are analysis tags only

Do not tune these values based on one profitable/unprofitable window. The planned next validation is a contiguous 2–3 month run.

## 7. Trade audit visualisation

Open several XAU v1.1 trades from a saved/new run.

Where metadata is available, confirm the audit can display:
- 1H Liquidity
- SWEEP marker
- Type 3 Swing
- Type 3 confirmation
- Impulse High / Low
- Entry / 50% retracement
- Stop
- Target
- Exit

Check at least one long and one short.

## 8. Reliability regression smoke test

Charts:
- AAPL 1m -> 5m -> 15m -> 1m remains visible.
- XAUUSD 1m -> 5m -> 15m -> 1m remains visible.
- Existing drawings remain anchored to market time/price as expected.

Replay:
- AAPL weekday replay loads.
- Weekend/holiday request advances to an available session instead of a 400.
- XAUUSD supports 24h/full-provider-session replay.
- Rewinding after reveal keeps the integrity warning/flag behaviour.

Providers:
- XAUUSD continues to route to OANDA.
- Stocks continue to route to Alpaca.
- NQ1!/Massive remains deferred; do not use it as a release blocker.

## 9. Handoff to Codex

Before the first Codex task, ask it to read root `AGENTS.md`.

For each task, provide one bounded outcome and explicit acceptance checks. Use `CODEX_WORKFLOW.md` as the prompt template. Codex should report changed files and actual tests run before you accept the change.
