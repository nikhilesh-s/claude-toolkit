"""Exports. The local record is canonical; Google Docs/Sheets are human-readable views.
Master = one Google Doc with an ongoing table. Destinations = a doc (or sheet) per bucket."""
from __future__ import annotations

from datetime import datetime

from . import config
from .google_api import DOC_MIME, SHEET_MIME, Google, GoogleError, doc_url, sheet_url
from .records import DESTINATIONS, clip

DOC_TITLES = {
    "intake_master": "Intake Master",
    "supplement_ideas": "Supplemental Reel / Content Bank",
    "design_inspo": "Design Inspo Bank",
    "personal_ig": "Personal Instagram Inspiration",
    "inbox": "Intake Inbox",
    "scholarships_doc": "Scholarships Intake (doc fallback)",
}
SHEET_TITLES = {"scholarships": "Scholarships Intake"}
MASTER_HEADER = ["Date", "Destination", "Source", "Title / Creator", "My Instruction", "Extracted Result",
                 "Context / Summary", "Status", "Original URL"]
SCHOLAR_HEADER = ["Date", "Scholarship", "Organization", "Deadline", "Amount", "Eligibility", "Required materials",
                  "Link", "Notes", "My instruction", "Status", "Source URL"]
SCHOLAR_FIELDS = ["scholarship", "organization", "deadline", "amount", "eligibility", "required_materials", "link", "notes"]


def ensure_doc(g: Google, cfg: dict, key: str) -> str:
    doc_id = cfg["google"]["docs"].get(key)
    if not doc_id:
        doc_id = g.find_or_create(DOC_TITLES[key], DOC_MIME, cfg["google"]["folder_id"])
        cfg["google"]["docs"][key] = doc_id
        config.save(cfg)
    return doc_id


def ensure_sheet(g: Google, cfg: dict, key: str) -> str:
    sid = cfg["google"]["sheets"].get(key)
    if not sid:
        sid = g.find_or_create(SHEET_TITLES[key], SHEET_MIME, cfg["google"]["folder_id"])
        cfg["google"]["sheets"][key] = sid
        config.save(cfg)
    if not g.sheet_values(sid, "A1:A1"):
        g.sheet_append(sid, [SCHOLAR_HEADER])
    return sid


def _date(rec: dict) -> str:
    try:
        return datetime.fromisoformat(rec["created_at"]).astimezone().strftime("%Y-%m-%d")
    except Exception:
        return rec["created_at"][:10]


def _title_creator(rec: dict) -> str:
    s = rec["source"]
    return " — ".join(x for x in (s.get("title"), s.get("creator")) if x)


def master_row(rec: dict) -> list[str]:
    s, i, c, e = rec["source"], rec["intent"], rec["context"], rec["extraction"]
    return [
        _date(rec), DESTINATIONS[i["destination"]], f"{s['platform']} ({s['source_class']})", clip(_title_creator(rec), 200),
        i["user_instruction"], clip("\n".join(f"• {t}" for t in e.get("takeaways") or []) or e.get("focused_result", ""), 1500),
        clip(c.get("short_source_summary", ""), 800),
        f"{rec['status']} ({e.get('confidence', 0):.2f})", s["original_url"],
    ]


def entry_block(rec: dict) -> str:
    s, i, c, e = rec["source"], rec["intent"], rec["context"], rec["extraction"]
    lines = [f"■ {_date(rec)} · {DESTINATIONS[i['destination']]} · {s['platform']}",
             _title_creator(rec) or s["original_url"],
             f"Source: {s['original_url']}",
             f"Instruction: {i['user_instruction']}"]
    for t in e.get("takeaways") or []:
        lines.append(f"  • {t}")
    lines.append(f"Result: {clip(e.get('focused_result', '') or '(no extraction)', 3000)}")
    if e.get("uncertainty"):
        lines.append(f"Uncertain: {clip(e['uncertainty'], 400)}")
    if c.get("visual_notes"):
        lines.append(f"Visual: {clip(c['visual_notes'], 800)}")
    if c.get("short_source_summary"):
        lines.append(f"Context: {clip(c['short_source_summary'], 800)}")
    if e.get("structured_data"):
        lines.append("Fields: " + "; ".join(f"{k}: {v}" for k, v in e["structured_data"].items() if v))
    lines.append(f"Status: {rec['status']} · confidence {e.get('confidence', 0):.2f} · intake {rec['id']}")
    return "\n".join(lines) + "\n\n"


def export_payload(rec: dict) -> dict:
    """Everything a Claude session needs to export this record through its own Google Drive tool."""
    dest = rec["intent"]["destination"]
    target = {"wishlist": "existing Wishlist doc, Media Queue tab (staging block only)",
              "scholarships": f"sheet '{SHEET_TITLES['scholarships']}' (columns: {', '.join(SCHOLAR_HEADER)})"}.get(
        dest, f"doc '{DOC_TITLES.get(dest, dest)}' (append entry block)")
    sd = rec["extraction"].get("structured_data", {})
    return {
        "record_id": rec["id"],
        "master_doc": DOC_TITLES["intake_master"],
        "master_columns": MASTER_HEADER,
        "master_row": master_row(rec),
        "destination": DESTINATIONS[dest],
        "destination_target": target,
        "entry_block": entry_block(rec),
        "scholarship_row": [_date(rec)] + [sd.get(f, "") for f in SCHOLAR_FIELDS] if dest == "scholarships" else None,
    }


def export(rec: dict) -> dict:
    cfg = config.load()
    if cfg["google"].get("export_mode", "off") != "rest":
        return {"status": "export_pending", "via": "claude", "master": {}, "destination": {}}
    out: dict = {"status": "exported", "via": "rest", "master": {}, "destination": {}}
    try:
        g = Google()
    except GoogleError as exc:
        out["status"] = "export_pending"
        out["master"] = out["destination"] = {"ok": False, "error": str(exc)}
        return out
    out["account"] = g.account
    try:
        mid = ensure_doc(g, cfg, "intake_master")
        g.doc_append_table_row(mid, master_row(rec), MASTER_HEADER, link_columns=(8,))
        out["master"] = {"ok": True, "url": doc_url(mid)}
    except GoogleError as exc:
        out["master"] = {"ok": False, "error": str(exc)}
    try:
        out["destination"] = _export_destination(g, cfg, rec)
    except GoogleError as exc:
        out["destination"] = {"ok": False, "error": str(exc)}
    if not (out["master"].get("ok") and out["destination"].get("ok")):
        out["status"] = "export_pending"
    return out


def _export_destination(g: Google, cfg: dict, rec: dict) -> dict:
    dest = rec["intent"]["destination"]
    if dest == "wishlist":
        doc_id = cfg["google"]["docs"]["wishlist"]
        tab = cfg["google"].get("wishlist_tab_id", "")
        s, e = rec["source"], rec["extraction"]
        sd = e.get("structured_data", {})
        lines = [f"• {sd.get('product_item') or s.get('title') or s['original_url']}",
                 f"  Source: {s['original_url']}",
                 "  Status: Unprocessed (link-intake)",
                 f"  Instruction: {rec['intent']['user_instruction']}",
                 f"  Extracted: {clip(e.get('focused_result', ''), 1200)}"]
        fields = "; ".join(f"{k}: {v}" for k, v in sd.items() if v)
        if fields:
            lines.append(f"  Fields: {fields}")
        lines.append(f"  Intake: {rec['id']} · {rec['status']}")
        g.doc_append_text(doc_id, "\n".join(lines) + "\n", tab_id=tab)
        return {"ok": True, "url": doc_url(doc_id) + (f"?tab={tab}" if tab else "")}
    if dest == "scholarships":
        sd = rec["extraction"].get("structured_data", {})
        row = [_date(rec)] + [sd.get(f, "") for f in SCHOLAR_FIELDS]
        row[8] = row[8] or clip(rec["extraction"].get("focused_result", ""), 1000)  # notes
        row += [rec["intent"]["user_instruction"], rec["status"], rec["source"]["original_url"]]
        try:
            sid = ensure_sheet(g, cfg, "scholarships")
            g.sheet_append(sid, [row])
            return {"ok": True, "url": sheet_url(sid)}
        except GoogleError as exc:
            if "sheets.googleapis.com" not in str(exc):
                raise
            # ponytail: Sheets API not enabled on the OAuth project -> same row into a doc table until it is.
            doc_id = ensure_doc(g, cfg, "scholarships_doc")
            g.doc_append_table_row(doc_id, row, SCHOLAR_HEADER, link_columns=(7, 11))
            return {"ok": True, "url": doc_url(doc_id), "note": "Sheets API disabled; wrote to doc table instead"}
    key = {"supplement_ideas": "supplement_ideas", "design_inspo": "design_inspo", "personal_ig": "personal_ig", "inbox": "inbox"}[dest]
    doc_id = ensure_doc(g, cfg, key)
    g.doc_append_text(doc_id, entry_block(rec))
    return {"ok": True, "url": doc_url(doc_id)}
