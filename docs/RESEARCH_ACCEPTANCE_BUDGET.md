# Initial OpenAI acceptance: maximum USD 5

This is a one-time acceptance allowance, not permission for ongoing campaigns.
The user subsequently requested no paid calls yet while Windows backend state
is established. No paid calls or demo orders were made in this checkpoint.

## Windows configuration findings (24 October 2026)

Application settings were loaded without printing the key. An OpenAI key is
present, model access is enabled, and the configured model is `gpt-6.1-sol`.
An authenticated, non-generating `GET /v1/models/gpt-6.1-sol` subsequently returned
HTTP 200 with the expected model ID. This verifies authentication/model visibility,
not paid generation, billing balance or complete Research Agent acceptance.
The shell alone did not contain these settings; application configuration did.

Configured rates are USD 1 input / 5 output per million tokens. Current standard
rates are USD 2 input / 10 output; the lower rates are Flex/Batch pricing. Sources:
[official pricing](https://developers.openai.com/api/docs/pricing) and
[configured model](https://developers.openai.com/api/docs/models/gpt-6.1-sol).
The adapter now explicitly requests the default service tier. Do not use the
underpriced configuration for standard acceptance calls. No model substitution
or secret-file edit was performed.

No Ledger API responded on localhost ports 8000, 8001, 8010 or 8080. Listener
inspection found the isolated frontend test server on 19441, not a Ledger API.
The normal app lifespan starts broker scheduling and research workers and can
perform recovery writes; it was not launched against the user database.
Read-only inspection found three campaigns (CANCELLED, DEVELOPMENT_COMPLETE,
PREPARATION_FAILED), no research-loop rows, and four projects (two BASELINE_RUNNING,
one BASELINE_ANALYSIS, one CREATED). These records were preserved, not retried or
rewritten. No holdout content was read.
The backtest queue has two completed, one failed and one cancelled job; none are
queued or running. No existing campaign/project/job state was modified.

## Safe status check

Once the backend is running with this checkpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/strategy-lab/research-agent/model-status
```

This GET reports configured model/pricing and acceptance accounting, never the
key. It does not contact OpenAI, create budget tables or start a campaign.
`connection_tested: false` distinguishes configuration from real acceptance.
For a non-paid startup, set `RESEARCH_LLM_ENABLED=false` in the launch process;
existing startup recovery/scheduling still requires operational care. Do not run
a second backend against the same database.

## Acceptance settings, only after the no-paid-call hold is lifted

Use process/service environment overrides rather than editing or exposing the
existing secret file:

```powershell
$env:RESEARCH_LLM_ACCEPTANCE_BUDGET_USD='5'
$env:RESEARCH_LLM_INPUT_USD_PER_MILLION='2'
$env:RESEARCH_LLM_OUTPUT_USD_PER_MILLION='10'
```

Keep the existing configured model and key. Recheck official pricing before use.
These settings alone do not start a campaign. Keep unrelated campaigns stopped;
use the minimum explicit development-only acceptance operation, never holdouts.
The existing key need not be recreated. If a future installation has no key,
create a project key through the [official quickstart](https://developers.openai.com/api/docs/quickstart)
and store it only in backend `RESEARCH_LLM_API_KEY`, using a protected service
environment file outside Git or a masked process-local prompt. Never put it in
frontend code, chat, command history or committed files.

## Enforcement

The adapter reserves conservative maximum cost before every outgoing request in
an immediate SQLite transaction shared by projects/campaigns. Two additive tables
are initialized on first capped use: `agent_acceptance_allowance` and
`agent_acceptance_calls`. The allowance is immutable, at most USD 5, survives
restart and remains enforced if its environment option is removed. No automatic
refund, retry, expiry, reset or increase is implemented. All app model-adapter
construction paths supply the same application database.

At the corrected rates, 250,000 reserved input tokens plus 4,096 maximum output
tokens reserve USD 0.54096 per call. Failed/interrupted/unknown-usage calls retain
the full reservation. Completed calls also retain reservations conservatively;
known usage estimates are reported separately. Unexpected excess usage blocks
later calls. Existing project/campaign budgets remain additional gates. Planned
project allocations are not invoices; this cap covers dispatched/in-flight calls.

`usage_estimate_usd` is not an independently reconciled invoice. Unknown usage is
not free. Correct conservative rates are mandatory; unexpected provider billing
cannot be undone. Other applications/API keys or deliberately different databases
are outside this local ledger; do not change databases to evade the allowance.

Current genuine acceptance result: **pending; zero calls and USD 0 spent**.
The cap is implemented/tested but has not been initialized in the production DB.
