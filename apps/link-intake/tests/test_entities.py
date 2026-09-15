"""Semantic duplicate/merge matrix for Wishlist products and Scholarship cycles. Run: uv run python tests/test_entities.py"""
import os
import tempfile

os.environ["LINKINTAKE_STATE_DIR"] = tempfile.mkdtemp(prefix="linkintake-ent-")

from linkintake import entities, store  # noqa: E402
from linkintake.records import new_record  # noqa: E402


def rec(url, dest, instruction, sd, conf=0.8, source_class="social_media"):
    r = new_record(original_url=url, canonical_url=url, source_class=source_class, platform="instagram" if source_class == "social_media" else "web",
                   destination=dest, instruction=instruction)
    r["status"] = "ready"
    r["extraction"].update({"structured_data": sd, "confidence": conf, "focused_result": "x", "takeaways": ["t"]})
    r["saved_at"] = r["created_at"]
    store.save(r)
    return r


def main():
    # --- 4. different URLs, same exact product -> one entity, both records kept
    a = rec("https://instagram.com/reel/AAA/", "wishlist", "identify this charger",
            {"product_item": "Desktop charging station", "brand": "Gitryin", "model": "12-in-1 Desktop Charging Station; exact model TBD", "price": "Not shown"})
    ra = entities.resolve(a)
    assert ra["action"] == "created", ra
    b = rec("https://instagram.com/reel/BBB/", "wishlist", "what charger is this",
            {"product_item": "Gitryin 12-in-1 charging station", "brand": "Gitryin", "model": "12-in-1 Desktop Charging Station", "price": "$89.99", "notes": "Amazon ASIN B0F4QRX9PB"})
    rb = entities.resolve(b)
    assert rb["action"] == "merged" and rb["entity_key"] == ra["entity_key"], rb
    ent = entities.get("wishlist", ra["entity_key"])
    assert set(ent["record_ids"]) == {a["id"], b["id"]} and len(ent["source_urls"]) == 2  # 13. provenance kept
    assert store.load(a["id"]) and store.load(b["id"])  # 13. both intake records remain
    # --- 7. unknown model then known model -> enrichment, TBD replaced, never the reverse
    assert "TBD" not in ent["fields"]["model"]["value"] and ent["identity"]["identifier"] == "B0F4QRX9PB"
    assert ent["price_observations"] and ent["price_observations"][-1]["price"] == "$89.99"  # G. price observed with provenance
    c = rec("https://instagram.com/reel/CCC/", "wishlist", "same thing again", {"brand": "Gitryin", "model": "12-in-1 Desktop Charging Station", "price": "unknown"}, conf=0.9)
    rc = entities.resolve(c)
    assert rc["action"] == "merged"
    ent = entities.get("wishlist", ra["entity_key"])
    assert ent["fields"]["price"]["value"] == "$89.99", "supported value replaced by unknown"
    assert len(ent["price_observations"]) == 1
    # --- 1. same Record ID re-resolved -> same outcome, no growth
    again = entities.resolve(b)
    assert again["entity_key"] == ra["entity_key"] and len(entities.get("wishlist", ra["entity_key"])["record_ids"]) == 3

    # --- 5. same product line, different variant (color) -> separate variant entity, linked
    d = rec("https://instagram.com/reel/DDD/", "wishlist", "backpack", {"product_item": "Everyday backpack", "brand": "Bellroy", "model": "Classic Backpack Plus", "variant": "Black"})
    rd = entities.resolve(d)
    assert rd["action"] == "created"
    e = rec("https://instagram.com/reel/EEE/", "wishlist", "backpack navy", {"product_item": "Everyday backpack", "brand": "Bellroy", "model": "Classic Backpack Plus", "variant": "Navy"})
    re_ = entities.resolve(e)
    assert re_["action"] == "created" and re_["variant_of"] == rd["entity_key"] and re_["entity_key"] != rd["entity_key"], re_
    f = rec("https://instagram.com/reel/FFF/", "wishlist", "backpack black again", {"brand": "Bellroy", "model": "Classic Backpack Plus", "variant": "black"})
    assert entities.resolve(f)["entity_key"] == rd["entity_key"]  # same variant -> merge
    # variant unspecified while two variants exist -> ask
    g = rec("https://instagram.com/reel/GGG/", "wishlist", "which one", {"brand": "Bellroy", "model": "Classic Backpack Plus"})
    assert entities.resolve(g)["action"] == "possible_duplicate"

    # --- 6. vague similarity (same brand, similar name, no model) -> possible_duplicate, nothing merged
    h = rec("https://instagram.com/reel/HHH/", "wishlist", "charger?", {"product_item": "Gitryin charging station cube", "brand": "Gitryin"})
    rh = entities.resolve(h)
    assert rh["action"] == "possible_duplicate" and rh["matched_entity"] == ra["entity_key"], rh
    assert h["id"] not in entities.get("wishlist", ra["entity_key"])["record_ids"]
    # user decides: merge (save_record persists the resolution on the record; mirror that here)
    h["destination_resolution"] = rh
    store.write(h)
    dec = entities.decide(h["id"], "merge")
    assert dec["action"] == "merged" and h["id"] in entities.get("wishlist", ra["entity_key"])["record_ids"]

    # --- 8. same scholarship from a Reel and a web page -> one cycle row; web page is authoritative for facts
    s1 = rec("https://instagram.com/reel/S1/", "scholarships", "deadline?", {"scholarship": "Coca-Cola Scholars Program", "organization": "Coca-Cola Scholars Foundation", "deadline": "2027-09-30", "amount": "$20,000"}, conf=0.6)
    r1 = entities.resolve(s1)
    assert r1["action"] == "created"
    s2 = rec("https://coca-colascholarsfoundation.org/apply/", "scholarships", "details", {"scholarship": "Coca-Cola Scholars Program 2027", "organization": "Coca-Cola Scholars Foundation", "deadline": "2027-10-02", "amount": "$20,000", "eligibility": "HS seniors"}, conf=0.7, source_class="web_page")
    r2 = entities.resolve(s2)
    assert r2["action"] == "merged" and r2["entity_key"] == r1["entity_key"], r2
    ent = entities.get("scholarship", r1["entity_key"])
    assert ent["fields"]["deadline"]["value"] == "2027-10-02" and ent["fields"]["eligibility"]["value"] == "HS seniors"  # 10. deadline updated in place
    assert any(h_["field"] == "deadline" for h_ in ent["history"])  # provenance of the change
    # --- 9. same program, different year -> separate row
    s3 = rec("https://example.org/coke-2028", "scholarships", "next year", {"scholarship": "Coca-Cola Scholars Program 2028", "organization": "Coca-Cola Scholars Foundation", "deadline": "2028-10-01"}, source_class="web_page")
    r3 = entities.resolve(s3)
    assert r3["action"] == "created" and r3["entity_key"] != r1["entity_key"], r3
    # --- E. year unknown -> possible duplicate, not merged
    s4 = rec("https://instagram.com/reel/S4/", "scholarships", "hm", {"scholarship": "Coca-Cola Scholars Program", "organization": "Coca-Cola Scholars Foundation"})
    assert entities.resolve(s4)["action"] == "possible_duplicate"
    # --- D. same org, different program -> separate
    s5 = rec("https://example.org/coke-community", "scholarships", "x", {"scholarship": "Coca-Cola Community Leaders Award", "organization": "Coca-Cola Scholars Foundation", "deadline": "2027-05-01"})
    assert entities.resolve(s5)["action"] in ("created", "possible_duplicate")

    # --- 11. supplement / design / instagram: never semantically deduplicated
    for dest in ("supplement_ideas", "design_inspo", "personal_ig"):
        x = rec("https://instagram.com/reel/SAME/", dest, "idea one", {})
        y = rec("https://instagram.com/reel/SAME/", dest, "idea two", {})
        assert entities.resolve(x)["action"] == "n/a" and entities.resolve(y)["action"] == "n/a"
        assert store.load(x["id"]) and store.load(y["id"])

    # --- 2/3. exact intake duplicate vs same URL different intent (dedupe_key layer)
    from linkintake.records import dedupe_key
    assert dedupe_key("u", "wishlist", "Identify this!") == dedupe_key("u", "wishlist", "identify this")
    assert dedupe_key("u", "wishlist", "identify this") != dedupe_key("u", "wishlist", "what color is this")

    # --- matcher robustness: harmless token differences must not defeat identity
    base = rec("https://instagram.com/reel/M1/", "wishlist", "charger", {"product_item": "Desktop charging station", "brand": "Gitryin2", "model": "12-in-1 Desktop Charging Station; exact model TBD"})
    rbase = entities.resolve(base)
    assert rbase["action"] == "created"
    for label, sd in [
        ("reordered tokens", {"brand": "Gitryin2", "model": "Desktop Charging Station 12-in-1"}),
        ("brand inside model", {"brand": "Gitryin2", "model": "Gitryin2 12 in 1 Desktop Charging Station"}),
        ("punctuation", {"brand": "Gitryin2", "model": "12 in 1 desktop charging-station"}),
        ("bundle word", {"brand": "Gitryin2", "model": "12-in-1 Desktop Charging Station (65W Combo)"}),
    ]:
        r_ = rec(f"https://example.com/{label.replace(' ', '-')}", "wishlist", label, sd)
        out = entities.resolve(r_)
        assert out["action"] == "merged" and out["entity_key"] == rbase["entity_key"], (label, out)
    # wattage descriptor: same line, becomes the variant of the (previously unspecified) entry
    w = rec("https://example.com/65w", "wishlist", "65w page", {"brand": "Gitryin2", "model": "Gitryin2 65W 12-in-1 Desktop Charging Station", "identifier": "NESA1V000"})
    out = entities.resolve(w)
    assert out["action"] == "merged" and out["entity_key"] == rbase["entity_key"], out
    ent = entities.get("wishlist", rbase["entity_key"])
    assert ent["identity"]["variant_key"] == "65w" and "NESA1V000" in ent["identity"]["model_numbers"]
    # exact identifier beats fuzzy naming: totally different wording, same model number -> merged
    x = rec("https://example.com/x", "wishlist", "x", {"brand": "Gitryin2", "product_item": "power strip cube thing", "model": "NESA1V000"})
    assert entities.resolve(x)["entity_key"] == rbase["entity_key"]
    # known different model numbers stay separate even with similar names
    y = rec("https://example.com/y", "wishlist", "y", {"brand": "Gitryin2", "model": "12-in-1 Desktop Charging Station", "identifier": "NESA2V000"})
    ry = entities.resolve(y)
    assert ry["action"] == "created" and ry["entity_key"] != rbase["entity_key"], ry
    # variant-only ambiguity (two variants known, new record unspecified) -> possible_duplicate, never first-variant
    z = rec("https://example.com/z", "wishlist", "z", {"brand": "Bellroy", "model": "Classic Backpack Plus", "variant": "Not chosen. Options: Black or Navy"})
    rz = entities.resolve(z)
    assert rz["action"] == "possible_duplicate", rz

    # --- absorb a stray entity into the canonical one: all ids/urls preserved, stray gone, idempotent
    stray = rec("https://example.com/stray", "wishlist", "stray", {"brand": "Gitryin2", "model": "Charging cube NESA1V000 deluxe", "price": "$99", "identifier": "ZZZ9999"})
    rs = entities.resolve(stray)
    if rs["action"] != "created":  # force a stray for the test
        rs = entities.decide(stray["id"], "new") if rs["action"] == "possible_duplicate" else rs
    stray_key = rs["entity_key"] if rs["action"] == "created" else None
    if stray_key and stray_key != rbase["entity_key"]:
        before_ids = set(entities.get("wishlist", rbase["entity_key"])["record_ids"])
        res_abs = entities.absorb("wishlist", stray_key, rbase["entity_key"])
        ent = entities.get("wishlist", rbase["entity_key"])
        assert stray["id"] in ent["record_ids"] and before_ids <= set(ent["record_ids"]) and "https://example.com/stray" in ent["source_urls"]
        assert entities.get("wishlist", stray_key) is None and any(p["price"] == "$99" for p in ent["price_observations"])
        assert store.load(stray["id"])["destination_resolution"]["entity_key"] == rbase["entity_key"]
        assert entities.absorb("wishlist", stray_key, rbase["entity_key"])["absorbed"] == []  # idempotent

    print("test_entities: ok (cases 1-11, 13, D-G, matcher robustness, absorb)")


if __name__ == "__main__":
    main()
