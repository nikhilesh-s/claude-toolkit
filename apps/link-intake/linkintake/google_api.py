"""Minimal Google Docs/Sheets/Drive REST client on stdlib. Token JSON = the shape workspace-mcp
(gswitch) stores: client_id, client_secret, refresh_token, token_uri. No credentials in code."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import config

DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"


class GoogleError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"Google API {status}: {body[:300]}")
        self.status = status


def find_creds_path(cfg: dict | None = None) -> Path | None:
    cfg = cfg or config.load()
    explicit = cfg["google"].get("creds_path")
    if explicit:
        return config.expand(explicit)
    own = config.STATE_DIR / "google-creds.json"
    return own if own.exists() else None


class Google:
    def __init__(self, creds_path: Path | None = None):
        self.path = creds_path or find_creds_path()
        if not self.path or not self.path.exists():
            raise GoogleError(401, "No Google credentials for the optional REST exporter (google.export_mode=rest needs google.creds_path).")
        self.creds = json.loads(self.path.read_text())
        self._token = self.creds.get("token", "")
        self._exp = 0.0
        self.account = self.path.stem if "@" in self.path.stem else ""

    def token(self) -> str:
        if self._token and time.time() < self._exp:
            return self._token
        body = urllib.parse.urlencode({
            "client_id": self.creds["client_id"], "client_secret": self.creds["client_secret"],
            "refresh_token": self.creds["refresh_token"], "grant_type": "refresh_token",
        }).encode()
        req = urllib.request.Request(self.creds.get("token_uri", "https://oauth2.googleapis.com/token"), data=body)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise GoogleError(e.code, e.read().decode(errors="ignore")) from None
        self._token = data["access_token"]
        self._exp = time.time() + int(data.get("expires_in", 3600)) - 60
        return self._token

    def request(self, method: str, url: str, body: dict | None = None, params: dict | None = None) -> dict:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + self.token(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise GoogleError(e.code, e.read().decode(errors="ignore")) from None

    # ---- Drive
    def drive_find(self, name: str, mime: str, parent: str = "") -> str | None:
        q = f"name = '{name}' and mimeType = '{mime}' and trashed = false"
        if parent:
            q += f" and '{parent}' in parents"
        res = self.request("GET", "https://www.googleapis.com/drive/v3/files", params={"q": q, "fields": "files(id,name)", "pageSize": 5})
        files = res.get("files", [])
        return files[0]["id"] if files else None

    def drive_create(self, name: str, mime: str, parent: str = "") -> str:
        body = {"name": name, "mimeType": mime}
        if parent:
            body["parents"] = [parent]
        return self.request("POST", "https://www.googleapis.com/drive/v3/files", body=body, params={"fields": "id"})["id"]

    def find_or_create(self, name: str, mime: str, parent: str = "") -> str:
        return self.drive_find(name, mime, parent) or self.drive_create(name, mime, parent)

    def drive_meta(self, file_id: str) -> dict:
        return self.request("GET", f"https://www.googleapis.com/drive/v3/files/{file_id}",
                            params={"fields": "id,name,mimeType,owners(emailAddress),modifiedTime,webViewLink", "supportsAllDrives": "true"})

    # ---- Docs
    def doc_get(self, doc_id: str) -> dict:
        return self.request("GET", f"https://docs.googleapis.com/v1/documents/{doc_id}", params={"includeTabsContent": "true"})

    def doc_batch(self, doc_id: str, requests: list[dict]) -> dict:
        return self.request("POST", f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate", body={"requests": requests})

    def doc_append_text(self, doc_id: str, text: str, tab_id: str = "") -> None:
        """Append plain text at the end of the body (or the given tab). Narrow, idempotency is the caller's job."""
        loc: dict = {"segmentId": ""}
        if tab_id:
            loc["tabId"] = tab_id
        self.doc_batch(doc_id, [{"insertText": {"text": text, "endOfSegmentLocation": loc}}])

    def doc_append_table_row(self, doc_id: str, cells: list[str], header: list[str], tab_id: str = "",
                             link_columns: tuple[int, ...] = ()) -> None:
        """Append one row to the last table in the doc/tab; create the table (with header) if absent.
        Fresh read before every mutation; cell writes applied highest index first (safe-edit protocol)."""
        body = self._body(self.doc_get(doc_id), tab_id)
        tables = [e for e in body.get("content", []) if "table" in e]
        loc: dict = {"segmentId": ""}
        if tab_id:
            loc["tabId"] = tab_id
        if not tables:
            self.doc_batch(doc_id, [{"insertTable": {"rows": 1, "columns": len(header), "endOfSegmentLocation": loc}}])
            body = self._body(self.doc_get(doc_id), tab_id)
            tables = [e for e in body.get("content", []) if "table" in e]
            self._fill_row(doc_id, tables[-1], -1, header, tab_id, ())
            body = self._body(self.doc_get(doc_id), tab_id)
            tables = [e for e in body.get("content", []) if "table" in e]
        table = tables[-1]
        last_row = len(table["table"]["tableRows"]) - 1
        start = {"index": table["startIndex"]}
        if tab_id:
            start["tabId"] = tab_id
        self.doc_batch(doc_id, [{"insertTableRow": {
            "tableCellLocation": {"tableStartLocation": start, "rowIndex": last_row, "columnIndex": 0},
            "insertBelow": True}}])
        body = self._body(self.doc_get(doc_id), tab_id)
        table = [e for e in body.get("content", []) if "table" in e][-1]
        self._fill_row(doc_id, table, -1, cells, tab_id, link_columns)

    def _fill_row(self, doc_id: str, table: dict, row_idx: int, values: list[str], tab_id: str, link_columns) -> None:
        row = table["table"]["tableRows"][row_idx]
        writes = []
        for ci, cell in enumerate(row["tableCells"]):
            text = (values[ci] if ci < len(values) else "") or ""
            if not text:
                continue
            idx = cell["content"][0]["startIndex"]
            writes.append((idx, text, ci in link_columns))
        reqs: list[dict] = []
        for idx, text, is_link in sorted(writes, key=lambda w: -w[0]):
            loc = {"index": idx}
            if tab_id:
                loc["tabId"] = tab_id
            reqs.append({"insertText": {"text": text, "location": loc}})
            if is_link and text.startswith("http"):
                rng = {"startIndex": idx, "endIndex": idx + len(text)}
                if tab_id:
                    rng["tabId"] = tab_id
                reqs.append({"updateTextStyle": {"range": rng, "textStyle": {"link": {"url": text}}, "fields": "link"}})
        if reqs:
            self.doc_batch(doc_id, reqs)

    @staticmethod
    def _body(doc: dict, tab_id: str = "") -> dict:
        if tab_id:
            for tab in _walk_tabs(doc.get("tabs", [])):
                if tab["tabProperties"]["tabId"] == tab_id:
                    return tab["documentTab"]["body"]
            raise GoogleError(404, f"tab {tab_id} not found")
        if doc.get("tabs"):
            return doc["tabs"][0]["documentTab"]["body"]
        return doc.get("body", {})

    # ---- Sheets
    def sheet_append(self, sheet_id: str, values: list[list[str]], rng: str = "A1") -> None:
        self.request("POST", f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{urllib.parse.quote(rng)}:append",
                     body={"values": values}, params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"})

    def sheet_values(self, sheet_id: str, rng: str = "A1:Z200") -> list[list[str]]:
        return self.request("GET", f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{urllib.parse.quote(rng)}").get("values", [])

    def sheet_get(self, sheet_id: str) -> dict:
        return self.request("GET", f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}", params={"fields": "properties.title,sheets.properties"})

    # ---- Slides
    def slides_get(self, pres_id: str) -> dict:
        return self.request("GET", f"https://slides.googleapis.com/v1/presentations/{pres_id}")


def _walk_tabs(tabs: list[dict]):
    for t in tabs:
        yield t
        yield from _walk_tabs(t.get("childTabs", []))


def doc_text(doc: dict, tab_id: str = "") -> str:
    """Flatten a Docs API document (all tabs unless tab_id) to plain text."""
    bodies = []
    if doc.get("tabs"):
        for t in _walk_tabs(doc["tabs"]):
            if tab_id and t["tabProperties"]["tabId"] != tab_id:
                continue
            bodies.append(("## " + t["tabProperties"].get("title", ""), t["documentTab"]["body"]))
    else:
        bodies.append(("", doc.get("body", {})))
    out = []
    for title, body in bodies:
        if title:
            out.append(title)
        out.append(_elements_text(body.get("content", [])))
    return "\n".join(out)


def _elements_text(elements: list[dict]) -> str:
    parts = []
    for el in elements:
        if "paragraph" in el:
            parts.append("".join(r.get("textRun", {}).get("content", "") for r in el["paragraph"].get("elements", [])))
        elif "table" in el:
            for row in el["table"]["tableRows"]:
                parts.append(" | ".join(_elements_text(c.get("content", [])).strip() for c in row["tableCells"]) + "\n")
    return "".join(parts)


def doc_url(doc_id: str) -> str:
    return f"https://docs.google.com/document/d/{doc_id}/edit"


def sheet_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
