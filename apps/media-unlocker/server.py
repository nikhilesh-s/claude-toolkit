#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP, Image
from mcp.server.transport_security import TransportSecuritySettings

APP_NAME = "media-unlocker"
HOME = Path.home()
STATE_DIR = Path(os.environ.get("MEDIAUNLOCK_STATE_DIR", HOME / ".media-unlocker"))
JOBS_DIR = STATE_DIR / "jobs"
PORT = int(os.environ.get("MEDIAUNLOCK_PORT", "8770"))
HOST = os.environ.get("MEDIAUNLOCK_HOST", "127.0.0.1")
DEFAULT_BROWSER = os.environ.get("MEDIAUNLOCK_BROWSER", "safari")
COBALT_URL = os.environ.get("MEDIAUNLOCK_COBALT_URL", "").rstrip("/")
MAX_MEDIA_MB = int(os.environ.get("MEDIAUNLOCK_MAX_MEDIA_MB", "250"))
MCP_ALLOWED_HOSTS = [
    value.strip()
    for value in os.environ.get(
        "MEDIAUNLOCK_ALLOWED_HOSTS",
        "127.0.0.1:*,localhost:*",
    ).split(",")
    if value.strip()
]

mcp = FastMCP(
    APP_NAME,
    host=HOST,
    port=PORT,
    stateless_http=True,
    transport_security=TransportSecuritySettings(allowed_hosts=MCP_ALLOWED_HOSTS),
)


def _run(cmd: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _validate_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public http(s) URLs are supported.")
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        raise ValueError("Local/private URLs are not allowed.")
    try:
        for result in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM):
            addr = ipaddress.ip_address(result[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
                raise ValueError("Local/private network targets are not allowed.")
    except socket.gaierror:
        pass
    return url


def _job_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _media_files(job_dir: Path) -> list[Path]:
    files: list[Path] = []
    for p in (job_dir / "media").glob("**/*"):
        if not p.is_file() or p.name.endswith((".json", ".part", ".ytdl")):
            continue
        mime, _ = mimetypes.guess_type(p.name)
        if mime and (mime.startswith("video/") or mime.startswith("image/")):
            files.append(p)
        elif p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            files.append(p)
    return sorted(files, key=lambda p: p.stat().st_size, reverse=True)


def _read_metadata(job_dir: Path) -> dict[str, Any]:
    candidates = list((job_dir / "media").glob("**/*.json"))
    merged: dict[str, Any] = {}
    for path in candidates[:20]:
        try:
            data = json.loads(path.read_text(errors="ignore"))
            if isinstance(data, dict):
                for key in (
                    "title", "description", "caption", "date", "username", "user",
                    "author", "id", "post_shortcode", "shortcode", "uploader", "channel"
                ):
                    if key in data and key not in merged:
                        merged[key] = data[key]
        except Exception:
            pass
    return merged


def _try_gallery_dl(url: str, job_dir: Path, browser: str) -> tuple[bool, str]:
    out = job_dir / "media"
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        "gallery-dl",
        "--no-input",
        "--write-metadata",
        "--write-info-json",
        "--filesize-max", f"{MAX_MEDIA_MB}M",
        "--directory", str(out),
        "--cookies-from-browser", browser,
        url,
    ]
    proc = _run(cmd, timeout=240)
    return proc.returncode == 0 and bool(_media_files(job_dir)), (proc.stderr or proc.stdout)[-6000:]


def _try_ytdlp(url: str, job_dir: Path, browser: str) -> tuple[bool, str]:
    out = job_dir / "media"
    out.mkdir(parents=True, exist_ok=True)
    tmpl = str(out / "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--write-info-json",
        "--max-filesize", f"{MAX_MEDIA_MB}M",
        "--cookies-from-browser", browser,
        "-o", tmpl,
        url,
    ]
    proc = _run(cmd, timeout=240)
    return proc.returncode == 0 and bool(_media_files(job_dir)), (proc.stderr or proc.stdout)[-6000:]


def _download_http(url: str, target_stem: Path) -> Path:
    import urllib.request

    with urllib.request.urlopen(url, timeout=90) as resp:
        ctype = resp.headers.get_content_type()
        ext = mimetypes.guess_extension(ctype) or Path(urlparse(url).path).suffix or ".bin"
        target = target_stem.with_suffix(ext)
        limit = MAX_MEDIA_MB * 1024 * 1024
        read = 0
        with target.open("wb") as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                read += len(chunk)
                if read > limit:
                    raise RuntimeError(f"Media exceeds {MAX_MEDIA_MB} MB limit")
                f.write(chunk)
    return target


def _try_cobalt(url: str, job_dir: Path) -> tuple[bool, str]:
    if not COBALT_URL:
        return False, "Cobalt fallback not configured (MEDIAUNLOCK_COBALT_URL is empty)."
    import urllib.request

    body = json.dumps({"url": url, "downloadMode": "auto"}).encode("utf-8")
    req = urllib.request.Request(
        COBALT_URL + "/",
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return False, f"Cobalt request failed: {exc}"

    if not isinstance(data, dict):
        return False, f"Unexpected Cobalt response: {data!r}"
    status = data.get("status")
    out = job_dir / "media"
    out.mkdir(parents=True, exist_ok=True)

    try:
        if status in {"redirect", "tunnel"} and data.get("url"):
            _download_http(data["url"], out / "cobalt-media")
        elif status == "picker" and isinstance(data.get("picker"), list):
            for i, item in enumerate(data["picker"][:20]):
                if isinstance(item, dict) and item.get("url"):
                    _download_http(item["url"], out / f"cobalt-{i:02d}")
        elif status == "local-processing":
            return False, "Cobalt returned local-processing; gallery-dl/yt-dlp should be preferred for this source."
        else:
            return False, f"Cobalt did not return downloadable media: {data!r}"
        return bool(_media_files(job_dir)), ""
    except Exception as exc:
        return False, f"Cobalt media download failed: {exc}"


def _probe_duration(path: Path) -> float:
    proc = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], timeout=20)
    try:
        return max(0.0, float(proc.stdout.strip()))
    except Exception:
        return 0.0


def _make_contact_sheet(job_dir: Path, frame_count: int = 12) -> Path:
    media = _media_files(job_dir)
    if not media:
        raise RuntimeError("No downloaded media found.")

    preview_dir = job_dir / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    sheet = preview_dir / "contact-sheet.jpg"
    if sheet.exists():
        return sheet

    source = media[0]
    suffix = source.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        proc = _run([
            "ffmpeg", "-y", "-i", str(source),
            "-vf", "scale='min(1200,iw)':-2", "-frames:v", "1", "-q:v", "2", str(sheet)
        ], timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg preview failed: {proc.stderr[-1500:]}")
        return sheet

    duration = _probe_duration(source)
    count = max(4, min(frame_count, 16))
    if duration <= 0.5:
        times = [0.0]
    else:
        margin = min(0.4, duration * 0.05)
        usable = max(0.1, duration - 2 * margin)
        times = [margin + usable * i / max(1, count - 1) for i in range(count)]

    frames: list[Path] = []
    for i, t in enumerate(times):
        frame = preview_dir / f"frame-{i:02d}.jpg"
        proc = _run([
            "ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(source),
            "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", str(frame)
        ], timeout=30)
        if proc.returncode == 0 and frame.exists():
            frames.append(frame)
    if not frames:
        raise RuntimeError("Could not extract video frames.")

    cols = 3
    rows = (len(frames) + cols - 1) // cols
    while len(frames) < rows * cols:
        frames.append(frames[-1])
    inputs: list[str] = []
    for frame in frames:
        inputs += ["-i", str(frame)]
    layout = "|".join(f"{c}*640_{r}*360" for r in range(rows) for c in range(cols))
    filters = [
        f"[{i}:v]scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2[v{i}]"
        for i in range(len(frames))
    ]
    filters.append(
        "".join(f"[v{i}]" for i in range(len(frames)))
        + f"xstack=inputs={len(frames)}:layout={layout}[out]"
    )
    proc = _run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(filters), "-map", "[out]", "-q:v", "3", str(sheet)
    ], timeout=90)
    if proc.returncode != 0 or not sheet.exists():
        raise RuntimeError(f"contact sheet failed: {proc.stderr[-2000:]}")
    return sheet


def _manifest(job_dir: Path) -> dict[str, Any]:
    path = job_dir / "manifest.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


@mcp.tool()
def unlock_media(url: str, browser: str = DEFAULT_BROWSER, refresh: bool = False) -> dict[str, Any]:
    """Resolve a public social-media/media URL and prepare a visual preview.

    Use this first for Instagram Reels/posts, TikTok, X, Reddit, YouTube, Vimeo,
    Loom, Pinterest, or direct image/video URLs. Returns a job_id; then call
    get_contact_sheet(job_id) so ChatGPT can visually inspect the item.
    """
    url = _validate_url(url)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    jid = _job_id(url)
    job_dir = JOBS_DIR / jid
    job_dir.mkdir(parents=True, exist_ok=True)

    if refresh:
        shutil.rmtree(job_dir / "media", ignore_errors=True)
        shutil.rmtree(job_dir / "preview", ignore_errors=True)
        (job_dir / "manifest.json").unlink(missing_ok=True)

    existing = _manifest(job_dir)
    if existing and _media_files(job_dir):
        return existing

    attempts: list[dict[str, str]] = []
    success = False
    resolver = ""

    if shutil.which("gallery-dl"):
        ok, log = _try_gallery_dl(url, job_dir, browser)
        attempts.append({"resolver": "gallery-dl", "result": "ok" if ok else "failed", "log": log[-1800:]})
        if ok:
            success, resolver = True, "gallery-dl"

    if not success and shutil.which("yt-dlp"):
        ok, log = _try_ytdlp(url, job_dir, browser)
        attempts.append({"resolver": "yt-dlp", "result": "ok" if ok else "failed", "log": log[-1800:]})
        if ok:
            success, resolver = True, "yt-dlp"

    if not success and COBALT_URL:
        ok, log = _try_cobalt(url, job_dir)
        attempts.append({"resolver": "cobalt-self-hosted", "result": "ok" if ok else "failed", "log": log[-1800:]})
        if ok:
            success, resolver = True, "cobalt-self-hosted"

    if not success:
        return {
            "ok": False,
            "job_id": jid,
            "source_url": url,
            "browser": browser,
            "attempts": attempts,
            "hint": "Instagram often requires logged-in browser cookies. Run `mediaunlock doctor`, then try Safari or Chrome cookies. A self-hosted Cobalt instance can be configured as a final fallback.",
        }

    files = _media_files(job_dir)
    meta = _read_metadata(job_dir)
    try:
        sheet = _make_contact_sheet(job_dir)
        preview_ready = sheet.exists()
    except Exception as exc:
        preview_ready = False
        attempts.append({"resolver": "ffmpeg-preview", "result": "failed", "log": str(exc)})

    manifest = {
        "ok": True,
        "job_id": jid,
        "source_url": url,
        "resolver": resolver,
        "browser": browser,
        "media_count": len(files),
        "media_types": [mimetypes.guess_type(p.name)[0] or p.suffix for p in files[:8]],
        "metadata": meta,
        "preview_ready": preview_ready,
        "attempts": attempts,
        "created_at": int(time.time()),
    }
    (job_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


@mcp.tool()
def get_contact_sheet(job_id: str) -> Image:
    """Return representative frames for an unlocked media job as one image."""
    if not re.fullmatch(r"[0-9a-f]{16}", job_id):
        raise ValueError("Invalid job_id")
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise FileNotFoundError("Unknown job_id. Call unlock_media first.")
    sheet = _make_contact_sheet(job_dir)
    return Image(path=str(sheet))


@mcp.tool()
def job_status(job_id: str) -> dict[str, Any]:
    """Return cached resolver metadata/status for a prior media job."""
    if not re.fullmatch(r"[0-9a-f]{16}", job_id):
        raise ValueError("Invalid job_id")
    job_dir = JOBS_DIR / job_id
    return _manifest(job_dir) or {"ok": False, "job_id": job_id, "status": "not_found"}


if __name__ == "__main__":
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    mcp.run(transport="streamable-http")
