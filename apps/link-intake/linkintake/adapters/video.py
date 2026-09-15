"""YouTube / Vimeo / Loom: metadata + transcript via yt-dlp *without downloading media*.
Visual inspection (contact sheet) still goes through Media Unlocker."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def _yt(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    exe = shutil.which("yt-dlp") or "/opt/homebrew/bin/yt-dlp"
    return subprocess.run([exe, "--no-playlist", "--no-warnings", "--quiet", *args], text=True, capture_output=True, timeout=timeout, check=False)


def metadata(url: str) -> dict:
    proc = _yt(["--dump-single-json", "--skip-download", url], timeout=90)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"yt-dlp metadata failed: {proc.stderr.strip()[-300:]}")
    d = json.loads(proc.stdout)
    return {
        "title": d.get("title", ""), "uploader": d.get("uploader") or d.get("channel") or "",
        "description": d.get("description", ""), "duration": d.get("duration"),
        "upload_date": d.get("upload_date", ""), "chapters": [c.get("title") for c in d.get("chapters") or [] if c.get("title")],
        "tags": d.get("tags") or [], "view_count": d.get("view_count"),
    }


def transcript(url: str, max_chars: int = 16000) -> str:
    """Best-effort English subtitles (manual first, then auto). Empty string if none."""
    with tempfile.TemporaryDirectory(prefix="linkintake-subs-") as td:
        proc = _yt(["--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "en.*,en,en-orig",
                    "--sub-format", "json3/vtt/best", "-o", str(Path(td) / "%(id)s"), url], timeout=120)
        files = sorted(Path(td).glob("*"))
        if not files:
            return ""
        manual = [f for f in files if ".en" in f.name and "auto" not in f.name]
        f = (manual or files)[0]
        raw = f.read_text(errors="ignore")
        text = _parse_json3(raw) if f.suffix == ".json3" else _parse_vtt(raw)
        return text[:max_chars]


def _parse_json3(raw: str) -> str:
    try:
        events = json.loads(raw).get("events", [])
    except json.JSONDecodeError:
        return ""
    lines = []
    for ev in events:
        seg = "".join(s.get("utf8", "") for s in ev.get("segs", []) or [])
        seg = seg.replace("\n", " ").strip()
        if seg and (not lines or lines[-1] != seg):
            lines.append(seg)
    return " ".join(lines)


def _parse_vtt(raw: str) -> str:
    lines, last = [], ""
    for line in raw.splitlines():
        if not line.strip() or "-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or re.match(r"^\d+$", line):
            continue
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and clean != last:
            lines.append(clean)
            last = clean
    return " ".join(lines)
