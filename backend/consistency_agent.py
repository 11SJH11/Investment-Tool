"""
consistency_agent.py

Deliberately narrow in scope: this agent does NOT predict whether a stock
is a good investment. It only checks your CURRENT holdings and metrics
against reasoning YOU already wrote down (in the journal) while presumably
thinking clearly -- and flags contradictions or unmet exit conditions.

Think of it as: "does reality still match the plan you made for yourself?"
not "what should the plan be?"

Two backend options, chosen automatically based on what's configured:
  1. Local Ollama (free, fully private -- nothing leaves your machine).
     Requires Ollama installed and running locally (https://ollama.com).
  2. Anthropic API (small per-use cost, requires your own API key from
     console.anthropic.com). Used only if Ollama isn't available/configured.

Set AI_BACKEND=ollama or AI_BACKEND=anthropic in .env to force one;
otherwise it tries Ollama first, then falls back to Anthropic.
"""

import os
import json
import requests

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
AI_BACKEND = os.environ.get("AI_BACKEND")  # "ollama" | "anthropic" | None (auto)

SYSTEM_PROMPT = """You are a consistency-checking assistant for a personal investment journal. \
Your ONLY job is to compare the user's own previously-written reasoning and exit conditions \
against their current portfolio data, and flag where reality has diverged from their stated plan.

Strict rules:
- NEVER recommend buying, selling, or holding anything based on your own judgment of the stock.
- NEVER predict future price movement.
- ONLY flag: (a) exit conditions that now appear to be met based on the data given, \
(b) stated theses that current data seems to contradict, (c) allocation drift from stated targets.
- If a journal entry's exit condition can't be evaluated from the data provided, say so explicitly \
rather than guessing.
- Be factual and neutral. Quote the user's own words back to them when flagging something -- \
this is about their own stated logic, not your opinion.
- Output valid JSON only, matching this schema, and nothing else -- no preamble, no markdown fences:
{"flags": [{"ticker": str, "type": "exit_condition_met" | "thesis_contradiction" | "unclear", \
"journal_note": str, "current_data_point": str, "explanation": str}], "summary": str}
"""


def _ollama_available() -> bool:
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def _call_ollama(user_content: str) -> str:
    resp = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "format": "json",
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _call_anthropic(user_content: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or Anthropic is None:
        raise RuntimeError("no_anthropic_key")

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return "".join(block.text for block in response.content if hasattr(block, "text"))


def review_journal(journal_entries: list, current_metrics: dict, current_holdings: dict) -> dict:
    """
    journal_entries: list of {date, ticker, note, exit_condition}
    current_metrics: {ticker: {fundamentals dict}} -- from fundamentals.py
    current_holdings: {ticker: {value, gain_loss_pct, current_allocation_pct, ...}}
    """
    if not journal_entries:
        return {"flags": [], "summary": "No journal entries yet -- nothing to check."}

    payload = json.dumps({
        "journal_entries": journal_entries,
        "current_metrics": current_metrics,
        "current_holdings": current_holdings,
    }, indent=2)

    backend = AI_BACKEND
    if backend is None:
        backend = "ollama" if _ollama_available() else "anthropic"

    if backend == "ollama":
        if not _ollama_available():
            raise RuntimeError(
                "Ollama isn't reachable at " + OLLAMA_HOST + ". Install it from "
                "https://ollama.com, run `ollama pull " + OLLAMA_MODEL + "`, and make sure it's "
                "running -- or set ANTHROPIC_API_KEY in .env to use the API instead."
            )
        text = _call_ollama(payload)
    else:
        try:
            text = _call_anthropic(payload)
        except RuntimeError:
            raise RuntimeError(
                "No local Ollama running and no ANTHROPIC_API_KEY configured. "
                "Install Ollama (free, private, https://ollama.com) and run `ollama pull " +
                OLLAMA_MODEL + "`, or add ANTHROPIC_API_KEY to .env."
            )

    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"flags": [], "summary": "Agent response couldn't be parsed.", "raw": text}
