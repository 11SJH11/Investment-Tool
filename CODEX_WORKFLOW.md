# Using Codex efficiently on Ledger

`AGENTS.md` is the standing engineering contract. Do not repeat all of it in every task; give Codex the behaviour you want and let it inspect the repository under those rules.

## Recommended task format

```text
Inspect the existing Ledger implementation before editing.

Task:
<one bounded outcome>

Required behaviour:
- ...
- ...

Must not change:
- ...
- ...

Acceptance checks:
- ...
- ...

After implementation:
- run relevant tests
- run the broad regression suite/build when practical
- report changed files, assumptions and any remaining risk
- do not refactor unrelated code
```

## Good task examples

- "Import closed OANDA trades into the existing common Journal, read-only, idempotent by OANDA trade ID. Do not add order placement."
- "Add VWAP standard-deviation bands as an indicator through the existing indicator registry. Do not change chart data routing or strategy rules."
- "Add a confluence variant of the frozen XAU baseline that records minimum sweep size without modifying the baseline plugin."
- "Add a side-by-side saved-run comparison for expectancy, trade count, drawdown and session breakdown; do not rerun saved results silently."

## Bad task examples

- "Improve the app."
- "Make the strategy more profitable."
- "Refactor the backend."
- "Fix all chart issues."

Those prompts are broad enough to encourage unnecessary changes or overfitting.

## Suggested division of work

Use the planning/discussion chat for:
- trading concepts and deterministic rule definitions;
- product direction and prioritisation;
- experiment design / avoiding overfitting;
- architecture decisions;
- interpreting backtest results;
- deciding what Codex should build next.

Use Codex for:
- repository inspection;
- bounded implementation tasks;
- tests and migrations;
- bug fixes;
- code review/diff cleanup;
- repetitive integration work once behaviour is clearly specified.
