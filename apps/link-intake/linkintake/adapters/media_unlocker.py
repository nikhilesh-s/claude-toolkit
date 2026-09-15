"""Adapter over the existing Media Unlocker MCP (apps/media-unlocker). Calls unlock_media / job_status /
get_contact_sheet over MCP; reads the resolver's info.json from the job dir for caption text.
No gallery-dl / yt-dlp logic lives here."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path

from .. import config


class MediaUnlockerError(RuntimeError):
    pass


def _cfg() -> dict:
    return config.load()["media_unlocker"]


def jobs_dir() -> Path:
    return config.expand(_cfg()["jobs_dir"])


def job_id_for(url: str) -> str:
    # Mirrors server._job_id so we can tell whether a job existed before we touched it.
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]


def job_dir(job_id: str) -> Path:
    return jobs_dir() / job_id


def job_preexisting(url: str) -> bool:
    d = job_dir(job_id_for(url))
    return d.exists() and any((d / "media").glob("*")) if d.exists() else False


async def _call_async(tool: str, args: dict, timeout: int):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    url = _cfg()["mcp_url"]
    async with streamablehttp_client(url, timeout=timedelta(seconds=timeout), sse_read_timeout=timedelta(seconds=timeout)) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return await s.call_tool(tool, args, read_timeout_seconds=timedelta(seconds=timeout))


def _call(tool: str, args: dict, timeout: int = 420):
    try:
        return asyncio.run(_call_async(tool, args, timeout))
    except Exception as exc:  # connection refused, timeouts, tool errors
        raise MediaUnlockerError(f"media-unlocker {tool} failed: {type(exc).__name__}: {str(exc)[:300]}") from None


def _json_result(res) -> dict:
    if getattr(res, "structuredContent", None):
        sc = res.structuredContent
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    for c in res.content:
        if getattr(c, "type", "") == "text":
            try:
                return json.loads(c.text)
            except json.JSONDecodeError:
                return {"ok": False, "raw": c.text}
    return {"ok": False}


def unlock(url: str, browser: str | None = None, refresh: bool = False) -> dict:
    browser = browser or _cfg()["browser"]
    if browser.startswith("chromium:~"):
        browser = "chromium:" + os.path.expanduser(browser[len("chromium:"):])
    manifest = _json_result(_call("unlock_media", {"url": url, "browser": browser, "refresh": refresh}))
    if not manifest.get("ok"):
        attempts = "; ".join(f"{a.get('resolver')}: {a.get('log', '')[-160:].strip()}" for a in manifest.get("attempts", []))
        raise MediaUnlockerError(manifest.get("hint") or "unlock_media returned ok=false" + (f" ({attempts})" if attempts else ""))
    return manifest


def status(job_id: str) -> dict:
    return _json_result(_call("job_status", {"job_id": job_id}, timeout=30))


def contact_sheet(job_id: str) -> bytes:
    res = _call("get_contact_sheet", {"job_id": job_id}, timeout=120)
    for c in res.content:
        if getattr(c, "type", "") == "image":
            return base64.b64decode(c.data)
    local = job_dir(job_id) / "preview" / "contact-sheet.jpg"
    if local.exists():
        return local.read_bytes()
    raise MediaUnlockerError("get_contact_sheet returned no image")


def read_info(job_id: str) -> dict:
    """Merge resolver-written *.json metadata (yt-dlp info.json / gallery-dl metadata) into a small dict."""
    keys = ("title", "fulltitle", "description", "caption", "uploader", "channel", "uploader_id", "upload_date",
            "timestamp", "duration", "like_count", "view_count", "tags", "webpage_url", "categories")
    merged: dict = {}
    for p in sorted((job_dir(job_id) / "media").glob("**/*.json")):
        try:
            data = json.loads(p.read_text(errors="ignore"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for k in keys:
            if data.get(k) not in (None, "", []) and k not in merged:
                merged[k] = data[k]
        node = data.get("node") or {}
        if isinstance(node, dict):  # gallery-dl instagram shape
            edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
            if edges and "description" not in merged:
                merged["description"] = edges[0].get("node", {}).get("text", "")
            owner = node.get("owner") or {}
            if owner.get("username") and "uploader" not in merged:
                merged["uploader"] = owner["username"]
    return merged
