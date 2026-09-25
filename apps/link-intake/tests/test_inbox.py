"""Watched inbox (Slack + Gmail bulk sources), fully offline: the HTTP layer is monkeypatched, never
called for real. Dormant feature (SPEC.md §4.3): no cron here, no real token, no real Google client.
Run: uv run python tests/test_inbox.py"""
import base64
import json
import os
import tempfile

os.environ["LINKINTAKE_STATE_DIR"] = tempfile.mkdtemp(prefix="linkintake-inbox-")

from linkintake import bulk, cli, config  # noqa: E402

REEL = "https://www.instagram.com/reel/ZZZZZZZ/"


# ---------- fakes -----------------------------------------------------------------------------
class FakeSlack:
    """Records every call; conversations.history returns whatever `history` holds for the call count."""

    def __init__(self, histories, users=None):
        self.histories = list(histories)  # one dict per successive conversations.history call
        self.users = users or {}
        self.calls = []

    def __call__(self, token, method, params):
        self.calls.append((token, method, dict(params)))
        if method == "conversations.history":
            data = self.histories.pop(0)
        elif method == "users.info":
            data = self.users[params["user"]]
        else:
            raise AssertionError(f"unexpected slack method {method}")
        if not data.get("ok"):
            raise RuntimeError(f"slack {method} failed: {data.get('error', 'unknown')}")
        return data


class FakeGoogle:
    """Enough of google_api.Google for discover_gmail: .request(method, url, params) -> dict."""

    def __init__(self, listing, messages):
        self.listing = listing
        self.messages = messages  # id -> full message dict
        self.calls = []

    def request(self, method, url, body=None, params=None):
        self.calls.append((method, url, params))
        if url.endswith("/messages"):
            return self.listing
        for mid, msg in self.messages.items():
            if url.endswith(f"/messages/{mid}"):
                return msg
        raise AssertionError(f"unexpected gmail url {url}")


def _b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _gmail_msg(mid, history_id, frm, text):
    return {"id": mid, "historyId": history_id,
            "payload": {"headers": [{"name": "From", "value": frm}],
                        "parts": [{"mimeType": "text/plain", "body": {"data": _b64(text)}}]}}


# ---------- tests -------------------------------------------------------------------------------
def test_discover_slack():
    fake = FakeSlack(
        histories=[{"ok": True, "messages": [
            {"user": "U1", "text": f"check this out {REEL}", "ts": "1700000010.000100"},
            {"user": "U2", "text": "no link here", "ts": "1700000020.000200"},
        ]}],
        users={"U1": {"ok": True, "user": {"profile": {"display_name": "Alex", "real_name": "Alex Kim"}}},
               "U2": {"ok": True, "user": {"profile": {"display_name": "", "real_name": "Jamie Lee"}}}},
    )
    bulk._slack_api = fake
    try:
        items = bulk.discover_slack("C123", "xoxb-test")
    finally:
        del bulk._slack_api
    assert items == [
        {"origin": "slack", "container": "C123", "title": "Alex", "text": f"check this out {REEL}"},
        {"origin": "slack", "container": "C123", "title": "Jamie Lee", "text": "no link here"},
    ]
    # first call has no persisted cursor yet -> oldest="0"
    assert fake.calls[0] == ("xoxb-test", "conversations.history", {"channel": "C123", "oldest": "0", "limit": "200"})
    # users.info called once per unique user, not once per message
    assert sorted(c[2]["user"] for c in fake.calls if c[1] == "users.info") == ["U1", "U2"]
    # cursor advanced to the newest ts seen
    cursor = json.loads((bulk.BULK_DIR / "slack-cursor.json").read_text())
    assert cursor["C123"] == "1700000020.000200"


def test_discover_slack_uses_persisted_cursor_and_skips_on_failure():
    bulk._write_cursor("slack", "C999", "1700000000.000000")
    fake = FakeSlack(histories=[{"ok": False, "error": "invalid_auth"}])
    bulk._slack_api = fake
    try:
        threw = False
        try:
            bulk.discover_slack("C999", "xoxb-bad")
        except RuntimeError:
            threw = True
        assert threw
    finally:
        del bulk._slack_api
    # the second (persisted) call read the prior cursor as "oldest" ...
    assert fake.calls[0][2]["oldest"] == "1700000000.000000"
    # ... and a failed sweep never advances it (nothing lost, per SPEC §7)
    assert bulk._read_cursor("slack", "C999") == "1700000000.000000"


def test_discover_gmail():
    listing = {"messages": [{"id": "m1"}, {"id": "m2"}]}
    messages = {
        "m1": _gmail_msg("m1", "100", "Creator One <c1@example.com>", f"reel: {REEL}"),
        "m2": _gmail_msg("m2", "101", "Creator Two <c2@example.com>", "hello"),
    }
    g = FakeGoogle(listing, messages)
    items = bulk.discover_gmail("Label_123", google=g)
    assert items == [
        {"origin": "gmail", "container": "Label_123", "title": "Creator One <c1@example.com>", "text": f"reel: {REEL}"},
        {"origin": "gmail", "container": "Label_123", "title": "Creator Two <c2@example.com>", "text": "hello"},
    ]
    cursor = json.loads((bulk.BULK_DIR / "gmail-cursor.json").read_text())
    assert cursor["Label_123"] == "101"


def test_discover_gmail_uses_persisted_cursor_to_skip_seen():
    listing = {"messages": [{"id": "m1"}, {"id": "m2"}]}
    messages = {
        "m1": _gmail_msg("m1", "100", "A <a@example.com>", "old, already swept"),
        "m2": _gmail_msg("m2", "102", "B <b@example.com>", "new since last sweep"),
    }
    g = FakeGoogle(listing, messages)
    items = bulk.discover_gmail("Label_456", since_history_id="100", google=g)
    assert len(items) == 1 and items[0]["title"] == "B <b@example.com>"
    assert bulk._read_cursor("gmail", "Label_456") == "102"


def test_dest_override_and_sender_mapping():
    """bulk run --dest forces the destination for every processed candidate; only slack/gmail-origin
    candidates get received_via/received_from on the pipeline.ingest call."""
    from linkintake import pipeline
    candidates = [
        {"id": "c001", "status": "ready", "original_url": REEL, "canonical_url": REEL,
         "inferred_destination": "personal_ig", "inferred_instruction": "capture the hook",
         "source_origin": "slack", "source_container": "C123", "source_context": "",
         "provenance": [{"origin": "slack", "container": "C123", "title": "Alex", "context": ""}]},
        {"id": "c002", "status": "ready", "original_url": "https://example.com/x", "canonical_url": "https://example.com/x",
         "inferred_destination": "wishlist", "inferred_instruction": "identify this",
         "source_origin": "reminders", "source_container": "Wishlist", "source_context": "",
         "provenance": [{"origin": "reminders", "container": "Wishlist", "title": "", "context": ""}]},
    ]
    run_id = bulk.new_run(candidates, ["fixture"])
    run = bulk.load_run(run_id)
    calls = []

    def fake_ingest(url, dest, instruction, *, save=False, force=False, refresh=False, batch=None, **kw):
        calls.append({"url": url, "dest": dest, "kw": kw})
        rec = {"id": f"rec-{len(calls)}", "status": "ready", "saved_at": "now",
               "destination_resolution": {"action": "created"}, "export": {"status": "synced"}}
        return rec

    real = pipeline.ingest
    pipeline.ingest = fake_ingest
    try:
        report = bulk.run_batch(run, dry_run=False, delay=0, dest_override="ugc")
    finally:
        pipeline.ingest = real
    assert report["saved"] == 2 and report["failed"] == 0
    slack_call = next(c for c in calls if c["url"] == REEL)
    reminders_call = next(c for c in calls if c["url"] == "https://example.com/x")
    assert slack_call["dest"] == "ugc"  # overridden from personal_ig
    assert slack_call["kw"] == {"received_via": "slack", "received_from": "Alex"}
    assert reminders_call["dest"] == "ugc"  # override applies to every processed candidate, not just inbox ones
    assert reminders_call["kw"] == {}  # no fabricated sender for a non-inbox source
    # candidate state persisted with the overridden destination too
    assert run["candidates"][0]["inferred_destination"] == "ugc"


def test_dest_override_dry_run_preview_reflects_override():
    candidates = [
        {"id": "c001", "status": "ready", "canonical_url": REEL, "inferred_destination": "personal_ig",
         "inferred_instruction": "x", "source_origin": "slack", "source_container": "C1", "source_context": "",
         "provenance": [{"origin": "slack", "container": "C1", "title": "Sam", "context": ""}]},
    ]
    run_id = bulk.new_run(candidates, ["fixture"])
    run = bulk.load_run(run_id)
    report = bulk.run_batch(run, dry_run=True, dest_override="ugc")
    assert report["would_process"] == [{"id": "c001", "url": REEL, "destination": "ugc", "instruction": "x"}]


def test_cli_sources_slack_gmail_wired_and_guarded():
    # missing config/env -> a clear SystemExit, not a crash
    cfg = config.load()
    cfg["inbox"] = {"slack_channel": "", "slack_token_env": "LINKINTAKE_SLACK_TOKEN", "gmail_label": ""}
    config.save(cfg)
    try:
        cli.main(["--json", "bulk", "scan", "--sources", "slack"])
        raised = False
    except SystemExit:
        raised = True
    assert raised

    # configured -> cli dispatches to bulk.discover_slack / discover_gmail with the config values
    cfg["inbox"] = {"slack_channel": "C1", "slack_token_env": "LINKINTAKE_SLACK_TOKEN", "gmail_label": "Label_1"}
    config.save(cfg)
    os.environ["LINKINTAKE_SLACK_TOKEN"] = "xoxb-fixture"
    seen = {}

    def fake_discover_slack(channel, token):
        seen["slack"] = (channel, token)
        return []

    def fake_discover_gmail(label):
        seen["gmail"] = (label,)
        return []

    real_slack, real_gmail = bulk.discover_slack, bulk.discover_gmail
    bulk.discover_slack, bulk.discover_gmail = fake_discover_slack, fake_discover_gmail
    try:
        rc = cli.main(["--json", "bulk", "scan", "--sources", "slack,gmail"])
    finally:
        bulk.discover_slack, bulk.discover_gmail = real_slack, real_gmail
        del os.environ["LINKINTAKE_SLACK_TOKEN"]
    assert rc == 0
    assert seen["slack"] == ("C1", "xoxb-fixture")
    assert seen["gmail"] == ("Label_1",)


def main():
    test_discover_slack()
    test_discover_slack_uses_persisted_cursor_and_skips_on_failure()
    test_discover_gmail()
    test_discover_gmail_uses_persisted_cursor_to_skip_seen()
    test_dest_override_and_sender_mapping()
    test_dest_override_dry_run_preview_reflects_override()
    test_cli_sources_slack_gmail_wired_and_guarded()
    print("test_inbox: ok")


if __name__ == "__main__":
    main()
