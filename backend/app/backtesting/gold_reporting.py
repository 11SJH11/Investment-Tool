"""Immutable experiment provenance and post-run audit; no signal decisions."""
from dataclasses import asdict
from hashlib import sha256
import json

from app.backtesting.intraday_reporting import annotate_intraday


def annotate_gold(result, frames, config, params):
    digest = sha256()
    for symbol, timeframes in sorted(frames.items()):
        for timeframe, frame in sorted(timeframes.items()):
            digest.update(f"{symbol}:{timeframe}:".encode())
            digest.update(frame.to_json(orient="split", index=False, date_format="iso", double_precision=15).encode())
    fingerprint = digest.hexdigest()
    signature = dict(data=fingerprint, engine=asdict(config), params=params,
                     start=result["start"], end=result["end"], session=result["session"],
                     providers=result["data"]["providers"], primary=result["primary_timeframe"])
    result["data"]["dataset_fingerprint"] = fingerprint
    result["data"]["comparison_signature"] = sha256(json.dumps(signature, sort_keys=True, default=str).encode()).hexdigest()
    result["strategy"]["params"] = dict(params)
    for record in [*result["trades"], *result["setups"]]:
        meta = record["metadata"]
        meta.setdefault("confirmed_at", meta.get("type3_confirmation_time"))
    annotate_intraday(result, frames)
    result["data"]["warnings"] = [
        "Experimental filter study, not optimized. Compare identical data/costs and validate out of sample.",
        "MFE/MAE are lower bounds excluding unknown exit-bar ordering; historical missing values remain unavailable.",
        "Rejecting a position can expose extra later setups: retention uses matched baseline setup identities."]
    key = result["strategy"]["key"]
    if "dxy" in key or "full_candidate" in key:
        result["data"]["warnings"].append("DXY data unavailable. This variant cannot validate performance; no proxy or future data is substituted.")
