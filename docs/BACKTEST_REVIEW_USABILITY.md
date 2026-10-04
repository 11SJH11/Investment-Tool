# Backtesting usability and Trade Review

Implemented workflow: configure a fixed run or parameter sweep, submit, keep working,
follow Activity, explicitly open a completed result, load Trades/Analysis on demand,
and inspect a trade with recorded and reconstructed evidence.

## Checkpoint status

1. Background-work UX (brief 4/5/6/8): implemented. Global Activity reuses shared
   job polling and persists up to 100 local notification entries. Terminal jobs
   remain in backend history. Toasts are dismissible and expire. Research does
   not navigate on submission; ongoing operations provide immediate feedback.
2. Saved-run responsiveness (9/10): implemented. Summary, trades and analysis
   projections preserve existing SQLite snapshots. Summary excludes trade and
   diagnostic JSON; trades and analysis fetch on demand. Nine section cache
   entries expire after 30 seconds; six review entries after 60 seconds.
3. Integrated parameter research (11/12/13): implemented. Numeric fields expose
   fixed/list/range choices; exact backend previews determine counts. Existing
   one/two-axis limits remain: 25 values for one axis, eight per axis for two.
   Multiple symbols queue separate research parents with independent capital and
   stable per-symbol retry keys. They are not a portfolio. Advanced band research
   and the existing rich Research Viewer remain available.
4. Generic Trade Review: implemented with the limits below. Full final gate and
   browser acceptance results are recorded in the final handoff.

Hosting, authentication, PWA and push are deliberately outside this change.

## Historical review contract

`StrategySpec.review_config` is optional and presentation-only. It is persisted
with future results. Existing plugins still run unchanged. A compatibility profile
covers the current VWAP V4 reference without editing its rules. The reference V4
module is included unchanged because the canonical HTF adapter depends on its math.

Example declaration:

```python
review_config={
    "version": 1,
    "series": [
        {"id": "ema20", "label": "EMA20", "indicator": "ema",
         "timeframe": "1d", "params": {"length": 20}, "history_days": 365},
        {"id": "atr", "indicator": "atr", "timeframe": "1m",
         "params": {"length": 14}, "role": "research_only"},
    ],
    "levels": [{"label": "Frozen pivot", "metadata_key": "pivot"}],
    "entry_fields": ["signal_close", "trend_filter_passed"],
}
```

Indicators resolve through the existing indicator registry. Only indicators marked
causal may reconstruct evidence. DataFrame outputs specify `column`; parameter
bindings use `{"parameter": "strategy_parameter_key"}`. Indicators declare whether
plotted over price or in a separate pane. Static levels must be genuinely frozen
references; no dynamic signal snapshot is drawn as a horizontal indicator.
Research-only series are separately toggled and labelled. Ordinary volume remains
an optional research overlay unless a strategy explicitly declares its use.

VWAP uses canonical `rth_vwap_bands`: NY RTH HLC3 times volume, resetting each session.
Distance bands move with every VWAP sample. The optional `rth_trend_ema` adapter
calls V4's existing `_trend_state` on completed history, retaining its RTH buckets,
rolling input count and cache-boundary semantics. It does not invent provider daily
bars. Extended history is opt-in because it may require 30?250 calendar days of
minute data. Only the displayed output window and a carry-in point are returned.

Future declared strategies record decision timestamp, signal candle close,
confirmation observations, preceding candle timestamps, effective parameters and
bounded canonical signal indicator values in `review_entry` / `review_exit`.
Recording happens only on decisions, not every bar. Trading decisions, position
sizing, fill timing and P&L calculations are unchanged. CSV metadata JSON retains
these fields; the saved result retains implementation hashes.

## Provenance and limits

- Recorded values take priority. Reconstructed values are labelled separately.
  Legacy runs infer confirmation signal time only for the declared next-open model.
- Confirmation highlights require the exact preceding N completed candles to pass
  the declared side test. Missing/mismatched evidence stays unavailable.
- Original provider revisions/bars are not permanently snapshotted. Reconstructed
  values cannot promise exact historical identity. Changed code, missing minutes,
  historical seeds, and incomplete/short sessions may differ from the saved run.
- The generic layer supports registered indicators; it cannot infer which arbitrary
  indicators an undeclared strategy used. Such strategies retain trade facts and
  legacy metadata. Other strategy families can progressively add declarations.
- HTF values already recorded in V4 trades remain authoritative. The extended line
  uses current canonical code and bounded available history, not a claim that an
  old hash has been re-executed exactly.
- Static entry/exit/stop/frozen levels span the review window for visual reference;
  they were not necessarily known before the signal/fill.
- If candles/provider history fail, the review retains recorded trade facts and
  reports the unavailable reconstruction without exposing provider exception text.
- Notification history is local to this browser, not a new multi-user server inbox.
  Backend job history remains the durable execution source. This is not push.
- Existing broker sync actions produce completion feedback; automatic provider
  schedules have not been rewritten as a new universal worker system.

## Rejected decisions

Existing setup records and engine rejection summaries remain available through
lazy Analysis. Do not infer an unexecuted strategy candidate from trade CSVs.
A future optional strategy-owned audit hook can emit candidate/accepted/rejected
records with a stable candidate ID, decision time, reason and evidence only when a
candidate changes state. It should use capped per-run storage and never emit on
every bar. V4's internal pre-EntrySignal rejections are not newly logged here:
adding that requires a separately measured strategy audit change, not a guessed
post-hoc reconstruction.

## Performance evidence

A synthetic 10,000-trade snapshot with 1,000 equity points was measured five times:
full response 5,976,404 bytes versus summary 37,158 bytes (99.38% smaller).
Full read/decode: 22.6?30.4 ms; summary: 15.0?17.4 ms.
JSON serialisation: full 25.7?27.0 ms; summary 0.49?0.89 ms.
These are local synthetic measurements, not live-provider/network benchmarks.
SQLite still inspects the original JSON: no schema rewrite or destructive migration.
The benchmark completed; Windows delayed cleanup of its temporary SQLite file.

Section responses expose SQLite-projection/JSON-decode timings. Browser performance
entries `ledger.saved-run.headers`, `.body`, `.json-parse` separate request/body/parsing
costs. React Profiler records `.react-render` in profiling/development React builds;
ordinary production React may disable that callback. Entries are bounded. Use browser
Performance recordings to measure chart rendering on actual provider data.

## Manual acceptance

1. Configure a run; submit and remain on Backtest. Navigate elsewhere. Activity must
   retain progress and offer Open results only after completion.
2. Set one numeric parameter to Multiple values; choose a second Range if needed.
   Confirm exact counts and independent per-symbol scope. Submit without navigation.
3. Open a saved run. Confirm immediate opening feedback, Summary first, Trades and
   Analysis requested only when opened. Export all trades and full JSON explicitly.
4. Open a VWAP V4 trade. Compare recorded signal/fill values with its CSV metadata.
   Check the changing session VWAP and moving distance bands; entry/exit/stop remain
   static trade facts. Confirm blue entry and amber exit confirmation candles.
5. For E3/E2, inspect exactly three entry and two exit confirmation candles. Missing
   or inconsistent data must show unavailable/mismatch, not a fabricated PASS.
6. Enable extended indicator history to inspect the completed-RTH HTF EMA. Compare
   recorded HTF values first; heed source/data/seed warnings if they differ.
7. Open old/undeclared trades and disable historical data: recorded facts remain
   accessible. Toggle evidence, volume/research overlays, timeframe and timezone.
8. Check 1024/1440/1920px: internal tables may scroll; the page must not overflow.

Automated tests use isolated databases and mocked history. Browser checks use mocked
API responses. Live historical trades/providers were not opened in the user's running
application, and no live services were restarted.

## Final verification ? 2026-10-04

- Full backend: **788 passed**, 87.38 seconds.
- Full frontend utility suite: **97 passed**, no failures/skips.
- Production build: **passed**, 129 modules, 1.27 seconds.
- Focused review/API/preservation suite: **8 passed**.
- Final mocked browser smoke: integrated sweep, no automatic viewer navigation,
  immediate saved-run feedback, lazy trades, dynamic review, completion toast and
  Activity; no runtime errors/page overflow at 1024, 1440 and 1920px.
- Scoped whitespace and documentation-link checks passed.
- Existing Starlette/httpx deprecation and large frontend chunk warnings remain.

Full gate command:
`powershell -ExecutionPolicy Bypass -File ./Verify-Ledger.ps1 -OutputDirectory <outside-repository-directory>`.
Browser script: `frontend/tests/browser/usability-review-smoke.mjs`, with
`LEDGER_CDP_URL` set to an isolated Chrome debugging endpoint and
`LEDGER_SMOKE_URL` pointing at the isolated production build. All API data is mocked.
