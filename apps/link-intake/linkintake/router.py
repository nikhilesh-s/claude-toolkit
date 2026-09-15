"""Source classification + URL canonicalization. Platform is metadata; source_class routes."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SOURCE_CLASSES = ("google_workspace", "social_media", "video", "web_page", "direct_file", "unknown")

_TRACKING = re.compile(r"^(utm_|igsh|igshid|igsi|fbclid|gclid|mc_cid|mc_eid|ref_src|ref_url|si$|feature$|_branch)")
_FILE_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|webp|heic|mp4|mov|m4v|webm|mp3|m4a|wav|zip|csv|docx?|pptx?|xlsx?)$", re.I)

_SOCIAL = {
    "instagram.com": "instagram", "tiktok.com": "tiktok", "x.com": "x", "twitter.com": "x",
    "reddit.com": "reddit", "redd.it": "reddit", "pinterest.com": "pinterest", "pin.it": "pinterest",
    "threads.net": "threads", "threads.com": "threads", "facebook.com": "facebook", "fb.watch": "facebook",
}
_WWW = {"instagram.com", "tiktok.com", "reddit.com", "pinterest.com", "facebook.com", "threads.net", "threads.com"}
_VIDEO = {"youtube.com": "youtube", "youtu.be": "youtube", "vimeo.com": "vimeo", "loom.com": "loom"}
_GOOGLE = {"docs.google.com": "google_docs", "drive.google.com": "google_drive"}


def _bare(host: str) -> str:
    for pre in ("www.", "m.", "mobile."):
        if host.startswith(pre):
            return host[len(pre):]
    return host


def _match(host: str, table: dict) -> str | None:
    for dom, name in table.items():
        if host == dom or host.endswith("." + dom):
            return name
    return None


def canonicalize(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    p = urlparse(url)
    host = (p.hostname or "").lower()
    path = p.path or "/"
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _TRACKING.match(k)]
    bare = _bare(host)

    if bare == "youtu.be":
        return f"https://www.youtube.com/watch?v={path.strip('/').split('/')[0]}"
    if bare == "youtube.com":
        if (m := re.match(r"^/shorts/([^/]+)", path)):
            return f"https://www.youtube.com/watch?v={m.group(1)}"
        if path == "/watch":
            return "https://www.youtube.com/watch?" + urlencode([(k, v) for k, v in query if k in {"v", "t"}])
        host = "www.youtube.com"
    elif _match(bare, _SOCIAL):
        query = []  # social share params are tracking only
        host = ("www." + bare) if bare in _WWW else bare
        if bare in {"instagram.com", "tiktok.com"}:
            path = path.rstrip("/") + "/"
    if path != "/" and path.endswith("/") and bare not in {"instagram.com", "tiktok.com"}:
        path = path.rstrip("/")
    return urlunparse(((p.scheme or "https").lower(), host, path, "", urlencode(query), ""))


def classify(url: str) -> tuple[str, str]:
    """Return (source_class, platform)."""
    host = _bare((urlparse(url).hostname or "").lower())
    path = urlparse(url).path or ""
    if not host:
        return "unknown", "unknown"
    if (g := _match(host, _GOOGLE)):
        if host == "docs.google.com":
            kind = path.split("/")[1] if path.count("/") >= 1 else ""
            return "google_workspace", {"document": "google_docs", "spreadsheets": "google_sheets",
                                        "presentation": "google_slides", "forms": "google_forms"}.get(kind, "google_docs")
        return "google_workspace", g
    if (s := _match(host, _SOCIAL)):
        return "social_media", s
    if (v := _match(host, _VIDEO)):
        return "video", v
    if _FILE_EXT.search(path):
        return "direct_file", host
    return "web_page", host
