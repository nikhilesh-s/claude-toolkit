"""One-time OAuth for a Google account (e.g. personal) using the same OAuth client gswitch uses.
Writes ~/.link-intake/google-creds.json in the workspace-mcp token shape. Loopback redirect on port 8792:
that exact URI must be registered on the OAuth client in Google Cloud Console."""
from __future__ import annotations

import http.server
import json
import os
import secrets
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

from . import config

SCOPES = ["https://www.googleapis.com/auth/documents", "https://www.googleapis.com/auth/drive",
          "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/userinfo.email"]
PORT = int(os.environ.get("LINKINTAKE_OAUTH_PORT", "8792"))
REDIRECT = f"http://localhost:{PORT}/oauth2callback"


def _client() -> tuple[str, str]:
    cid, sec = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""), os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
    cfg = Path.home() / ".gswitch" / "config"
    if (not cid or not sec) and cfg.exists():
        for line in cfg.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "GOOGLE_OAUTH_CLIENT_ID":
                cid = v.strip()
            elif k.strip() == "GOOGLE_OAUTH_CLIENT_SECRET":
                sec = v.strip()
    if not cid or not sec:
        raise SystemExit("No OAuth client. Set GOOGLE_OAUTH_CLIENT_ID/SECRET or run `gswitch config` first.")
    return cid, sec


def run() -> Path:
    cid, sec = _client()
    state = secrets.token_urlsafe(16)
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "scope": " ".join(SCOPES),
        "access_type": "offline", "prompt": "consent select_account", "state": state})
    got: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            got.update(q)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"link-intake: you can close this tab.")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", PORT), H)
    print("Opening browser for Google sign-in. Pick the account that owns your Wishlist / college-app docs.")
    print("If the browser does not open, visit:\n" + url)
    webbrowser.open(url)
    while "code" not in got and "error" not in got:
        srv.handle_request()
    srv.server_close()
    if got.get("error") or got.get("state") != state:
        raise SystemExit(f"OAuth failed: {got.get('error', 'state mismatch')}. If Google says redirect_uri_mismatch, add {REDIRECT} to the OAuth client.")
    body = urllib.parse.urlencode({"code": got["code"], "client_id": cid, "client_secret": sec, "redirect_uri": REDIRECT,
                                   "grant_type": "authorization_code"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=body), timeout=30) as r:
        tok = json.loads(r.read())
    req = urllib.request.Request("https://www.googleapis.com/oauth2/v3/userinfo", headers={"Authorization": "Bearer " + tok["access_token"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        email = json.loads(r.read()).get("email", "")
    out = config.STATE_DIR / "google-creds.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"client_id": cid, "client_secret": sec, "refresh_token": tok.get("refresh_token", ""),
                               "token": tok["access_token"], "token_uri": "https://oauth2.googleapis.com/token",
                               "scopes": SCOPES, "account": email}, indent=2))
    out.chmod(0o600)
    cfg = config.load()
    cfg["google"]["creds_path"] = str(out)
    config.save(cfg)
    print(f"Saved credentials for {email} -> {out}")
    return out
