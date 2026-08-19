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
from categorize_skills import (  # noqa: E402
    CATEGORIES, SOURCE_OVERRIDES as SOURCES, DEFAULT_SOURCE,
    GSTACK_ROOT, GSTACK_EXTRA_FILES,
)

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
        if name in GSTACK_EXTRA_FILES:
            continue
        if name != "gstack" and os.path.realpath(md).startswith(GSTACK_ROOT + os.sep):
            continue  # gstack facets, not independent skills — same rule as categorize
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
    return TEMPLATE.replace("__DATA__", data_json)


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude Toolkit Catalog</title>
<style>
  :root {
    --bg: #0f1115; --panel: #171a21; --panel2: #1d212b; --text: #e6e9ef;
    --muted: #9aa3b2; --line: #2a2f3a; --accent: #d97757; --chip: #232836;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg:#f6f5f2; --panel:#ffffff; --panel2:#f0eeea; --text:#1f2328;
            --muted:#5c6570; --line:#dcd9d3; --accent:#c05d3d; --chip:#eceae5; }
  }
  * { box-sizing: border-box; margin: 0; }
  body { background: var(--bg); color: var(--text);
         font: 15px/1.5 ui-sans-serif, -apple-system, "Segoe UI", sans-serif; }
  header { padding: 28px 24px 12px; max-width: 1200px; margin: 0 auto; }
  h1 { font-size: 22px; letter-spacing: -.02em; }
  h1 span { color: var(--accent); }
  .sub { color: var(--muted); margin-top: 4px; font-size: 13.5px; }
  main { max-width: 1200px; margin: 0 auto; padding: 12px 24px 64px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
          gap: 12px; margin-top: 16px; }
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
          padding: 14px 16px; cursor: pointer; }
  .card:hover { border-color: var(--accent); }
  .card h3 { font-size: 15px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .card .desc { color: var(--muted); font-size: 13px; margin-top: 6px;
                display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
                overflow: hidden; }
  .meta { display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap; }
  .badge { font-size: 11px; padding: 2px 8px; border-radius: 99px; background: var(--chip);
           color: var(--muted); }
  .badge.kind-skill { color: var(--accent); }
</style>
</head>
<body>
<header>
  <h1>Claude <span>Toolkit</span> Catalog</h1>
  <div class="sub" id="sub"></div>
</header>
<main>
  <div class="grid" id="grid"></div>
</main>
<script>
const DATA = __DATA__;
const grid = document.getElementById('grid');
function esc(s){ return (s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function card(e, i){
  return `<div class="card" data-i="${i}">
    <h3>${esc(e.name)}</h3>
    <div class="desc">${esc(e.desc)}</div>
    <div class="meta">
      <span class="badge kind-${e.kind}">${e.kind}</span>
      <span class="badge">${esc(e.category)}</span>
    </div>
  </div>`;
}
function draw(list){
  grid.innerHTML = list.map(([e,i]) => card(e,i)).join('');
  const s = list.filter(([e]) => e.kind==='skill').length;
  document.getElementById('sub').textContent =
    `${s} skills · ${list.length - s} plugins — click a card for full details`;
}
draw(DATA.map((e,i)=>[e,i]));
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
