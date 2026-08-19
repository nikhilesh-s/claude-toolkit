#!/usr/bin/env python3
"""
Builds skills-catalog.html: a single self-contained interactive catalog of
every skill and plugin in this toolkit. No server, no CDN, no build step —
open the file in a browser.

Usage:
    uv run python scripts/build_catalog.py          # writes skills-catalog.html
Run after adding, removing, or updating a skill or plugin.
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from categorize_skills import CATEGORIES, SOURCES, DEFAULT_SOURCE  # noqa: E402

SKILLS_DIR = os.path.join(REPO, "skills")
TSV = os.path.join(REPO, "scripts", "skill_index.tsv")
OUT = os.path.join(REPO, "skills-catalog.html")

CAT_BY_SKILL = {n: cat for cat, names in CATEGORIES.items() for n in names}


def parse_skill_md(path):
    """Return (frontmatter dict, body str) for one SKILL.md."""
    text = open(path, encoding="utf-8", errors="replace").read()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    fm, body = {}, m.group(2).strip()
    key = None
    for line in m.group(1).split("\n"):
        km = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
        if km:
            key = km.group(1)
            fm[key] = km.group(2).strip()
        elif key and line.startswith(" "):
            fm[key] += " " + line.strip()
    return fm, body


def collect():
    entries = []
    seen_skills = set()
    for name in sorted(os.listdir(SKILLS_DIR)):
        md = os.path.join(SKILLS_DIR, name, "SKILL.md")
        if not os.path.isfile(md):
            continue
        fm, body = parse_skill_md(md)
        entries.append({
            "kind": "skill",
            "name": name,
            "category": CAT_BY_SKILL.get(name, "Uncategorized"),
            "source": SOURCES.get(name, DEFAULT_SOURCE),
            "desc": fm.get("description", ""),
            "body": body,
        })
        seen_skills.add(name)
    # plugins (and any machine skills not in this repo) from the which-skill index
    for line in open(TSV, encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        kind, name, source, desc = (line.rstrip("\n").split("\t") + ["", "", "", ""])[:4]
        if kind == "plugin":
            entries.append({
                "kind": "plugin", "name": name, "category": "Plugins",
                "source": source, "desc": desc, "body": None,
            })
    return entries


def main():
    entries = collect()
    data = json.dumps(entries, ensure_ascii=False)
    html = render(data, entries)
    open(OUT, "w", encoding="utf-8").write(html)
    n_s = sum(1 for e in entries if e["kind"] == "skill")
    n_p = len(entries) - n_s
    print(f"wrote {OUT}: {n_s} skills + {n_p} plugins")


def render(data_json, entries):
    # UI arrives in later iterations; emit a valid page with raw data for now.
    return ("<!doctype html><meta charset='utf-8'><title>Claude Toolkit Catalog</title>"
            f"<script>const DATA = {data_json};</script>"
            "<body><p>catalog UI pending</p></body>")


if __name__ == "__main__":
    main()
