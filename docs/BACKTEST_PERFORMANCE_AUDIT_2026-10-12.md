# Backtest performance audit — 12 October 2026

## Scope and measurement status

This audit starts from `01ce536` plus the current local confluence strategies and
Research Director continuation. It does not change trading rules, fills, market
data, saved results or input fingerprint semantics. Measurements use cached QQQ
Alpaca SIP split-adjusted bars, never provider credentials or a live database write.
Only selected configuration/data fields of runs 191–199 were inspected, with
SQLite `mode=ro`. Results go to an isolated database outside the repository.

The workstation has another active Python workload. These are busy-workstation
measurements, not controlled hardware benchmarks. cProfile adds substantial
overhead; bounded profiles must not be presented as completed-period backtests.
Inclusive function durations overlap and must not be added together.

Artifacts: `C:/Users/jamie/Project/performance-audit-20261012/`.
Harness: `backend/tools/audit_backtest_performance.py`. It reports wall/CPU time,
core equivalents, bar progress, memory, phase spans and optional cProfile output.
Windows process I/O counters are not physical disk throughput. Run one case at a
time. `--no-profile` disables cProfile for before/after wall-time comparisons;
`--reference-normalizer` selects the frozen pre-audit implementation from a test
fixture. Such instrumented reference runs are audit artifacts, not published runs.

## Initial measured bottlenecks, before optimization

Three-month range: 2026-01-01 through 2026-03-31, 23,790 primary bars. Each initial
profile was stopped at a 150-second budget. All-day entry eligibility and zero
costs are explicit benchmark settings; these do not reproduce the saved runs'
09:30–11:30 entry window. Position sizing is 100% position value, no leverage.

| Case | Processed bars | Wall s | CPU s | bars/s | Core equivalents |
|---|---:|---:|---:|---:|---:|
| D6 | 16,448 | 150.278 | 148.641 | 109.45 | 0.989 |
| MSS15 | 17,600 | 150.069 | 147.984 | 117.28 | 0.986 |
| MidVol | 17,152 | 150.658 | 147.969 | 113.85 | 0.982 |
| SweepS5 | 16,192 | 150.425 | 148.141 | 107.64 | 0.985 |

For D6, ranked inclusive costs:

1. `_today_rth`: 100.186 s / **66.7%**; `_normalise_1m` accounts for 82.271 s
   (**54.7%**) within it. Every decision converts/filter/copies up to 500 bars.
2. `_vwap`: 20.730 s / **13.8%**. Repeated pandas arithmetic and reductions on
   current-session data. Changing to cumulative sums may change floating-point
   rounding, so it was deliberately left unchanged.
3. `_row_to_series`: 9.720 s / **6.5%**, 35,504 calls.
4. `StrategyContext.bars`: 7.498 s / **5.0%**, 16,944 calls (part of strategy time).
5. Data load/session preparation: about 0.15 s / **0.1%**.

MSS15's confluence work was 3.920 s, including 2.291 s rebuilding pivots, versus
98.080 s in session normalization. MidVol's confluence work was 4.632 s, including
1.526 s building historical same-minute samples, versus 97.995 s normalization.
These short prefixes include warmup and do not establish long-run confluence costs.
SweepS5 spent 12.166 s rebuilding strict pivots (115 calls); its peak RSS was
140,152,832 bytes. All four profiles used one simulation worker.

First proposed/implemented fix: avoid temporary Series and the initial full-frame
copy in `_normalise_1m`, using DatetimeIndex calendar arrays and one masked copy.
The algorithm still processes only the supplied completed prefix. It preserves
the exact output, RTH bounds, timezone conversion, row order and defensive copying.
The theoretical ceiling from eliminating all normalization work is approximately
3x; actual improvement must be measured. Primary risks are dtype, DST, index and
mutation differences. Exact reference tests cover these and full engine outputs.

## Architecture findings

- Context already precomputes completion indexes and uses `searchsorted` on the
  causal boundary. Its defensive copies protect strategy isolation; do not replace
  them with writable shared views indiscriminately.
- V4/V5 higher-timeframe regime calculation is already cached per daily/hourly
  decision bucket. Confluence hooks already run only for candidate entries or
  reversals after parent filters. Adding another such gate is not a new gain.
- `strict_pivots`, BOS and FVG helpers rebuild events from bounded completed windows.
  FVG fill scans can be quadratic within sessions. SweepS5 repeats multi-session
  pivot construction. MidVol caches prior distributions daily but still normalizes
  up to 26,000 rows per candidate. These remain potential follow-up targets.
- The discovery tool precomputes event indexes. Its definitions are not a drop-in
  execution substitute: rolling-window edges, latest-pivot consumption and causal
  confirmation rules must match exactly. Do not replace executable rules with
  a superficially similar research statistic.
- Ordinary jobs use a ThreadPoolExecutor; research variants already use Windows
  spawn processes with provider/repository-free prepared inputs, frozen source,
  shared CPU reservations and cancellation. Near-one-core CPU time here is
  consistent with a serial Python/pandas workload, not proof of a measured
  multi-thread scaling curve.
- Per-worker prepared snapshots and per-simulation frame copies consume RAM.
  Shared memory/event caches require immutability and identities covering data,
  concepts, source and session rules. No shared cache or process-queue migration
  has been introduced in this increment.
- Equity uses a dict per timestamp. Reporting and serialization occur after the
  simulation, so bounded profiles do not measure their completed-run cost.
- The job UI already shows phase/count/percent. Rolling throughput, elapsed and
  ETA remain missing; a persisted backend start time is needed to distinguish
  queue time from execution time.

## Fingerprints: runs 191 and 196

Both use fingerprint `5752f0395279be8060ec084ae6a5e6c29fe2ac7e9cdebeadd8990bc9594020b2`
and inputs QQQ 1m: **660,990**, 15m: **44,121**. Runs 192–195 and 197–199 use
`afaefe1e6bcdbabf13074ac273b116f1e0ca67c1e0604d038c1cb46ed67b6899` and only
QQQ 1m: **660,990**. The composite identity hashes all timeframe frames, diagnostic
history, providers and source namespaces. Extra 15m input therefore legitimately
changes it. These 15m frames are loaded through the normal cache path, not silently
substituted by an audit resample.

The saved records lack separate timeframe hashes. Equal 1m counts cannot prove
historical 1m values identical across the two groups. A changed cache can also
change values without changing row count. No claim of exact cross-group 1m parity
is made, and no fingerprint logic or historical run was rewritten.

## GPU assessment

The measured dominant work allocates pandas/Python objects and filters small
session windows inside a sequential stateful loop. A GPU cannot accelerate those
operations without a different data/execution architecture; transfer/launch costs
would recur frequently. CPU allocation reduction and causal precomputation are
the evidence-supported next steps. No CUDA, cuDF, CuPy or PyTorch speedup is claimed
without a benchmark. No GPU dependencies were added.

## Verification and remaining work

### Completed three-month before/after comparison

Each run completed all **23,790 bars**. cProfile was disabled; the same timing
wrappers remained enabled. Reference uses the frozen old normalizer. Runs were
serial, on the same busy workstation, one observation per configuration.

| Strategy | Trades | Before wall / CPU s | After wall / CPU s | Wall reduction |
|---|---:|---:|---:|---:|
| D6 | 138 | 88.548 / 88.031 | 72.713 / 72.266 | 17.9% |
| MSS15 | 84 | 92.085 / 91.766 | 75.465 / 75.406 | 18.0% |
| MidVol | 110 | 94.846 / 94.609 | 79.500 / 79.219 | 16.2% |
| SweepS5 | 91 | 105.043 / 104.766 | 88.954 / 88.719 | 15.3% |

All result keys match exactly except intentionally excluded performance timings
and saved-run bookkeeping. This includes setup/rejection records, metadata,
entry/exit paths, trades, PF/returns/drawdown/R, equity and every analysis output.
No tolerance, rounding or historical database update was used. Peak RSS across
these eight runs was approximately 165–167 MiB. Source instrumentation and the
reference override are explicitly identified in audit reports.

For the complete D6 reference, data load/session preparation was 0.101 s; engine
inclusive 87.979 s; strategy 76.739 s; row conversion 5.986 s; context access
4.649 s; equity merge/decorate 0.114 s; metrics 0.010 s; isolated database save
0.441 s. Per-bar equity dictionary construction remains inside engine time, not
separately measured. Process I/O includes the isolated DB and is not simulation-
only disk traffic. Do not infer a disk bottleneck from these cumulative counters.

The first normalization change passes 14 exact-reference tests, including engine
trade/metadata/rejection/equity/metric/analysis equality for the VWAP parent, D6,
MSS15, MidVol and SweepS5. No rounding tolerance or metric-only comparison is used.
Final verification on 13 October: **1,234 backend passed**, zero failures/errors/
skips (563.80 s), including 31 real-Docker tests; **133 frontend passed**; production
build passed. Browser fixtures passed at 1024/1440/1920px. Existing warnings remain.
No orphan Ledger containers, unrelated containers unchanged. The first full run's
single Docker tag lookup failure was repaired by restoring the existing immutable
image tag; the complete rerun is green. No production logic fix was required.
Final harness smoke also passes with an explicit 09:30–11:30 entry window; that
one-day smoke is not a performance or strategy-validity benchmark.

Still pending: long-period confluence profiles; completed one-year/full-range
comparisons where practical; 1/2/4/6 independent-worker scaling and RAM measurements;
causal event-index optimization if supported by those measurements; progress ETA;
and the rest of the Research Director work described in its current handoff.
This first increment is not completion of the full performance audit.

The next priority is repeating the profiles with the actual saved-run **09:30–11:30**
entry window, using `--entry-start 09:30 --entry-end 11:30`. Engine entry guardrails
are evaluated after strategy decisions; time-window rejection can leave a strategy
flat and change candidate/confluence frequency. Thus the all-day benchmark's cost
ranking must not be assumed to explain the user's exact multi-hour workload.
This is a code-supported hypothesis to measure, not a reason to skip strategy
decisions or change the execution contract.
