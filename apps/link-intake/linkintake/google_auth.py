"""One-time OAuth for the PERSONAL Google account using a Desktop OAuth client (loopback redirect, no URI
registration, no tunnel). Writes ~/.link-intake/google/client.json and token.json, mode 600.
Refuses college (.edu) accounts. Never touches ~/.gswitch."""
from __future__ import annotations

import http.server
import json
import os
import secrets
import urllib.parse
import urllib.request
import webbrowser

from . import config
from .google_api import CLIENT_PATH, GOOGLE_DIR, TOKEN_PATH, required_account

SCOPES = ["https://www.googleapis.com/auth/documents", "https://www.googleapis.com/auth/drive",
          "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/userinfo.email"]
PORT = int(os.environ.get("LINKINTAKE_OAUTH_PORT", "8792"))
REDIRECT = f"http://localhost:{PORT}/oauth2callback"
BLOCKED_DOMAINS = (".edu",)


def _client() -> dict:
    """Desktop client id/secret: env, existing client.json, else prompt once."""
    cid, sec = os.environ.get("LINKINTAKE_GOOGLE_CLIENT_ID", ""), os.environ.get("LINKINTAKE_GOOGLE_CLIENT_SECRET", "")
    if not (cid and sec) and CLIENT_PATH.exists():
        c = json.loads(CLIENT_PATH.read_text())
        cid, sec = c.get("client_id", ""), c.get("client_secret", "")
    if not (cid and sec):
        print("Paste the Desktop OAuth client values from Google Cloud Console (Credentials page).")
        cid = input("Client ID: ").strip()
        sec = input("Client secret: ").strip()
    if not cid.endswith(".apps.googleusercontent.com") or not sec:
        raise SystemExit("That does not look like a Google OAuth client id/secret.")
    GOOGLE_DIR.mkdir(parents=True, exist_ok=True)
    CLIENT_PATH.write_text(json.dumps({"client_id": cid, "client_secret": sec, "type": "desktop"}, indent=2))
    CLIENT_PATH.chmod(0o600)
    return {"client_id": cid, "client_secret": sec}


def check_account(email: str, required: str) -> None:
    """Only the configured personal account may be saved; any .edu is refused even if misconfigured as required."""
    if not email:
        raise SystemExit("Google did not return an email address; nothing saved.")
    if email.endswith(BLOCKED_DOMAINS):
        raise SystemExit(f"Refusing {email}: that is a college account. Re-run and pick your personal Google account. Nothing saved.")
    if email != required:
        raise SystemExit(f"Refusing {email}: link-intake only writes as {required or '(google.required_account not set)'}. Nothing saved.")


def run() -> str:
    client = _client()
    state = secrets.token_urlsafe(16)
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client["client_id"], "redirect_uri": REDIRECT, "response_type": "code", "scope": " ".join(SCOPES),
        "access_type": "offline", "prompt": "consent select_account", "state": state})
    got: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            got.update(dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query)))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"link-intake: signed in. You can close this tab.")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", PORT), H)
    srv.timeout = 300
    print("Opening your browser. Sign in with your PERSONAL Google account (not the college one).")
    print("If nothing opens, paste this into a browser:\n" + url)
    webbrowser.open(url)
    while "code" not in got and "error" not in got:
        srv.handle_request()
    srv.server_close()
    if got.get("error") or got.get("state") != state:
        raise SystemExit(f"Google sign-in failed: {got.get('error', 'state mismatch')}")
    body = urllib.parse.urlencode({"code": got["code"], "client_id": client["client_id"], "client_secret": client["client_secret"],
                                   "redirect_uri": REDIRECT, "grant_type": "authorization_code"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=body), timeout=30) as r:
        tok = json.loads(r.read())
    req = urllib.request.Request("https://www.googleapis.com/oauth2/v3/userinfo", headers={"Authorization": "Bearer " + tok["access_token"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        email = json.loads(r.read()).get("email", "").lower()
    check_account(email, required_account())
    if not tok.get("refresh_token"):
        raise SystemExit("Google returned no refresh token. Remove link-intake from https://myaccount.google.com/permissions and re-run.")
    TOKEN_PATH.write_text(json.dumps({"email": email, "refresh_token": tok["refresh_token"], "token": tok["access_token"],
                                      "expires_at": 0, "scopes": SCOPES}, indent=2))
    TOKEN_PATH.chmod(0o600)
    cfg = config.load()
    cfg["google"]["account"] = email
    cfg["google"]["export_mode"] = "auto"
    config.save(cfg)
    print(f"Authorized {email}. Token saved to {TOKEN_PATH} (mode 600). Next: linkintake google-setup")
    return email
