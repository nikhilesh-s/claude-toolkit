"""Google sync with idempotent, bounded, never-fatal writes.

save -> local record committed -> sync_record(): Master Intake row, then destination write, each checked for the
Record ID before appending -> then a bounded sweep of older pending/partial records. Any failure is recorded on
the record (last_error) and left for the next sweep. Nothing here can make a local save fail."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from . import config, destinations as D, store
from .google_api import Google, GoogleError, OwnershipError, doc_text, doc_url, is_configured, sheet_url
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
    return _sheet_row_number(g, sheet_id, [record_id]) > 0


def _sheet_row_number(g: Google, sheet_id: str, record_ids: list[str], exclude: tuple[str, ...] = ()) -> int:
    """1-based row whose Record ID cell contains any of record_ids (and none of exclude), else 0."""
    if not record_ids:
        return 0
    col = chr(ord("A") + len(D.SCHOLAR_HEADER) - 1)  # Record ID column
    for i, row in enumerate(g.sheet_values(sheet_id, f"{col}1:{col}5000"), start=1):
        if row and any(rid in row[0] for rid in record_ids) and not any(x in row[0] for x in exclude):
            return i
    return 0


def write_master(g: Google, rec: dict, cfg: dict) -> dict:
    doc_id = _targets(cfg).get("master_doc")
    if not doc_id:
        raise GoogleError(412, "Master Intake doc not configured: run `linkintake google-setup`")
    g.assert_owned(doc_id, "Intake Master")  # explicit; request() enforces it again on every write
    if not _doc_has(g, doc_id, rec["id"]):
        g.doc_append_table_row(doc_id, D.master_row(rec), D.MASTER_HEADER, link_columns=(8,))
    return {"remote_file_id": doc_id, "remote_ref": doc_url(doc_id)}


class NeedsDecision(GoogleError):
    """Semantic possible-duplicate: nothing is written until the user decides (linkintake resolve)."""


def _entity_for(rec: dict):
    from . import entities
    res = rec.get("destination_resolution") or {}
    if res.get("action") == "possible_duplicate":
        raise NeedsDecision(409, f"possible duplicate of '{res.get('candidate_label', res.get('matched_entity'))}' — run `linkintake resolve {rec['id']} --merge` or `--new`")
    ent = entities.get("wishlist" if rec["intent"]["destination"] == "wishlist" else "scholarship", res.get("entity_key", ""))
    if not ent:
        raise GoogleError(412, "no destination entity for this record (save it first)")
    return ent


def write_destination(g: Google, rec: dict, cfg: dict) -> dict:
    dest = rec["intent"]["destination"]
    key, kind = D.TARGET_FOR[dest]
    t = _targets(cfg)
    if kind == "master_only":
        return {"remote_file_id": t.get("master_doc", ""), "remote_ref": "master"}
    fid = t.get(key)
    if not fid:
        raise GoogleError(412, f"{D.DOC_TITLES.get(key, key)} not configured: run `linkintake google-setup`")
    g.assert_owned(fid, D.DOC_TITLES.get(key, "Wishlist"))
    if kind == "wishlist_tab":
        tab = t.get("wishlist_tab_id")
        if not tab:
            raise GoogleError(412, "Wishlist 'Intake Staging' tab not configured: run `linkintake google-setup`")
        if _doc_has(g, fid, rec["id"], tab):
            return {"remote_file_id": fid, "remote_ref": doc_url(fid, tab)}  # idempotency: this record already on the sheet
        ent = _entity_for(rec)
        row = D.entity_wishlist_row(ent, rec)
        # merged: rewrite the entity's existing row (found by any earlier contributing Record ID); else append
        updated = any(g.doc_update_table_row(fid, rid, row, tab_id=tab, link_columns=(8,)) for rid in ent["record_ids"] if rid != rec["id"])
        if not updated:
            g.doc_append_table_row(fid, row, D.WISHLIST_HEADER, tab_id=tab, link_columns=(8,))
        return {"remote_file_id": fid, "remote_ref": doc_url(fid, tab), "merged_row": updated}
    if kind == "sheet":
        if _sheet_has(g, fid, rec["id"]):
            return {"remote_file_id": fid, "remote_ref": sheet_url(fid)}
        ent = _entity_for(rec)
        row = D.entity_scholarship_row(ent, rec)
        n = _sheet_row_number(g, fid, [rid for rid in ent["record_ids"] if rid != rec["id"]])
        if n:
            g.sheet_update_row(fid, n, row)
        else:
            g.sheet_append(fid, [row])
        return {"remote_file_id": fid, "remote_ref": sheet_url(fid), "merged_row": bool(n)}
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
    except NeedsDecision as exc:
        part["status"] = "needs_decision"
        part["last_error"] = str(exc)
        return False
    except OwnershipError as exc:  # wrong account or foreign-owned target: blocked, never written
        part["status"] = "blocked"
        part["last_error"] = str(exc)
        return False
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
        g.verify_identity()
    except OwnershipError as exc:
        ex["status"] = "blocked"
        ex["last_error"] = str(exc)
        ex["last_attempt"] = _now()
        if persist:
            store.write(rec)
        return ex
    except GoogleError as exc:
        ex["status"] = "export_pending"
        ex["last_error"] = str(exc)
        if persist:
            store.write(rec)
        return ex
    m_ok = ex["master_sync"]["status"] == "synced" or _attempt(ex["master_sync"], lambda: write_master(g, rec, cfg))
    d_ok = ex["destination_sync"]["status"] == "synced" or _attempt(ex["destination_sync"], lambda: write_destination(g, rec, cfg))
    if ex["destination_sync"]["status"] == "needs_decision":
        ex["status"] = "needs_decision"
    elif "blocked" in (ex["master_sync"]["status"], ex["destination_sync"]["status"]):
        ex["status"] = "blocked"  # local save stands; retried by `sync` once the target is personal-owned
    else:
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
        if rec.get("saved_at") and rec.get("export", {}).get("status") in {"export_pending", "partial", "not_configured", "blocked", None}:  # needs_decision waits for the user
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
        if rec["export"]["status"] == "blocked" and not getattr(g, "identity", "x"):
            break  # wrong signed-in account: every record would be refused
    return done


def absorb_remote(kind: str, into_key: str, stray_record_ids: list[str], g: Google | None = None) -> dict:
    """After entities.absorb: drop the stray's remote row(s) and rewrite the canonical row with merged provenance.
    Idempotent: a missing stray row is fine; the canonical row is found by any of its record ids."""
    from . import entities, store
    cfg = config.load()
    t = _targets(cfg)
    ent = entities.get(kind, into_key)
    if not ent or google_state(cfg) != "ready":
        return {"remote": "skipped"}
    g = g or Google()
    keep = tuple(r for r in ent["record_ids"] if r not in stray_record_ids)  # the canonical row carries these; never delete it
    anchor = keep[0] if keep else ent["record_ids"][0]
    rec = store.load(anchor)
    if kind == "wishlist":
        fid, tab = t.get("wishlist_doc"), t.get("wishlist_tab_id")
        removed = [rid for rid in stray_record_ids if g.doc_delete_table_row(fid, rid, tab_id=tab, exclude=keep)]
        row = D.entity_wishlist_row(ent, rec)
        updated = any(g.doc_update_table_row(fid, rid, row, tab_id=tab, link_columns=(8,)) for rid in ent["record_ids"])
        if not updated:
            g.doc_append_table_row(fid, row, D.WISHLIST_HEADER, tab_id=tab, link_columns=(8,))
        return {"removed_rows": removed, "canonical_row_updated": updated}
    fid = t.get("scholarship_sheet")
    n_stray = _sheet_row_number(g, fid, stray_record_ids, exclude=keep)
    if n_stray:
        g.sheet_delete_row(fid, n_stray)
    row = D.entity_scholarship_row(ent, rec)
    n = _sheet_row_number(g, fid, ent["record_ids"])
    if n:
        g.sheet_update_row(fid, n, row)
    else:
        g.sheet_append(fid, [row])
    return {"removed_rows": [n_stray] if n_stray else [], "canonical_row_updated": bool(n)}


def summary_line(ex: dict, rec: dict | None = None) -> str:
    """'Saved locally ✓ · Google synced ✓ · merged with existing Wishlist item' style line for Raycast/CLI."""
    from .entities import describe
    st = ex.get("status", "export_pending")
    tail = ""
    if rec and rec.get("destination_resolution", {}).get("action") in ("merged", "possible_duplicate") or (rec and rec.get("destination_resolution", {}).get("variant_of")):
        tail = " · " + describe(rec["destination_resolution"], rec["intent"]["destination"])
    if st == "blocked":
        return "Saved locally ✓ · Google BLOCKED (not personal-owned)" + tail
    if st == "needs_decision":
        return "Saved locally ✓ · " + (tail.strip(" ·") or "possible duplicate — review needed")
    if st == "synced":
        return "Saved locally ✓ · Google synced ✓" + tail
    if st == "off":
        return "Saved locally ✓ · Google export off" + tail
    if st == "skipped":
        return "Saved locally ✓ · Google skipped" + tail
    if st == "not_configured":
        return "Saved locally ✓ · Google not authorized" + tail
    if st == "partial":
        m = ex["master_sync"]["status"] == "synced"
        return f"Saved locally ✓ · Master {'synced ✓' if m else 'pending'} · Destination {'pending' if m else 'synced ✓'}" + tail
    return "Saved locally ✓ · Google pending" + tail
