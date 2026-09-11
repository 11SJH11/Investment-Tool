from __future__ import annotations

import json
from typing import Any

from app.storage.database import Database


class ResearchRepository:
    """Persistence for normalised research records from any source.

    Provider-specific payloads belong in metadata; the common fields remain
    queryable so the UI does not need one table/model per data vendor.
    """

    def __init__(self, database: Database):
        self.database = database

    def upsert_item(self, payload: dict[str, Any]) -> dict:
        data = _normalise(payload)
        source_item_id = data["source_item_id"]
        with self.database.connect() as connection:
            if source_item_id:
                existing = connection.execute(
                    "SELECT id FROM research_items WHERE source=? AND source_item_id=?",
                    (data["source"], source_item_id),
                ).fetchone()
                if existing:
                    connection.execute(
                        """
                        UPDATE research_items
                        SET item_type=?, instrument=?, published_at=?, title=?, summary=?, direction=?,
                            confidence=?, url=?, metadata_json=?, updated_at=CURRENT_TIMESTAMP
                        WHERE id=?
                        """,
                        (
                            data["item_type"], data["instrument"], data["published_at"], data["title"],
                            data["summary"], data["direction"], data["confidence"], data["url"],
                            data["metadata_json"], existing["id"],
                        ),
                    )
                    row = connection.execute("SELECT * FROM research_items WHERE id=?", (existing["id"],)).fetchone()
                    return _decode(row)

            cursor = connection.execute(
                """
                INSERT INTO research_items(
                    source,source_item_id,item_type,instrument,published_at,title,summary,
                    direction,confidence,url,metadata_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    data["source"], data["source_item_id"], data["item_type"], data["instrument"],
                    data["published_at"], data["title"], data["summary"], data["direction"],
                    data["confidence"], data["url"], data["metadata_json"],
                ),
            )
            row = connection.execute("SELECT * FROM research_items WHERE id=?", (cursor.lastrowid,)).fetchone()
        return _decode(row)

    def list_items(
        self,
        *,
        instrument: str | None = None,
        source: str | None = None,
        item_type: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        where: list[str] = []
        params: list[Any] = []
        if instrument:
            where.append("UPPER(instrument)=?")
            params.append(instrument.strip().upper())
        if source:
            where.append("source=?")
            params.append(source.strip().lower())
        if item_type:
            where.append("item_type=?")
            params.append(item_type.strip().lower())
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM research_items {clause}
                ORDER BY COALESCE(published_at, created_at) DESC, id DESC
                LIMIT ?
                """,
                (*params, max(1, min(int(limit), 1000))),
            ).fetchall()
        return [_decode(row) for row in rows]

    def delete_item(self, item_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM research_items WHERE id=?", (item_id,))
        return cursor.rowcount > 0


def _normalise(payload: dict[str, Any]) -> dict[str, Any]:
    source = str(payload.get("source") or "manual").strip().lower()
    title = str(payload.get("title") or "").strip()
    if not source:
        raise ValueError("research source is required")
    if not title:
        raise ValueError("research title is required")

    direction = str(payload.get("direction") or "neutral").strip().lower()
    if direction not in {"bullish", "bearish", "neutral", "mixed", "unknown"}:
        raise ValueError("direction must be bullish, bearish, neutral, mixed or unknown")

    confidence = payload.get("confidence")
    if confidence in (None, ""):
        confidence = None
    else:
        confidence = float(confidence)
        if confidence < 0 or confidence > 100:
            raise ValueError("confidence must be between 0 and 100")

    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")

    return {
        "source": source,
        "source_item_id": str(payload.get("source_item_id") or "").strip(),
        "item_type": str(payload.get("item_type") or "note").strip().lower(),
        "instrument": str(payload.get("instrument") or "").strip().upper(),
        "published_at": payload.get("published_at") or None,
        "title": title,
        "summary": str(payload.get("summary") or "").strip(),
        "direction": direction,
        "confidence": confidence,
        "url": str(payload.get("url") or "").strip(),
        "metadata_json": json.dumps(metadata, separators=(",", ":"), sort_keys=True),
    }


def _decode(row) -> dict:
    result = dict(row)
    try:
        result["metadata"] = json.loads(result.pop("metadata_json", "{}") or "{}")
    except json.JSONDecodeError:
        result["metadata"] = {}
    return result
