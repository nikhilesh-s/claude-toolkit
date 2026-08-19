#!/usr/bin/env python3
"""
Email the result of a sync run to Nik.

Credentials are NEVER stored in this repo. The SMTP app password lives in the
macOS Keychain and is read at send time:

    security add-generic-password -a nebula.markdown@gmail.com \
        -s claude-toolkit-smtp -w   # prompts for the password, does not echo it

For Gmail this must be an APP PASSWORD (myaccount.google.com/apppasswords),
not the account password. Gmail rejects the account password over SMTP.

If no credential is stored, this exits 0 quietly. A missing email must never
turn a successful sync into a failed one.

    python3 scripts/nik_mail_report.py            send report for the last run
    python3 scripts/nik_mail_report.py --test     send a test email now
"""
import os, smtplib, subprocess, sys, socket
from datetime import datetime
from email.message import EmailMessage

TO       = "niksuravarjjala@gmail.com"
FROM     = os.environ.get("NIK_SMTP_USER", "niksuravarjjala@gmail.com")
SMTP     = ("smtp.gmail.com", 587)
KEYCHAIN = "claude-toolkit-smtp"

HOME    = os.path.expanduser("~")
LOG_DIR = os.path.join(HOME, "Library", "Logs", "claude-toolkit")
STATUS  = os.path.join(LOG_DIR, "last-run.txt")
LOG     = os.path.join(LOG_DIR, "sync.log")
REPO    = os.path.join(HOME, "claude-toolkit")


def password():
    """Read the app password from the Keychain. Returns None if absent."""
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN, "-w"],
            capture_output=True, text=True, timeout=15)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except Exception:
        return None


def sh(*cmd, cwd=REPO):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=60)
        return r.stdout.strip()
    except Exception:
        return ""


def profile_stats():
    import json
    out = []
    for p in (os.path.join(HOME, ".claude"), os.path.join(HOME, ".claude-nebula")):
        try:
            reg = json.load(open(p + "/plugins/installed_plugins.json"))["plugins"]
            en = json.load(open(p + "/settings.json")).get("enabledPlugins", {})
            skills = sorted(os.listdir(os.path.join(p, "skills")))
            out.append((os.path.basename(p), len(skills), len(reg),
                        sum(1 for k in reg if en.get(k)), skills))
        except Exception as e:
            out.append((os.path.basename(p), -1, -1, -1, []))
    return out


def build():
    status = ["", "", ""]
    if os.path.exists(STATUS):
        status = (open(STATUS).read().split("\n") + ["", "", ""])[:3]
    ts, state, detail = status[0], status[1], status[2]

    stats = profile_stats()
    parity = "YES" if len(stats) == 2 and stats[0][4] == stats[1][4] else "NO — profiles differ"

    tail = ""
    if os.path.exists(LOG):
        lines = open(LOG, errors="replace").read().split("\n")
        # last run block: from the final "daily sync start" onward
        idx = max((i for i, l in enumerate(lines) if "daily sync start" in l), default=0)
        tail = "\n".join(lines[idx:])[-4000:]

    head = sh("git", "log", "-1", "--format=%h %s")
    behind = sh("git", "rev-list", "--count", "HEAD..upstream/main") or "?"
    dirty = "clean" if not sh("git", "status", "--porcelain") else "DIRTY"
    broken = sh("bash", "-c",
                "find -L ~/.claude/skills ~/.claude-nebula/skills -maxdepth 1 -type l 2>/dev/null | wc -l")

    body = [
        f"Sync result : {state}",
        f"Detail      : {detail}",
        f"When        : {ts}",
        f"Host        : {socket.gethostname()}",
        "",
        "REPO",
        f"  commit          {head}",
        f"  worktree        {dirty}",
        f"  behind Arnav    {behind}",
        "",
        "PROFILES",
    ]
    for name, ns, np_, ne, _ in stats:
        body.append(f"  {name:16} {ns:4} skills  {np_:3} plugins  {ne:3} enabled")
    body += [
        f"  identical       {parity}",
        f"  broken links    {broken.strip()}",
        "",
        "LOG (last run)",
        "-" * 60,
        tail,
    ]
    return state, "\n".join(body)


def main():
    test = "--test" in sys.argv
    pw = password()
    if not pw:
        print("no SMTP credential in Keychain — skipping email", file=sys.stderr)
        print(f"store one with:\n  security add-generic-password -a {FROM} "
              f"-s {KEYCHAIN} -w", file=sys.stderr)
        return 0

    if test:
        state, body = "TEST", "Test email from claude-toolkit sync.\n\n" + build()[1]
    else:
        state, body = build()

    flag = "" if state in ("SYNCED", "UP TO DATE", "TEST") else " [ATTENTION]"
    msg = EmailMessage()
    msg["Subject"] = f"claude-toolkit sync: {state}{flag} — {datetime.now():%Y-%m-%d %H:%M}"
    msg["From"], msg["To"] = FROM, TO
    msg.set_content(body)

    try:
        with smtplib.SMTP(*SMTP, timeout=45) as s:
            s.starttls()
            s.login(FROM, pw)
            s.send_message(msg)
        print(f"emailed {TO}: {state}")
        return 0
    except Exception as e:
        print(f"email failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
