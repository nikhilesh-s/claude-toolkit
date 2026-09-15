"""Google Docs / Sheets / Slides / Drive links -> text. Read-only. Uses the same creds as the exporters."""
from __future__ import annotations

import re

from ..google_api import Google, doc_text

_ID = re.compile(r"/(?:document|spreadsheets|presentation|file|forms)/(?:u/\d+/)?d/([A-Za-z0-9_-]+)")


def parse(url: str) -> tuple[str, str]:
    m = _ID.search(url) or re.search(r"[?&]id=([A-Za-z0-9_-]+)", url)
    if not m:
        raise ValueError("Could not find a Google file id in the URL")
    kind = "drive"
    for k in ("document", "spreadsheets", "presentation", "forms"):
        if f"/{k}/" in url:
            kind = k
    return kind, m.group(1)


def read(url: str, max_chars: int = 20000) -> dict:
    kind, fid = parse(url)
    g = Google()
    if kind == "drive":
        meta = g.drive_meta(fid)
        mime = meta.get("mimeType", "")
        kind = {"application/vnd.google-apps.document": "document", "application/vnd.google-apps.spreadsheet": "spreadsheets",
                "application/vnd.google-apps.presentation": "presentation"}.get(mime, "drive")
        if kind == "drive":
            return {"title": meta.get("name", ""), "creator": (meta.get("owners") or [{}])[0].get("emailAddress", ""),
                    "published": meta.get("modifiedTime", ""), "text": f"[Drive file, {mime}] {meta.get('name', '')}"}
    if kind == "document":
        doc = g.doc_get(fid)
        return {"title": doc.get("title", ""), "creator": "", "published": "", "text": doc_text(doc)[:max_chars]}
    if kind == "spreadsheets":
        meta = g.sheet_get(fid)
        rows = g.sheet_values(fid)
        text = "\n".join(" | ".join(r) for r in rows)
        return {"title": meta.get("properties", {}).get("title", ""), "creator": "", "published": "", "text": text[:max_chars]}
    if kind == "presentation":
        pres = g.slides_get(fid)
        out = []
        for i, slide in enumerate(pres.get("slides", []), 1):
            runs = []
            for el in slide.get("pageElements", []):
                for p in el.get("shape", {}).get("text", {}).get("textElements", []):
                    runs.append(p.get("textRun", {}).get("content", ""))
            out.append(f"--- Slide {i}\n" + "".join(runs).strip())
        return {"title": pres.get("title", ""), "creator": "", "published": "", "text": "\n".join(out)[:max_chars]}
    meta = g.drive_meta(fid)
    return {"title": meta.get("name", ""), "creator": "", "published": "", "text": f"[{kind}] {meta.get('name', '')}"}
