"""Destination entities: one Wishlist product / one Scholarship cycle may be fed by many intake records.

Three duplicate concepts, kept apart:
  idempotency  — same Record ID retried remotely            -> sync.py (Record ID present? skip)
  exact intake — same URL + destination + instruction        -> pipeline.py (dedupe_key, confirm to override)
  semantic     — different records, same underlying entity   -> this module (created / merged / possible_duplicate)

Entities live in ~/.link-intake/entities/<kind>.json. Every intake record is kept; an entity only points at them.
Merge safety: never replace a supported value with blank/unknown or with a lower-confidence claim; keep every
source URL and Record ID; record provenance per field."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from . import config
from .records import DESTINATIONS

ENT_DIR = config.STATE_DIR / "entities"
UNKNOWN = re.compile(r"\b(tbd|unknown|not shown|unclear|n/?a|none)\b", re.I)
_STOP = {"the", "a", "an", "and", "of", "for", "with", "in", "to", "by", "scholarship", "scholarships", "program", "award",
         "fund", "foundation", "inc", "llc", "official", "version", "edition"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def tokens(s: str) -> set[str]:
    return {t for t in norm(s).split() if t not in _STOP and len(t) > 1}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def is_unknown(v: str) -> bool:
    return not v or bool(UNKNOWN.search(v))


# ---------- store
def _path(kind: str):
    return ENT_DIR / f"{kind}.json"


def load(kind: str) -> list[dict]:
    p = _path(kind)
    return json.loads(p.read_text()) if p.exists() else []


def save(kind: str, items: list[dict]) -> None:
    ENT_DIR.mkdir(parents=True, exist_ok=True)
    _path(kind).write_text(json.dumps(items, indent=2, ensure_ascii=False))


def get(kind: str, key: str) -> dict | None:
    return next((e for e in load(kind) if e["key"] == key), None)


# ---------- identity extraction
_ASIN = re.compile(r"\b(B0[A-Z0-9]{8})\b")
_MODEL_NO = re.compile(r"\b([A-Z]{1,4}[- ]?\d{2,5}[A-Z0-9-]{0,6})\b")
_WATT = re.compile(r"\b(\d{2,4})\s?w\b", re.I)


def wishlist_identity(rec: dict) -> dict:
    sd = rec["extraction"].get("structured_data", {}) or {}
    blob = " ".join(str(v) for v in sd.values())
    ident = sd.get("identifier") or sd.get("asin") or sd.get("sku") or ""
    if not ident:
        m = _ASIN.search(blob)
        ident = m.group(1) if m else ""
    model = sd.get("model", "")
    model_core = norm(re.sub(r"[;(].*$", "", model))  # "12-in-1 Desktop Charging Station; exact model TBD (...)" -> "12 in 1 desktop charging station"
    if is_unknown(model_core):
        model_core = ""
    watt = _WATT.search(blob)
    variant_bits = [sd.get("variant", ""), sd.get("color_style", ""), sd.get("size_spec", "")]
    variant = norm(" ".join(b for b in variant_bits if b and not is_unknown(b)))
    # variant identity = discrete choices that change the purchase (color, size, wattage), not descriptive prose
    variant_key = norm(sd.get("variant", "")) or (f"{watt.group(1)}w" if watt and not is_unknown(sd.get("model", "")) else "")
    return {
        "identifier": ident.upper(), "product_url": (sd.get("product_url") or "").strip().lower().rstrip("/"),
        "brand": norm(sd.get("brand", "")), "model": model_core, "name": norm(sd.get("product_item") or sd.get("item") or rec["source"].get("title", "")),
        "variant": variant, "variant_key": variant_key,
    }


def scholarship_identity(rec: dict) -> dict:
    sd = rec["extraction"].get("structured_data", {}) or {}
    name = sd.get("scholarship") or sd.get("program_name") or rec["source"].get("title", "")
    year = str(sd.get("cycle_year") or "")
    if not year:
        m = re.search(r"\b(20[2-4]\d)\b", str(sd.get("deadline", "")) + " " + name)
        year = m.group(1) if m else ""
    return {"organization": norm(sd.get("organization", "")), "program": " ".join(sorted(tokens(re.sub(r"\b20[2-4]\d\b", "", name)))),
            "program_raw": name, "year": year}


# ---------- matching
def match_wishlist(ident: dict, entities: list[dict]) -> tuple[dict | None, str, float, list[str]]:
    """Returns (entity, action, confidence, reasons). action in created|merged|possible_duplicate|variant."""
    for e in entities:
        ei = e["identity"]
        if ident["identifier"] and ident["identifier"] == ei.get("identifier"):
            return e, "merged", 0.97, ["same product identifier"]
        if ident["product_url"] and ident["product_url"] == ei.get("product_url"):
            return e, "merged", 0.92, ["same official product URL"]
    same_line = [e for e in entities if ident["brand"] and e["identity"].get("brand") == ident["brand"]
                 and ident["model"] and e["identity"].get("model") == ident["model"]]
    if same_line:
        # Rule (Case D): variant_key (color/size/wattage choice) is part of identity. No variant on the new record
        # -> enrich the existing line (single variant) or flag if several variants exist.
        if not ident["variant_key"]:
            return (same_line[0], "merged", 0.85, ["same brand + model"]) if len(same_line) == 1 else (same_line[0], "possible_duplicate", 0.6, ["same brand + model, several variants exist"])
        exact_variant = [e for e in same_line if e["identity"].get("variant_key") == ident["variant_key"]]
        if exact_variant:
            return exact_variant[0], "merged", 0.9, ["same brand + model + variant"]
        unspecified = [e for e in same_line if not e["identity"].get("variant_key")]
        if unspecified:
            return unspecified[0], "merged", 0.85, ["same brand + model; existing entry had no variant, now specified"]
        return same_line[0], "variant", 0.85, ["same brand + model, different variant -> separate variant entry"]
    for e in entities:
        ei = e["identity"]
        if ident["model"] and ei.get("model") and ident["model"] != ei["model"]:
            continue  # two *known*, different models are different products; Case F is only for uncertain identity
        if ident["brand"] and ei.get("brand") == ident["brand"]:
            bt = tokens(ident["brand"])
            a = (tokens(ident["name"]) | tokens(ident["model"])) - bt
            b = (tokens(ei.get("name", "")) | tokens(ei.get("model", ""))) - bt
            sim = len(a & b) / min(len(a), len(b)) if a and b else 0.0  # overlap coefficient: "charging station cube" ~ "12-in-1 desktop charging station"
            if sim >= 0.5:
                return e, "possible_duplicate", round(sim, 2), [f"same brand, similar name ({sim:.2f}); model identity uncertain"]
    return None, "created", 1.0, []


def match_scholarship(ident: dict, entities: list[dict]) -> tuple[dict | None, str, float, list[str]]:
    other_cycle: set[str] = set()  # same program, different known year: a separate row by rule, never "similar"
    for e in entities:
        ei = e["identity"]
        if ident["organization"] and ei.get("organization") == ident["organization"] and ei.get("program") == ident["program"]:
            if ident["year"] and ei.get("year") and ident["year"] == ei["year"]:
                return e, "merged", 0.95, ["same organization + program + cycle year"]
            if ident["year"] and ei.get("year") and ident["year"] != ei["year"]:
                other_cycle.add(e["key"])
                continue
            return e, "possible_duplicate", 0.6, ["same organization + program but cycle year unknown on one side"]
    for e in entities:
        ei = e["identity"]
        if e["key"] in other_cycle:
            continue
        if ident["organization"] and ei.get("organization") == ident["organization"]:
            sim = jaccard(set(ident["program"].split()), set(ei.get("program", "").split()))
            if sim >= 0.6:
                return e, "possible_duplicate", round(sim, 2), [f"same organization, similar program name ({sim:.2f})"]
    return None, "created", 1.0, []


# ---------- merge
def _field_conf(rec: dict, value: str) -> float:
    c = float(rec["extraction"].get("confidence", 0) or 0)
    return c * (0.5 if is_unknown(value) else 1.0)


def _more_specific(new: str, old: str) -> bool:
    return is_unknown(old) or (not is_unknown(new) and len(new) > len(old) and tokens(old) <= tokens(new))


def merge_fields(entity: dict, rec: dict, fields: list[str], authoritative: bool = False) -> list[str]:
    """Enrich entity['fields'] from rec's structured_data. Returns list of changed field names."""
    sd = rec["extraction"].get("structured_data", {}) or {}
    changed = []
    for f in fields:
        new = str(sd.get(f, "") or "").strip()
        if not new:
            continue
        cur = entity["fields"].get(f)
        new_conf = _field_conf(rec, new) + (0.15 if authoritative else 0)
        if cur is None or is_unknown(cur["value"]):
            take = not is_unknown(new) or cur is None
        else:
            if is_unknown(new):
                take = False  # never replace supported with unknown
            else:
                take = new_conf >= cur["confidence"] - 0.05 and (_more_specific(new, cur["value"]) or new_conf > cur["confidence"])
        if take and (cur is None or cur["value"] != new):
            entity.setdefault("history", []).append({"field": f, "from": cur["value"] if cur else "", "to": new, "record_id": rec["id"], "at": _now()})
            entity["fields"][f] = {"value": new, "confidence": round(new_conf, 2), "record_id": rec["id"], "observed_at": _now(),
                                   "source_url": rec["source"]["original_url"]}
            changed.append(f)
    return changed


WISHLIST_FIELDS = ["product_item", "brand", "model", "identifier", "product_url", "variant", "color_style", "size_spec", "price", "notes"]
SCHOLAR_FIELDS = ["scholarship", "organization", "amount", "deadline", "eligibility", "required_materials", "link", "notes", "cycle_year"]


def _touch(entity: dict, rec: dict) -> None:
    if rec["id"] not in entity["record_ids"]:
        entity["record_ids"].append(rec["id"])
    url = rec["source"]["original_url"]
    if url not in entity["source_urls"]:
        entity["source_urls"].append(url)
    entity["updated_at"] = _now()


def _new_entity(kind: str, key: str, ident: dict, rec: dict) -> dict:
    return {"key": key, "kind": kind, "identity": ident, "fields": {}, "record_ids": [], "source_urls": [], "history": [],
            "price_observations": [], "created_at": _now(), "updated_at": _now(), "primary_record_id": rec["id"], "remote": {}}


def resolve(rec: dict) -> dict:
    """Decide created / merged / variant / possible_duplicate for wishlist & scholarships; persist entity changes.
    Other destinations are never semantically deduplicated (one Reel can inspire many ideas)."""
    dest = rec["intent"]["destination"]
    if dest not in ("wishlist", "scholarships"):
        return {"action": "n/a", "entity_key": "", "matched_entity": "", "match_confidence": 1.0, "match_reasons": ["destination keeps every intake"],
                "contributing_record_ids": [rec["id"]]}
    kind = "wishlist" if dest == "wishlist" else "scholarship"
    ents = load(kind)
    ident = wishlist_identity(rec) if kind == "wishlist" else scholarship_identity(rec)
    # a retry of the same record must not re-resolve into a different outcome
    for e in ents:
        if rec["id"] in e["record_ids"]:
            return {"action": "merged" if len(e["record_ids"]) > 1 else "created", "entity_key": e["key"], "matched_entity": e["key"],
                    "match_confidence": 1.0, "match_reasons": ["record already part of this entity"], "contributing_record_ids": list(e["record_ids"])}
    ent, action, conf, reasons = (match_wishlist if kind == "wishlist" else match_scholarship)(ident, ents)
    fields = WISHLIST_FIELDS if kind == "wishlist" else SCHOLAR_FIELDS
    authoritative = rec["source"]["source_class"] in ("web_page", "google_workspace")  # official/page beats a Reel for facts
    if action == "possible_duplicate":
        return {"action": "possible_duplicate", "entity_key": "", "matched_entity": ent["key"], "match_confidence": conf, "match_reasons": reasons,
                "contributing_record_ids": [rec["id"]], "candidate_label": _label(ent)}
    if action == "merged":
        changed = merge_fields(ent, rec, fields, authoritative)
        if kind == "wishlist":
            _observe_price(ent, rec)
        _touch(ent, rec)
        if kind == "wishlist" and not ent["identity"].get("variant_key") and ident["variant_key"]:
            ent["identity"]["variant_key"] = ident["variant_key"]  # specificity went up
        for k in ("identifier", "product_url"):
            if ident.get(k) and not ent["identity"].get(k):
                ent["identity"][k] = ident[k]
        save(kind, ents)
        return {"action": "merged", "entity_key": ent["key"], "matched_entity": ent["key"], "match_confidence": conf, "match_reasons": reasons,
                "contributing_record_ids": list(ent["record_ids"]), "enriched_fields": changed}
    # created (or a new variant of an existing line)
    key = _make_key(kind, ident, rec["id"])
    ent = _new_entity(kind, key, ident, rec)
    if action == "variant":
        ent["product_group"] = next(e["key"] for e in ents if e["identity"].get("brand") == ident["brand"] and e["identity"].get("model") == ident["model"])
    merge_fields(ent, rec, fields, authoritative)
    if kind == "wishlist":
        _observe_price(ent, rec)
    _touch(ent, rec)
    ents.append(ent)
    save(kind, ents)
    return {"action": "created", "entity_key": key, "matched_entity": "", "match_confidence": conf, "match_reasons": reasons or ["no matching entity"],
            "contributing_record_ids": [rec["id"]], "variant_of": ent.get("product_group", "")}


def _make_key(kind: str, ident: dict, rid: str) -> str:
    if kind == "wishlist":
        core = ident["identifier"] or ident["product_url"] or " ".join(x for x in (ident["brand"], ident["model"] or ident["name"], ident["variant_key"]) if x)
    else:
        core = " ".join(x for x in (ident["organization"], ident["program"], ident["year"]) if x)
    return f"{kind}:{norm(core)[:80] or rid}"


def _observe_price(ent: dict, rec: dict) -> None:
    price = str((rec["extraction"].get("structured_data") or {}).get("price", "") or "").strip()
    if price and not is_unknown(price) and re.search(r"\d", price):
        ent.setdefault("price_observations", []).append({"price": price, "record_id": rec["id"], "source_url": rec["source"]["original_url"], "at": _now()})


def _label(ent: dict) -> str:
    f = ent.get("fields", {})
    v = lambda k: (f.get(k) or {}).get("value", "")  # noqa: E731
    if ent["kind"] == "wishlist":
        return " ".join(x for x in (v("brand"), v("model") or v("product_item"), v("variant") or v("color_style")) if x) or ent["key"]
    return " ".join(x for x in (v("organization"), v("scholarship"), v("cycle_year")) if x) or ent["key"]


def entity_row_values(ent: dict) -> dict:
    """Best current value per field for remote rows."""
    return {k: v["value"] for k, v in ent["fields"].items() if isinstance(v, dict)}


def decide(record_id: str, choice: str, entity_key: str = "") -> dict:
    """User decision for a possible_duplicate: 'merge' into entity_key, or 'new'."""
    from . import store
    rec = store.load(record_id)
    res = rec.get("destination_resolution", {})
    kind = "wishlist" if rec["intent"]["destination"] == "wishlist" else "scholarship"
    ents = load(kind)
    fields = WISHLIST_FIELDS if kind == "wishlist" else SCHOLAR_FIELDS
    if choice == "merge":
        key = entity_key or res.get("matched_entity", "")
        ent = next((e for e in ents if e["key"] == key), None)
        if not ent:
            raise ValueError(f"no entity {key}")
        changed = merge_fields(ent, rec, fields)
        _touch(ent, rec)
        save(kind, ents)
        rec["destination_resolution"] = {"action": "merged", "entity_key": key, "matched_entity": key, "match_confidence": 1.0,
                                         "match_reasons": ["user confirmed merge"], "contributing_record_ids": list(ent["record_ids"]), "enriched_fields": changed}
    elif choice == "new":
        ident = wishlist_identity(rec) if kind == "wishlist" else scholarship_identity(rec)
        key = _make_key(kind, ident, rec["id"]) + "~" + rec["id"][-6:]
        ent = _new_entity(kind, key, ident, rec)
        merge_fields(ent, rec, fields)
        _touch(ent, rec)
        ents.append(ent)
        save(kind, ents)
        rec["destination_resolution"] = {"action": "created", "entity_key": key, "matched_entity": "", "match_confidence": 1.0,
                                         "match_reasons": ["user chose separate entry"], "contributing_record_ids": [rec["id"]]}
    else:
        raise ValueError("choice must be merge or new")
    rec.setdefault("export", {}).setdefault("destination_sync", {})["status"] = "pending"
    rec["export"]["status"] = "export_pending"
    store.write(rec)
    return rec["destination_resolution"]


def describe(res: dict, dest: str) -> str:
    a = res.get("action")
    name = DESTINATIONS.get(dest, dest)
    if a == "merged":
        return f"merged with existing {name} item"
    if a == "possible_duplicate":
        return f"possible {name} duplicate — review needed"
    if a == "created" and res.get("variant_of"):
        return f"new variant of an existing {name} item"
    if a == "created":
        return f"new {name} item"
    return ""
