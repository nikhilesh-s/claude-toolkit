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
# a real model/part number: letters+digits mixed, 5+ chars, at least 2 digits (NESA1V000, WH-1000XM5, A2338), never a plain word or "12-in-1"
_MODEL_NO = re.compile(r"\b(?=[A-Z0-9-]{5,}\b)(?=[A-Z0-9-]*\d[A-Z0-9-]*\d)(?=[A-Z0-9-]*[A-Z])[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
_WATT = re.compile(r"\b(\d{2,4})\s?w\b", re.I)
_UNKNOWN_VARIANT = re.compile(r"\b(not chosen|options?:|unspecified|varies|tbd|unknown)\b", re.I)
_MODEL_NOISE = {"combo", "set", "bundle", "pack", "version", "edition", "official", "new", "original", "model", "w", "watt", "watts"}


def model_core_tokens(model: str, brand: str = "") -> set[str]:
    """Descriptive model tokens with brand, wattage, bundle words, punctuation and order removed."""
    m = re.sub(r"[;(].*$", "", model or "")
    m = _WATT.sub(" ", m)
    t = tokens(m) - tokens(brand) - _MODEL_NOISE
    return {x for x in t if not _MODEL_NO.fullmatch(x.upper())}


def model_numbers(*fields: str) -> set[str]:
    out = set()
    for f in fields:
        for m in _MODEL_NO.findall((f or "").upper()):
            if not _ASIN.fullmatch(m) and not re.fullmatch(r"\d+-IN-\d+", m):
                out.add(m)
    return out


def wishlist_identity(rec: dict) -> dict:
    sd = rec["extraction"].get("structured_data", {}) or {}
    blob = " ".join(str(v) for v in sd.values())
    ident = sd.get("identifier") or sd.get("asin") or sd.get("sku") or ""
    if not ident:
        m = _ASIN.search(blob)
        ident = m.group(1) if m else ""
    model = sd.get("model", "")
    brand = norm(sd.get("brand", ""))
    core = model_core_tokens(model, brand)
    model_from = "model" if core else "name"
    if not core:
        core = model_core_tokens(sd.get("product_item", ""), brand)  # weak: a product name is not a model
    nums = model_numbers(sd.get("identifier", ""), model)  # part numbers (NESA1V000), never the ASIN
    head = re.sub(r"[;(].*$", "", model or "")  # "(40W/65W/160W bundle not shown)" is a list of options, not a choice
    v_ = sd.get("variant", "") or ""
    watt = _WATT.search(head) or (_WATT.search(v_) if not _UNKNOWN_VARIANT.search(v_) else None)
    variant_bits = [sd.get("variant", ""), sd.get("color_style", ""), sd.get("size_spec", "")]
    variant = norm(" ".join(b for b in variant_bits if b and not is_unknown(b)))
    # variant identity = a discrete purchase choice (color, size, wattage). Prose like "Not chosen. Options: White or Black" is not a choice.
    v = sd.get("variant", "") or ""
    variant_key = norm(v) if v and not _UNKNOWN_VARIANT.search(v) and len(tokens(v)) <= 3 else ""
    if not variant_key and watt:
        variant_key = f"{watt.group(1)}w"
    return {
        "identifier": ident.upper(), "product_url": (sd.get("product_url") or "").strip().lower().rstrip("/"),
        "brand": brand, "model": " ".join(sorted(core)), "model_from": model_from, "model_numbers": sorted(nums),
        "name": norm(sd.get("product_item") or sd.get("item") or rec["source"].get("title", "")),
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
def _core(e_ident: dict) -> set[str]:
    # re-normalize on read so entities stored before matcher v2 compare the same way
    return model_core_tokens(e_ident.get("model") or "", e_ident.get("brand", ""))


def _same_line(ident: dict, ei: dict) -> bool:
    """Same brand and the descriptive model tokens are equal or one contains the other (>=2 tokens)."""
    if not ident["brand"] or ei.get("brand") != ident["brand"]:
        return False
    if ident.get("model_from", "model") != "model" or ei.get("model_from", "model") != "model":
        return False  # a name-derived core can only ever reach possible_duplicate
    a, b = _core(ident), _core(ei)
    if not a or not b:
        return False
    return a == b or (len(a & b) >= 2 and (a <= b or b <= a))


def match_wishlist(ident: dict, entities: list[dict]) -> tuple[dict | None, str, float, list[str]]:
    """Returns (entity, action, confidence, reasons). action in created|merged|possible_duplicate|variant.
    Strongest evidence first; fuzzy similarity can only ever produce possible_duplicate."""
    for e in entities:
        ei = e["identity"]
        if ident["identifier"] and ident["identifier"] == ei.get("identifier"):
            return e, "merged", 0.97, ["same product identifier"]
        if ident["product_url"] and ident["product_url"] == ei.get("product_url"):
            return e, "merged", 0.92, ["same official product URL"]
        if set(ident.get("model_numbers", [])) & set(ei.get("model_numbers", [])):
            return e, "merged", 0.95, ["same model number"]
    same_line = []
    for e in entities:
        ei = e["identity"]
        if ident.get("model_numbers") and ei.get("model_numbers") and not set(ident["model_numbers"]) & set(ei["model_numbers"]):
            continue  # two known, different part numbers are different products
        if _same_line(ident, ei):
            same_line.append(e)
    if same_line:
        # Case D: variant_key (color/size/wattage choice) is part of identity. No variant on the new record ->
        # enrich the single existing line; if several variants exist, ask (never attach to the first one).
        if not ident["variant_key"]:
            if len(same_line) == 1:
                return same_line[0], "merged", 0.85, ["same brand + model"]
            return same_line[0], "possible_duplicate", 0.6, ["same brand + model, several variants exist; which one?"]
        exact_variant = [e for e in same_line if e["identity"].get("variant_key") == ident["variant_key"]]
        if exact_variant:
            return exact_variant[0], "merged", 0.9, ["same brand + model + variant"]
        unspecified = [e for e in same_line if not e["identity"].get("variant_key")]
        if unspecified:
            return unspecified[0], "merged", 0.85, ["same brand + model; existing entry had no variant, now specified"]
        return same_line[0], "variant", 0.85, ["same brand + model, different variant -> separate variant entry"]
    for e in entities:
        ei = e["identity"]
        if ident.get("model_numbers") and ei.get("model_numbers") and not set(ident["model_numbers"]) & set(ei["model_numbers"]):
            continue
        if ident.get("model_from", "model") == "model" and ei.get("model_from", "model") == "model" and _core(ident) and _core(ei) and not (_core(ident) & _core(ei)):
            continue  # both models known and sharing no descriptive token: different products, not "similar"
        if ident["brand"] and ei.get("brand") == ident["brand"]:
            a = (tokens(ident["name"]) | _core(ident)) - tokens(ident["brand"]) - _MODEL_NOISE
            b = (tokens(ei.get("name", "")) | _core(ei)) - tokens(ident["brand"]) - _MODEL_NOISE
            sim = len(a & b) / min(len(a), len(b)) if a and b else 0.0  # overlap coefficient
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
        new_conf = min(1.0, _field_conf(rec, new) + (0.15 if authoritative else 0))
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
        if ident.get("model_numbers"):
            ent["identity"]["model_numbers"] = sorted(set(ent["identity"].get("model_numbers", [])) | set(ident["model_numbers"]))
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


def refresh_identity(ent: dict) -> dict:
    """Recompute identity from the entity's records with the current identity code (entities stored by older
    code keep working). Unions identifiers/model numbers; variant_key = first real purchase choice seen."""
    from . import store
    if ent["kind"] != "wishlist":
        return ent["identity"]
    idents = []
    for rid in ent["record_ids"]:
        try:
            idents.append(wishlist_identity(store.load(rid)))
        except FileNotFoundError:
            continue
    if not idents:
        return ent["identity"]
    base = idents[0]
    merged = dict(base)
    merged["identifier"] = next((i["identifier"] for i in idents if i["identifier"]), "")
    merged["product_url"] = next((i["product_url"] for i in idents if i["product_url"]), "")
    merged["model_numbers"] = sorted({n for i in idents for n in i.get("model_numbers", [])})
    with_model = [i for i in idents if i.get("model_from") == "model" and i["model"]]
    if with_model:
        merged["model"], merged["model_from"] = with_model[0]["model"], "model"
    merged["variant_key"] = next((i["variant_key"] for i in idents if i["variant_key"]), "")
    ent["identity"] = merged
    return merged


def absorb(kind: str, stray_key: str, into_key: str) -> dict:
    """Merge stray entity into the canonical one. Records are untouched except their resolution now points at the
    canonical entity. Provenance (record ids, urls, price observations, history) is carried over; fields merge by
    the usual rules (higher confidence / more specific wins, unknown never overwrites). Idempotent."""
    from . import store
    ents = load(kind)
    into = next((e for e in ents if e["key"] == into_key), None)
    stray = next((e for e in ents if e["key"] == stray_key), None)
    if not into:
        raise ValueError(f"no entity {into_key}")
    if not stray:
        return {"absorbed": [], "into": into_key, "note": "stray already gone"}
    moved = []
    for rid in stray["record_ids"]:
        if rid not in into["record_ids"]:
            into["record_ids"].append(rid)
        moved.append(rid)
    for u in stray["source_urls"]:
        if u not in into["source_urls"]:
            into["source_urls"].append(u)
    for f, val in stray["fields"].items():
        if not isinstance(val, dict):
            continue
        cur = into["fields"].get(f)
        if cur is None or (is_unknown(cur["value"]) and not is_unknown(val["value"])) or (
                not is_unknown(val["value"]) and val["confidence"] >= cur["confidence"] - 0.05 and (_more_specific(val["value"], cur["value"]) or val["confidence"] > cur["confidence"])):
            into.setdefault("history", []).append({"field": f, "from": cur["value"] if cur else "", "to": val["value"], "record_id": val.get("record_id", ""), "at": _now(), "via": "absorb"})
            into["fields"][f] = val
    into["price_observations"] = into.get("price_observations", []) + [p for p in stray.get("price_observations", []) if p not in into.get("price_observations", [])]
    into["history"] = into.get("history", []) + stray.get("history", [])
    into["updated_at"] = _now()
    refresh_identity(into)  # never trust a stray's stored identity; recompute from the records
    into.setdefault("absorbed_keys", []).append(stray_key)
    ents = [e for e in ents if e["key"] != stray_key]
    save(kind, ents)
    for rid in moved:
        try:
            rec = store.load(rid)
        except FileNotFoundError:
            continue
        rec["destination_resolution"] = {"action": "merged", "entity_key": into_key, "matched_entity": into_key, "match_confidence": 1.0,
                                         "match_reasons": [f"absorbed stray entity {stray_key}"], "contributing_record_ids": list(into["record_ids"])}
        store.write(rec)
    return {"absorbed": moved, "into": into_key, "record_ids": into["record_ids"], "source_urls": into["source_urls"]}


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
