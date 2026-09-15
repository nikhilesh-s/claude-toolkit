"""Minimal Google Docs/Sheets/Drive REST client on stdlib.

Auth lives in ~/.link-intake/google/: client.json (Desktop OAuth client id/secret) and token.json (the
personal account's refresh token). Nothing here reads gswitch, workspace-mcp, or any tunnel. Every request
has a timeout so a slow Google never hangs a Raycast save."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import config

DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_DIR = config.STATE_DIR / "google"
CLIENT_PATH = GOOGLE_DIR / "client.json"
TOKEN_PATH = GOOGLE_DIR / "token.json"
DEFAULT_TIMEOUT = 15


class GoogleError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"Google API {status}: {body[:300]}")
        self.status = status
        self.body = body

    @property
    def sheets_api_disabled(self) -> bool:
        return self.status == 403 and "sheets.googleapis.com" in self.body


def is_configured() -> bool:
    return CLIENT_PATH.exists() and TOKEN_PATH.exists()


class Google:
    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        if not is_configured():
            raise GoogleError(401, "Google not authorized. Run `linkintake google-auth` (personal account).")
        self.client = json.loads(CLIENT_PATH.read_text())
        self.tok = json.loads(TOKEN_PATH.read_text())
        self.account = self.tok.get("email", "")
        self.timeout = timeout
        self._access = self.tok.get("token", "")
        self._exp = float(self.tok.get("expires_at", 0))

    # ---- auth
    def token(self) -> str:
        if self._access and time.time() < self._exp - 60:
            return self._access
        body = urllib.parse.urlencode({
            "client_id": self.client["client_id"], "client_secret": self.client["client_secret"],
            "refresh_token": self.tok["refresh_token"], "grant_type": "refresh_token"}).encode()
        req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise GoogleError(e.code, "token refresh failed: " + e.read().decode(errors="ignore")) from None
        except Exception as e:
            raise GoogleError(0, f"token refresh unreachable: {type(e).__name__}: {e}") from None
        self._access = data["access_token"]
        self._exp = time.time() + int(data.get("expires_in", 3600))
        self.tok.update({"token": self._access, "expires_at": self._exp})
        TOKEN_PATH.write_text(json.dumps(self.tok, indent=2))
        TOKEN_PATH.chmod(0o600)
        return self._access

    def request(self, method: str, url: str, body: dict | None = None, params: dict | None = None) -> dict:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + self.token(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise GoogleError(e.code, e.read().decode(errors="ignore")) from None
        except Exception as e:  # timeouts, DNS, offline
            raise GoogleError(0, f"unreachable: {type(e).__name__}: {e}") from None

    # ---- Drive
    def drive_search(self, q: str, fields: str = "id,name,mimeType,parents,modifiedTime", page_size: int = 25) -> list[dict]:
        res = self.request("GET", "https://www.googleapis.com/drive/v3/files",
                           params={"q": q + " and trashed = false", "fields": f"files({fields})", "pageSize": page_size,
                                   "orderBy": "modifiedTime desc", "includeItemsFromAllDrives": "true", "supportsAllDrives": "true"})
        return res.get("files", [])

    def drive_find_by_name(self, name: str, mime: str, parent: str = "", contains: bool = False) -> list[dict]:
        q = f"name {'contains' if contains else '='} '{name.replace(chr(39), chr(92) + chr(39))}' and mimeType = '{mime}'"
        if parent:
            q += f" and '{parent}' in parents"
        return self.drive_search(q)

    def drive_create(self, name: str, mime: str, parent: str = "") -> str:
        body = {"name": name, "mimeType": mime}
        if parent:
            body["parents"] = [parent]
        return self.request("POST", "https://www.googleapis.com/drive/v3/files", body=body, params={"fields": "id"})["id"]

    def drive_meta(self, file_id: str) -> dict:
        return self.request("GET", f"https://www.googleapis.com/drive/v3/files/{file_id}",
                            params={"fields": "id,name,mimeType,parents,owners(emailAddress),modifiedTime,webViewLink", "supportsAllDrives": "true"})

    def drive_path(self, file_id: str, depth: int = 4) -> str:
        """'My Drive / College Applications / Scholarships' for display during setup."""
        parts = []
        cur = file_id
        for _ in range(depth):
            try:
                m = self.drive_meta(cur)
            except GoogleError:
                break
            parts.append(m.get("name", "?"))
            parents = m.get("parents") or []
            if not parents:
                break
            cur = parents[0]
        return " / ".join(reversed(parts))

    # ---- Docs
    def doc_get(self, doc_id: str) -> dict:
        return self.request("GET", f"https://docs.googleapis.com/v1/documents/{doc_id}", params={"includeTabsContent": "true"})

    def doc_batch(self, doc_id: str, requests: list[dict]) -> dict:
        return self.request("POST", f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate", body={"requests": requests})

    def doc_add_tab(self, doc_id: str, title: str) -> str:
        """Add a top-level tab at the end; returns its tabId. Other tabs untouched."""
        n = len(self.doc_get(doc_id).get("tabs", []))
        res = self.doc_batch(doc_id, [{"addDocumentTab": {"tabProperties": {"title": title, "index": max(n, 1)}}}])
        for reply in res.get("replies", []):
            for key in ("addDocumentTab", "createDocumentTab"):
                if key in reply:
                    return reply[key].get("tabProperties", {}).get("tabId", "")
        for t in _walk_tabs(self.doc_get(doc_id).get("tabs", [])):  # fallback: find by title
            if t["tabProperties"].get("title") == title:
                return t["tabProperties"]["tabId"]
        raise GoogleError(500, "addDocumentTab returned no tabId")

    def doc_append_text(self, doc_id: str, text: str, tab_id: str = "") -> None:
        loc: dict = {"segmentId": ""}
        if tab_id:
            loc["tabId"] = tab_id
        self.doc_batch(doc_id, [{"insertText": {"text": text, "endOfSegmentLocation": loc}}])

    def doc_append_table_row(self, doc_id: str, cells: list[str], header: list[str], tab_id: str = "",
                             link_columns: tuple[int, ...] = ()) -> None:
        """Append one row to the last table in the doc/tab; create the table with a header if absent.
        Fresh read before every mutation; writes applied highest index first (safe-edit protocol)."""
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
            "tableCellLocation": {"tableStartLocation": start, "rowIndex": last_row, "columnIndex": 0}, "insertBelow": True}}])
        body = self._body(self.doc_get(doc_id), tab_id)
        table = [e for e in body.get("content", []) if "table" in e][-1]
        self._fill_row(doc_id, table, -1, cells, tab_id, link_columns)

    def doc_update_table_row(self, doc_id: str, needle: str, cells: list[str], tab_id: str = "", link_columns: tuple[int, ...] = ()) -> bool:
        """Rewrite the cells of the last table row whose text contains `needle` (a Record ID). Fresh read, then
        delete+insert per cell from highest index down. Returns False if no such row (caller appends instead)."""
        body = self._body(self.doc_get(doc_id), tab_id)
        tables = [e for e in body.get("content", []) if "table" in e]
        if not tables:
            return False
        table = tables[-1]
        target = None
        for row in table["table"]["tableRows"]:
            if any(needle in _elements_text(c.get("content", [])) for c in row["tableCells"]):
                target = row
        if target is None:
            return False
        reqs: list[dict] = []
        for ci in sorted(range(len(target["tableCells"])), reverse=True):
            cell = target["tableCells"][ci]
            text = (cells[ci] if ci < len(cells) else "") or ""
            start, end = cell["startIndex"] + 1, cell["endIndex"] - 1  # keep the cell's final newline
            loc = {"index": start}
            rng = {"startIndex": start, "endIndex": end}
            if tab_id:
                loc["tabId"] = tab_id
                rng["tabId"] = tab_id
            if end > start:
                reqs.append({"deleteContentRange": {"range": rng}})
            if text:
                reqs.append({"insertText": {"text": text, "location": loc}})
                if ci in link_columns and text.startswith("http"):
                    lr = {"startIndex": start, "endIndex": start + len(text.split("\n")[0])}
                    if tab_id:
                        lr["tabId"] = tab_id
                    reqs.append({"updateTextStyle": {"range": lr, "textStyle": {"link": {"url": text.split("\n")[0]}}, "fields": "link"}})
        if reqs:
            self.doc_batch(doc_id, reqs)
        return True

    def doc_delete_table_row(self, doc_id: str, needle: str, tab_id: str = "", exclude: tuple[str, ...] = ()) -> bool:
        """Delete the last table row (not the header) whose text contains needle and none of `exclude`.
        Idempotent: False if absent."""
        body = self._body(self.doc_get(doc_id), tab_id)
        tables = [e for e in body.get("content", []) if "table" in e]
        if not tables:
            return False
        table = tables[-1]
        idx = None
        for i, row in enumerate(table["table"]["tableRows"]):
            text = " ".join(_elements_text(c.get("content", [])) for c in row["tableCells"])
            if i > 0 and needle in text and not any(x in text for x in exclude):
                idx = i
        if idx is None:
            return False
        start = {"index": table["startIndex"]}
        if tab_id:
            start["tabId"] = tab_id
        self.doc_batch(doc_id, [{"deleteTableRow": {"tableCellLocation": {"tableStartLocation": start, "rowIndex": idx, "columnIndex": 0}}}])
        return True

    def _fill_row(self, doc_id: str, table: dict, row_idx: int, values: list[str], tab_id: str, link_columns) -> None:
        row = table["table"]["tableRows"][row_idx]
        writes = []
        for ci, cell in enumerate(row["tableCells"]):
            text = (values[ci] if ci < len(values) else "") or ""
            if text:
                writes.append((cell["content"][0]["startIndex"], text, ci in link_columns))
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
            raise GoogleError(404, f"tab {tab_id} not found in document")
        if doc.get("tabs"):
            return doc["tabs"][0]["documentTab"]["body"]
        return doc.get("body", {})

    # ---- Sheets
    def sheet_append(self, sheet_id: str, values: list[list[str]], rng: str = "A1") -> None:
        self.request("POST", f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{urllib.parse.quote(rng)}:append",
                     body={"values": values}, params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"})

    def sheet_update_row(self, sheet_id: str, row_number: int, values: list[str]) -> None:
        last = chr(ord("A") + len(values) - 1)
        rng = f"A{row_number}:{last}{row_number}"
        self.request("PUT", f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{urllib.parse.quote(rng)}",
                     body={"values": [values]}, params={"valueInputOption": "USER_ENTERED"})

    def sheet_delete_row(self, sheet_id: str, row_number: int) -> None:
        """Delete one data row (1-based, never the header) from the first sheet tab."""
        if row_number <= 1:
            return
        gid = self.sheet_get(sheet_id)["sheets"][0]["properties"]["sheetId"]
        self.request("POST", f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}:batchUpdate", body={"requests": [
            {"deleteDimension": {"range": {"sheetId": gid, "dimension": "ROWS", "startIndex": row_number - 1, "endIndex": row_number}}}]})

    def sheet_values(self, sheet_id: str, rng: str = "A1:Z500") -> list[list[str]]:
        return self.request("GET", f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{urllib.parse.quote(rng)}").get("values", [])

    def sheet_get(self, sheet_id: str) -> dict:
        return self.request("GET", f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}", params={"fields": "properties.title,sheets.properties"})

    def sheet_create(self, title: str, parent: str, header: list[str]) -> str:
        sid = self.drive_create(title, SHEET_MIME, parent)
        self.sheet_append(sid, [header])
        return sid

    # ---- Slides (read-only, for the google_workspace source adapter)
    def slides_get(self, pres_id: str) -> dict:
        return self.request("GET", f"https://slides.googleapis.com/v1/presentations/{pres_id}")


def _walk_tabs(tabs: list[dict]):
    for t in tabs:
        yield t
        yield from _walk_tabs(t.get("childTabs", []))


def doc_tabs(doc: dict) -> list[dict]:
    return [{"id": t["tabProperties"]["tabId"], "title": t["tabProperties"].get("title", "")} for t in _walk_tabs(doc.get("tabs", []))]


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


def doc_url(doc_id: str, tab_id: str = "") -> str:
    return f"https://docs.google.com/document/d/{doc_id}/edit" + (f"?tab={tab_id}" if tab_id else "")


def sheet_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"


def folder_url(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}"
