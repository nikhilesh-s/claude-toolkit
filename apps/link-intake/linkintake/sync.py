"""Google sync with idempotent, bounded, never-fatal writes.

save -> local record committed -> sync_record(): Master Intake row, then destination write, each checked for the
Record ID before appending -> then a bounded sweep of older pending/partial records. Any failure is recorded on
the record (last_error) and left for the next sweep. Nothing here can make a local save fail."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from . import config, destinations as D, store
from .google_api import Google, GoogleError, doc_text, doc_url, is_configured, sheet_url
from .records import empty_export, empty_sync

DEFAULT_BUDGET_S = 25


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def google_state(cfg: dict | None = None) -> str:
    cfg = cfg or config.load()
    if cfg["google"].get("export_mode", "auto") == "off":
        return "off"
    return "ready" if is_configured() else "not_authorized"


def _targets(cfg: dict) -> dict:
    return cfg["google"].get("targets", {})


# ---------- idempotent writers
def _doc_has(g: Google, doc_id: str, record_id: str, tab_id: str = "") -> bool:
    return record_id in doc_text(g.doc_get(doc_id), tab_id)


def _sheet_has(g: Google, sheet_id: str, record_id: str) -> bool:
    col = chr(ord("A") + len(D.SCHOLAR_HEADER) - 1)  # Record ID column
    return any(row and row[0] == record_id for row in g.sheet_values(sheet_id, f"{col}1:{col}5000"))


def write_master(g: Google, rec: dict, cfg: dict) -> dict:
    doc_id = _targets(cfg).get("master_doc")
    if not doc_id:
        raise GoogleError(412, "Master Intake doc not configured: run `linkintake google-setup`")
    if not _doc_has(g, doc_id, rec["id"]):
        g.doc_append_table_row(doc_id, D.master_row(rec), D.MASTER_HEADER, link_columns=(8,))
    return {"remote_file_id": doc_id, "remote_ref": doc_url(doc_id)}


def write_destination(g: Google, rec: dict, cfg: dict) -> dict:
    dest = rec["intent"]["destination"]
    key, kind = D.TARGET_FOR[dest]
    t = _targets(cfg)
    if kind == "master_only":
        return {"remote_file_id": t.get("master_doc", ""), "remote_ref": "master"}
    fid = t.get(key)
    if not fid:
        raise GoogleError(412, f"{D.DOC_TITLES.get(key, key)} not configured: run `linkintake google-setup`")
    if kind == "wishlist_tab":
        tab = t.get("wishlist_tab_id")
        if not tab:
            raise GoogleError(412, "Wishlist 'Intake Staging' tab not configured: run `linkintake google-setup`")
        if not _doc_has(g, fid, rec["id"], tab):
            g.doc_append_table_row(fid, D.wishlist_row(rec), D.WISHLIST_HEADER, tab_id=tab, link_columns=(8,))
        return {"remote_file_id": fid, "remote_ref": doc_url(fid, tab)}
    if kind == "sheet":
        if not _sheet_has(g, fid, rec["id"]):
            g.sheet_append(fid, [D.scholarship_row(rec)])
        return {"remote_file_id": fid, "remote_ref": sheet_url(fid)}
    if not _doc_has(g, fid, rec["id"]):
        g.doc_append_text(fid, D.ENTRY_FOR[dest](rec))
    return {"remote_file_id": fid, "remote_ref": doc_url(fid)}


# ---------- record-level sync
def _attempt(part: dict, fn) -> bool:
    part["last_attempt"] = _now()
    try:
        res = fn()
        part.update(res)
        part["status"] = "synced"
        part["last_error"] = ""
        part["synced_at"] = _now()
        return True
    except GoogleError as exc:
        part["status"] = "failed"
        part["last_error"] = str(exc)
        return False
    except Exception as exc:  # never let a formatting bug reach the caller
        part["status"] = "failed"
        part["last_error"] = f"{type(exc).__name__}: {exc}"[:300]
        return False


def sync_record(rec: dict, g: Google | None = None, cfg: dict | None = None, persist: bool = True) -> dict:
    """Master then destination. Idempotent. Updates rec['export'] in place and persists if asked."""
    cfg = cfg or config.load()
    ex = rec.setdefault("export", empty_export())
    ex.setdefault("master_sync", empty_sync())
    ex.setdefault("destination_sync", empty_sync())
    ex["destination_sync"]["destination"] = rec["intent"]["destination"]
    state = google_state(cfg)
    if state != "ready":
        ex["status"] = "off" if state == "off" else "not_configured"
        ex["last_error"] = "" if state == "off" else "Google not authorized: run `linkintake google-auth`"
        if persist:
            store.write(rec)
        return ex
    try:
        g = g or Google()
    except GoogleError as exc:
        ex["status"] = "export_pending"
        ex["last_error"] = str(exc)
        if persist:
            store.write(rec)
        return ex
    m_ok = ex["master_sync"]["status"] == "synced" or _attempt(ex["master_sync"], lambda: write_master(g, rec, cfg))
    d_ok = ex["destination_sync"]["status"] == "synced" or _attempt(ex["destination_sync"], lambda: write_destination(g, rec, cfg))
    ex["status"] = "synced" if (m_ok and d_ok) else "partial" if (m_ok or d_ok) else "export_pending"
    ex["last_error"] = "" if ex["status"] == "synced" else (ex["master_sync"]["last_error"] or ex["destination_sync"]["last_error"])
    ex["last_attempt"] = _now()
    if ex["status"] == "synced":
        ex["synced_at"] = _now()
    if persist:
        store.write(rec)
    return ex


def pending_records() -> list[dict]:
    out = []
    for e in store.index():  # oldest first
        try:
            rec = store.load(e["id"])
        except FileNotFoundError:
            continue
        if rec.get("saved_at") and rec.get("export", {}).get("status") in {"export_pending", "partial", "not_configured", None}:
            out.append(rec)
    return out


def sync_pending(limit: int = 5, budget_s: float = DEFAULT_BUDGET_S, exclude: str = "", g: Google | None = None) -> list[dict]:
    """Retry oldest pending/partial records first. Bounded by count and wall-clock so Raycast never hangs."""
    cfg = config.load()
    if google_state(cfg) != "ready":
        return []
    try:
        g = g or Google()
    except GoogleError:
        return []
    deadline = time.monotonic() + budget_s
    done = []
    for rec in pending_records():
        if rec["id"] == exclude or len(done) >= limit or time.monotonic() > deadline:
            break
        sync_record(rec, g=g, cfg=cfg)
        done.append({"id": rec["id"], "status": rec["export"]["status"], "error": rec["export"].get("last_error", "")})
        if rec["export"]["status"] == "export_pending" and rec["export"].get("last_error", "").startswith("Google API 0"):
            break  # Google unreachable; stop burning the budget
    return done


def summary_line(ex: dict) -> str:
    """'Saved locally · Google synced' style line for Raycast/CLI."""
    st = ex.get("status", "export_pending")
    if st == "synced":
        return "Saved locally · Google synced"
    if st == "off":
        return "Saved locally · Google export off"
    if st == "not_configured":
        return "Saved locally · Google not authorized"
    if st == "partial":
        m = ex["master_sync"]["status"] == "synced"
        return f"Saved locally · Master {'synced' if m else 'pending'} · Destination {'pending' if m else 'synced'}"
    return "Saved locally · Google pending"
