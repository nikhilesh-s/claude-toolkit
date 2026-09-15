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


def history(n: int = 50, include_pending: bool = True) -> list[dict]:
    """Compact rows for the History view: saved records (from their files) plus unsaved reviews, newest first."""
    from .records import DESTINATIONS
    from .sync import summary_line
    rows = []
    files = list(RECORDS.glob("*.json")) + (list(PENDING.glob("*.json")) if include_pending else [])
    for f in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[: n * 2]:
        try:
            r = json.loads(f.read_text())
        except Exception:
            continue
        ex = r.get("export") or {}
        rows.append({
            "id": r["id"], "title": r["source"].get("title") or r["source"]["original_url"], "creator": r["source"].get("creator", ""),
            "platform": r["source"].get("platform", ""), "url": r["source"]["original_url"],
            "destination": r["intent"]["destination"], "destination_title": DESTINATIONS.get(r["intent"]["destination"], r["intent"]["destination"]),
            "instruction": r["intent"]["user_instruction"], "created_at": r["created_at"], "saved_at": r.get("saved_at", ""),
            "saved": bool(r.get("saved_at")), "status": r["status"], "confidence": r["extraction"].get("confidence", 0),
            "export_status": ex.get("status", "") if r.get("saved_at") else "", "sync_line": summary_line(ex, r) if r.get("saved_at") else "Not saved",
            "master_status": (ex.get("master_sync") or {}).get("status", ""), "destination_status": (ex.get("destination_sync") or {}).get("status", ""),
            "last_error": ex.get("last_error", "") or (ex.get("destination_sync") or {}).get("last_error", ""),
            "resolution": (r.get("destination_resolution") or {}).get("action", ""), "resolution_label": (r.get("destination_resolution") or {}).get("candidate_label", ""),
            "bulk_run": (r.get("batch") or {}).get("run_id", ""), "bulk_origin": (r.get("batch") or {}).get("source_origin", ""), "bulk_container": (r.get("batch") or {}).get("source_container", ""),
            "google_ref": (ex.get("destination_sync") or {}).get("remote_ref", "") or (ex.get("master_sync") or {}).get("remote_ref", ""),
        })
    rows.sort(key=lambda x: x.get("saved_at") or x["created_at"], reverse=True)
    return rows[:n]


def recent(n: int = 20) -> list[dict]:
    return list(reversed(index()))[:n]


def describe(e: dict) -> str:
    return f"{e['id']}  {DESTINATIONS.get(e['destination'], e['destination'])}  {e['status']}  {e['canonical_url']}  — {e['instruction'][:60]}"
