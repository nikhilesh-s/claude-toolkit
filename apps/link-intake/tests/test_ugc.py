"""UGC destination: row shape, sheet-kind append-once, guidance, setup. No network, no Google.
Run: uv run python tests/test_ugc.py"""
import json
import os
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

os.environ["LINKINTAKE_STATE_DIR"] = tempfile.mkdtemp(prefix="linkintake-ugc-test-")

from linkintake import cli, config, destinations as D, extract, google_api, google_setup, pipeline, store, sync  # noqa: E402
from linkintake.adapters import media_unlocker as mu  # noqa: E402
from linkintake.extract import GUIDANCE  # noqa: E402
from linkintake.google_api import GoogleError  # noqa: E402
from linkintake.records import DESTINATIONS, dedupe_key, new_record, normalize_destination  # noqa: E402
from linkintake.router import canonicalize  # noqa: E402


class FakeGoogle:
    """Minimal fake: sheet_append and drive_upload_file are what the ugc_sheet kind exercises."""

    def __init__(self, upload_result=("DRVID", "https://drive.google.com/uc?id=DRVID"), fail_upload=False):
        self.sheets = {"UGC": []}
        self.calls = []
        self.upload_result = upload_result
        self.fail_upload = fail_upload

    def verify_identity(self):  # the real guard is covered by tests/test_ownership.py
        return "me@example.com"

    def assert_owned(self, file_id, label=""):
        return {"id": file_id}

    def sheet_append(self, sheet_id, values, rng="A1"):
        self.calls.append(("sheet_append", sheet_id))
        self.sheets[sheet_id].extend(values)

    def drive_upload_file(self, path, name, parent, mime="image/jpeg"):
        self.calls.append(("drive_upload_file", str(path), name, parent, mime))
        if self.fail_upload:
            raise RuntimeError("drive is down")
        return self.upload_result


def make_ugc_record(**extra_source):
    rec = new_record(original_url="https://www.instagram.com/reel/AAAAAAA/", canonical_url="https://www.instagram.com/reel/AAAAAAA/",
                      source_class="social_media", platform="instagram", destination="ugc", instruction="")
    rec["source"].update(extra_source)
    return rec


def test_destination_and_aliases():
    assert DESTINATIONS["ugc"] == "UGC"
    assert normalize_destination("ugc") == "ugc"
    assert normalize_destination("reel") == "ugc"
    assert normalize_destination("creator") == "ugc"
    assert normalize_destination("UGC") == "ugc"


def test_new_record_ugc_fields():
    rec = make_ugc_record()
    assert rec["source"]["received_via"] == ""
    assert rec["source"]["received_from"] == ""
    assert rec["metrics"] == {"like_count": None, "view_count": None, "duration_s": None, "captured_at": ""}
    assert rec["senders"] == []


def test_ugc_row_shape():
    assert len(D.UGC_HEADER) == 19
    rec = make_ugc_record(creator="thecreator")
    rec["context"]["caption_or_text"] = "a" * 400
    row = D.ugc_row(rec)
    assert len(row) == 19
    assert len(row) == len(D.UGC_HEADER)
    assert row[D.UGC_HEADER.index("Status")] == "new"
    assert row[D.UGC_HEADER.index("Owner")] == ""
    assert row[D.UGC_HEADER.index("Notes")] == ""
    assert row[D.UGC_HEADER.index("Rights asked")] == "no"
    assert row[D.UGC_HEADER.index("Record ID")] == rec["id"]
    assert row[D.UGC_HEADER.index("Creator")] == "thecreator"
    assert row[D.UGC_HEADER.index("URL")] == rec["source"]["original_url"]
    # blank metrics stay "", never "0"
    assert row[D.UGC_HEADER.index("Views at intake")] == ""
    assert row[D.UGC_HEADER.index("Likes at intake")] == ""
    # no thumbnail_url -> blank cell, not =IMAGE(
    assert row[D.UGC_HEADER.index("Thumbnail")] == ""
    # caption clipped 300
    assert len(row[D.UGC_HEADER.index("Caption")]) <= 300
    # duration blank when unset
    assert row[D.UGC_HEADER.index("Duration")] == ""

    rec["artifacts"]["thumbnail_url"] = "https://drive.google.com/uc?id=xyz"
    rec["metrics"]["duration_s"] = 31
    rec["metrics"]["view_count"] = 0  # a real zero must NOT be treated as blank
    rec["metrics"]["like_count"] = 5
    row2 = D.ugc_row(rec)
    assert row2[D.UGC_HEADER.index("Thumbnail")] == '=IMAGE("https://drive.google.com/uc?id=xyz")'
    assert row2[D.UGC_HEADER.index("Duration")] == "31s"
    assert row2[D.UGC_HEADER.index("Views at intake")] == "0"
    assert row2[D.UGC_HEADER.index("Likes at intake")] == "5"


def test_target_for_and_config():
    assert D.TARGET_FOR["ugc"] == ("ugc_sheet", "ugc_sheet")
    cfg = config.load()
    assert "ugc_sheet" in cfg["google"]["targets"]
    assert "ugc_media_folder" in cfg["google"]["targets"]
    assert cfg["google"]["targets"]["ugc_sheet"] == ""
    assert cfg["google"]["targets"]["ugc_media_folder"] == ""


def test_ugc_sheet_appends_once():
    cfg = config.load()
    cfg["google"]["targets"]["ugc_sheet"] = "UGC"
    config.save(cfg)
    g = FakeGoogle()
    rec = make_ugc_record()
    res1 = sync.write_destination(g, rec, cfg)
    assert len(g.sheets["UGC"]) == 1
    assert g.sheets["UGC"][0] == D.ugc_row(rec)
    assert res1["remote_ref"]
    # mark synced the way sync_record would, then call again: write_destination itself must no-op
    rec["export"]["destination_sync"]["status"] = "synced"
    rec["export"]["destination_sync"].update(res1)
    sync.write_destination(g, rec, cfg)
    assert len(g.sheets["UGC"]) == 1, "second write_destination call must not append again once synced"


def test_master_row_unchanged():
    rec = make_ugc_record()
    row = D.master_row(rec)
    assert len(row) == 10


def test_guidance_present():
    assert "ugc" in GUIDANCE
    assert GUIDANCE["ugc"].strip()


# ---------- Task 2: metrics/duration on the record, offline (mu + extract faked)
def _fake_unlock(url, refresh=False):
    return {"job_id": "fakejob", "resolver": "test", "metadata": {}}


def _fake_job_preexisting(url):
    return False


def _fake_contact_sheet(job_id):
    return b""


def _fake_read_info_with_metrics(job_id):
    return {"title": "t", "uploader": "thecreator", "upload_date": "20240101", "description": "cap",
            "like_count": 120, "view_count": 4000, "duration": 31}


def _fake_read_info_without_metrics(job_id):
    return {"title": "t", "uploader": "thecreator", "upload_date": "20240101", "description": "cap"}


def _fake_extract_run(rec, flags, images, documents):
    return ({"title": "", "creator": "", "short_source_summary": "s", "takeaways": [], "focused_result": "",
              "uncertainty": "", "tags": [], "visual_notes": "", "structured_data": {}, "confidence": 0.9,
              "needs_review": False, "review_reason": ""}, "test")


def test_metrics_and_duration_on_ingest():
    orig_unlock, orig_read_info, orig_contact_sheet, orig_job_preexisting = mu.unlock, mu.read_info, mu.contact_sheet, mu.job_preexisting
    orig_extract_run = extract.run
    try:
        mu.unlock = _fake_unlock
        mu.job_preexisting = _fake_job_preexisting
        mu.contact_sheet = _fake_contact_sheet
        extract.run = _fake_extract_run

        mu.read_info = _fake_read_info_with_metrics
        rec = pipeline.ingest("https://www.instagram.com/reel/ZZZZZZZ/", "ugc", "", save=False)
        assert rec["metrics"]["view_count"] == 4000
        assert rec["metrics"]["like_count"] == 120
        assert rec["metrics"]["duration_s"] == 31
        assert rec["metrics"]["captured_at"], "captured_at must be a non-empty ISO string"
        datetime.fromisoformat(rec["metrics"]["captured_at"])
        assert "[duration: 31s]" in rec["context"]["caption_or_text"]  # footer unchanged
        assert D.ugc_row(rec)[16:18] == ["4000", "120"]

        mu.read_info = _fake_read_info_without_metrics
        rec2 = pipeline.ingest("https://www.instagram.com/reel/YYYYYYY/", "ugc", "", save=False)
        assert rec2["metrics"]["view_count"] is None
        assert rec2["metrics"]["like_count"] is None
        assert rec2["metrics"]["duration_s"] is None
        assert D.ugc_row(rec2)[16:18] == ["", ""]
    finally:
        mu.unlock, mu.read_info, mu.contact_sheet, mu.job_preexisting = orig_unlock, orig_read_info, orig_contact_sheet, orig_job_preexisting
        extract.run = orig_extract_run


def _with_fakes(fn):
    """Swap in the offline media_unlocker + extract fakes for the duration of fn(), then restore."""
    orig_unlock, orig_read_info, orig_contact_sheet, orig_job_preexisting = mu.unlock, mu.read_info, mu.contact_sheet, mu.job_preexisting
    orig_extract_run = extract.run
    try:
        mu.unlock = _fake_unlock
        mu.job_preexisting = _fake_job_preexisting
        mu.contact_sheet = _fake_contact_sheet
        mu.read_info = _fake_read_info_with_metrics
        extract.run = _fake_extract_run
        fn()
    finally:
        mu.unlock, mu.read_info, mu.contact_sheet, mu.job_preexisting = orig_unlock, orig_read_info, orig_contact_sheet, orig_job_preexisting
        extract.run = orig_extract_run


# ---------- Task 3: sender on ingest, duplicate appends sender
def test_ingest_records_sender():
    def body():
        rec = pipeline.ingest("https://www.instagram.com/reel/SENDER1/", "ugc", "", save=False,
                               received_via="voice", received_from="Alice")
        assert rec["source"]["received_via"] == "voice"
        assert rec["source"]["received_from"] == "Alice"
        assert rec["senders"] == ["Alice"]

        rec2 = pipeline.ingest("https://www.instagram.com/reel/SENDER2/", "ugc", "", save=False)
        assert rec2["source"]["received_via"] == ""
        assert rec2["source"]["received_from"] == ""
        assert rec2["senders"] == []
    _with_fakes(body)


def test_duplicate_appends_sender_no_export():
    calls = {"n": 0}
    orig_sync_record = pipeline.sync.sync_record

    def fake_sync_record(rec, g=None, cfg=None, persist=True):
        calls["n"] += 1
        return rec["export"]

    def body():
        pipeline.sync.sync_record = fake_sync_record
        try:
            rec1 = pipeline.ingest("https://www.instagram.com/reel/DUPDUPDUP/", "ugc", "", save=True,
                                    received_via="voice", received_from="Alice")
            assert calls["n"] == 1
            assert rec1["senders"] == ["Alice"]
            assert not rec1.get("duplicate")

            rec2 = pipeline.ingest("https://www.instagram.com/reel/DUPDUPDUP/", "ugc", "", save=True,
                                    received_via="voice", received_from="Bob")
            assert calls["n"] == 1, "duplicate must not trigger an export"
            assert rec2["duplicate"] is True
            assert rec2["id"] == rec1["id"]
            assert rec2["senders"] == ["Alice", "Bob"]

            # same sender again: no duplicate append, still no export
            rec3 = pipeline.ingest("https://www.instagram.com/reel/DUPDUPDUP/", "ugc", "", save=True,
                                    received_via="voice", received_from="Bob")
            assert calls["n"] == 1
            assert rec3["senders"] == ["Alice", "Bob"]

            stored = store.load(rec1["id"])
            assert stored["senders"] == ["Alice", "Bob"]
        finally:
            pipeline.sync.sync_record = orig_sync_record
    _with_fakes(body)


def test_duplicate_other_destinations_still_raise():
    def body():
        pipeline.ingest("https://www.instagram.com/reel/OTHERDEST/", "personal_ig", "check this out", save=True)
        try:
            pipeline.ingest("https://www.instagram.com/reel/OTHERDEST/", "personal_ig", "check this out", save=True)
            assert False, "expected DuplicateError"
        except pipeline.DuplicateError:
            pass
    _with_fakes(body)


# ---------- Task 4: thumbnail upload
class _FakeHTTPResponse:
    def __init__(self, data: bytes):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._data


def test_drive_upload_file_multipart():
    """Google.drive_upload_file builds one hand-rolled multipart/related POST, then a permissions call.
    No real Google account needed: construct the instance bare and fake urlopen."""
    g = google_api.Google.__new__(google_api.Google)
    g.timeout = 5
    g.client, g.tok, g.account = {}, {}, ""
    g._access, g._exp = "test-token", time.time() + 3600
    g._guard = lambda *a: None  # wire shape only here; the ownership guard on upload is covered in test_ownership.py

    tmp = Path(tempfile.mkdtemp(prefix="linkintake-thumb-")) / "frame.jpg"
    tmp.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")

    captured = []

    def fake_urlopen(req, timeout=None):
        captured.append(req)
        if "uploadType=multipart" in req.full_url:
            return _FakeHTTPResponse(b'{"id": "FILE123"}')
        if req.full_url == "https://www.googleapis.com/drive/v3/files/FILE123/permissions":
            return _FakeHTTPResponse(b'{"id": "perm1"}')
        raise AssertionError(f"unexpected url {req.full_url}")

    orig_urlopen = google_api.urllib.request.urlopen
    google_api.urllib.request.urlopen = fake_urlopen
    try:
        file_id, url = g.drive_upload_file(tmp, "thumb.jpg", "FOLDER123")
    finally:
        google_api.urllib.request.urlopen = orig_urlopen

    assert file_id == "FILE123"
    assert url == "https://drive.google.com/uc?id=FILE123"
    assert len(captured) == 2

    upload_req, perm_req = captured
    assert "uploadType=multipart" in upload_req.full_url and "fields=id" in upload_req.full_url
    ctype = upload_req.get_header("Content-type")
    assert ctype.startswith("multipart/related; boundary=")
    boundary = ctype.split("boundary=", 1)[1]
    body = upload_req.data
    assert boundary.encode() in body, "body must contain the declared boundary"
    assert b'"parents": ["FOLDER123"]' in body
    assert b"Content-Type: image/jpeg" in body

    assert perm_req.full_url == "https://www.googleapis.com/drive/v3/files/FILE123/permissions"
    assert json.loads(perm_req.data) == {"role": "reader", "type": "anyone"}


def _ugc_cfg(folder="MEDIA_FOLDER"):
    cfg = config.load()
    cfg["google"]["targets"]["ugc_sheet"] = "UGC"
    cfg["google"]["targets"]["ugc_media_folder"] = folder
    return cfg


def _write_frame(name: str) -> Path:
    p = config.STATE_DIR / "test-frames" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"fake-jpeg-bytes")
    return p


def test_thumbnail_uploaded_for_ugc_record_with_frame():
    cfg = _ugc_cfg()
    g = FakeGoogle()
    rec = make_ugc_record()
    frame = _write_frame("frame-first.jpg")
    rec["artifacts"]["first_frame_path"] = str(frame)

    sync.write_destination(g, rec, cfg)

    assert g.calls[0] == ("drive_upload_file", str(frame), f"{rec['id']}.jpg", "MEDIA_FOLDER", "image/jpeg")
    assert rec["artifacts"]["thumbnail_url"] == "https://drive.google.com/uc?id=DRVID"
    row = D.ugc_row(rec)
    assert row[D.UGC_HEADER.index("Thumbnail")].startswith('=IMAGE("https://drive.google.com/uc?id=')
    assert g.sheets["UGC"][-1] == row  # the exported row already carries the thumbnail


def test_thumbnail_falls_back_to_contact_sheet():
    cfg = _ugc_cfg()
    g = FakeGoogle()
    rec = make_ugc_record()
    sheet = _write_frame("contact-sheet.jpg")
    rec["artifacts"]["contact_sheet"] = str(sheet)  # no first_frame_path this time

    sync.write_destination(g, rec, cfg)

    assert g.calls[0][1] == str(sheet)
    assert rec["artifacts"]["thumbnail_url"]


def test_thumbnail_upload_failure_lands_in_errors_row_still_exported():
    cfg = _ugc_cfg()
    g = FakeGoogle(fail_upload=True)
    rec = make_ugc_record()
    frame = _write_frame("frame-fail.jpg")
    rec["artifacts"]["first_frame_path"] = str(frame)

    res = sync.write_destination(g, rec, cfg)

    assert not rec["artifacts"].get("thumbnail_url")
    assert any("thumbnail" in e for e in rec["errors"]), rec["errors"]
    assert g.sheets["UGC"][-1] == D.ugc_row(rec)  # export still happened, blank Thumbnail cell
    assert res["remote_ref"]


def test_no_upload_attempted_without_media_folder_or_frame():
    g = FakeGoogle()
    cfg = _ugc_cfg(folder="")  # not configured
    rec = make_ugc_record()
    rec["artifacts"]["first_frame_path"] = str(_write_frame("frame-unused.jpg"))
    sync.write_destination(g, rec, cfg)
    assert g.calls == [("sheet_append", "UGC")], "no folder configured -> no upload attempt"

    g2 = FakeGoogle()
    cfg2 = _ugc_cfg()
    rec2 = make_ugc_record()  # no frame, no contact sheet on disk
    sync.write_destination(g2, rec2, cfg2)
    assert g2.calls == [("sheet_append", "UGC")], "no local image -> no upload attempt"


def test_visual_capture_enabled_for_ugc():
    from linkintake.depth import infer
    assert infer("social_media", "ugc", "")["visual"], "ugc must always fetch a contact sheet/frames for the thumbnail"


# ---------- Review fix 1: doctor backfills records orphaned by canonicalize changes
def test_doctor_recanonicalizes_legacy_records():
    legacy_url = "https://www.instagram.com/reels/LEGACYBACKFILL/"
    rec = make_ugc_record()
    rec["source"]["original_url"] = legacy_url
    rec["source"]["canonical_url"] = legacy_url  # the stale pre-fix canonical form (/reels/, kept verbatim)
    legacy_key = dedupe_key(legacy_url, "ugc", "")
    rec["dedupe_key"] = legacy_key
    store.save(rec)

    new_canonical = canonicalize(legacy_url)
    assert new_canonical != legacy_url, "fixture must actually be stale for this test to mean anything"
    new_key = dedupe_key(new_canonical, "ugc", "")
    assert "/reel/" in new_canonical and "/reels/" not in new_canonical

    assert store.find_exact(new_key) is None, "not migrated yet: old key still the only one on record"

    n = cli._recanonicalize_records()
    assert n >= 1

    found = store.find_exact(new_key)
    assert found is not None and found["id"] == rec["id"]
    stored = store.load(rec["id"])
    assert stored["source"]["canonical_url"] == new_canonical
    assert stored["dedupe_key"] == new_key

    # idempotent: a second pass leaves the now-fixed record alone
    cli._recanonicalize_records()
    stored2 = store.load(rec["id"])
    assert stored2["source"]["canonical_url"] == new_canonical


# ---------- Review fix 2: google_setup must not skip config.save when the ugc media folder create fails
class _FakeSetupGoogle:
    account = identity = required = "person@example.com"

    def verify_identity(self):  # the real guard is covered by tests/test_ownership.py
        return self.identity

    def drive_meta(self, file_id):  # every PRESET target is personal-owned, so setup keeps it
        return {"id": file_id, "owners": [{"emailAddress": self.required}]}

    def doc_get(self, doc_id):
        return {"tabs": [{"tabProperties": {"tabId": "TAB1", "title": D.WISHLIST_TAB_TITLE}}]}

    def sheet_create(self, title, parent, header):
        return "UGCSHEETID"

    def drive_create(self, name, mime, parent):
        raise GoogleError(500, "drive is down")


def test_google_setup_survives_media_folder_failure():
    cfg = config.load()
    t = cfg["google"].setdefault("targets", {})
    for k in ("master_doc", "wishlist_doc", "college_folder", "supplement_doc", "media_folder",
              "design_doc", "personal_ig_doc", "scholarships_folder", "scholarship_sheet"):
        t[k] = "PRESET"
    t["ugc_sheet"] = ""
    t["ugc_media_folder"] = ""
    config.save(cfg)

    fake = _FakeSetupGoogle()
    orig_google, orig_ask = google_setup.Google, google_setup._ask
    google_setup.Google = lambda: fake
    google_setup._ask = lambda prompt, default="": default
    try:
        result = google_setup.run()
    finally:
        google_setup.Google, google_setup._ask = orig_google, orig_ask

    assert result["ugc_sheet"] == "UGCSHEETID", "ugc_sheet must be created and kept despite the later failure"
    assert result["ugc_media_folder"] == "", "media folder creation failed, as intended by the fake"
    saved = config.load()
    assert saved["google"]["targets"]["ugc_sheet"] == "UGCSHEETID", "config.save must still run after the guarded failure"


# ---------- Review fix 3: save_record mirrors ingest's ugc duplicate-append path
def test_save_record_duplicate_appends_sender_no_export():
    calls = {"n": 0}
    orig_sync_record = pipeline.sync.sync_record

    def fake_sync_record(rec, g=None, cfg=None, persist=True):
        calls["n"] += 1
        return rec["export"]

    def body():
        pipeline.sync.sync_record = fake_sync_record
        try:
            first = pipeline.ingest("https://www.instagram.com/reel/SAVEDUP1/", "ugc", "", save=True,
                                     received_via="voice", received_from="Alice")
            assert calls["n"] == 1
            assert not first.get("duplicate")

            pending = pipeline.ingest("https://www.instagram.com/reel/SAVEDUP1/", "ugc", "", save=False,
                                       received_via="voice", received_from="Carol")
            assert pending["exact_duplicate"] == first["id"]
            assert not pending.get("saved_at")

            result = pipeline.save_record(pending["id"])
            assert calls["n"] == 1, "duplicate save_record must not trigger an export"
            assert result.get("duplicate") is True
            assert result["id"] == first["id"]
            assert result["senders"] == ["Alice", "Carol"]

            stored = store.load(first["id"])
            assert stored["senders"] == ["Alice", "Carol"]
        finally:
            pipeline.sync.sync_record = orig_sync_record
    _with_fakes(body)


# ---------- Review fix 4: save_record's ugc duplicate branch cleans up the duplicate's own pending file
def test_save_record_duplicate_cleans_up_pending():
    calls = []
    orig_cleanup_record = pipeline.cleanup.cleanup_record

    def fake_cleanup_record(rec):
        calls.append(rec["id"])
        return {"skipped": True}

    def body():
        pipeline.cleanup.cleanup_record = fake_cleanup_record
        try:
            first = pipeline.ingest("https://www.instagram.com/reel/CLEANUPDUP1/", "ugc", "", save=True)
            pending = pipeline.ingest("https://www.instagram.com/reel/CLEANUPDUP1/", "ugc", "", save=False)
            pending_path = store.PENDING / f"{pending['id']}.json"
            assert pending_path.exists(), "fixture must actually be pending for this test to mean anything"

            pipeline.save_record(pending["id"])

            assert not pending_path.exists(), "duplicate's own pending file must be unlinked"
            assert pending["id"] in calls, "cleanup.cleanup_record must be called with the duplicate rec"
        finally:
            pipeline.cleanup.cleanup_record = orig_cleanup_record
    _with_fakes(body)


# ---------- Review fix 5: doctor backfill tolerates malformed/legacy record files
def test_doctor_backfill_skips_malformed_records():
    legacy_url = "https://www.instagram.com/reels/LEGACYBACKFILL2/"
    rec = make_ugc_record()
    rec["source"]["original_url"] = legacy_url
    rec["source"]["canonical_url"] = legacy_url
    rec["dedupe_key"] = dedupe_key(legacy_url, "ugc", "")
    store.save(rec)

    (store.RECORDS / "malformed-missing-fields.json").write_text(json.dumps({"id": "x"}))
    (store.RECORDS / "malformed-not-json.json").write_text("not json{{{")

    new_canonical = canonicalize(legacy_url)
    n = cli._recanonicalize_records()  # must not raise despite the two bad files above
    assert n >= 1

    stored = store.load(rec["id"])
    assert stored["source"]["canonical_url"] == new_canonical


# ---------- Review fix 6: _merge_ugc_duplicate raises DuplicateError when the index outlives the record file
def test_merge_ugc_duplicate_missing_file_raises_duplicate_error():
    def body():
        first = pipeline.ingest("https://www.instagram.com/reel/GONEFILE1/", "ugc", "", save=True)
        rec_path = store.RECORDS / f"{first['id']}.json"
        assert rec_path.exists()
        rec_path.unlink()  # index line still references it; file gone (index is append-only)

        try:
            pipeline._merge_ugc_duplicate(first["id"], "Someone")
            assert False, "expected DuplicateError"
        except pipeline.DuplicateError as exc:
            assert first["id"] in str(exc)
    _with_fakes(body)


def main():
    test_destination_and_aliases()
    test_new_record_ugc_fields()
    test_ugc_row_shape()
    test_target_for_and_config()
    test_ugc_sheet_appends_once()
    test_master_row_unchanged()
    test_guidance_present()
    test_metrics_and_duration_on_ingest()
    test_ingest_records_sender()
    test_duplicate_appends_sender_no_export()
    test_duplicate_other_destinations_still_raise()
    test_drive_upload_file_multipart()
    test_thumbnail_uploaded_for_ugc_record_with_frame()
    test_thumbnail_falls_back_to_contact_sheet()
    test_thumbnail_upload_failure_lands_in_errors_row_still_exported()
    test_no_upload_attempted_without_media_folder_or_frame()
    test_visual_capture_enabled_for_ugc()
    test_doctor_recanonicalizes_legacy_records()
    test_google_setup_survives_media_folder_failure()
    test_save_record_duplicate_appends_sender_no_export()
    test_save_record_duplicate_cleans_up_pending()
    test_doctor_backfill_skips_malformed_records()
    test_merge_ugc_duplicate_missing_file_raises_duplicate_error()
    print("test_ugc: ok (23 scenarios)")


if __name__ == "__main__":
    main()
