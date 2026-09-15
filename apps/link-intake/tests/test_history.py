"""History rows: saved vs unsaved, newest first, re-save refused. Run: uv run python tests/test_history.py"""
import os
import tempfile
import time

os.environ["LINKINTAKE_STATE_DIR"] = tempfile.mkdtemp(prefix="linkintake-hist-")

from linkintake import pipeline, store  # noqa: E402
from linkintake.records import new_record  # noqa: E402


def rec(url, saved):
    r = new_record(original_url=url, canonical_url=url, source_class="web_page", platform="example.com", destination="inbox", instruction="x")
    r["status"] = "ready"
    if saved:
        r["saved_at"] = r["created_at"]
        r["export"] = {"status": "synced", "master_sync": {"status": "synced"}, "destination_sync": {"status": "synced"}}
        store.save(r)
    else:
        store.write_pending(r)
    time.sleep(0.01)
    return r


def main():
    a = rec("https://example.com/a", saved=True)
    b = rec("https://example.com/b", saved=False)
    c = rec("https://example.com/c", saved=True)
    rows = store.history(10)
    ids = [r["id"] for r in rows]
    assert ids[0] == c["id"], "newest first"
    by = {r["id"]: r for r in rows}
    assert by[a["id"]]["saved"] and by[a["id"]]["sync_line"] == "Saved locally ✓ · Google synced ✓"
    assert not by[b["id"]]["saved"] and by[b["id"]]["sync_line"] == "Not saved" and by[b["id"]]["export_status"] == ""
    assert store.history(10, include_pending=False) and all(r["saved"] for r in store.history(10, include_pending=False))
    # a saved record cannot be saved twice (duplicate prevention at the CLI layer)
    try:
        pipeline.save_record(a["id"])
        raise AssertionError("re-save should be refused")
    except pipeline.DuplicateError:
        pass
    # history survives a fresh read (it is built from files, not memory)
    assert [r["id"] for r in store.history(10)] == ids
    # a failed record saves locally (audit) but never exports or seeds an entity
    from linkintake import entities
    f = new_record(original_url="https://example.com/404", canonical_url="https://example.com/404", source_class="web_page", platform="example.com",
                   destination="scholarships", instruction="x")
    f["status"] = "failed"; f["errors"] = ["adapter: HTTP 404"]
    store.write_pending(f)
    out = pipeline.save_record(f["id"])
    assert out["saved_at"] and out["export"]["status"] == "skipped" and out["destination_resolution"]["action"] == "n/a"
    assert not [e for e in entities.load("scholarship") if f["id"] in e["record_ids"]]
    assert store.history(20)[0]["id"] == f["id"] and store.history(20)[0]["sync_line"].startswith("Saved locally ✓ · Google skipped")
    # exact duplicate with --save is refused before any processing
    try:
        pipeline.ingest("https://example.com/a", "inbox", "x", save=True)
        raise AssertionError("exact duplicate should be refused")
    except pipeline.DuplicateError:
        pass
    print("test_history: ok")


if __name__ == "__main__":
    main()
