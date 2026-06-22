from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "insight.db"


def first_url(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return first_url(parsed)
        for part in text.split(","):
            url = part.strip().strip("\"'")
            if url:
                return url
        return None
    if isinstance(value, list):
        for item in value:
            url = first_url(item)
            if url:
                return url
    if isinstance(value, dict):
        for key in ("cover_url", "video_cover_url", "image_list", "url", "src", "image_url"):
            url = first_url(value.get(key))
            if url:
                return url
    return None


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    updated = 0
    try:
        rows = conn.execute(
            "SELECT note_id, raw_json FROM notes WHERE cover_url IS NULL OR cover_url = '' OR cover_url LIKE '\"http%' OR cover_url LIKE '''http%'"
        ).fetchall()
        for row in rows:
            raw_text = row["raw_json"]
            if not raw_text:
                continue
            try:
                raw = json.loads(raw_text)
            except json.JSONDecodeError:
                continue
            url = first_url(raw)
            if not url:
                continue
            conn.execute(
                "UPDATE notes SET cover_url = ? WHERE note_id = ?",
                (url, row["note_id"]),
            )
            updated += 1
        conn.commit()
    finally:
        conn.close()
    print(f"backfilled_cover_urls={updated}")


if __name__ == "__main__":
    main()
