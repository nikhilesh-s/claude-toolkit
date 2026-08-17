#!/usr/bin/env python3
"""
Builds a compact, greppable index of every skill and plugin on this machine:
    <kind>\t<name>\t<source>\t<one-line description>

Used by scripts/which-skill.sh so the `which-skill` router skill can find a
match with one cheap grep, instead of an LLM reasoning over the full catalog
of skill/plugin names and descriptions that Claude Code already auto-loads
into context every turn. That auto-load is fixed and outside any skill's
control - this index does not shrink it. It only makes finding the right
name inside that catalog fast and deterministic, and gives the router a way
to describe the search results in tokens instead of holding the whole
catalog in reasoning.

Usage:
    uv run python scripts/build_skill_index.py > scripts/skill_index.tsv

Run this after adding, removing, or updating a skill or plugin.
"""
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(REPO_ROOT, "skills")


def extract_description(skill_md_path):
    lines = open(skill_md_path, encoding="utf-8", errors="replace").read().splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^description:\s*(.*)$", line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest in (">", "|", ">-", "|-"):
            block = []
            for cont in lines[i + 1:]:
                if cont.startswith((" ", "\t")) and cont.strip():
                    block.append(cont.strip())
                elif not cont.strip():
                    continue
                else:
                    break
            return " ".join(block)
        return rest.strip('"')
    return ""


def clean(text, limit=140):
    text = text.replace("\t", " ").replace("\n", " ").strip()
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def skill_rows():
    for name in sorted(os.listdir(SKILLS_DIR), key=str.lower):
        skill_md = os.path.join(SKILLS_DIR, name, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        desc = clean(extract_description(skill_md))
        yield ("skill", name, "skills-dir", desc)


def plugin_rows():
    installed_path = os.path.join(HOME, ".claude", "plugins", "installed_plugins.json")
    known_path = os.path.join(HOME, ".claude", "plugins", "known_marketplaces.json")
    if not os.path.isfile(installed_path) or not os.path.isfile(known_path):
        return
    installed = json.load(open(installed_path)).get("plugins", {})
    known = json.load(open(known_path))
    mp_loc = {name: info["installLocation"] for name, info in known.items()}

    for key in sorted(installed.keys()):
        plugin_name, marketplace = key.split("@", 1)
        loc = mp_loc.get(marketplace)
        desc = ""
        if loc:
            mj_path = os.path.join(loc, ".claude-plugin", "marketplace.json")
            if os.path.exists(mj_path):
                try:
                    mj = json.load(open(mj_path))
                    for p in mj.get("plugins", []):
                        if p.get("name") == plugin_name:
                            desc = p.get("description", "")
                            break
                except Exception:
                    pass
        yield ("plugin", plugin_name, marketplace, clean(desc))


def main():
    rows = list(skill_rows()) + list(plugin_rows())
    for kind, name, source, desc in rows:
        print(f"{kind}\t{name}\t{source}\t{desc}")
    print(f"# {len(rows)} entries", file=sys.stderr)


if __name__ == "__main__":
    main()
