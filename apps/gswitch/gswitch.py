#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastmcp>=2.3",
#   "google-api-python-client>=2.100",
#   "google-auth-oauthlib>=1.2",
# ]
# ///
"""gswitch — multi-account Google MCP server for ChatGPT.

All tools operate on the "active" account (~/.gswitch/active), so the Dock
picker can flip accounts instantly without ChatGPT reconnecting.

CLI: add | list | use <email> | serve | up | url | selfcheck
"""

import argparse
import base64
import json
import os
import secrets as pysecrets
import signal
import subprocess
import sys
from email.mime.text import MIMEText
from functools import wraps
from pathlib import Path

GSWITCH_DIR = Path(os.environ.get("GSWITCH_DIR", str(Path.home() / ".gswitch")))
ACCOUNTS_DIR = GSWITCH_DIR / "accounts"
ACTIVE_FILE = GSWITCH_DIR / "active"
SECRET_FILE = GSWITCH_DIR / "secret"
CLIENT_SECRET = GSWITCH_DIR / "client_secret.json"
NGROK_DOMAIN_FILE = GSWITCH_DIR / "ngrok_domain"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar",
]
PORT = 8765
# ponytail: hardcoded tz for events given without a UTC offset; make configurable if Nik leaves PT
DEFAULT_TZ = "America/Los_Angeles"
MAX_CHARS = 50_000


# ---------- account store ----------

def list_accounts() -> list[str]:
    if not ACCOUNTS_DIR.is_dir():
        return []
    return sorted(p.stem for p in ACCOUNTS_DIR.glob("*.json"))

def active_account() -> str | None:
    try:
        email = ACTIVE_FILE.read_text().strip()
    except FileNotFoundError:
        return None
    return email if email in list_accounts() else None

def set_active(email: str) -> None:
    if email not in list_accounts():
        raise SystemExit(f"unknown account {email!r}; known: {list_accounts() or 'none'}")
    GSWITCH_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(email + "\n")

def secret_path() -> str:
    if not SECRET_FILE.exists():
        GSWITCH_DIR.mkdir(parents=True, exist_ok=True)
        SECRET_FILE.write_text(pysecrets.token_hex(16))
        SECRET_FILE.chmod(0o600)
    return "/mcp-" + SECRET_FILE.read_text().strip()

def _creds():
    from google.oauth2.credentials import Credentials
    email = active_account()
    if not email:
        raise RuntimeError("no active Google account; run `gswitch add` on the Mac")
    return Credentials.from_authorized_user_file(str(ACCOUNTS_DIR / f"{email}.json"), SCOPES)

def _svc(api: str, version: str):
    from googleapiclient.discovery import build
    return build(api, version, credentials=_creds(), cache_discovery=False)


# ---------- MCP server ----------

from fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("gswitch")

def tool(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        try:
            out = fn(*a, **kw)
            return out if isinstance(out, str) else json.dumps(out, indent=1, default=str)
        except Exception as e:  # surface errors to ChatGPT instead of 500ing
            return f"ERROR: {type(e).__name__}: {e}"
    return mcp.tool(wrapper)


@tool
def active_google_account() -> str:
    """Report which Google account gswitch tools currently operate on."""
    return active_account() or "none — no active account configured"


@tool
def drive_search(query: str, max_results: int = 10) -> str:
    """Search Google Drive by content/name. Returns file ids, names, types, links."""
    q = f"(fullText contains '{query}' or name contains '{query}') and trashed=false"
    r = _svc("drive", "v3").files().list(
        q=q, pageSize=min(max_results, 50),
        fields="files(id,name,mimeType,modifiedTime,webViewLink)").execute()
    return r.get("files", [])


@tool
def drive_read_file(file_id: str) -> str:
    """Read a Drive file's content as text. Google Docs/Sheets/Slides are exported; other text files downloaded."""
    svc = _svc("drive", "v3")
    meta = svc.files().get(fileId=file_id, fields="id,name,mimeType").execute()
    mime = meta["mimeType"]
    exports = {
        "application/vnd.google-apps.document": "text/plain",
        "application/vnd.google-apps.spreadsheet": "text/csv",
        "application/vnd.google-apps.presentation": "text/plain",
    }
    if mime in exports:
        data = svc.files().export(fileId=file_id, mimeType=exports[mime]).execute()
    elif mime.startswith("application/vnd.google-apps."):
        return f"{meta['name']}: unsupported Google type {mime}"
    else:
        data = svc.files().get_media(fileId=file_id).execute()
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
    if "\x00" in text[:1000]:
        return f"{meta['name']}: binary file ({mime}), cannot render as text"
    suffix = f"\n…[truncated at {MAX_CHARS} chars]" if len(text) > MAX_CHARS else ""
    return f"# {meta['name']} ({mime})\n\n{text[:MAX_CHARS]}{suffix}"


def _doc_media(content: str):
    from googleapiclient.http import MediaInMemoryUpload
    return MediaInMemoryUpload(content.encode(), mimetype="text/plain")


@tool
def drive_create_doc(title: str, content: str) -> str:
    """Create a new Google Doc with the given title and plain-text content."""
    f = _svc("drive", "v3").files().create(
        body={"name": title, "mimeType": "application/vnd.google-apps.document"},
        media_body=_doc_media(content), fields="id,webViewLink").execute()
    return f"created doc {f['id']}: {f.get('webViewLink', '')}"


@tool
def drive_update_doc(file_id: str, content: str) -> str:
    """REPLACE a Google Doc's entire content with the given plain text."""
    _svc("drive", "v3").files().update(fileId=file_id, media_body=_doc_media(content)).execute()
    return f"updated doc {file_id} (content replaced)"


@tool
def gmail_search(query: str, max_results: int = 10) -> str:
    """Search Gmail (standard Gmail query syntax, e.g. 'from:x subject:y newer_than:7d')."""
    svc = _svc("gmail", "v1")
    ids = svc.users().messages().list(
        userId="me", q=query, maxResults=min(max_results, 25)).execute().get("messages", [])
    out = []
    for m in ids:
        msg = svc.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]).execute()
        h = {x["name"]: x["value"] for x in msg["payload"].get("headers", [])}
        out.append({"id": m["id"], "from": h.get("From"), "subject": h.get("Subject"),
                    "date": h.get("Date"), "snippet": msg.get("snippet")})
    return out


def _body_text(payload) -> str:
    if payload.get("mimeType", "").startswith("text/") and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain":
            t = _body_text(part)
            if t:
                return t
    for part in payload.get("parts", []) or []:
        t = _body_text(part)
        if t:
            return t
    return ""


@tool
def gmail_read(message_id: str) -> str:
    """Read one Gmail message in full by id (from gmail_search)."""
    msg = _svc("gmail", "v1").users().messages().get(
        userId="me", id=message_id, format="full").execute()
    h = {x["name"]: x["value"] for x in msg["payload"].get("headers", [])}
    body = _body_text(msg["payload"]) or msg.get("snippet", "")
    head = "\n".join(f"{k}: {h.get(k, '')}" for k in ("From", "To", "Subject", "Date"))
    return f"{head}\n\n{body[:MAX_CHARS]}"


def _mime(to: str, subject: str, body: str, cc: str | None) -> dict:
    m = MIMEText(body)
    m["to"], m["subject"] = to, subject
    if cc:
        m["cc"] = cc
    return {"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()}


@tool
def gmail_send(to: str, subject: str, body: str, cc: str | None = None) -> str:
    """Send an email from the active account. to/cc are comma-separated addresses."""
    r = _svc("gmail", "v1").users().messages().send(
        userId="me", body=_mime(to, subject, body, cc)).execute()
    return f"sent, message id {r['id']}"


@tool
def gmail_draft(to: str, subject: str, body: str, cc: str | None = None) -> str:
    """Create a Gmail draft (not sent) in the active account."""
    r = _svc("gmail", "v1").users().drafts().create(
        userId="me", body={"message": _mime(to, subject, body, cc)}).execute()
    return f"draft created, id {r['id']}"


@tool
def calendar_list_events(time_min: str | None = None, time_max: str | None = None,
                         query: str | None = None, max_results: int = 25) -> str:
    """List primary-calendar events. Times are RFC3339 (e.g. 2026-08-18T00:00:00-07:00); time_min defaults to now."""
    import datetime as dt
    kwargs = dict(calendarId="primary", singleEvents=True, orderBy="startTime",
                  maxResults=min(max_results, 100),
                  timeMin=time_min or dt.datetime.now(dt.timezone.utc).isoformat())
    if time_max:
        kwargs["timeMax"] = time_max
    if query:
        kwargs["q"] = query
    items = _svc("calendar", "v3").events().list(**kwargs).execute().get("items", [])
    return [{"id": e["id"], "summary": e.get("summary"), "start": e.get("start"),
             "end": e.get("end"), "location": e.get("location")} for e in items]


def _when(iso: str) -> dict:
    has_offset = "Z" in iso or "+" in iso[10:] or "-" in iso[10:]
    return {"dateTime": iso} if has_offset else {"dateTime": iso, "timeZone": DEFAULT_TZ}


@tool
def calendar_create_event(summary: str, start_iso: str, end_iso: str,
                          description: str = "", attendees: str | None = None) -> str:
    """Create a primary-calendar event. start/end ISO datetimes; attendees comma-separated emails."""
    body = {"summary": summary, "description": description,
            "start": _when(start_iso), "end": _when(end_iso)}
    if attendees:
        body["attendees"] = [{"email": a.strip()} for a in attendees.split(",") if a.strip()]
    e = _svc("calendar", "v3").events().insert(calendarId="primary", body=body).execute()
    return f"created event {e['id']}: {e.get('htmlLink', '')}"


# ---------- CLI ----------

def cmd_add() -> None:
    if not CLIENT_SECRET.exists():
        raise SystemExit(f"missing {CLIENT_SECRET} — see README 'Google Cloud setup'")
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES).run_local_server(port=0)
    email = build("gmail", "v1", credentials=creds, cache_discovery=False).users() \
        .getProfile(userId="me").execute()["emailAddress"]
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ACCOUNTS_DIR / f"{email}.json"
    path.write_text(creds.to_json())
    path.chmod(0o600)
    if not active_account():
        set_active(email)
    print(f"added {email}" + (" (active)" if active_account() == email else ""))

def cmd_list() -> None:
    act = active_account()
    for a in list_accounts():
        print(("* " if a == act else "  ") + a)
    if not list_accounts():
        print("no accounts; run `gswitch add`")

def cmd_url() -> None:
    if not NGROK_DOMAIN_FILE.exists():
        raise SystemExit(f"missing {NGROK_DOMAIN_FILE} — put your ngrok static domain in it (see README)")
    print(f"https://{NGROK_DOMAIN_FILE.read_text().strip()}{secret_path()}")

def cmd_serve() -> None:
    mcp.run(transport="http", host="127.0.0.1", port=PORT, path=secret_path())

def cmd_up() -> None:
    domain = NGROK_DOMAIN_FILE.read_text().strip() if NGROK_DOMAIN_FILE.exists() else None
    if not domain:
        raise SystemExit(f"missing {NGROK_DOMAIN_FILE} — put your ngrok static domain in it (see README)")
    ngrok = subprocess.Popen(["ngrok", "http", "--url", domain, str(PORT)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"ngrok up: https://{domain}{secret_path()}")
    try:
        cmd_serve()
    finally:
        ngrok.send_signal(signal.SIGTERM)
        ngrok.wait(timeout=10)

def cmd_selfcheck() -> None:
    import tempfile
    global GSWITCH_DIR, ACCOUNTS_DIR, ACTIVE_FILE, SECRET_FILE
    with tempfile.TemporaryDirectory() as td:
        GSWITCH_DIR = Path(td)
        ACCOUNTS_DIR = GSWITCH_DIR / "accounts"
        ACTIVE_FILE = GSWITCH_DIR / "active"
        SECRET_FILE = GSWITCH_DIR / "secret"
        assert list_accounts() == [] and active_account() is None
        ACCOUNTS_DIR.mkdir(parents=True)
        (ACCOUNTS_DIR / "a@x.com.json").write_text("{}")
        (ACCOUNTS_DIR / "b@y.edu.json").write_text("{}")
        assert list_accounts() == ["a@x.com", "b@y.edu"]
        set_active("b@y.edu")
        assert active_account() == "b@y.edu"
        ACTIVE_FILE.write_text("gone@nowhere\n")  # stale active -> None, not crash
        assert active_account() is None
        s = secret_path()
        assert s == secret_path() and s.startswith("/mcp-") and len(s) == len("/mcp-") + 32
        try:
            set_active("nope@no")
            raise AssertionError("set_active accepted unknown account")
        except SystemExit:
            pass
        assert _when("2026-08-18T10:00:00")["timeZone"] == DEFAULT_TZ
        assert "timeZone" not in _when("2026-08-18T10:00:00-07:00")
        assert _body_text({"mimeType": "text/plain",
                           "body": {"data": base64.urlsafe_b64encode(b"hi").decode()}}) == "hi"
    print("selfcheck OK")

def main() -> None:
    p = argparse.ArgumentParser(prog="gswitch", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("add", "list", "serve", "up", "url", "selfcheck"):
        sub.add_parser(name)
    use = sub.add_parser("use")
    use.add_argument("email")
    args = p.parse_args()
    if args.cmd == "use":
        set_active(args.email)
        print(f"active: {args.email}")
    else:
        {"add": cmd_add, "list": cmd_list, "serve": cmd_serve, "up": cmd_up,
         "url": cmd_url, "selfcheck": cmd_selfcheck}[args.cmd]()

if __name__ == "__main__":
    main()
