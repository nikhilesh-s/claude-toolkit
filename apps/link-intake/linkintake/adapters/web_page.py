"""Ordinary web page -> title/author/description + readable text. stdlib only."""
from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 link-intake/0.1"
MAX_BYTES = 4 * 1024 * 1024


class FetchError(RuntimeError):
    pass


def fetch(url: str, max_bytes: int = MAX_BYTES, timeout: int = 20) -> tuple[str, bytes, str]:
    """Return (content_type, body, final_url)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.headers.get_content_type(), r.read(max_bytes), r.geturl()
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code} fetching {url}") from None
    except Exception as e:
        raise FetchError(f"fetch failed: {type(e).__name__}: {e}") from None


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe", "template"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.main_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.title = ""
        self._skip = 0
        self._in_main = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag in ("main", "article") or a.get("role") == "main":
            self._in_main += 1
        elif tag in self.BLOCK:
            self._emit("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in ("main", "article") and self._in_main:
            self._in_main -= 1
        elif tag in self.BLOCK:
            self._emit("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self._emit(data)

    def _emit(self, s: str):
        self.parts.append(s)
        if self._in_main:
            self.main_parts.append(s)


def parse_html(body: bytes) -> dict:
    text = body.decode("utf-8", errors="ignore")
    p = _Text()
    try:
        p.feed(text)
    except Exception:
        pass
    raw = "".join(p.main_parts if len("".join(p.main_parts).strip()) > 200 else p.parts)
    raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
    raw = re.sub(r"\n\s*\n+", "\n\n", raw).strip()
    m = p.meta
    return {
        "title": html.unescape((m.get("og:title") or p.title or "").strip()),
        "description": m.get("og:description") or m.get("description") or "",
        "author": m.get("author") or m.get("article:author") or m.get("og:site_name") or "",
        "published": m.get("article:published_time") or m.get("date") or "",
        "site": m.get("og:site_name", ""),
        "text": raw,
    }
