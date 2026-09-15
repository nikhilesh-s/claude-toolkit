"""Sync behaviour with a fake Google. No network, no real Drive. Run: uv run python tests/test_sync.py"""
import json
import os
import tempfile

os.environ["LINKINTAKE_STATE_DIR"] = tempfile.mkdtemp(prefix="linkintake-test-")

from linkintake import config, entities, store, sync  # noqa: E402
from linkintake.destinations import MASTER_HEADER, SCHOLAR_HEADER  # noqa: E402
from linkintake.google_api import GoogleError  # noqa: E402
from linkintake.records import new_record  # noqa: E402

TARGETS = {"master_doc": "MASTER", "wishlist_doc": "WISH", "wishlist_tab_id": "t.staging", "college_folder": "F1",
           "supplement_doc": "SUPP", "media_folder": "F2", "design_doc": "DESIGN", "personal_ig_doc": "IG",
           "scholarships_folder": "F3", "scholarship_sheet": "SHEET"}


class FakeGoogle:
    """Docs are dicts of text (tab-aware); sheets are row lists. Optional failure injection per method."""

    def __init__(self):
        self.docs = {k: {"": ""} for k in ("MASTER", "SUPP", "DESIGN", "IG")}
        self.docs["WISH"] = {"": "Overview stays untouched\n", "t.staging": ""}
        self.sheets = {"SHEET": [SCHOLAR_HEADER]}
        self.fail = {}  # method name -> GoogleError
        self.calls = []
        self.account = "me@example.com"

    def _maybe_fail(self, name):
        self.calls.append(name)
        if name in self.fail:
            raise self.fail[name]

    def doc_get(self, doc_id):
        self._maybe_fail("doc_get")
        return {"_fake": doc_id}

    def doc_append_table_row(self, doc_id, cells, header, tab_id="", link_columns=()):
        self._maybe_fail("doc_append_table_row")
        self.docs[doc_id][tab_id] += " | ".join(c.replace("\n", " / ") for c in cells) + "\n"  # one line per row

    def doc_update_table_row(self, doc_id, needle, cells, tab_id="", link_columns=()):
        self._maybe_fail("doc_update_table_row")
        lines = self.docs[doc_id][tab_id].split("\n")
        for i, line in enumerate(lines):
            if needle in line:
                lines[i] = " | ".join(c.replace("\n", " / ") for c in cells)
                self.docs[doc_id][tab_id] = "\n".join(lines)
                return True
        return False

    def doc_delete_table_row(self, doc_id, needle, tab_id="", exclude=()):
        self._maybe_fail("doc_delete_table_row")
        lines = self.docs[doc_id][tab_id].split("\n")
        keep = [l for l in lines if not (needle in l and not any(x in l for x in exclude))]
        self.docs[doc_id][tab_id] = "\n".join(keep)
        return len(keep) != len(lines)

    def sheet_delete_row(self, sheet_id, row_number):
        self._maybe_fail("sheet_delete_row")
        del self.sheets[sheet_id][row_number - 1]

    def sheet_update_row(self, sheet_id, row_number, values):
        self._maybe_fail("sheet_update_row")
        self.sheets[sheet_id][row_number - 1] = values

    def doc_append_text(self, doc_id, text, tab_id=""):
        self._maybe_fail("doc_append_text")
        self.docs[doc_id][tab_id] += text

    def sheet_values(self, sheet_id, rng="A1:Z500"):
        self._maybe_fail("sheet_values")
        col = rng[0]
        idx = ord(col) - ord("A")
        return [[r[idx]] if len(r) > idx else [] for r in self.sheets[sheet_id]]

    def sheet_append(self, sheet_id, values, rng="A1"):
        self._maybe_fail("sheet_append")
        self.sheets[sheet_id].extend(values)


def fake_doc_text(doc, tab_id=""):
    fake = FAKE.docs[doc["_fake"]]
    return fake.get(tab_id, "") if tab_id else "\n".join(fake.values())


FAKE = FakeGoogle()
sync.doc_text = fake_doc_text          # monkeypatch idempotency read
sync.is_configured = lambda: True      # pretend token exists


def make(dest="personal_ig", instruction="test"):
    rec = new_record(original_url=f"https://example.com/{dest}", canonical_url=f"https://example.com/{dest}", source_class="web_page",
                     platform="example.com", destination=dest, instruction=instruction)
    rec["status"] = "ready"
    rec["extraction"].update({"takeaways": ["a", "b"], "focused_result": "detail", "tags": ["x"], "confidence": 0.8,
                              "structured_data": {"scholarship": "S" + instruction, "organization": "Org", "deadline": "2027-01-01",
                                                  "product_item": "Lamp " + instruction, "brand": "Acme", "model": "L-" + instruction}})
    rec["saved_at"] = rec["created_at"]
    store.save(rec)
    if dest in ("wishlist", "scholarships"):
        rec["destination_resolution"] = entities.resolve(rec)
        store.write(rec)
    return rec


def setup_cfg():
    cfg = config.load()
    cfg["google"]["export_mode"] = "auto"
    cfg["google"]["targets"] = dict(TARGETS)
    config.save(cfg)
    return cfg


def main():
    global FAKE
    cfg = setup_cfg()

    # 1. both succeed -> synced, record id present in master + destination
    FAKE = FakeGoogle(); sync.doc_text = fake_doc_text
    r = make("personal_ig")
    ex = sync.sync_record(r, g=FAKE, cfg=cfg)
    assert ex["status"] == "synced" and ex["master_sync"]["status"] == "synced" and ex["destination_sync"]["status"] == "synced"
    assert r["id"] in FAKE.docs["MASTER"][""] and r["id"] in FAKE.docs["IG"][""]
    assert ex["destination_sync"]["destination"] == "personal_ig" and ex["synced_at"]
    assert sync.summary_line(ex) == "Saved locally ✓ · Google synced ✓"

    # 2. retry after success never duplicates (idempotent by Record ID)
    before = (FAKE.docs["MASTER"][""], FAKE.docs["IG"][""])
    r["export"]["master_sync"]["status"] = "pending"; r["export"]["destination_sync"]["status"] = "pending"  # force re-check
    sync.sync_record(r, g=FAKE, cfg=cfg)
    assert (FAKE.docs["MASTER"][""], FAKE.docs["IG"][""]) == before, "duplicate row written"
    assert FAKE.docs["MASTER"][""].count(r["id"]) == 1

    # 3. master fails, destination succeeds -> partial, error preserved
    FAKE = FakeGoogle(); sync.doc_text = fake_doc_text
    FAKE.fail["doc_append_table_row"] = GoogleError(503, "backend error")
    r = make("supplement_ideas")
    ex = sync.sync_record(r, g=FAKE, cfg=cfg)
    assert ex["status"] == "partial" and ex["master_sync"]["status"] == "failed" and "503" in ex["master_sync"]["last_error"]
    assert ex["destination_sync"]["status"] == "synced" and r["id"] in FAKE.docs["SUPP"][""]
    assert sync.summary_line(ex) == "Saved locally ✓ · Master pending · Destination synced ✓"
    # ...then master recovers on retry; destination not re-appended
    del FAKE.fail["doc_append_table_row"]
    ex = sync.sync_record(r, g=FAKE, cfg=cfg)
    assert ex["status"] == "synced" and FAKE.docs["SUPP"][""].count(r["id"]) == 1 and FAKE.docs["MASTER"][""].count(r["id"]) == 1

    # 4. master succeeds, destination (wishlist tab) fails -> partial; other wishlist content untouched
    FAKE = FakeGoogle(); sync.doc_text = fake_doc_text
    r = make("wishlist")
    FAKE.fail["doc_append_table_row"] = GoogleError(500, "boom")
    # master uses the same method; make it fail only on the 2nd call
    calls = {"n": 0}
    real = FAKE.doc_append_table_row
    def flaky(doc_id, cells, header, tab_id="", link_columns=()):
        calls["n"] += 1
        if doc_id == "WISH":
            raise GoogleError(500, "wishlist boom")
        FAKE.calls.append("doc_append_table_row"); FAKE.docs[doc_id][tab_id] += " | ".join(cells) + "\n"
    FAKE.fail.clear(); FAKE.doc_append_table_row = flaky
    ex = sync.sync_record(r, g=FAKE, cfg=cfg)
    assert ex["status"] == "partial" and ex["master_sync"]["status"] == "synced" and "wishlist boom" in ex["destination_sync"]["last_error"]
    assert FAKE.docs["WISH"][""] == "Overview stays untouched\n"
    assert sync.summary_line(ex) == "Saved locally ✓ · Master synced ✓ · Destination pending"

    # 5. Google unreachable -> export_pending, nothing written, local record intact
    FAKE = FakeGoogle(); sync.doc_text = fake_doc_text
    FAKE.fail["doc_get"] = GoogleError(0, "unreachable: timeout")
    r = make("design_inspo")
    ex = sync.sync_record(r, g=FAKE, cfg=cfg)
    assert ex["status"] == "export_pending" and "unreachable" in ex["last_error"]
    assert store.load(r["id"])["export"]["status"] == "export_pending"

    # 6. pending retry sweep: oldest first, bounded, skips exclude
    FAKE = FakeGoogle(); sync.doc_text = fake_doc_text
    pend_before = [x["id"] for x in sync.pending_records()]
    assert pend_before, "expected pending records from earlier steps"
    done = sync.sync_pending(limit=2, budget_s=5, g=FAKE)
    assert len(done) == 2 and [d["id"] for d in done] == pend_before[:2]
    assert all(d["status"] == "synced" for d in done)
    done2 = sync.sync_pending(limit=50, budget_s=5, g=FAKE, exclude=pend_before[2] if len(pend_before) > 2 else "")
    assert all(d["id"] != (pend_before[2] if len(pend_before) > 2 else "-") for d in done2)

    # 7. sheets: duplicate Record ID skip + Sheets API disabled error surfaces verbatim
    FAKE = FakeGoogle(); sync.doc_text = fake_doc_text
    r = make("scholarships")
    ex = sync.sync_record(r, g=FAKE, cfg=cfg)
    assert ex["status"] == "synced" and FAKE.sheets["SHEET"][-1][-1] == r["id"] and len(FAKE.sheets["SHEET"]) == 2
    r["export"]["destination_sync"]["status"] = "pending"
    sync.sync_record(r, g=FAKE, cfg=cfg)
    assert len(FAKE.sheets["SHEET"]) == 2, "sheet row duplicated"
    FAKE2 = FakeGoogle(); FAKE2.fail["sheet_values"] = GoogleError(403, '{"error":{"message":"Google Sheets API has not been used in project 1 before or it is disabled sheets.googleapis.com"}}')
    r2 = make("scholarships", "another")
    FAKE = FAKE2; sync.doc_text = fake_doc_text
    ex = sync.sync_record(r2, g=FAKE2, cfg=cfg)
    assert ex["status"] == "partial" and "sheets.googleapis.com" in ex["destination_sync"]["last_error"]

    # 8. not authorized -> not_configured, no calls
    sync.is_configured = lambda: False
    r = make("inbox")
    ex = sync.sync_record(r, g=None, cfg=cfg)
    assert ex["status"] == "not_configured"
    sync.is_configured = lambda: True

    # 9. off switch
    cfg["google"]["export_mode"] = "off"
    ex = sync.sync_record(make("inbox", "off"), g=None, cfg=cfg)
    assert ex["status"] == "off"

    # 10. semantic merge on the remote: second record about the same product updates the existing row, never appends;
    #     a retry of either record after a partial failure still never duplicates (case 12)
    cfg["google"]["export_mode"] = "auto"
    FAKE = FakeGoogle(); sync.doc_text = fake_doc_text
    w1 = make("wishlist", "same-product")   # entity created
    ex1 = sync.sync_record(w1, g=FAKE, cfg=cfg)
    assert ex1["status"] == "synced" and FAKE.docs["WISH"]["t.staging"].count("\n") == 1  # one product row (fake writes no header)
    w2 = new_record(original_url="https://example.com/other-reel", canonical_url="https://example.com/other-reel", source_class="web_page",
                    platform="example.com", destination="wishlist", instruction="another angle")
    w2["status"] = "ready"; w2["saved_at"] = w2["created_at"]
    w2["extraction"].update({"confidence": 0.9, "structured_data": {"brand": "Acme", "model": "L-same-product", "price": "$10"}})
    store.save(w2)
    w2["destination_resolution"] = entities.resolve(w2)
    assert w2["destination_resolution"]["action"] == "merged"
    FAKE.fail["doc_update_table_row"] = GoogleError(500, "flaky")
    ex2 = sync.sync_record(w2, g=FAKE, cfg=cfg)
    assert ex2["status"] == "partial" and ex2["master_sync"]["status"] == "synced"
    del FAKE.fail["doc_update_table_row"]
    ex2 = sync.sync_record(w2, g=FAKE, cfg=cfg)  # retry after partial failure
    assert ex2["status"] == "synced" and ex2["destination_sync"].get("merged_row") is True
    rows = FAKE.docs["WISH"]["t.staging"].strip().split("\n")
    assert len(rows) == 1, rows  # still ONE product row
    assert w1["id"] in rows[0] and w2["id"] in rows[0] and "$10" in rows[0]
    sync.sync_record(w1, g=FAKE, cfg=cfg); sync.sync_record(w2, g=FAKE, cfg=cfg)  # idempotent retries
    assert FAKE.docs["WISH"]["t.staging"].strip().count("\n") == 0
    # possible duplicate: nothing written, status needs_decision, not swept
    w3 = new_record(original_url="https://example.com/vague", canonical_url="https://example.com/vague", source_class="web_page",
                    platform="example.com", destination="wishlist", instruction="vague")
    w3["status"] = "ready"; w3["saved_at"] = w3["created_at"]
    w3["extraction"].update({"confidence": 0.7, "structured_data": {"brand": "Acme", "product_item": "Lamp same product deluxe"}})
    store.save(w3)
    w3["destination_resolution"] = entities.resolve(w3)
    assert w3["destination_resolution"]["action"] == "possible_duplicate"
    ex3 = sync.sync_record(w3, g=FAKE, cfg=cfg)
    assert ex3["status"] == "needs_decision" and FAKE.docs["WISH"]["t.staging"].strip().count("\n") == 0
    assert all(r["id"] != w3["id"] for r in sync.pending_records())
    assert sync.summary_line(ex3, w3).startswith("Saved locally ✓ · possible Wishlist duplicate")

    # 12. absorb a stray remote row: stray row removed, canonical row carries both ids, retries stay idempotent
    stray = new_record(original_url="https://example.com/stray-src", canonical_url="https://example.com/stray-src", source_class="web_page",
                       platform="example.com", destination="wishlist", instruction="stray")
    stray["status"] = "ready"; stray["saved_at"] = stray["created_at"]
    stray["extraction"].update({"confidence": 0.9, "structured_data": {"brand": "Acme", "model": "L-same-product", "identifier": "QQQ12345"}})
    store.save(stray)
    stray["destination_resolution"] = {"action": "created", "entity_key": "wishlist:stray-test", "contributing_record_ids": [stray["id"]]}
    ents = entities.load("wishlist")
    ents.append({"key": "wishlist:stray-test", "kind": "wishlist", "identity": {"brand": "acme", "model": "l same product", "identifier": "QQQ12345", "model_numbers": []},
                 "fields": {"price": {"value": "$12", "confidence": 0.9, "record_id": stray["id"], "observed_at": "", "source_url": ""}},
                 "record_ids": [stray["id"]], "source_urls": ["https://example.com/stray-src"], "history": [], "price_observations": [], "created_at": "", "updated_at": "", "primary_record_id": stray["id"], "remote": {}})
    entities.save("wishlist", ents)
    store.write(stray)
    sync.sync_record(stray, g=FAKE, cfg=cfg)
    assert FAKE.docs["WISH"]["t.staging"].strip().count("\n") == 1  # two rows now (canonical + stray)
    canonical_key = w1["destination_resolution"]["entity_key"]
    entities.absorb("wishlist", "wishlist:stray-test", canonical_key)
    out = sync.absorb_remote("wishlist", canonical_key, [stray["id"]], g=FAKE)
    assert out["removed_rows"] == [stray["id"]] and out["canonical_row_updated"]
    rows = FAKE.docs["WISH"]["t.staging"].strip().split("\n")
    assert len(rows) == 1 and all(i in rows[0] for i in (w1["id"], w2["id"], stray["id"])), rows
    sync.sync_record(store.load(stray["id"]), g=FAKE, cfg=cfg); sync.sync_record(w1, g=FAKE, cfg=cfg)
    assert FAKE.docs["WISH"]["t.staging"].strip().count("\n") == 0
    assert sync.absorb_remote("wishlist", canonical_key, [stray["id"]], g=FAKE)["removed_rows"] == []  # idempotent

    print("test_sync: ok (12 scenarios)")


if __name__ == "__main__":
    main()
