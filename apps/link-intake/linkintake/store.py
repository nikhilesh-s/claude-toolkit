"""Local canonical store: one JSON per record + an index line for dedupe/listing.
Google Docs is the human-readable mirror; swap this module for a DB later without touching extraction."""
from __future__ import annotations

import json
from pathlib import Path

from . import config
from .records import DESTINATIONS

RECORDS = config.STATE_DIR / "records"
PENDING = config.STATE_DIR / "pending"
PREVIEWS = config.STATE_DIR / "previews"
INDEX = config.STATE_DIR / "index.jsonl"


def _p(d: Path, rid: str) -> Path:
    return d / f"{rid}.json"


def write_pending(rec: dict) -> Path:
    PENDING.mkdir(parents=True, exist_ok=True)
    p = _p(PENDING, rec["id"])
    p.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    return p


def load(rid: str) -> dict:
    for d in (RECORDS, PENDING):
        p = _p(d, rid)
        if p.exists():
            return json.loads(p.read_text())
    raise FileNotFoundError(f"no record {rid}")


def write(rec: dict) -> Path:
    RECORDS.mkdir(parents=True, exist_ok=True)
    p = _p(RECORDS, rec["id"])
    p.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    return p


def save(rec: dict) -> Path:
    p = write(rec)
    with INDEX.open("a") as f:
        f.write(json.dumps({
            "id": rec["id"], "created_at": rec["created_at"], "canonical_url": rec["source"]["canonical_url"],
            "destination": rec["intent"]["destination"], "instruction": rec["intent"]["user_instruction"],
            "dedupe_key": rec["dedupe_key"], "status": rec["status"], "title": rec["source"].get("title", ""),
        }) + "\n")
    _p(PENDING, rec["id"]).unlink(missing_ok=True)
    return p


def index() -> list[dict]:
    if not INDEX.exists():
        return []
    out: dict[str, dict] = {}
    for line in INDEX.read_text().splitlines():
        if line.strip():
            try:
                e = json.loads(line)
                out[e["id"]] = e  # last write wins; a re-export appends a fresh line
            except (json.JSONDecodeError, KeyError):
                pass
    return list(out.values())


def find_by_url(canonical_url: str) -> list[dict]:
    return [e for e in index() if e["canonical_url"] == canonical_url]


def find_exact(dedupe_key: str) -> dict | None:
    # Only a successfully-saved, non-failed record blocks a retry as a duplicate.
    for e in reversed(index()):
        if e["dedupe_key"] == dedupe_key and e.get("status") != "failed":
            return e
    return None


def pending_exports() -> list[dict]:
    out = []
    for e in index():
        try:
            rec = load(e["id"])
        except FileNotFoundError:
            continue
        if rec.get("export", {}).get("status", "export_pending") != "exported":
            out.append(rec)
    return out


def recent(n: int = 20) -> list[dict]:
    return list(reversed(index()))[:n]


def describe(e: dict) -> str:
    return f"{e['id']}  {DESTINATIONS.get(e['destination'], e['destination'])}  {e['status']}  {e['canonical_url']}  — {e['instruction'][:60]}"
