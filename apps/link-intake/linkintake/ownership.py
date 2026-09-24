"""Read-only Google ownership audit: who is signed in, and who owns every configured destination.

Never writes, moves, renames or trashes anything. Used by `linkintake google-audit`, `doctor`, and as the
before/after check around `google-rehome`."""
from __future__ import annotations

from . import config
from .destinations import WISHLIST_TAB_TITLE
from .google_api import (DOC_MIME, FOLDER_MIME, SHEET_MIME, Google, GoogleError, doc_tabs, doc_url, folder_url,
                         owner_emails, required_account, sheet_url)

PERSONAL, FOREIGN, MISSING, WRONG_ACCOUNT, INVALID = "PERSONAL_OWNED", "SHARED_FOREIGN_OWNED", "MISSING", "WRONG_ACCOUNT", "INVALID"
# config key -> (label shown in doctor, expected MIME)
TARGETS = {
    "master_doc": ("Master", DOC_MIME),
    "wishlist_doc": ("Wishlist", DOC_MIME),
    "scholarship_sheet": ("Scholarship Tracker", SHEET_MIME),
    "supplement_doc": ("Supplement", DOC_MIME),
    "design_doc": ("Design", DOC_MIME),
    "personal_ig_doc": ("Personal Instagram", DOC_MIME),
    "college_folder": ("College Applications folder", FOLDER_MIME),
    "media_folder": ("Media folder", FOLDER_MIME),
    "scholarships_folder": ("Scholarships folder", FOLDER_MIME),
}
# Names of intake files (current and G-Switch era). Only used to list foreign copies the token can see.
INTAKE_NAME_HINTS = ("Intake Master", "Intake Inbox", "Scholarships Intake", "Scholarship Tracker", "Supplement Inspiration Bank",
                     "Design Inspiration Bank", "Personal Instagram Inspiration", "Supplemental Reel", "Content Bank")


def _url(fid: str, mime: str) -> str:
    return {DOC_MIME: doc_url, SHEET_MIME: sheet_url, FOLDER_MIME: folder_url}.get(mime, lambda i: f"https://drive.google.com/open?id={i}")(fid)


def inspect(g: Google, key: str, fid: str, label: str, mime: str, required: str, identity_ok: bool) -> dict:
    row = {"config_key": key, "label": label, "file_id": fid, "title": "", "mime_type": "", "drive_path": "", "owners": [],
           "owned_by_expected_account": False, "accessible": False, "url": _url(fid, mime) if fid else "", "status": MISSING, "note": ""}
    if not fid:
        row["note"] = "not configured"
        return row
    try:
        meta = g.drive_meta(fid)
    except GoogleError as exc:
        row["status"] = INVALID if exc.status == 400 else MISSING
        row["note"] = f"not accessible to this account ({exc.status})"
        return row
    owners = owner_emails(meta)
    row.update({"title": meta.get("name", ""), "mime_type": meta.get("mimeType", ""), "owners": owners, "accessible": True,
                "owned_by_expected_account": required in owners, "url": meta.get("webViewLink") or row["url"]})
    try:
        row["drive_path"] = g.drive_path(fid)
    except GoogleError:
        pass
    if not identity_ok:
        row["status"], row["note"] = WRONG_ACCOUNT, "signed-in account is not the required account; ownership cannot be trusted"
    elif meta.get("trashed"):
        row["status"], row["note"] = INVALID, "file is in the trash"
    elif mime and meta.get("mimeType") != mime:
        row["status"], row["note"] = INVALID, f"expected {mime.rsplit('.', 1)[-1]}, found {meta.get('mimeType', '?').rsplit('.', 1)[-1]}"
    else:
        row["status"] = PERSONAL if required in owners else FOREIGN
    return row


def audit(g: Google | None = None, cfg: dict | None = None, *, legacy: bool = True, scan_foreign: bool = True) -> dict:
    cfg = cfg or config.load()
    g = g or Google()
    required = required_account(cfg)
    identity = g.whoami()
    ok = bool(required) and identity == required
    t = cfg["google"].get("targets", {})
    rows = [inspect(g, k, t.get(k, ""), label, mime, required, ok) for k, (label, mime) in TARGETS.items()]
    wish = next(r for r in rows if r["config_key"] == "wishlist_doc")
    tab = {"config_key": "wishlist_tab_id", "label": f"Wishlist '{WISHLIST_TAB_TITLE}' tab", "tab_id": t.get("wishlist_tab_id", ""),
           "found": False, "title": "", "status": MISSING, "note": ""}
    if wish["accessible"] and tab["tab_id"]:
        try:
            tabs = {x["id"]: x["title"] for x in doc_tabs(g.doc_get(wish["file_id"]))}
            tab["found"], tab["title"] = tab["tab_id"] in tabs, tabs.get(tab["tab_id"], "")
            tab["status"] = wish["status"] if tab["found"] and tab["title"].strip().lower() == WISHLIST_TAB_TITLE.lower() else INVALID
            tab["note"] = "" if tab["status"] != INVALID else f"tab id not found or not titled '{WISHLIST_TAB_TITLE}'"
        except GoogleError as exc:
            tab["note"] = f"could not read tabs: {exc}"[:200]
    out = {"authenticated_account": identity, "required_account": required, "identity_ok": ok, "token_json_email": g.account,
           "targets": rows, "wishlist_tab": tab}
    active_ids = {r["file_id"] for r in rows if r["file_id"]}
    if legacy:
        out["legacy_config"] = _legacy(g, cfg, required, ok, active_ids)
    if scan_foreign:
        out["foreign_intake_files_visible"] = _foreign_visible(g, required, active_ids)
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in (PERSONAL, FOREIGN, MISSING, WRONG_ACCOUNT, INVALID)}
    out["summary"] = {"personal_owned": counts[PERSONAL], "foreign_owned": counts[FOREIGN], "missing": counts[MISSING],
                      "invalid": counts[INVALID], "wrong_account": counts[WRONG_ACCOUNT]}
    out["active_foreign_targets"] = [r["config_key"] for r in rows if r["status"] == FOREIGN]
    out["migration_needed"] = bool(out["active_foreign_targets"])
    out["all_personal"] = ok and counts[PERSONAL] == len(rows) and tab["status"] == PERSONAL
    return out


def _legacy(g: Google, cfg: dict, required: str, ok: bool, active_ids: set[str]) -> list[dict]:
    """Old G-Switch-era keys (google.docs.*, google.sheets.*). Nothing reads them; reported so their owners are known."""
    gc = cfg["google"]
    items = [(f"docs.{k}", v, "") for k, v in (gc.get("docs") or {}).items()] + [(f"sheets.{k}", v, "") for k, v in (gc.get("sheets") or {}).items()]
    out = []
    for key, fid, mime in items:
        r = inspect(g, f"google.{key}", fid, key, mime, required, ok)
        r["active"] = fid in active_ids
        out.append(r)
    return out


def _foreign_visible(g: Google, required: str, active_ids: set[str]) -> list[dict]:
    q = "(" + " or ".join(f"name contains '{n}'" for n in INTAKE_NAME_HINTS) + ")"
    try:
        items = g.drive_search(q, page_size=100)
    except GoogleError:
        return []
    return [{"title": it.get("name", ""), "file_id": it["id"], "owners": owner_emails(it), "mime_type": it.get("mimeType", ""),
             "url": _url(it["id"], it.get("mimeType", "")), "active": it["id"] in active_ids}
            for it in items if required not in owner_emails(it)]


def text_report(a: dict) -> str:
    L = [f"Google authenticated identity: {a['authenticated_account'] or '(unknown)'}",
         f"Required identity:             {a['required_account'] or '(not configured)'}",
         f"Identity OK:                   {'yes' if a['identity_ok'] else 'NO — all Google writes blocked'}", ""]
    for r in a["targets"]:
        mark = "✓" if r["status"] == PERSONAL else "✗"
        L.append(f"{mark} {r['label']:28s} {r['status']:22s} {', '.join(r['owners']) or '-':34s} {r['title'] or r['note']}")
        if r["file_id"]:
            L.append(f"    {r['config_key']} = {r['file_id']}  {r['mime_type'].rsplit('.', 1)[-1]}  {r['drive_path']}  {r['url']}")
        if r["note"] and r["title"]:
            L.append(f"    note: {r['note']}")
    tab = a["wishlist_tab"]
    L.append(f"{'✓' if tab['status'] == PERSONAL else '✗'} {tab['label']:28s} {tab['status']:22s} {tab['tab_id']} {tab['title']} {tab['note']}")
    if a.get("legacy_config"):
        L += ["", "Legacy config entries (google.docs / google.sheets; not read by any code):"]
        for r in a["legacy_config"]:
            L.append(f"  {r['config_key']:32s} {r['status']:22s} {', '.join(r['owners']) or '-':34s} {r['title'] or r['note']}  {'ACTIVE' if r['active'] else 'inactive'}")
    if a.get("foreign_intake_files_visible") is not None:
        L += ["", f"Intake-looking files visible to this token but NOT owned by {a['required_account']}: {len(a['foreign_intake_files_visible'])}"]
        for f in a["foreign_intake_files_visible"]:
            L.append(f"  {f['title']:40s} {', '.join(f['owners']) or 'shared drive':34s} {'ACTIVE TARGET' if f['active'] else 'not a target'}  {f['file_id']}")
    s = a["summary"]
    L += ["", f"Personal-owned targets: {s['personal_owned']}", f"Foreign-owned targets: {s['foreign_owned']}",
          f"Missing targets: {s['missing']}" + (f"   Invalid: {s['invalid']}" if s["invalid"] else "") + (f"   Wrong account: {s['wrong_account']}" if s["wrong_account"] else ""),
          "Migration needed: " + ("YES — active targets foreign-owned: " + ", ".join(a["active_foreign_targets"]) if a["migration_needed"] else "no")]
    return "\n".join(L)
