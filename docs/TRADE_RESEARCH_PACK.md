# Trade Review navigation and Research Packs

## Review workflow

Open Backtest > Runs > Open > Trades. Filter by symbol, direction, result,
exit reason and entry UTC date. Choose oldest, newest or highest-R order.
View chart scrolls to Trade Review. Previous/Next and J/K follow the entire
matching list, including rows outside the initial 20-row preview. Boundaries
are disabled; typing and modified/repeated keystrokes do not navigate.
Chart settings persist while stepping. Jump to trade lists original trade
numbers, symbols and timestamps. If a filter excludes the open trade, the
review explicitly says it is outside current filters.

## Export

Choose All trades, Current filters/order, or Selected trades (checkboxes).
Export research pack produces downloadable PDF parts of at most 50 trades and
one UTF-8 CSV. Exit detail is optional. Keep this viewer and tab open until
completion; changing away cancels rendering and releases download URLs.
Download completed files before starting another export or leaving the viewer.
Cancel retains completed PDF parts, but does not present an incomplete CSV as
complete. Missing historical data is labelled in evidence and CSV warnings.

Each part has a full saved-run overview, configuration/provenance, metrics and
the whole equity/drawdown curve. These remain whole-portfolio observations,
not recomputed returns for the selected subset. Each trade includes facts,
full context, entry detail (40 bars before / 25 after), optional exit detail
(15 before / 20 after), and available recorded/reconstructed evidence.
Windows count available session bars, not wall-clock minutes. Short history
clips the window; missing bars/indicators are never fabricated.

References such as `Run 175 / Trade 42` identify the original immutable saved
snapshot ordinal, not the filtered table position. Reopen that saved run,
clear filters if necessary, open a trade and choose #42 in Jump to trade.
CSV includes the same identity, raw numeric facts, generic flattened evidence
and its provenance, warnings, strategy provenance, and recorded metadata.
Unavailable percentages remain blank rather than inferred from account equity.

## Implementation and accuracy

ResearchPack mounts the existing TradeAuditChart and PerformanceChart in one
offscreen rendering area. TradeAuditChart makes one canonical review request
per trade, includes extended declared history, then changes only the chart's
visible range to capture full/entry/exit views. It uses the same indicator
series, markers, levels, confirmation highlighting and candles as interactive
review. No new indicator calculations, execution rules or database writes.

The existing six-entry review cache deduplicates identical requests; the
backend market-data cache reuses historical bars. Trades render sequentially,
not as a burst of provider calls. Indicator reconstruction can still run per
trade; no unsafe cross-trade indicator state is introduced. Provider latency
and available history determine real export time.

A small PDF writer embeds chart JPEGs at 95% quality and selectable text on
landscape A4 pages. Evidence continues across labelled pages. No browser
installation, server-side renderer, new dependency or print dialog is required.
One 50-trade batch of chart images is retained while writing its PDF; completed
PDF blobs stay available until reset/unmount. Large packs may still require
significant browser memory/disk space. Raster charts are not vector artwork.

## Limits deliberately retained

- Export is local to the open viewer, not a persistent server job. No resume
  after reload, background notification service or shared export storage.
- Copyable immutable run/trade references instead of artificial URL routing.
- Exports use the original timeframe/session, New York chart time and standard
  evidence overlays, rather than arbitrary interactive research-only overlays.
- Current canonical reconstruction may differ from original historical data
  revisions or indicator seeds. Recorded facts take precedence; existing
  provenance warnings are included. Live-data parity is not claimed.
- PDF core fonts use ASCII; other characters are preserved as explicit Unicode
  escapes. CSV retains full Unicode. Embedded Unicode fonts are not included.
- Very long holding periods can compress the full-context chart; detail pages
  retain the requested readable candle windows.

## Verification and manual acceptance

Automated utility tests cover navigation, typing protection, scopes/IDs, detail
windows, missing evidence, CSV consistency, pagination and PDF cross references.
The isolated browser fixture exercises one and 103 trades, cancellation,
missing-history warnings and 1024/1440/1920 widths. It uses mocked historical
data, never broker credentials. Run full checks with Verify-Ledger.ps1.

Manual acceptance:
1. Open a saved run with many trades. Filter losers/shorts and a UTC date range;
   choose newest first. Open a trade, change bars/overlays, step with J/K and
   verify order, settings persistence and disabled boundaries.
2. Select several rows. Export selected trades, then current filters. Download
   PDF and CSV; compare IDs, counts, entry/exit, R, P&L and evidence to the viewer.
3. For VWAP V4 enable extended history interactively, use 50 bars before/25
   after and compare VWAP/bands/HTF evidence with the same exported trade.
   Repeat with another declared indicator family and a legacy run.
4. Inspect full equity start/end and drawdown. Read entry and exit detail at
   100% PDF zoom. Reopen a trade using its saved-run/original trade number.
5. Export 100+ trades; watch progress, cancel once, then complete. Confirm split
   PDFs and the single complete CSV. Missing history must show a warning.

### Verified fixture results (2026-10-05)

Full backend: 789 passed. Frontend utilities: 117 passed. Production build
passed (existing large-chunk warning remains). Browser: 103 trades in ~41s,
three PDF parts (~17.9MB, ~17.9MB, ~1.2MB), 103 CSV rows and 103 review requests.
Final sampled JS heap ~10.5MB (not a peak or total browser memory measurement).
No page overflow at 1024/1440/1920 and no runtime exceptions. An independent
PDF reader parsed/rendered the first 50-trade PDF without repairs: 202 pages,
151 embedded charts and selectable trade references through #50. Entry-detail
and whole-run equity/drawdown pages were visually inspected. Real provider
latency and historical-data parity were not measured in this mocked fixture.

## Visible-window price scaling

Interactive review and each exported window use the same candle-anchored domain.
Every valid visible high/low is retained, including extreme wicks. Overlay values
can expand that domain only if within half the original candle span of its edges;
expansion never chains from one overlay to another. This applies generically to
all price series and fixed levels, including HTF evidence, stops and targets.
Nearby HTF values remain plotted; distant ones do not flatten local candles.
A minimum reference span of 0.01% of midpoint (floor 1e-8) handles flat windows.
Padding is 5% of the expanded range or half that minimum reference span, whichever
is larger, with chart margins for marker labels. Non-price panes keep their own
scales. Invalid/missing OHLC rows are omitted with a count; valid extreme bars
are never discarded to improve appearance.

Off-scale labels and value ranges appear under the interactive chart and in
per-window Research Pack evidence. Original indicator calculations, series,
recorded values, trade facts and fills are unchanged. Pan/zoom recalculates the
scale from the visible window. Existing price-axis manual gestures remain a
user override; double-click the price axis to restore automatic scaling.

Acceptance: open a QQQ example near 737-739 with extended daily EMA near 709;
check candle wicks and VWAP are readable and the scale-evidence text reports
the EMA below scale. Repeat near 714-716 with EMA around 713, which should be
included. Export entry/exit/full views and compare their evidence and wicks.
