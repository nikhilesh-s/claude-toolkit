"""Destination formats. Pure functions: record -> row/entry text. Every remote entry carries the Record ID,
which is what makes retries idempotent. The local JSON stays the complete canonical copy."""
from __future__ import annotations

from datetime import datetime

from .records import DESTINATIONS, clip

MASTER_HEADER = ["Date", "Destination", "Source", "Title / Creator", "User Instruction", "Extracted Insight",
                 "Tags", "Status", "URL", "Record ID"]
WISHLIST_HEADER = ["Date Added", "Item", "Brand", "Model", "Variant / Color / Size", "Price", "Why I Saved It",
                   "Notes", "Source", "Record ID"]
SCHOLAR_HEADER = ["Scholarship", "Organization", "Amount", "Deadline", "Eligibility", "Required Materials",
                  "Application Link", "Status", "Priority", "Notes", "Source", "Date Added", "Record ID"]
WISHLIST_TAB_TITLE = "Intake Staging"
DOC_TITLES = {
    "master_doc": "Intake Master",
    "supplement_doc": "Supplement Inspiration Bank",
    "design_doc": "Design Inspiration Bank",
    "personal_ig_doc": "Personal Instagram Inspiration",
    "scholarship_sheet": "Scholarship Tracker",
}
# destination key -> (config target key, kind)
TARGET_FOR = {
    "wishlist": ("wishlist_doc", "wishlist_tab"),
    "supplement_ideas": ("supplement_doc", "doc"),
    "design_inspo": ("design_doc", "doc"),
    "personal_ig": ("personal_ig_doc", "doc"),
    "scholarships": ("scholarship_sheet", "sheet"),
    "inbox": ("master_doc", "master_only"),
}


def _date(rec: dict) -> str:
    try:
        return datetime.fromisoformat(rec["created_at"]).astimezone().strftime("%Y-%m-%d")
    except Exception:
        return rec["created_at"][:10]


def _title_creator(rec: dict) -> str:
    s = rec["source"]
    return " — ".join(x for x in (s.get("title"), s.get("creator")) if x)


def _insight(rec: dict, n: int = 900) -> str:
    e = rec["extraction"]
    tk = e.get("takeaways") or []
    return clip("\n".join(f"• {t}" for t in tk) if tk else e.get("focused_result", ""), n)


def _tags(rec: dict) -> str:
    return ", ".join(rec["extraction"].get("tags") or [])


def _sd(rec: dict, *keys: str) -> str:
    sd = rec["extraction"].get("structured_data", {})
    for k in keys:
        if sd.get(k):
            return str(sd[k])
    return ""


# ---------- Master Intake (table)
def master_row(rec: dict) -> list[str]:
    s, i = rec["source"], rec["intent"]
    return [_date(rec), DESTINATIONS[i["destination"]], s["platform"], clip(_title_creator(rec), 160),
            i["user_instruction"], _insight(rec), _tags(rec), f"{rec['status']} ({rec['extraction'].get('confidence', 0):.2f})",
            s["original_url"], rec["id"]]


# ---------- Wishlist -> Intake Staging tab (table)
def wishlist_row(rec: dict) -> list[str]:
    sd = rec["extraction"].get("structured_data", {})
    variant = " / ".join(v for v in (sd.get("color_style"), sd.get("size_spec"), sd.get("variant")) if v)
    return [_date(rec), sd.get("product_item") or sd.get("item") or rec["source"].get("title", ""), sd.get("brand", ""),
            sd.get("model", ""), variant, sd.get("price", ""), rec["intent"]["user_instruction"],
            clip(sd.get("notes") or _insight(rec, 400), 400), rec["source"]["original_url"], rec["id"]]


def entity_wishlist_row(ent: dict, rec: dict) -> list[str]:
    """One Wishlist row per product entity; provenance = every source URL + every Record ID."""
    v = {k: x["value"] for k, x in ent["fields"].items() if isinstance(x, dict)}
    variant = v.get("variant") or " / ".join(x for x in (v.get("color_style"), v.get("size_spec")) if x)
    prices = ent.get("price_observations") or []
    price = v.get("price", "")
    if prices:
        latest = prices[-1]
        price = f"{latest['price']} (seen {latest['at'][:10]})"
    why = "\n".join(f"• {w}" for w in _instructions(ent, rec))
    return [_date(rec), v.get("product_item") or rec["source"].get("title", ""), v.get("brand", ""), v.get("model", ""), variant, price,
            why, clip(v.get("notes", ""), 400), "\n".join(ent["source_urls"]), ", ".join(ent["record_ids"])]


def _instructions(ent: dict, rec: dict) -> list[str]:
    from . import store
    out = []
    for rid in ent["record_ids"]:
        try:
            r = rec if rid == rec["id"] else store.load(rid)
            ins = r["intent"]["user_instruction"]
        except Exception:
            continue
        if ins and ins not in out:
            out.append(ins)
    return out


def entity_scholarship_row(ent: dict, rec: dict) -> list[str]:
    v = {k: x["value"] for k, x in ent["fields"].items() if isinstance(x, dict)}
    return [v.get("scholarship") or rec["source"].get("title", ""), v.get("organization", ""), v.get("amount", ""), v.get("deadline", ""),
            v.get("eligibility", ""), v.get("required_materials", ""), v.get("link") or ent["source_urls"][0], "New", "",
            clip(v.get("notes") or _insight(rec, 500), 500), "\n".join(ent["source_urls"]), _date(rec), ", ".join(ent["record_ids"])]


# ---------- Scholarship Tracker (sheet)
def scholarship_row(rec: dict) -> list[str]:
    sd = rec["extraction"].get("structured_data", {})
    return [sd.get("scholarship", "") or rec["source"].get("title", ""), sd.get("organization", ""), sd.get("amount", ""),
            sd.get("deadline", ""), sd.get("eligibility", ""), sd.get("required_materials", ""),
            sd.get("link", "") or rec["source"]["original_url"], "New", "", clip(sd.get("notes") or _insight(rec, 500), 500),
            rec["source"]["original_url"], _date(rec), rec["id"]]


# ---------- Loose doc entries
def _entry(lines: list[tuple[str, str]]) -> str:
    out = [f"{k}: {v}" if k else v for k, v in lines if v]
    return "\n".join(out) + "\n\n"


def supplement_entry(rec: dict) -> str:
    e, c = rec["extraction"], rec["context"]
    return _entry([
        ("", f"■ {_date(rec)} · Supplement Idea · {rec['id']}"),
        ("Source", clip(_title_creator(rec) or rec["source"]["original_url"], 160)),
        ("What I liked", rec["intent"]["user_instruction"]),
        ("Idea", clip(e.get("focused_result", ""), 2500)),
        ("Context", clip(c.get("short_source_summary", ""), 600)),
        ("Tags", _tags(rec)),
        ("URL", rec["source"]["original_url"]),
    ])


def design_entry(rec: dict) -> str:
    e, c = rec["extraction"], rec["context"]
    return _entry([
        ("", f"■ {_date(rec)} · Design Inspo · {rec['id']}"),
        ("Tags", _tags(rec)),
        ("Instruction", rec["intent"]["user_instruction"]),
        ("What stood out", clip(_sd(rec, "what_stood_out") or "\n".join(f"• {t}" for t in e.get("takeaways") or []), 1200)),
        ("Reusable ideas", clip(_sd(rec, "reusable_ideas") or e.get("focused_result", ""), 2000)),
        ("Visual notes", clip(_sd(rec, "visual_notes") or c.get("visual_notes", ""), 800)),
        ("Source", rec["source"]["original_url"]),
    ])


def personal_ig_entry(rec: dict) -> str:
    e, c = rec["extraction"], rec["context"]
    return _entry([
        ("", f"■ {_date(rec)} · Instagram Inspiration · {rec['id']}"),
        ("Instruction", rec["intent"]["user_instruction"]),
        ("Summary", clip(c.get("short_source_summary", ""), 500)),
        ("Takeaways", "\n" + "\n".join(f"  • {t}" for t in e.get("takeaways") or []) if e.get("takeaways") else ""),
        ("Shots / framing", _sd(rec, "key_shots", "composition")),
        ("Lighting / color", _sd(rec, "lighting_color")),
        ("Transitions / sequence", _sd(rec, "transitions_sequence", "editing_or_sequence")),
        ("Pacing / editing", _sd(rec, "pacing_editing")),
        ("Hooks / text", _sd(rec, "hooks_text")),
        ("Techniques to recreate", _sd(rec, "techniques_to_recreate")),
        ("Unknowns", e.get("uncertainty") or _sd(rec, "unknowns")),
        ("Source", rec["source"]["original_url"]),
    ])


ENTRY_FOR = {"supplement_ideas": supplement_entry, "design_inspo": design_entry, "personal_ig": personal_ig_entry}
