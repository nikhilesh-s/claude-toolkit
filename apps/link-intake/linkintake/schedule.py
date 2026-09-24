"""Weekly Reminder sweep as a user LaunchAgent. It runs the same CLI (`reminders run --execute --scheduled`); no
G-Switch, workspace-mcp, tunnel, ChatGPT or Raycast involved. Claude auth comes from extract.claude_env() at spawn
time (USER/LOGNAME/HOME restored, CLAUDE_CONFIG_DIR = llm.claude_config_dir, default ~/.claude-nebula), exactly as
for Raycast. LINKINTAKE_SCHEDULED=1 makes `reminders clear` refuse: a scheduled run never completes a reminder.

Only our own plist (LABEL) is ever written, loaded, unloaded or removed."""
from __future__ import annotations

import os
import plistlib
import pwd
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from . import config

LABEL = "com.nik.linkintake.reminders"
WEEKDAYS = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
DEFAULT_WEEKDAY, DEFAULT_TIME = "sun", "19:00"


def agents_dir() -> Path:
    return Path(os.environ.get("LINKINTAKE_LAUNCHAGENTS_DIR", "~/Library/LaunchAgents")).expanduser()


def plist_path() -> Path:
    return agents_dir() / f"{LABEL}.plist"


def launcher() -> str:
    """The installed CLI symlink if present, else this checkout's bin/linkintake (both run the uv project)."""
    installed = Path("~/.local/bin/linkintake").expanduser()
    return str(installed if installed.exists() else Path(__file__).resolve().parents[1] / "bin" / "linkintake")


def parse(weekday: str, at: str) -> tuple[int, int, int]:
    wd = WEEKDAYS.get(weekday.strip().lower()[:3])
    try:
        h, m = (int(x) for x in at.split(":"))
    except ValueError:
        h = m = -1
    if wd is None or not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"bad schedule {weekday!r} {at!r}: use --weekday sun..sat --time HH:MM (24h)")
    return wd, h, m


def build(weekday: str = DEFAULT_WEEKDAY, at: str = DEFAULT_TIME) -> dict:
    wd, h, m = parse(weekday, at)
    user = pwd.getpwuid(os.getuid()).pw_name
    home = str(Path.home())
    log = str(config.STATE_DIR / "reminder-sweeps" / "launchd.log")
    env = {"PATH": f"/opt/homebrew/bin:/usr/local/bin:{home}/.local/bin:/usr/bin:/bin", "HOME": home, "USER": user, "LOGNAME": user,
           "LINKINTAKE_SCHEDULED": "1"}
    if os.environ.get("LINKINTAKE_STATE_DIR"):
        env["LINKINTAKE_STATE_DIR"] = str(config.STATE_DIR)
    return {"Label": LABEL, "ProgramArguments": [launcher(), "reminders", "run", "--execute", "--scheduled"],
            "StartCalendarInterval": {"Weekday": wd, "Hour": h, "Minute": m}, "EnvironmentVariables": env,
            "StandardOutPath": log, "StandardErrorPath": log, "RunAtLoad": False, "ProcessType": "Background",
            "WorkingDirectory": home}


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=False)


def _domain() -> str:
    return f"gui/{os.getuid()}"


def describe(p: dict) -> str:
    c = p["StartCalendarInterval"]
    day = next(k for k, v in WEEKDAYS.items() if v == c["Weekday"]).capitalize()
    return f"every {day} at {c['Hour']:02d}:{c['Minute']:02d} local time"


def next_run(p: dict, now: datetime | None = None) -> str:
    c = p["StartCalendarInterval"]
    now = now or datetime.now()
    days = (c["Weekday"] - (now.isoweekday() % 7)) % 7
    t = (now + timedelta(days=days)).replace(hour=c["Hour"], minute=c["Minute"], second=0, microsecond=0)
    return (t if t > now else t + timedelta(days=7)).strftime("%a %Y-%m-%d %H:%M")


def install(weekday: str = DEFAULT_WEEKDAY, at: str = DEFAULT_TIME, dry_run: bool = False) -> dict:
    p = build(weekday, at)
    out = {"label": LABEL, "path": str(plist_path()), "schedule": describe(p), "next_run": next_run(p), "program": p["ProgramArguments"],
           "plist": plistlib.dumps(p).decode()}
    if dry_run:
        return {**out, "installed": False, "dry_run": True}
    (config.STATE_DIR / "reminder-sweeps").mkdir(parents=True, exist_ok=True)
    agents_dir().mkdir(parents=True, exist_ok=True)
    _launchctl("bootout", f"{_domain()}/{LABEL}")  # replace an older schedule of ours; fine if none loaded
    plist_path().write_bytes(plistlib.dumps(p))
    r = _launchctl("bootstrap", _domain(), str(plist_path()))
    return {**out, "installed": True, "loaded": r.returncode == 0, "launchctl": (r.stderr or r.stdout).strip()[:300]}


def remove() -> dict:
    path = plist_path()
    r = _launchctl("bootout", f"{_domain()}/{LABEL}")
    existed = path.exists()
    path.unlink(missing_ok=True)
    return {"label": LABEL, "path": str(path), "removed": existed, "unloaded": r.returncode == 0}


def status() -> dict:
    from . import reminders
    path = plist_path()
    out: dict = {"label": LABEL, "path": str(path), "installed": path.exists(), "loaded": False, "schedule": "", "next_run": "",
                 "proposed_default": describe(build()) + " (not installed)" if not path.exists() else ""}
    if path.exists():
        p = plistlib.loads(path.read_bytes())
        out.update(schedule=describe(p), next_run=next_run(p), program=p.get("ProgramArguments"),
                   loaded=_launchctl("print", f"{_domain()}/{LABEL}").returncode == 0)
    st = reminders._read(reminders.STATE, {"runs": []})
    out["last_successful_sweep"] = st.get("last_successful_sweep", "")
    out["last_run"] = (st.get("runs") or [{}])[-1]
    return out
