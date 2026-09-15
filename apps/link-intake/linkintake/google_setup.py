"""One-time interactive destination setup. Discovers candidates in the PERSONAL Drive, asks when ambiguous,
never silently picks, and persists exact file/folder IDs to config. Creates only what you confirm."""
from __future__ import annotations

from . import config
from .destinations import DOC_TITLES, SCHOLAR_HEADER, WISHLIST_TAB_TITLE
from .google_api import DOC_MIME, FOLDER_MIME, SHEET_MIME, Google, GoogleError, doc_tabs, doc_url, folder_url, sheet_url


def _ask(prompt: str, default: str = "") -> str:
    v = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return v or default


def _choose(label: str, items: list[dict], g: Google, allow_create: str = "", allow_skip: bool = True) -> dict | None:
    """Present candidates with their Drive path; return the chosen item, {'create': True}, or None."""
    print(f"\n== {label}")
    if not items:
        print("  (no matches)")
    for i, it in enumerate(items, 1):
        print(f"  {i}. {it['name']}   — {g.drive_path(it['id'])}   (modified {it.get('modifiedTime', '')[:10]})")
    opts = []
    if allow_create:
        opts.append(f"c = create '{allow_create}'")
    if allow_skip:
        opts.append("s = skip for now")
    opts.append("id:<drive id> = paste an exact id")
    while True:
        ans = _ask("Pick number, " + ", ".join(opts))
        if ans.lower() == "s" and allow_skip:
            return None
        if ans.lower() == "c" and allow_create:
            return {"create": True}
        if ans.lower().startswith("id:"):
            fid = ans[3:].strip()
            try:
                m = g.drive_meta(fid)
                print(f"  -> {m['name']} ({g.drive_path(fid)})")
                return m
            except GoogleError as exc:
                print(f"  not found: {exc}")
                continue
        if ans.isdigit() and 1 <= int(ans) <= len(items):
            return items[int(ans) - 1]
        print("  ?")


def _pick_folder(g: Google, label: str, name_hint: str) -> str:
    items = g.drive_find_by_name(name_hint, FOLDER_MIME, contains=True)
    while True:
        chosen = _choose(f"{label} folder (searched folders containing '{name_hint}')", items, g)
        if chosen is None:
            other = _ask("Search a different folder name (blank = skip)")
            if not other:
                return ""
            items = g.drive_find_by_name(other, FOLDER_MIME, contains=True)
            continue
        return chosen["id"]


def _pick_or_create_doc(g: Google, label: str, title: str, parent: str) -> str:
    items = g.drive_find_by_name(title, DOC_MIME, parent=parent) or g.drive_find_by_name(title, DOC_MIME, contains=True)
    chosen = _choose(f"{label}: '{title}'" + (f" in {g.drive_path(parent)}" if parent else ""), items, g, allow_create=title)
    if chosen is None:
        return ""
    if chosen.get("create"):
        fid = g.drive_create(title, DOC_MIME, parent)
        print(f"  created {doc_url(fid)}")
        return fid
    return chosen["id"]


def run() -> dict:
    g = Google()
    cfg = config.load()
    t = cfg["google"].setdefault("targets", {})
    print(f"Signed in as {g.account}. Setting up destinations in this account's Drive.\n(Enter = keep current value; s = skip; nothing is created without your confirmation.)")

    # 1. Master Intake
    if not t.get("master_doc") or _ask("Master Intake already set; re-pick? (y/N)", "N").lower() == "y":
        t["master_doc"] = _pick_or_create_doc(g, "MASTER INTAKE doc", DOC_TITLES["master_doc"], "") or t.get("master_doc", "")

    # 2. Wishlist (existing doc) + Intake Staging tab
    if not t.get("wishlist_doc") or _ask("Wishlist doc already set; re-pick? (y/N)", "N").lower() == "y":
        items = g.drive_find_by_name("Wish", DOC_MIME, contains=True)
        chosen = _choose("WISHLIST: your EXISTING wishlist doc (never created here)", items, g)
        if chosen:
            t["wishlist_doc"] = chosen["id"]
    if t.get("wishlist_doc"):
        tabs = doc_tabs(g.doc_get(t["wishlist_doc"]))
        existing = [x for x in tabs if x["title"].strip().lower() == WISHLIST_TAB_TITLE.lower()]
        if existing:
            t["wishlist_tab_id"] = existing[0]["id"]
            print(f"  Wishlist tab '{WISHLIST_TAB_TITLE}' found ({t['wishlist_tab_id']}).")
        elif _ask(f"  Create tab '{WISHLIST_TAB_TITLE}' at the end of the Wishlist doc (other tabs untouched)? (Y/n)", "Y").lower() != "n":
            t["wishlist_tab_id"] = g.doc_add_tab(t["wishlist_doc"], WISHLIST_TAB_TITLE)
            print(f"  created tab {t['wishlist_tab_id']}")

    # 3. College Applications folder -> Supplement Inspiration Bank
    if not t.get("college_folder"):
        t["college_folder"] = _pick_folder(g, "COLLEGE APPLICATIONS", "College App")
    if t.get("college_folder") and not t.get("supplement_doc"):
        t["supplement_doc"] = _pick_or_create_doc(g, "SUPPLEMENT IDEAS doc", DOC_TITLES["supplement_doc"], t["college_folder"])

    # 4. Media folder -> Design Inspiration Bank
    if not t.get("media_folder"):
        t["media_folder"] = _pick_folder(g, "MEDIA", "Media")
    if not t.get("design_doc"):
        t["design_doc"] = _pick_or_create_doc(g, "DESIGN INSPO doc", DOC_TITLES["design_doc"], t.get("media_folder", ""))

    # 5. Personal Instagram Inspiration (personal Drive root unless you pick a folder)
    if not t.get("personal_ig_doc"):
        t["personal_ig_doc"] = _pick_or_create_doc(g, "PERSONAL INSTAGRAM INSPIRATION doc", DOC_TITLES["personal_ig_doc"], "")

    # 6. Scholarships folder inside College Applications -> Scholarship Tracker sheet
    if t.get("college_folder") and not t.get("scholarships_folder"):
        items = g.drive_find_by_name("Scholarship", FOLDER_MIME, parent=t["college_folder"], contains=True)
        chosen = _choose("SCHOLARSHIPS folder inside College Applications", items, g, allow_create="Scholarships")
        if chosen and chosen.get("create"):
            t["scholarships_folder"] = g.drive_create("Scholarships", FOLDER_MIME, t["college_folder"])
            print(f"  created {folder_url(t['scholarships_folder'])}")
        elif chosen:
            t["scholarships_folder"] = chosen["id"]
    if t.get("scholarships_folder") and not t.get("scholarship_sheet"):
        items = g.drive_find_by_name("", SHEET_MIME, parent=t["scholarships_folder"], contains=True)
        chosen = _choose("SCHOLARSHIP TRACKER sheet (existing sheets in that folder)", items, g, allow_create=DOC_TITLES["scholarship_sheet"])
        try:
            if chosen and chosen.get("create"):
                t["scholarship_sheet"] = g.sheet_create(DOC_TITLES["scholarship_sheet"], t["scholarships_folder"], SCHOLAR_HEADER)
                print(f"  created {sheet_url(t['scholarship_sheet'])}")
            elif chosen:
                t["scholarship_sheet"] = chosen["id"]
                if not g.sheet_values(t["scholarship_sheet"], "A1:A1"):
                    g.sheet_append(t["scholarship_sheet"], [SCHOLAR_HEADER])
        except GoogleError as exc:
            if exc.sheets_api_disabled:
                print("  Google Sheets API is not enabled on your Cloud project. Scholarships stay pending until you enable it, then re-run google-setup.")
            else:
                print(f"  sheet step failed: {exc}")

    config.save(cfg)
    print("\nSaved destination IDs to", config.CONFIG_PATH)
    for k, v in t.items():
        print(f"  {k:20s} {v or '(not set)'}")
    return t
