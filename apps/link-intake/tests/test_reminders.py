"""Weekly Reminder sweep with fixtures: fake Reminders (osascript), fake adapter + Claude, REAL candidate inference,
pipeline, store, entities and ledger. No network, no Google, no real Reminders. Run: uv run python tests/test_reminders.py"""
import json
import os
import plistlib
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

os.environ["LINKINTAKE_STATE_DIR"] = tempfile.mkdtemp(prefix="linkintake-rem-")
os.environ["LINKINTAKE_LAUNCHAGENTS_DIR"] = tempfile.mkdtemp(prefix="linkintake-agents-")
os.environ.pop("LINKINTAKE_SCHEDULED", None)

from linkintake import bulk, entities, extract, pipeline, reminders as R, schedule, store, sync  # noqa: E402
from linkintake.records import new_record  # noqa: E402

SEP, RS = bulk.SEP, bulk.RS


class FakeReminders:
    def __init__(self):
        self.items = {}
        self.calls = []  # (script name, args)

    def add(self, rid, lst, title, body):
        self.items[rid] = {"id": f"x-apple-reminder://{rid}", "list": lst, "title": title, "body": body, "completed": False}

    def __call__(self, script, timeout=600, args=()):
        name = {bulk.REMINDERS_SCRIPT: "discover", R.READ_BY_ID_SCRIPT: "read_by_id", R.COMPLETE_SCRIPT: "complete"}.get(script)
        assert name, "unexpected AppleScript (Notes must never be read by the Reminder sweep):\n" + script[:200]
        self.calls.append((name, tuple(args)))
        if name == "discover":
            return "".join(SEP.join([r["list"], r["title"], r["body"], str(r["completed"]).lower(), "Monday, September 21, 2026 at 9:00:00 AM",
                                     r["id"], "Monday, September 21, 2026 at 9:00:00 AM", ""]) + RS for r in self.items.values()) + "\n"
        by_id = {r["id"]: r for r in self.items.values()}
        out = ""
        for a in args:
            r = by_id.get(a)
            if name == "complete" and r:
                r["completed"] = True
            out += (SEP.join([a, r["title"], r["body"], str(r["completed"]).lower()]) if r else SEP.join([a, "", "", "missing"])) + RS
        return out + "\n"


FAKE = FakeReminders()
bulk._osa = FAKE
NOTIFICATIONS = []
R.send_notification = lambda title, msg: NOTIFICATIONS.append((title, msg))
QUOTA = {"on": False}
SYNCED = []
_real_sync = sync.sync_record
sync.sync_record = lambda rec, **kw: (SYNCED.append(rec["source"]["original_url"]), _real_sync(rec, **kw))[1]


def fake_adapter(rec, flags, images, documents, refresh):
    if "adapterfail" in rec["source"]["original_url"]:
        raise RuntimeError("HTTP 404 page gone")
    rec["context"]["caption_or_text"] = "fixture page text"


def fake_extract(rec, flags, images, documents):
    url, dest = rec["source"]["original_url"], rec["intent"]["destination"]
    if QUOTA["on"] or "quota" in url:
        raise RuntimeError("claude CLI [/Users/x/.claude-nebula]: Claude AI usage limit reached|1790000000")
    sd = {}
    if dest == "wishlist":
        sd = {"product_item": "Desk Lamp", "brand": "Acme", "model": "Glow L1", "identifier": "B0LAMP0001"} if "lamp" in url else \
             {"product_item": "Thing " + url[-6:], "brand": "Brand" + url[-4:], "model": "M" + url[-4:]}
    if dest == "scholarships":
        sd = {"scholarship": "Test Scholars", "organization": "Test Org", "cycle_year": "2027", "deadline": "2027-01-01"}
    out = {"title": "Fixture " + url[-12:], "creator": "", "short_source_summary": "summary", "takeaways": ["a", "b"],
           "focused_result": "" if "empty" in url else "focused answer", "uncertainty": "", "tags": ["x"], "visual_notes": "",
           "structured_data": sd, "confidence": 0.9, "needs_review": False, "review_reason": ""}
    return extract._normalize(out), "claude"


pipeline._run_adapter = fake_adapter
extract.run = fake_extract


def urls_in_entities():
    return {u for k in ("wishlist", "scholarship") for e in entities.load(k) for u in e["source_urls"]}


def by_url(rep):
    return {i["url"]: i for i in rep["items"]}


def main():
    # 1. every AppleScript the sweep uses is read-only, except COMPLETE_SCRIPT (clear only)
    mutating = re.compile(r"\bset\s+(?!\w+\s+to\b)|\b(delete|make new|move|remove)\b", re.I)
    for s in (bulk.REMINDERS_SCRIPT, R.READ_BY_ID_SCRIPT):
        assert not mutating.search(s), mutating.search(s)
    assert mutating.search(R.COMPLETE_SCRIPT) and "delete" not in R.COMPLETE_SCRIPT.lower()

    FAKE.add("WISH", "00 Inbox", "want this lamp for my dorm", "https://shop.example.com/lamp-a")
    FAKE.add("FAIL", "00 Inbox", "want this desk for my dorm", "https://shop.example.com/adapterfail-desk")  # fails first; sweep goes on
    FAKE.add("WISH2", "00 Inbox", "need this lamp for my desk setup", "https://other.example.com/acme-lamp")  # same product -> merge
    FAKE.add("SCHOL", "00 Inbox", "scholarship deadline apply before january", "https://scholars.example.org/apply")
    FAKE.add("VIDEO", "07 Personal + Home", "video inspo love the transitions in this reel", "https://www.instagram.com/reel/VIDEO1/")
    FAKE.add("IG2", "07 Personal + Home", "want this camera for my dorm", "https://www.instagram.com/reel/VIDEO1/")  # same URL, other intent
    FAKE.add("VAGUE", "00 Inbox", "cool", "https://example.com/cool-thing")
    FAKE.add("DESK", "00 Inbox", "desk stuff", "https://www.instagram.com/reel/DESK1/")
    FAKE.add("TOOL", "00 Inbox", "check the supabase dashboard", "https://github.com/acme/tool")
    FAKE.add("EXIST", "00 Inbox", "want this mug for my dorm", "https://shop.example.com/mug")
    FAKE.add("TWO", "00 Inbox", "misc", "want this lamp for my dorm\nhttps://shop.example.com/lamp-b\nlook at this\nhttps://example.com/cool2")
    FAKE.add("NOURL", "00 Inbox", "buy milk", "")
    old = new_record(original_url="https://shop.example.com/mug", canonical_url="https://shop.example.com/mug", source_class="web_page",
                     platform="shop", destination="wishlist", instruction="want this mug for my dorm")
    old.update(status="ready", saved_at=old["created_at"])
    store.save(old)

    # dry runs write nothing
    pv = R.preview()
    assert pv["dry_run"] and pv["new_candidates"] == 12 and not R.LEDGER.exists() and not R.STATE.exists()
    assert {c[0] for c in FAKE.calls} == {"discover"}

    rep = R.sweep()
    u = by_url(rep)
    k = rep["counts"]
    # 5-10: routing
    assert u["https://shop.example.com/lamp-a"]["outcome"] == "AUTO_INGESTED" and u["https://shop.example.com/lamp-a"]["destination"] == "wishlist"
    assert u["https://scholars.example.org/apply"]["outcome"] == "AUTO_INGESTED" and u["https://scholars.example.org/apply"]["destination"] == "scholarships"
    vid = [i for i in rep["items"] if i["url"] == "https://www.instagram.com/reel/VIDEO1/"]
    assert {i["destination"] for i in vid} == {"personal_ig", "wishlist"} and all(i["outcome"] == "AUTO_INGESTED" for i in vid)  # 4 + 7
    assert u["https://example.com/cool-thing"]["outcome"] == "REVIEW" and u["https://www.instagram.com/reel/DESK1/"]["outcome"] == "REVIEW"  # 8
    assert u["https://github.com/acme/tool"]["outcome"] == "SKIPPED_UNSUPPORTED" and "https://github.com/acme/tool" not in {e["canonical_url"] for e in store.index()}  # 9: never auto-Inbox
    assert not any(i["destination"] == "inbox" and i["outcome"] == "AUTO_INGESTED" for i in rep["items"])
    assert u["https://shop.example.com/mug"]["outcome"] == "ALREADY_INGESTED" and u["https://shop.example.com/mug"]["record_id"] == old["id"]  # 10
    # 11: semantic Wishlist duplicate merged into one entity carrying both sources
    lamp = [e for e in entities.load("wishlist") if "https://shop.example.com/lamp-a" in e["source_urls"]]
    assert len(lamp) == 1 and "https://other.example.com/acme-lamp" in lamp[0]["source_urls"], entities.load("wishlist")
    assert u["https://other.example.com/acme-lamp"]["resolution"] == "merged" and k["wishlist_merged"] >= 1
    # 13: the adapter failure is FAILED and did not stop anything after it
    assert u["https://shop.example.com/adapterfail-desk"]["outcome"] == "FAILED" and "404" in u["https://shop.example.com/adapterfail-desk"]["reason"]
    assert "https://shop.example.com/adapterfail-desk" not in {e["canonical_url"] for e in store.index()}  # no casualty record
    # provenance: the stable Reminder id rides on the record
    rec = store.load(u["https://shop.example.com/lamp-a"]["record_id"])
    assert rec["batch"]["reminder_ids"] == ["x-apple-reminder://WISH"] and rec["batch"]["source_origin"] == "reminders"
    # counts + reconciliation + report files + one notification
    assert k["urls_discovered"] == 12 and k["new_candidates"] == 12 and k["failed"] == 1 and k["needs_review"] == 3 and k["skipped_unsupported"] == 1
    rc = rep["reconciliation"]["summary"]
    assert rc["reminders_found"] == 11 and rc["needs_review"] == 3 and rc["failed"] == 1 and rc["unsupported"] == 1  # NOURL has no URL
    elig = {r["reminder_id"] for r in rep["reconciliation"]["reminders"] if r["eligible_to_clear"]}
    assert elig == {f"x-apple-reminder://{x}" for x in ("WISH", "WISH2", "SCHOL", "VIDEO", "IG2", "EXIST")}, elig
    two = next(r for r in rep["reconciliation"]["reminders"] if r["reminder_id"].endswith("TWO"))
    assert not two["eligible_to_clear"] and {l["outcome"] for l in two["links"]} == {"AUTO_INGESTED", "REVIEW"}
    assert "11 URL reminders found." in rep["reconciliation"]["confirmation"] and "6 reminders are fully handled and eligible to clear." in rep["reconciliation"]["confirmation"]
    d = R.SWEEP_DIR / rep["run_id"]
    assert (d / "report.json").exists() and "Needs attention" in (d / "report.md").read_text() and "Next action" in (d / "report.md").read_text()
    assert len(NOTIFICATIONS) == 1 and "12 links found" in NOTIFICATIONS[0][1]
    assert not any(c[0] == "complete" for c in FAKE.calls)  # a sweep never modifies a reminder
    n_records = len(store.index())

    # 14: the report survives a restart (read back from disk, not memory)
    again = R.load_report()
    assert again["run_id"] == rep["run_id"] and again["counts"] == rep["counts"] and len(again["attention"]) == 4

    # 2: unchanged reminders are ignored next week (case/punctuation/spacing is not meaningful)
    FAKE.items["VIDEO"]["title"] = "  Video inspo — love the TRANSITIONS in this reel! "
    rep2 = R.sweep()
    assert rep2["counts"]["new_candidates"] == 0 and rep2["counts"]["previously_accounted"] == 12 and len(store.index()) == n_records
    # 3: a meaningful wording change is reconsidered as a new candidate
    FAKE.items["VAGUE"]["title"] = "want this for my dorm room"
    rep3 = R.sweep()
    assert rep3["counts"]["new_candidates"] == 1 and by_url(rep3)["https://example.com/cool-thing"]["destination"] == "wishlist"
    assert by_url(rep3)["https://example.com/cool-thing"]["outcome"] == "AUTO_INGESTED"
    n_records = len(store.index())

    # 12: Claude quota -> DEFERRED, the rest of the sweep continues, no record/entity/Google row, candidate kept
    QUOTA["on"] = True
    FAKE.add("Q1", "00 Inbox", "want this chair for my dorm", "https://shop.example.com/chair")
    FAKE.add("Q2", "00 Inbox", "scholarship grant opportunity apply", "https://grants.example.org/g2")
    FAKE.add("Q3", "00 Inbox", "check the vercel dashboard", "https://vercel.com/acme")  # unaffected by quota
    SYNCED.clear()
    rep4 = R.sweep()
    q = by_url(rep4)
    assert q["https://shop.example.com/chair"]["outcome"] == "DEFERRED" and "usage limit" in q["https://shop.example.com/chair"]["reason"]
    assert q["https://grants.example.org/g2"]["outcome"] == "DEFERRED" and "not attempted" in q["https://grants.example.org/g2"]["reason"]
    assert q["https://vercel.com/acme"]["outcome"] == "SKIPPED_UNSUPPORTED"
    assert len(store.index()) == n_records and not SYNCED and not {"https://shop.example.com/chair", "https://grants.example.org/g2"} & urls_in_entities()
    assert not list(store.PENDING.glob("*.json")) or all("chair" not in p.read_text() for p in store.PENDING.glob("*.json"))
    assert rep4["counts"]["deferred"] == 2 and "retry-deferred" in q["https://shop.example.com/chair"]["next_action"]
    # 15: retry-deferred while Claude is still out: still deferred, nothing saved; then once back: saved exactly once
    r1 = R.retry_deferred()
    assert r1["still_deferred"] == 2 and len(store.index()) == n_records
    QUOTA["on"] = False
    r2 = R.retry_deferred()
    assert r2["ingested"] == 2 and len(store.index()) == n_records + 2
    r3 = R.retry_deferred()
    assert r3["retried"] == 0 and len(store.index()) == n_records + 2
    rep5 = R.load_report()  # overlay reflects the retry: nothing deferred remains outstanding
    assert not [i for i in rep5["attention"] if i["outcome"] == "DEFERRED"]

    # review: approve with a destination, process now
    ledger = R.load_ledger()
    desk = next(e for e in ledger.values() if e["url"] == "https://www.instagram.com/reel/DESK1/")
    R.review_update(ledger, desk["id"], dest="wishlist", instruction="identify the desk mat")
    R.save_ledger(ledger)
    done = R.process_queued()
    assert [d["outcome"] for d in done] == ["AUTO_INGESTED"] and store.load(done[0]["record_id"])["intent"]["user_instruction"] == "identify the desk mat"

    # interrupted sweep resumes: items not reached stay QUEUED and the next sweep processes them
    FAKE.add("I1", "00 Inbox", "want this pen for my dorm", "https://shop.example.com/pen")
    FAKE.add("I2", "00 Inbox", "want this cup for my dorm", "https://shop.example.com/cup")
    real_pc = bulk.process_candidate

    def boom(c, batch):
        if "pen" in c["original_url"]:
            raise KeyboardInterrupt
        return real_pc(c, batch)
    bulk.process_candidate = boom
    try:
        R.sweep()
        raise AssertionError("expected interrupt")
    except KeyboardInterrupt:
        pass
    finally:
        bulk.process_candidate = real_pc
    assert {e["outcome"] for e in R.load_ledger().values() if e["url"] in ("https://shop.example.com/pen", "https://shop.example.com/cup")} == {"QUEUED"}
    rep6 = R.sweep()
    assert all(by_url(rep6)[u]["outcome"] == "AUTO_INGESTED" for u in ("https://shop.example.com/pen", "https://shop.example.com/cup"))
    assert any(r["status"] == "interrupted" for r in json.loads(R.STATE.read_text())["runs"])

    # CLEAR: preview only reads; scheduled context refuses; wrong token refuses; changed text excluded; confirm completes exactly the preview
    FAKE.calls.clear()
    FAKE.items["WISH2"]["body"] += "\nedited after the sweep"
    pv = R.clear_preview()
    will = {r["reminder_id"] for r in pv["will_complete"]}
    assert "x-apple-reminder://WISH2" not in will and any(r["why"] == "text changed since the sweep read it" for r in pv["untouched"])
    assert "x-apple-reminder://TWO" not in will and "x-apple-reminder://TOOL" not in will and "x-apple-reminder://FAIL" not in will
    assert "x-apple-reminder://WISH" in will and "x-apple-reminder://VAGUE" in will  # approved via changed wording and ingested
    assert {c[0] for c in FAKE.calls} == {"read_by_id"}
    os.environ["LINKINTAKE_SCHEDULED"] = "1"
    for bad in (lambda: R.clear_confirm(pv["token"]),):
        try:
            bad()
            raise AssertionError("scheduled clear allowed")
        except PermissionError:
            pass
    del os.environ["LINKINTAKE_SCHEDULED"]
    try:
        R.clear_confirm("deadbeef0000")
        raise AssertionError("wrong token accepted")
    except PermissionError:
        pass
    assert not any(c[0] == "complete" for c in FAKE.calls)
    res = R.clear_confirm(pv["token"])
    assert {r["reminder_id"] for r in res["completed"]} == will and not res["failed"]
    assert {r["id"] for r in FAKE.items.values() if r["completed"]} == will
    assert len(FAKE.items) == 17 and not FAKE.items["TWO"]["completed"] and not FAKE.items["NOURL"]["completed"]  # nothing deleted, others untouched
    assert R.load_report()["clear_decision"]["action"] == "cleared" and len(R.CLEAR_LOG.read_text().splitlines()) == len(will)
    assert R.clear_keep()["changed"] == 0 and R.load_report()["clear_decision"]["action"] == "kept"
    assert NOTIFICATIONS and all(t == "Link Intake Weekly" for t, _ in NOTIFICATIONS) and len(NOTIFICATIONS) == 5  # one per completed sweep; none for the interrupted one

    # 16/17: LaunchAgent plist + install/status/remove, never touching another agent
    agents = schedule.agents_dir()
    other = agents / "com.someone.else.plist"
    other.write_bytes(plistlib.dumps({"Label": "com.someone.else", "ProgramArguments": ["/bin/true"]}))
    before = other.read_bytes()
    calls = []
    schedule._launchctl = lambda *a: (calls.append(a), subprocess.CompletedProcess(a, 0, "", ""))[1]
    p = schedule.build()
    assert p["StartCalendarInterval"] == {"Weekday": 0, "Hour": 19, "Minute": 0} and p["Label"] == schedule.LABEL
    assert p["ProgramArguments"][1:] == ["reminders", "run", "--execute", "--scheduled"] and "clear" not in json.dumps(p)
    env = p["EnvironmentVariables"]
    assert env["LINKINTAKE_SCHEDULED"] == "1" and env["USER"] and env["LOGNAME"] == env["USER"] and env["HOME"] and "/opt/homebrew/bin" in env["PATH"]
    dry = schedule.install("sat", "08:30", dry_run=True)
    assert not schedule.plist_path().exists() and not calls and "<integer>6</integer>" in dry["plist"]
    for badw, badt in (("funday", "19:00"), ("sun", "25:00"), ("sun", "7pm")):
        try:
            schedule.parse(badw, badt)
            raise AssertionError("bad schedule accepted")
        except ValueError:
            pass
    ins = schedule.install("sat", "08:30")
    got = plistlib.loads(schedule.plist_path().read_bytes())
    assert ins["installed"] and got["StartCalendarInterval"] == {"Weekday": 6, "Hour": 8, "Minute": 30} and ins["schedule"] == "every Sat at 08:30 local time"
    assert schedule.next_run(got, datetime(2026, 9, 24, 12, 0)) == "Sat 2026-09-26 08:30"
    assert schedule.next_run(got, datetime(2026, 9, 26, 9, 0)) == "Sat 2026-10-03 08:30"
    st = schedule.status()
    assert st["installed"] and st["loaded"] and st["last_successful_sweep"]
    rm = schedule.remove()
    assert rm["removed"] and not schedule.plist_path().exists() and other.read_bytes() == before
    assert all(any(schedule.LABEL in x for x in c) for c in calls), calls
    assert not schedule.status()["installed"]
    # the launchd environment still reaches the configured Claude profile with USER/LOGNAME restored
    saved = {k: os.environ.pop(k, None) for k in ("USER", "LOGNAME", "CLAUDE_CONFIG_DIR")}
    try:
        ce = extract.claude_env({"llm": {"claude_config_dir": "~/.claude-nebula"}})
        assert ce["USER"] and ce["LOGNAME"] and ce["CLAUDE_CONFIG_DIR"].endswith("/.claude-nebula")
    finally:
        os.environ.update({k: v for k, v in saved.items() if v})
    print("test_reminders: ok (read-only discovery, routing, dedupe, semantic merge, quota defer, retry idempotent, restart, clear, launchd)")


if __name__ == "__main__":
    main()
