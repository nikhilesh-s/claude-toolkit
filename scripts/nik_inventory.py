#!/usr/bin/env python3
"""
Regenerates the machine-specific inventory block in README.md.

This is Nik's script. It is not in upstream (ArnavKakani/claude-toolkit) and it
reads the live state of THIS machine, not a snapshot:

  - skills/*/SKILL.md            what the repo ships
  - ~/.claude/skills/            what is actually wired into Claude Code
  - ~/.claude/plugins/           installed plugins and their marketplaces
  - ~/.claude/settings.json      which plugins are enabled
  - each plugin's .mcp.json      MCP servers a plugin brings with it
  - ~/Library/.../claude_desktop_config.json   Claude Desktop MCP servers

It rewrites everything between the BEGIN/END markers in README.md and leaves
the hand-written prose alone.

Usage:
    python3 scripts/nik_inventory.py            # rewrite README.md in place
    python3 scripts/nik_inventory.py --print    # print the block, change nothing
    python3 scripts/nik_inventory.py --check    # exit 1 if README.md is stale
"""
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(REPO_ROOT, "skills")
README = os.path.join(REPO_ROOT, "README.md")

# This machine has more than one Claude Code config directory:
#   ~/.claude          the plain `claude` CLI in a terminal
#   ~/.claude-nebula   the Claude Desktop app (it exports CLAUDE_CONFIG_DIR)
# They share ~/.claude/plugins but each keeps its own skills/ folder, so a skill
# linked into only one of them is invisible in the other.
def claude_dirs():
    found, seen = [], set()
    for cand in (os.environ.get("CLAUDE_CONFIG_DIR"),
                 os.path.join(HOME, ".claude"),
                 os.path.join(HOME, ".claude-nebula")):
        if not cand:
            continue
        real = os.path.realpath(os.path.expanduser(cand))
        if real in seen or not os.path.isdir(real):
            continue
        seen.add(real)
        found.append(real)
    return found


CLAUDE_DIRS = claude_dirs()
# Plugins, settings and MCP config are read from the plain ~/.claude when it
# exists, since that is where plugin installPaths actually point.
CLAUDE_DIR = next((d for d in CLAUDE_DIRS if d.endswith("/.claude")), CLAUDE_DIRS[0] if CLAUDE_DIRS else os.path.join(HOME, ".claude"))

BEGIN = "<!-- BEGIN GENERATED INVENTORY -->"
END = "<!-- END GENERATED INVENTORY -->"

# claude-multiprofile gives each Claude Desktop profile its own data folder, and
# each one carries its own MCP config.
DESKTOP_PROFILES = {
    "default": os.path.join(HOME, "Library", "Application Support", "Claude",
                            "claude_desktop_config.json"),
    "nebula": os.path.join(HOME, "Library", "Application Support", "Claude-Nebula",
                           "claude_desktop_config.json"),
}

# Skills whose origin the SKILL.md itself does not record. Everything not listed
# here and not under gstack/ came from the K-Dense-AI bulk install.
SOURCE_OVERRIDES = {
    "ste-writing": "loose file (~/Downloads)",
    "task-observer": "rebelytics/one-skill-to-rule-them-all (submodule)",
    "finding-duplicate-functions": "obra/superpowers-lab",
    "mcp-cli": "obra/superpowers-lab",
    "using-tmux-for-interactive-commands": "obra/superpowers-lab",
    "windows-vm": "obra/superpowers-lab",
    "ffuf-web-fuzzing": "jthack/ffuf_claude_skill",
    "d3-viz": "chrisvoncsefalvay/claude-d3js-skill",
    "video-use": "browser-use/video-use",
    "find-skills": "vercel-labs/skills",
    "emil-design-eng": "emilkowalski/skills",
    "which-skill": "written for this repo",
    "_gstack-command": "garrytan/gstack (vendored router)",
    "gstack-upgrade": "garrytan/gstack",
    "connect-chrome": "garrytan/gstack",
}
DEFAULT_SOURCE = "K-Dense-AI/claude-scientific-skills"
GSTACK_SOURCE = "garrytan/gstack (submodule)"

# Env vars that look like credentials. Deliberately narrow: a wide pattern turns
# every mention of the word KEY into a false "needs an API key" claim.
CRED_RE = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_(?:API_KEY|APIKEY|TOKEN|SECRET|KEY))\b")
CRED_IGNORE = {
    "PRIMARY_KEY", "FOREIGN_KEY", "PUBLIC_KEY", "PRIVATE_KEY", "SORT_KEY",
    "INDEX_KEY", "CACHE_KEY", "GROUP_KEY", "ROW_KEY", "SSH_KEY", "GPG_KEY",
    "LICENSE_KEY", "PARTITION_KEY", "OBJECT_KEY", "DICT_KEY", "JOIN_KEY",
    "SHORT_KEY", "TASK_TOKEN", "SESSION_KEY", "STATE_KEY", "SPLIT_KEY",
    "ENTITY_KEY", "META_KEY", "MODEL_KEY", "FILE_KEY", "COLUMN_KEY",
    "GENE_KEY", "SAMPLE_KEY", "BATCH_KEY", "RANDOM_KEY", "PRNG_KEY",
    "MERGE_KEY", "UNIQUE_KEY", "COMPOSITE_KEY", "NATURAL_KEY", "SURROGATE_KEY",
    "IDEMPOTENCY_KEY", "CANDIDATE_KEY", "ACCESS_TOKEN", "REFRESH_TOKEN",
    "BEARER_TOKEN", "CSRF_TOKEN", "PAD_TOKEN", "EOS_TOKEN", "BOS_TOKEN",
    "UNK_TOKEN", "MASK_TOKEN", "CLS_TOKEN", "SEP_TOKEN", "SPECIAL_TOKEN",
    "START_TOKEN", "END_TOKEN", "STOP_TOKEN", "NEXT_TOKEN", "PAGE_TOKEN",
}
MCP_RE = re.compile(r"\bmcp__([A-Za-z0-9_-]+?)__")

# Names that only ever appear as documentation placeholders in an example block.
PLACEHOLDER_RE = re.compile(
    r"^(YOUR|MY|SOME|EXAMPLE|DEMO|FOO|BAR|BAZ|TEST|DUMMY|FAKE|PLACEHOLDER|XXX|SAMPLE)_"
    r"|^(API_KEY|AUTH_TOKEN|INTERNAL_TOKEN|SENSITIVE_KEY|SECRET_KEY|THE_KEY)$"
)


def read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {} if default is None else default


def frontmatter(text):
    """Return (name, description) from a SKILL.md YAML frontmatter block.

    Handles plain scalars, quoted scalars, and block scalars (`description: |`
    and `description: >`), which several skills use for long descriptions.
    """
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return None, None
    out, key, in_block = {}, None, False
    for line in m.group(1).split("\n"):
        kv = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if kv and not (in_block and line.startswith((" ", "\t"))):
            key = kv.group(1).strip()
            val = kv.group(2).strip()
            in_block = val in ("|", ">", "|-", ">-", "|+", ">+")
            out[key] = "" if in_block else val
        elif key and (line.startswith((" ", "\t")) or in_block):
            out[key] = (out[key] + " " + line.strip()).strip()
    def clean(v):
        v = (v or "").strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        return re.sub(r"\s+", " ", v).strip()
    return clean(out.get("name")), clean(out.get("description"))


def skill_body(folder):
    """SKILL.md plus any sibling reference files, for requirement detection."""
    parts = []
    for root, _dirs, files in os.walk(folder, followlinks=True):
        for fn in files:
            if fn.endswith((".md", ".py", ".sh", ".json", ".ts", ".js")):
                parts.append(read(os.path.join(root, fn)))
        if len(parts) > 60:
            break
    return "\n".join(parts)


def scan_skills():
    rows = []
    if not os.path.isdir(SKILLS_DIR):
        return rows
    for name in sorted(os.listdir(SKILLS_DIR), key=str.lower):
        folder = os.path.join(SKILLS_DIR, name)
        skill_md = os.path.join(folder, "SKILL.md")
        if not os.path.isdir(folder) or not os.path.exists(skill_md):
            continue

        fm_name, desc = frontmatter(read(skill_md))
        body = skill_body(folder)

        creds = sorted({
            c for c in CRED_RE.findall(body)
            if c not in CRED_IGNORE
            and not c.endswith("_PUBLIC_KEY")
            and not PLACEHOLDER_RE.match(c)
        })
        mcps = sorted({m for m in MCP_RE.findall(body) if m.lower() != "name"})

        # gstack skills are symlinks into the gstack submodule
        real = os.path.realpath(skill_md)
        from_gstack = os.path.sep + "gstack" + os.path.sep in real

        if from_gstack:
            source = GSTACK_SOURCE
        else:
            source = SOURCE_OVERRIDES.get(name, DEFAULT_SOURCE)

        states = []
        for cdir in CLAUDE_DIRS:
            link = os.path.join(cdir, "skills", name)
            if os.path.islink(link):
                states.append("linked" if os.path.exists(link) else "BROKEN LINK")
            elif os.path.isdir(link):
                states.append("copy (not linked)")
            else:
                states.append("not installed")
        if "BROKEN LINK" in states:
            wired = "BROKEN LINK"
        elif all(s == "linked" for s in states):
            wired = "linked"
        elif any(s == "linked" for s in states):
            wired = "linked (only %s)" % ", ".join(
                os.path.basename(c) for c, s in zip(CLAUDE_DIRS, states) if s == "linked")
        elif "copy (not linked)" in states:
            wired = "copy (not linked)"
        else:
            wired = "not installed"

        rows.append({
            "name": name,
            "fm_name": fm_name or name,
            "desc": desc or "",
            "source": source,
            "creds": creds,
            "mcps": mcps,
            "wired": wired,
            "name_mismatch": bool(fm_name) and fm_name != name,
        })
    return rows


def scan_extra_skills(known):
    """Skills wired into any Claude skills dir that this repo does not own."""
    out, seen = [], set()
    for cdir in CLAUDE_DIRS:
        sk = os.path.join(cdir, "skills")
        if not os.path.isdir(sk):
            continue
        for name in sorted(os.listdir(sk), key=str.lower):
            if name in known or name.startswith(".") or name in seen:
                continue
            p = os.path.join(sk, name)
            target = os.path.realpath(p)
            if target.startswith(os.path.realpath(REPO_ROOT)):
                continue
            seen.add(name)
            _, desc = frontmatter(read(os.path.join(p, "SKILL.md")))
            homes = [os.path.basename(c) for c in CLAUDE_DIRS
                     if os.path.exists(os.path.join(c, "skills", name))]
            out.append({
                "name": name,
                "desc": desc or "",
                "kind": "symlink" if os.path.islink(p) else "real folder",
                "target": target.replace(HOME, "~"),
                "homes": ", ".join("`%s`" % h for h in homes),
            })
    return out


def scan_plugins():
    installed = load_json(os.path.join(CLAUDE_DIR, "plugins", "installed_plugins.json"))
    markets = load_json(os.path.join(CLAUDE_DIR, "plugins", "known_marketplaces.json"))
    enabled = load_json(os.path.join(CLAUDE_DIR, "settings.json")).get("enabledPlugins", {})

    rows = []
    for key, entries in (installed.get("plugins") or {}).items():
        entry = (entries or [{}])[0]
        path = entry.get("installPath", "")
        mcp = load_json(os.path.join(path, ".mcp.json")).get("mcpServers", {}) if path else {}
        market = key.split("@")[-1]
        src = (markets.get(market, {}).get("source") or {})

        def count(sub, want_dirs):
            d = os.path.join(path, sub)
            if not os.path.isdir(d):
                return 0
            if want_dirs:
                return sum(1 for n in os.listdir(d)
                           if os.path.exists(os.path.join(d, n, "SKILL.md")))
            return sum(1 for n in os.listdir(d)
                       if n.endswith(".md") and not n.startswith("_"))

        rows.append({
            "n_skills": count("skills", True),
            "n_commands": count("commands", False),
            "n_agents": count("agents", False),
            "key": key,
            "version": entry.get("version", "?"),
            "scope": entry.get("scope", "?"),
            "installed_at": (entry.get("installedAt") or "")[:10],
            "enabled": bool(enabled.get(key)),
            "marketplace": market,
            "repo": src.get("repo", "?"),
            "auto_update": bool(markets.get(market, {}).get("autoUpdate")),
            "mcp_servers": sorted(mcp.keys()),
            "mcp_detail": mcp,
            "path": path.replace(HOME, "~"),
        })
    return sorted(rows, key=lambda r: r["key"])


def scan_desktop_mcp():
    """{profile: {server: detail}} across every Claude Desktop profile."""
    out = {}
    for profile, path in DESKTOP_PROFILES.items():
        if os.path.exists(path):
            out[profile] = load_json(path).get("mcpServers", {}) or {}
    return out


def scan_project_mcp():
    """MCP servers registered through the Claude Code CLI (user + project scope)."""
    cfg = load_json(os.path.join(HOME, ".claude.json"))
    out = {"user": cfg.get("mcpServers", {}) or {}, "projects": {}}
    for proj, val in (cfg.get("projects") or {}).items():
        servers = val.get("mcpServers") or {}
        if servers:
            out["projects"][proj.replace(HOME, "~")] = sorted(servers.keys())
    return out


def md_escape(s):
    return s.replace("|", "\\|").replace("\n", " ")


def truncate(s, n):
    s = md_escape(s)
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def build():
    skills = scan_skills()
    extras = scan_extra_skills({s["name"] for s in skills})
    plugins = scan_plugins()
    desktop = scan_desktop_mcp()
    cli_mcp = scan_project_mcp()

    linked = [s for s in skills if s["wired"] == "linked"]
    broken = [s for s in skills if s["wired"] == "BROKEN LINK"]
    missing = [s for s in skills if s["wired"] == "not installed"]
    gstack = [s for s in skills if s["source"] == GSTACK_SOURCE]
    with_creds = [s for s in skills if s["creds"]]
    with_mcp = [s for s in skills if s["mcps"]]

    L = []
    a = L.append

    a(BEGIN)
    a("")
    a("<!-- Generated by scripts/nik_inventory.py — do not edit by hand. -->")
    a("<!-- Regenerate:  python3 scripts/nik_inventory.py  -->")
    a("")

    # ---------------------------------------------------------------- summary
    a("### At a glance")
    a("")
    a("| | Count |")
    a("|---|---|")
    dirs_txt = " + ".join("`%s`" % os.path.basename(d) for d in CLAUDE_DIRS)
    a(f"| Skills shipped by this repo | {len(skills)} |")
    a(f"| …wired into every config dir ({dirs_txt}) | {len(linked)} |")
    a(f"| …broken symlinks | {len(broken)} |")
    a(f"| …present in repo but not installed | {len(missing)} |")
    a(f"| …that come from the gstack submodule | {len(gstack)} |")
    a(f"| Skills installed outside this repo | {len(extras)} |")
    a(f"| Plugins installed | {len(plugins)} ({sum(1 for p in plugins if p['enabled'])} enabled) |")
    a(f"| Skills naming a credential env var | {len(with_creds)} |")
    a(f"| Skills naming an MCP server | {len(with_mcp)} |")
    a("")

    # ------------------------------------------------------ skills not from repo
    if extras:
        a("### Skills installed outside this repo")
        a("")
        a("These live in `~/.claude/skills/` but this repo does not own them. A `git pull`")
        a("from upstream will never touch them.")
        a("")
        a("| Skill | How it is installed | Present in | Real location | What it does |")
        a("|---|---|---|---|---|")
        for e in extras:
            a(f"| `{e['name']}` | {e['kind']} | {e['homes']} | `{e['target']}` | "
              f"{truncate(e['desc'], 80)} |")
        a("")

    # --------------------------------------------------------------- plugins
    a("### Plugins")
    a("")
    a("Plugins do **not** live in this repo. They install into `~/.claude/plugins/`.")
    a("A plugin can carry its own skills, its own slash commands, and its own MCP servers.")
    a("")
    a("| Plugin | Version | Enabled | Marketplace repo | Auto-update | Skills | Commands | Agents | MCP servers it brings |")
    a("|---|---|---|---|---|---|---|---|---|")
    for p in plugins:
        mcp = ", ".join(f"`{m}`" for m in p["mcp_servers"]) or "—"
        a(f"| `{p['key']}` | {p['version']} | {'yes' if p['enabled'] else 'no'} | "
          f"`{p['repo']}` | {'yes' if p['auto_update'] else 'no'} | {p['n_skills']} | "
          f"{p['n_commands']} | {p['n_agents']} | {mcp} |")
    a("")
    a(f"That is **{sum(p['n_skills'] for p in plugins)} more skills** on top of the "
      f"{len(skills)} in this repo. Plugin skills are versioned with their plugin — "
      "`claude plugin update` changes them, this repo never does.")
    a("")

    # ----------------------------------------------------------- MCP servers
    a("### MCP servers")
    a("")
    a("#### From plugins")
    a("")
    if any(p["mcp_servers"] for p in plugins):
        a("| Server | Comes from | Transport | Endpoint / command | Credential needed |")
        a("|---|---|---|---|---|")
        for p in plugins:
            for nm, detail in sorted(p["mcp_detail"].items()):
                transport = detail.get("type", "stdio")
                target = detail.get("url") or detail.get("command") or "—"
                if len(target) > 60:
                    target = target[:57] + "…"
                needs = "OAuth" if transport == "http" and "url" in detail else "none"
                a(f"| `{nm}` | `{p['key']}` | {transport} | `{target}` | {needs} |")
    else:
        a("None.")
    a("")

    a("#### Registered through the Claude Code CLI")
    a("")
    if cli_mcp["user"]:
        a("| Server | Scope |")
        a("|---|---|")
        for nm in sorted(cli_mcp["user"]):
            a(f"| `{nm}` | user |")
    else:
        a("None. `~/.claude.json` has an empty `mcpServers` block, and no project in it")
        a("registers a project-scoped server.")
    a("")

    a("#### From the Claude Desktop app")
    a("")
    a("`claude-multiprofile` gives each Desktop profile its own data folder and its own MCP")
    a("config. These belong to the Desktop app, not to Claude Code, and this repo does not")
    a("manage them.")
    a("")
    a("| Profile | Config file | Server | Command |")
    a("|---|---|---|---|")
    for profile, servers in sorted(desktop.items()):
        path = DESKTOP_PROFILES[profile].replace(HOME, "~")
        if not servers:
            a(f"| `{profile}` | `{path}` | *(none)* | — |")
        for nm, d in sorted(servers.items()):
            cmd = " ".join([d.get("command", "")] + list(d.get("args", []))).strip() or "—"
            a(f"| `{profile}` | `{path}` | `{nm}` | `{cmd}` |")
    a("")

    # ------------------------------------------------------- credential needs
    a("### Skills that name a credential")
    a("")
    a("Each row lists the environment variables the skill's own files mention. Naming a")
    a("variable is not the same as needing it for every task — some skills only use one for")
    a("an optional higher rate limit. Treat this as the list to check before you trust a")
    a("skill to run unattended, not as a shopping list.")
    a("")
    a("| Skill | Env vars it names | Source |")
    a("|---|---|---|")
    for s in with_creds:
        a(f"| `{s['name']}` | {', '.join('`'+c+'`' for c in s['creds'])} | {s['source']} |")
    a("")

    # -------------------------------------------------------- MCP-dependent
    a("### Skills that call an MCP server")
    a("")
    a("These skills reference `mcp__<server>__*` tools. If the server is not registered,")
    a("the skill loads but its MCP steps fail.")
    a("")
    a("| Skill | MCP servers it calls | Registered here? |")
    a("|---|---|---|")
    known_servers = set()
    for p in plugins:
        known_servers |= set(p["mcp_servers"])
    for servers in desktop.values():
        known_servers |= set(servers)
    known_servers |= set(cli_mcp["user"])
    for s in with_mcp:
        marks = []
        for m in s["mcps"]:
            hit = any(m == k or m.endswith(k) or k in m for k in known_servers)
            marks.append(f"`{m}`{'' if hit else ' ✗'}")
        ok = all("✗" not in x for x in marks)
        a(f"| `{s['name']}` | {', '.join(marks)} | {'yes' if ok else 'no'} |")
    a("")

    # ------------------------------------------------------------- full list
    a("### Every skill in this repo")
    a("")
    a(f"All {len(skills)} skill folders, alphabetical. **Wired** means `~/.claude/skills/<name>`")
    a("points back here, so editing the file in this repo changes the live skill immediately.")
    a("")
    a("| Skill | Wired | Source | Needs a credential | Needs MCP | What it does |")
    a("|---|---|---|---|---|---|")
    for s in skills:
        a(f"| `{s['name']}` | {s['wired']} | {s['source']} | "
          f"{'yes' if s['creds'] else 'no'} | {'yes' if s['mcps'] else 'no'} | "
          f"{truncate(s['desc'], 110)} |")
    a("")

    mismatched = [s for s in skills if s["name_mismatch"]]
    if mismatched:
        a("### Folder name does not match the `name:` in frontmatter")
        a("")
        a("Claude Code loads a skill under its frontmatter `name`, not its folder name.")
        a("")
        a("| Folder | Loads as |")
        a("|---|---|")
        for s in mismatched:
            a(f"| `{s['name']}` | `{s['fm_name']}` |")
        a("")

    a(END)
    return "\n".join(L)


def splice(block):
    text = read(README)
    if BEGIN in text and END in text:
        pre = text.split(BEGIN)[0]
        post = text.split(END, 1)[1]
        return pre + block + post
    return text.rstrip() + "\n\n" + block + "\n"


def main():
    block = build()
    if "--print" in sys.argv:
        print(block)
        return 0
    new = splice(block)
    if "--check" in sys.argv:
        if new != read(README):
            print("README.md inventory is stale. Run: python3 scripts/nik_inventory.py",
                  file=sys.stderr)
            return 1
        print("README.md inventory is current.")
        return 0
    with open(README, "w", encoding="utf-8") as fh:
        fh.write(new)
    print(f"Wrote inventory block to {README}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
