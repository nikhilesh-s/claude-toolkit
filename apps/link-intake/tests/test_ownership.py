"""Google account/ownership invariant with the REAL Google client over a fake HTTP layer (no network).
Run: uv run python tests/test_ownership.py"""
import builtins
import contextlib
import io
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

os.environ["LINKINTAKE_STATE_DIR"] = tempfile.mkdtemp(prefix="linkintake-own-")

from linkintake import config, google_api, google_auth, google_setup, ownership, store, sync  # noqa: E402
from linkintake.google_api import DOC_MIME, FOLDER_MIME, SHEET_MIME, Google, OwnershipError  # noqa: E402
from linkintake.records import new_record  # noqa: E402

ME = "niksuravarjjala@gmail.com"
SCHOOL = "student0002@examplecollege.edu"


class FakeHTTP:
    """Just enough of Drive/Docs/Sheets/userinfo. Every non-GET is recorded; the invariant is that foreign ones never are."""

    def __init__(self, identity=ME):
        self.identity = identity
        self.files = {}
        self.writes = []
        self.queries = []

    def add(self, fid, name, mime, owner, parents=()):
        self.files[fid] = {"id": fid, "name": name, "mimeType": mime, "owners": [{"emailAddress": owner}] if owner else [],
                           "parents": list(parents), "modifiedTime": "2026-09-01T00:00:00Z"}

    def __call__(self, req, timeout=None):
        url, method = req.full_url, req.get_method()
        base, _, qs = url.partition("?")
        if method != "GET":
            self.writes.append((method, base, json.loads(req.data) if req.data else None))
            if base == google_api.DRIVE_FILES:
                return _resp({"id": "NEW1"})
            return _resp({"replies": []})
        if base == google_api.USERINFO:
            return _resp({"email": self.identity})
        if base == google_api.DRIVE_FILES:
            q = urllib.parse.parse_qs(qs)["q"][0]
            self.queries.append(q)
            return _resp({"files": list(self.files.values())})  # server ignores the owner clause: the client must still filter
        if base.startswith(google_api.DRIVE_FILES + "/"):
            fid = base.rsplit("/", 1)[-1]
            if fid not in self.files:
                raise urllib.error.HTTPError(url, 404, "nf", {}, io.BytesIO(b'{"error":"notFound"}'))
            return _resp(self.files[fid])
        if "docs.googleapis.com" in base:
            return _resp({"title": "d", "tabs": [{"tabProperties": {"tabId": "t.staging", "title": "Intake Staging"},
                                                  "documentTab": {"body": {"content": []}}}]})
        if "sheets.googleapis.com" in base:
            return _resp({"sheets": [{"properties": {"sheetId": 0}}], "values": []})
        raise AssertionError(f"unexpected GET {url}")


class _resp(io.BytesIO):
    def __init__(self, obj):
        super().__init__(json.dumps(obj).encode())

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def install(fake):
    urllib.request.urlopen = fake  # google_api calls urllib.request.urlopen at call time


def world(identity=ME):
    f = FakeHTTP(identity)
    f.add("MASTER", "Intake Master", DOC_MIME, ME)
    f.add("WISH", "Personal -- College Wishlist", DOC_MIME, ME)
    f.add("SHEET", "Scholarship Tracker", SHEET_MIME, ME)
    f.add("SUPP", "Supplement Inspiration Bank", DOC_MIME, ME)
    f.add("DESIGN", "Design Inspiration Bank", DOC_MIME, ME)
    f.add("IG", "Personal Instagram Inspiration", DOC_MIME, ME)
    for fid in ("F1", "F2", "F3"):
        f.add(fid, fid, FOLDER_MIME, ME)
    # the bug class: a college-owned file SHARED WITH and EDITABLE BY the personal account
    f.add("SCHOOLDOC", "Intake Master", DOC_MIME, SCHOOL)
    f.add("SCHOOLFOLDER", "College Applications", FOLDER_MIME, SCHOOL)
    f.add("SHAREDDRIVE", "Intake Inbox", DOC_MIME, "")  # shared drive: no owner at all
    install(f)
    return f


def setup_state(targets=None):
    google_api.GOOGLE_DIR.mkdir(parents=True, exist_ok=True)
    google_api.CLIENT_PATH.write_text(json.dumps({"client_id": "x.apps.googleusercontent.com", "client_secret": "s"}))
    google_api.TOKEN_PATH.write_text(json.dumps({"email": ME, "refresh_token": "r", "token": "t", "expires_at": time.time() + 3600}))
    cfg = config.load()
    cfg["google"]["targets"] = targets or {"master_doc": "MASTER", "wishlist_doc": "WISH", "wishlist_tab_id": "t.staging", "college_folder": "F1",
                                           "supplement_doc": "SUPP", "media_folder": "F2", "design_doc": "DESIGN", "personal_ig_doc": "IG",
                                           "scholarships_folder": "F3", "scholarship_sheet": "SHEET"}
    config.save(cfg)


def expect_blocked(fn, fake, *needles):
    before = len(fake.writes)
    try:
        fn()
    except OwnershipError as exc:
        for n in needles:
            assert n in str(exc), (n, str(exc))
    else:
        raise AssertionError("write was not blocked")
    assert len(fake.writes) == before, fake.writes[before:]


def main():
    setup_state()
    assert google_api.required_account() == ME

    # 1. .edu identity refused (token.json may say otherwise: userinfo wins), and google-auth refuses it outright
    f = world(identity=SCHOOL)
    g = Google()
    assert g.account == ME  # token.json claims personal...
    expect_blocked(lambda: g.doc_append_text("MASTER", "x"), f, SCHOOL, "not the required account")
    for bad in (SCHOOL, "someone.else@gmail.com", ""):
        try:
            google_auth.check_account(bad, ME)
            raise AssertionError(f"accepted {bad}")
        except SystemExit:
            pass
    try:
        google_auth.check_account(SCHOOL, SCHOOL)  # even if someone sets required_account to a .edu
        raise AssertionError(".edu accepted as required")
    except SystemExit:
        pass
    google_auth.check_account(ME, ME)

    # 2. personal token + personal-owned file -> allowed
    f = world()
    g = Google()
    g.doc_append_text("MASTER", "row")
    g.sheet_append("SHEET", [["a"]])
    assert [w[1] for w in f.writes] == ["https://docs.googleapis.com/v1/documents/MASTER:batchUpdate",
                                        "https://sheets.googleapis.com/v4/spreadsheets/SHEET/values/A1:append"]
    assert g.identity == ME

    # 3. personal token + editable college-owned file -> every write path refused, zero writes
    f = world()
    g = Google()
    msg = ("Configured target Intake Master is owned by", SCHOOL, f"instead of required account {ME}", "Google write blocked")
    expect_blocked(lambda: g.doc_append_text("SCHOOLDOC", "x"), f, *msg)
    expect_blocked(lambda: g.doc_batch("SCHOOLDOC", [{"insertText": {}}]), f, *msg)
    expect_blocked(lambda: g.doc_append_table_row("SCHOOLDOC", ["a"], ["h"]), f, *msg)
    expect_blocked(lambda: g.doc_add_tab("SCHOOLDOC", "Intake Staging"), f, *msg)
    expect_blocked(lambda: g.sheet_append("SCHOOLDOC", [["x"]]), f, SCHOOL)
    expect_blocked(lambda: g.sheet_update_row("SCHOOLDOC", 2, ["x"]), f, SCHOOL)
    expect_blocked(lambda: g.sheet_delete_row("SCHOOLDOC", 2), f, SCHOOL)
    expect_blocked(lambda: g.drive_create("x", DOC_MIME, "SCHOOLFOLDER"), f, SCHOOL)  # creating inside a college folder
    expect_blocked(lambda: g.sheet_create("x", "SCHOOLFOLDER", ["h"]), f, SCHOOL)
    expect_blocked(lambda: g.doc_append_text("SHAREDDRIVE", "x"), f, "shared drive")
    # 6. write path cannot bypass the guard: raw request() to any other mutating endpoint is refused
    expect_blocked(lambda: g.request("PATCH", "https://www.googleapis.com/drive/v3/files/SCHOOLDOC", body={"name": "x"}), f, "unrecognized")
    expect_blocked(lambda: g.request("POST", "https://www.googleapis.com/drive/v3/files/SCHOOLDOC/copy", body={}), f, "unrecognized")
    expect_blocked(lambda: g.request("DELETE", "https://www.googleapis.com/drive/v3/files/SCHOOLDOC"), f, "unrecognized")
    expect_blocked(lambda: g.request("POST", "https://docs.googleapis.com/v1/documents/SCHOOLDOC:batchUpdate", body={"requests": []}), f, SCHOOL)
    assert f.writes == []
    # root-level create lands in the verified identity's own Drive -> allowed
    g.drive_create("Intake Master", DOC_MIME)
    assert len(f.writes) == 1

    # 4. google-setup never offers a foreign-owned candidate, and shows the owner of each
    f = world()
    g = Google()
    g.verify_identity()
    found = g.drive_find_by_name("Intake", DOC_MIME, contains=True)
    assert f"'{ME}' in owners" in f.queries[-1]
    assert {x["id"] for x in found} >= {"MASTER"} and not {"SCHOOLDOC", "SHAREDDRIVE"} & {x["id"] for x in found}
    answers = iter(["1"])
    builtins_input = builtins.input
    builtins.input = lambda *_: next(answers)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            items = [f.files["SCHOOLDOC"], f.files["SHAREDDRIVE"], f.files["MASTER"]]  # even if a search leaks them
            chosen = google_setup._choose("MASTER", items, g)
        assert chosen["id"] == "MASTER", chosen
        assert SCHOOL not in out.getvalue() and "Intake Inbox" not in out.getvalue() and f"owner {ME}" in out.getvalue(), out.getvalue()

        # 5. pasted foreign-owned id refused (then skip)
        answers = iter(["id:SCHOOLDOC", "id:SHAREDDRIVE", "s"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert google_setup._choose("MASTER", [], g) is None
        assert out.getvalue().count("refused") == 2 and SCHOOL in out.getvalue()
        answers = iter(["id:MASTER"])
        with contextlib.redirect_stdout(io.StringIO()):
            assert google_setup._choose("MASTER", [], g)["id"] == "MASTER"
    finally:
        builtins.input = builtins_input

    # 7. google-audit identifies a foreign-owned active target (and writes nothing)
    setup_state()
    cfg = config.load()
    cfg["google"]["targets"]["master_doc"] = "SCHOOLDOC"
    cfg["google"]["docs"] = {"inbox": "SHAREDDRIVE"}  # legacy G-Switch key
    config.save(cfg)
    f = world()
    rep = ownership.audit()
    by = {r["config_key"]: r for r in rep["targets"]}
    assert by["master_doc"]["status"] == ownership.FOREIGN and by["master_doc"]["owners"] == [SCHOOL] and not by["master_doc"]["owned_by_expected_account"]
    assert by["wishlist_doc"]["status"] == ownership.PERSONAL and rep["wishlist_tab"]["status"] == ownership.PERSONAL
    assert rep["migration_needed"] and rep["active_foreign_targets"] == ["master_doc"] and rep["summary"]["foreign_owned"] == 1
    assert rep["legacy_config"][0]["status"] == ownership.FOREIGN and rep["legacy_config"][0]["active"] is False
    assert f.writes == []
    assert "Foreign-owned targets: 1" in ownership.text_report(rep)
    # wrong signed-in account -> every target WRONG_ACCOUNT
    world(identity=SCHOOL)
    rep = ownership.audit(legacy=False, scan_foreign=False)
    assert not rep["identity_ok"] and {r["status"] for r in rep["targets"]} == {ownership.WRONG_ACCOUNT}

    # 8. sync: foreign-owned configured target -> local save stands, export BLOCKED with the owner named, nothing written
    setup_state()
    cfg = config.load()
    cfg["google"]["targets"].update({"master_doc": "SCHOOLDOC", "personal_ig_doc": "SCHOOLDOC"})
    config.save(cfg)
    f = world()
    rec = new_record(original_url="https://example.com/a", canonical_url="https://example.com/a", source_class="web_page",
                     platform="example.com", destination="personal_ig", instruction="framing")
    rec.update(status="ready", saved_at=rec["created_at"])
    rec["extraction"]["focused_result"] = "x"
    store.save(rec)
    ex = sync.sync_record(rec)
    assert ex["status"] == "blocked" and ex["master_sync"]["status"] == "blocked" and ex["destination_sync"]["status"] == "blocked", ex
    assert SCHOOL in ex["last_error"] and "Google write blocked" in ex["last_error"]
    assert f.writes == [] and store.load(rec["id"])["saved_at"]
    assert "BLOCKED" in sync.summary_line(ex) and rec["id"] in [r["id"] for r in sync.pending_records()]  # retried once rehomed
    # wrong account: blocked before any read or write
    f = world(identity=SCHOOL)
    ex = sync.sync_record(store.load(rec["id"]))
    assert ex["status"] == "blocked" and "not the required account" in ex["last_error"] and f.writes == []
    # once the target is personal-owned the same record syncs
    setup_state()
    f = world()
    ex = sync.sync_record(store.load(rec["id"]))
    assert ex["destination_sync"]["status"] == "synced", ex
    assert all("SCHOOL" not in w[1] for w in f.writes)
    print("test_ownership: ok (identity, owner guard on every write path, setup filter, pasted id, audit, sync blocked)")


if __name__ == "__main__":
    main()
