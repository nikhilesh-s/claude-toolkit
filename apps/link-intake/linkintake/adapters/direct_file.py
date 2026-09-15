"""PDF / image / video / download URLs. PDFs are passed to the extractor as a document; images and
videos go through Media Unlocker for a contact sheet."""
from __future__ import annotations

import urllib.request
from pathlib import Path

from .. import config
from .web_page import UA, FetchError

MAX_PDF = 30 * 1024 * 1024


def head(url: str) -> dict:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return {"content_type": r.headers.get_content_type(), "size": int(r.headers.get("Content-Length") or 0), "url": r.geturl()}
    except Exception:
        return {"content_type": "", "size": 0, "url": url}


def download_pdf(url: str, record_id: str) -> Path:
    tmp = config.STATE_DIR / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    target = tmp / f"{record_id}.pdf"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, target.open("wb") as f:
            read = 0
            while chunk := r.read(1 << 20):
                read += len(chunk)
                if read > MAX_PDF:
                    raise FetchError("PDF exceeds 30 MB")
                f.write(chunk)
    except FetchError:
        raise
    except Exception as e:
        raise FetchError(f"pdf download failed: {e}") from None
    return target
