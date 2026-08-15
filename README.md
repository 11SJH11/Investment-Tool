# Ledger — Portfolio Analysis Web App

A local-only web dashboard for investment research and tracking. Two parts:

- `backend/` — FastAPI wrapping the analysis engine (fundamentals, diversification,
  backtesting, portfolio tracking). Talks to Yahoo Finance for real data.
- `frontend/` — React app (Vite + Tailwind) that gives you a proper UI on top of it.

Nothing here executes trades or moves money. It's research and record-keeping only.

## First-time setup

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Leave this running in one terminal.

**Optional: enable macro context + AI journal review**
```bash
cd backend
cp .env.example .env
```
- **Macro context** needs a free key from https://fred.stlouisfed.org/docs/api/api_key.html
- **AI journal review** has two options:
  - **Free + fully private (recommended):** install [Ollama](https://ollama.com).
    On Fedora: `sudo dnf install ollama` (or use their install script if that
    package isn't available in your repos yet). Then:
    ```bash
    ollama pull llama3.1
    ollama serve   # or it may already run as a background service
    ```
    Nothing to configure in `.env` — it's detected and used automatically.
  - **Anthropic API (small per-use cost):** add `ANTHROPIC_API_KEY` to `.env`
    from https://console.anthropic.com. Used automatically as a fallback if
    Ollama isn't running.

The app works fine without either — those two specific panels just show a
setup message instead of data until you configure something.

**Frontend (separate terminal):**
```bash
cd frontend
npm install
npm run dev
```
Open the URL it prints (usually http://localhost:5173).

## Using it

- **Fundamentals** — enter comma-separated tickers, see valuation/growth/margin
  metrics grouped by sector and asset class, plus a sector-relative valuation
  table (each stock's P/E vs. its sector ETF's P/E — a fairer comparison than
  pitting a tech stock against an energy stock).
- **Diversification** — same ticker list, shows a correlation matrix so you can
  see if your picks actually move independently or are secretly one big bet.
- **Backtest** — define a target allocation (`TICKER:weight, ...` summing to 1.0),
  a monthly contribution, and a benchmark to compare against. Runs against real
  historical prices.
- **Portfolio** — your actual record. Includes:
  - **Macro context** — current Fed funds rate, 10-year Treasury yield, inflation,
    unemployment. Informational only, never a signal.
  - **Drift chart** — target vs. actual allocation per holding.
  - **Contribution log** — record what you actually bought (never places trades).
  - **Stress test** — estimates how your current holdings would move in a
    hypothetical market shock, based on each holding's historical beta.
  - **Reasoning journal** — write down your thesis and exit conditions for each
    holding while thinking clearly. An AI agent can review your *current* data
    against your *own* stated logic and flag contradictions or met exit
    conditions — it never generates its own buy/sell opinions, only checks
    your plan against reality.
- **Settings** — refresh interval notes and preference (stored in your browser only).

## Notes

- Portfolio data persists to `backend/portfolio_state.json`. Back this up if you
  care about the history — it's a plain JSON file, easy to inspect or edit by hand.
- Price/fundamentals data is cached in `backend/data_cache/` to avoid hammering
  Yahoo Finance. Delete that folder to force a refresh.
- This is a personal tool, not a hosted product — there's no auth, and CORS is
  wide open between localhost:5173 and localhost:8000 since nothing leaves your
  machine.
- See `backend/README` (the original portfolio_tool README carried over) for
  details on the underlying calculation logic (IRR-based returns, drift
  thresholds, etc.) if you want to tweak the math.
