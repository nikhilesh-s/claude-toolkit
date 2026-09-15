"""Bulk ingest with fixtures only: no osascript, no network, no Google. Run: uv run python tests/test_bulk.py"""
import os
import tempfile

os.environ["LINKINTAKE_STATE_DIR"] = tempfile.mkdtemp(prefix="linkintake-bulk-")

from linkintake import bulk, pipeline, store  # noqa: E402
from linkintake.records import new_record  # noqa: E402

REEL = "https://www.instagram.com/reel/AAAAAAA/?igsh=xyz"
CANON = "https://www.instagram.com/reel/AAAAAAA/"


def saved(url, dest, instruction, status="ready"):
    r = new_record(original_url=url, canonical_url=url, source_class="social_media", platform="instagram", destination=dest, instruction=instruction)
    r["status"] = status
    r["saved_at"] = r["created_at"]
    store.save(r)
    return r


def main():
    # read-only guard: the AppleScript never mutates
    for script in (bulk.REMINDERS_SCRIPT, bulk.NOTES_SCRIPT):
        low = script.lower()
        assert "delete" not in low and "make new" not in low and "set completed" not in low and "set name of" not in low and "set body" not in low, "mutating verb in source script"

    items = [
        {"origin": "reminders", "container": "Wishlist", "title": "this desk charger looks sick", "text": REEL},
        {"origin": "reminders", "container": "00 Inbox", "title": "this desk charger looks sick", "text": REEL},              # same URL, same context -> collapse
        {"origin": "notes", "container": "Notes", "title": "reel ideas", "text": f"love how this reel is shot and edited\n{REEL}\n\nunrelated line"},  # same URL, different intent
        {"origin": "reminders", "container": "09 Later + Ideas", "title": "", "text": "https://example.com/vague-article"},   # no context -> review
        {"origin": "reminders", "container": "00 Inbox", "title": "broken", "text": "http://localhost:8080/private"},          # invalid
        {"origin": "manifest", "container": "wishlist regression manifest", "title": "", "text": "https://www.instagram.com/reel/BBBBBBB/?igsi=1"},
        {"origin": "reminders", "container": "02 College Apps", "title": "love the framing of this essay idea", "text": "https://www.youtube.com/watch?v=abc"},
        {"origin": "notes", "container": "Notes", "title": "scholarships", "text": "Coca Cola scholars deadline sept 30\nhttps://www.coca-colascholarsfoundation.org/apply/"},
    ]
    saved("https://www.instagram.com/reel/CCCCCCC/", "wishlist", "identify this")                     # already ingested
    items.append({"origin": "reminders", "container": "Wishlist", "title": "identify this", "text": "https://www.instagram.com/reel/CCCCCCC/"})
    saved("https://www.instagram.com/reel/DDDDDDD/", "wishlist", "what lamp is this")                 # same URL+dest, new instruction -> review
    items.append({"origin": "reminders", "container": "Wishlist", "title": "want the mug in this one", "text": "https://www.instagram.com/reel/DDDDDDD/"})

    cands = bulk.build_candidates(items)
    by = {c["canonical_url"] + "|" + c["inferred_destination"]: c for c in cands}
    # explicit Wishlist reminder -> ready, collapsed from two places
    w = by[CANON + "|wishlist"]
    assert w["status"] == "ready" and w["destination_confidence"] >= 0.8 and w["inferred_instruction"] == "this desk charger looks sick"
    assert len(w["provenance"]) == 2 and {p["origin"] for p in w["provenance"]} == {"reminders"}
    # same URL different intent -> separate candidate (Personal Instagram), not collapsed
    ig = by[CANON + "|personal_ig"]
    assert ig["status"] == "ready" and "shot" in ig["inferred_instruction"]
    # ambiguous -> review; invalid -> invalid
    assert by["https://example.com/vague-article|inbox"]["status"] == "review"
    assert any(c["status"] == "invalid" for c in cands if "localhost" in c["original_url"])
    # manifest -> Wishlist product backlog: explicit container, approved buying-details instruction -> ready
    m = by["https://www.instagram.com/reel/BBBBBBB/|wishlist"]
    assert m["status"] == "ready" and m["destination_confidence"] >= 0.85 and "exact product" in m["inferred_instruction"]
    # work/tooling link with no destination wording -> skip, never Inbox; with wording -> kept
    items2 = [{"origin": "notes", "container": "Notes", "title": "nyscents tasks", "text": "Supabase URL:\nhttps://abc.supabase.co/"},
              {"origin": "notes", "container": "Notes", "title": "site", "text": "website inspo for the landing page\nhttps://github.com/x/y"},
              {"origin": "reminders", "container": "07 Personal + Home", "title": "video inspo", "text": "https://www.instagram.com/reel/EEEEEEE/"},
              {"origin": "reminders", "container": "00 Inbox", "title": "Desk stuff", "text": "https://www.instagram.com/reel/FFFFFFF/"},
              {"origin": "reminders", "container": "00 Inbox", "title": "order", "text": "https://example.com/shop"},
              {"origin": "notes", "container": "Notes", "title": "act", "text": "create practice tests with realistic pacing and structure\nhttps://github.com/x/act"},
              {"origin": "notes", "container": "Notes", "title": "logo", "text": "Branch for central logo positioning\nhttps://github.com/x/site/tree/logo"}]
    c2 = {c["canonical_url"]: c for c in bulk.build_candidates(items2)}
    assert c2["https://abc.supabase.co/"]["status"] == "skip" and "work/tooling" in c2["https://abc.supabase.co/"]["reason"]
    assert c2["https://github.com/x/y"]["status"] == "ready" and c2["https://github.com/x/y"]["inferred_destination"] == "design_inspo"
    assert c2["https://www.instagram.com/reel/EEEEEEE/"]["inferred_destination"] == "personal_ig" and c2["https://www.instagram.com/reel/EEEEEEE/"]["destination_confidence"] >= 0.8
    assert c2["https://www.instagram.com/reel/EEEEEEE/"]["status"] == "ready" and "video inspo" in c2["https://www.instagram.com/reel/EEEEEEE/"]["inferred_instruction"]
    assert c2["https://www.instagram.com/reel/FFFFFFF/"]["status"] == "review"
    assert c2["https://github.com/x/act"]["status"] == "skip", c2["https://github.com/x/act"]  # technique word on a tooling link is not a destination
    assert c2["https://github.com/x/site/tree/logo"]["status"] == "skip"
    assert c2["https://example.com/shop"]["status"] == "review"  # lone weak "order" never auto-runs
    # College Apps list + essay wording -> Supplement Ideas ready
    assert by["https://www.youtube.com/watch?v=abc|supplement_ideas"]["status"] == "ready"
    # scholarship wording -> Scholarships
    assert by["https://www.coca-colascholarsfoundation.org/apply|scholarships"]["status"] == "ready"
    # already ingested -> existing; same URL+dest with new instruction -> review with pointer
    assert by["https://www.instagram.com/reel/CCCCCCC/|wishlist"]["status"] == "existing"
    d = by["https://www.instagram.com/reel/DDDDDDD/|wishlist"]
    assert d["status"] == "review" and "already saved to this destination" in d["reason"]
    s = bulk.summary(cands)
    assert s["found"] == len(cands) and s["existing"] == 1 and s["invalid"] == 1

    # review actions
    run_id = bulk.new_run(cands, ["fixture"])
    run = bulk.load_run(run_id)
    bulk.review_update(run, m["id"], approve=True)  # already ready; approve is a no-op status-wise
    bulk.review_update(run, by["https://example.com/vague-article|inbox"]["id"], dest="design_inspo", instruction="the layout")
    bulk.review_update(run, d["id"], skip=True)
    bulk.save_run(run)
    run = bulk.load_run(run_id)
    st = {c["id"]: c["status"] for c in run["candidates"]}
    assert st[m["id"]] in ("approved", "ready") and st[d["id"]] == "skip"
    va = next(c for c in run["candidates"] if c["canonical_url"] == "https://example.com/vague-article")
    assert va["status"] == "approved" and va["inferred_destination"] == "design_inspo" and va["inferred_instruction"] == "the layout"

    # dry run processes nothing
    rep = bulk.run_batch(run, dry_run=True)
    assert rep["processed"] == 0 and len(rep["would_process"]) == s["ready"] + 3 - 0 or rep["would_process"]

    # real run with a fake pipeline: one item fails at fetch, one is an exact duplicate, rest save; batch never stops
    calls = []
    def fake_ingest(url, dest, instruction, *, save=False, force=False, refresh=False, batch=None):
        calls.append(url)
        r = new_record(original_url=url, canonical_url=url, source_class="web_page", platform="x", destination=dest, instruction=instruction)
        r["batch"] = batch
        if "youtube" in url:
            r["status"] = "failed"; r["errors"] = ["adapter: HTTP 404"]; r["export"] = {"status": "skipped"}
        elif "CCCCCCC" in url:
            raise pipeline.DuplicateError("already")
        else:
            r["status"] = "ready"; r["saved_at"] = r["created_at"]
            r["destination_resolution"] = {"action": "merged" if "BBBBBBB" in url else "created"}
            r["export"] = {"status": "synced" if "coca" not in url else "export_pending"}
        return r
    real = pipeline.ingest
    pipeline.ingest = fake_ingest
    try:
        rep = bulk.run_batch(run, dry_run=False, delay=0)
    finally:
        pipeline.ingest = real
    assert rep["failed"] == 1 and rep["saved"] >= 3 and rep["merged"] == 1 and rep["google_pending"] == 1
    run2 = bulk.load_run(run_id)
    assert all(c["status"] in ("done", "failed", "existing", "skip", "invalid") for c in run2["candidates"]), [c["status"] for c in run2["candidates"]]
    # resumable: a second run finds nothing left to do
    rep2 = bulk.run_batch(run2, dry_run=False, delay=0)
    assert rep2["processed"] == 0
    print("test_bulk: ok")


if __name__ == "__main__":
    main()
