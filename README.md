# Claude Toolkit

Everything Claude Code related on this machine, in one place. Set up 2026-08-08.

```
~/claude-toolkit/
├── README.md          you are here — what each thing is and how to fix it
├── status.sh          ./status.sh → health check for all of it
└── skills/            the real files; ~/.claude/skills/ just symlinks in here
    ├── humanizer/
    ├── ste-writing/
    └── task-observer/     (a git repo — `git pull` to update)
```

| Thing | Type | Status |
|---|---|---|
| [humanizer](#humanizer) | Skill | ✅ active |
| [ste-writing](#ste-writing) | Skill | ✅ active |
| [task-observer](#task-observer) | Skill | ✅ active |
| [claude-mem](#claude-mem) | Plugin + daemon | ✅ active |
| [claude-code-setup](#claude-code-setup) | Plugin | ✅ active |
| [OmniRoute](#omniroute) | Standalone gateway | ⚠️ running, MCP not wired |
| [Headroom](#headroom) | macOS app | ⛔ not installed |

**Skills** genuinely live here — `~/.claude/skills/` contains only symlinks pointing back into
`skills/`, so edit files here and the change is live. **Plugins and OmniRoute don't** — they
install into `~/.claude/plugins/` and global npm, and this README is just their index. So
don't expect to find their code in this folder.

Run `./status.sh` any time to see what's actually up.

---

## task-observer

**One Skill to Rule Them All** — a meta-skill that watches your sessions, notices corrections
and repeated patterns, and proposes new/updated skills. Author reports ~900 improvements
across 50 skills in six months.

- Source: https://github.com/rebelytics/one-skill-to-rule-them-all (CC BY 4.0)
- Installed as a symlink, so `git pull` in the repo updates the live skill:
  ```bash
  cd ~/claude-toolkit/skills/task-observer && git pull
  ```
- Loads as `task-observer@skills-dir`. It self-describes as "invoke at the start of every
  task-oriented session" — if that turns out to be too eager, trim the `description:`
  frontmatter in `SKILL.md` rather than deleting the skill.
- Read `USER-GUIDE.md` in the repo before leaning on it; it expects an observation log.

## humanizer

Strips signs of AI-generated writing from text — inflated symbolism, promotional language,
em dash overuse, rule of three, negative parallelisms, filler. Built on Wikipedia's
"Signs of AI writing" guide (WikiProject AI Cleanup).

- v2.9.1, MIT. Installed from a loose `SKILL.md` in `~/Downloads` on 2026-08-08.
- Source of truth is `skills/humanizer/SKILL.md` here — the Downloads copy is not tracked and
  can be deleted.
- Self-contained, no companion files.
- Origin unknown — it arrived as a bare file with no repo link, so there's no upstream to pull
  updates from. If you find where it came from, add the URL here.

## ste-writing

Rewrites prose into ASD-STE100 Simplified Technical English — docs, READMEs, PR text, error
messages, release notes. Explicitly *not* for code, marketing copy, or anything needing a
voice, since STE strips voice by design. Has strict and STE-flavored modes.

- Installed from `ste-writing-skill.md` in `~/Downloads` on 2026-08-08.
- Source of truth is `skills/ste-writing/SKILL.md` here.
- Self-contained. References the free standard at https://asd-ste100.org (copyrighted — the
  skill correctly says not to paste it in full).

**These two overlap and conflict.** Both fight AI-sounding prose, but in opposite directions:
`humanizer` adds voice and personality, `ste-writing` removes it. Invoke one deliberately;
don't let both fire on the same text.

## claude-mem

Persistent memory across Claude Code sessions. Captures tool usage, summarizes it via the
Agent SDK, and injects context from your previous 10 sessions in a project.

- Docs: https://docs.claude-mem.ai/introduction · Repo: `thedotmack/claude-mem`
- Version 13.14.0. Data + config in `~/.claude-mem` (local only).
- Worker UI: http://127.0.0.1:37701
- Worker does **not** autostart. After a reboot:
  ```bash
  npx claude-mem start
  ```
- Memory injection begins on your *second* session in a given project. Optional one-time
  ingest of a whole repo: run `/learn-codebase` inside that project (~5 min).
- Privacy: wrap anything you don't want captured in `<private>` tags. Native Claude Code
  memory was left enabled alongside it.
- Note: this observes everything you do in Claude Code. That's the point, but it's worth
  knowing it's on.

### Gotcha, already fixed
`npx claude-mem install` registered its marketplace by copying the npm package, which puts
`marketplace.json` at `.agents/plugins/` instead of `.claude-plugin/`. Claude Code then
reports `failed to load: cache-miss`. Fix (already applied — redo only if it recurs after an
upgrade):
```bash
claude plugin marketplace remove thedotmack
claude plugin marketplace add thedotmack/claude-mem
claude plugin install claude-mem@thedotmack
```

## claude-code-setup

Anthropic's official plugin that audits a repo **read-only** and recommends hooks, skills,
MCP servers, subagents, and slash commands.

- From the official marketplace, already known to this machine.
- Usage: from a project root, ask `recommend automations for this project`.
- The safety point from https://aident.ai/blog/use-claude-code-setup-plugin-safely:
  recommendation and implementation are separate steps. After an audit, confirm it stayed
  read-only (`git status`), then adopt suggestions **one at a time**, each with its own
  verification. Judge each on evidence, scope, permissions, and how you'd verify it.

## OmniRoute

Local AI gateway — one OpenAI-compatible endpoint fronting 290+ providers, with fallback
routing and token compression.

- Repo: https://github.com/diegosouzapw/OmniRoute (MIT) · v3.8.49, installed via `npm i -g omniroute`
- Dashboard http://localhost:20128 · API base http://localhost:20128/v1
- Currently **running as a daemon**. Control it with:
  ```bash
  omniroute serve --daemon --no-open   # start
  omniroute stop                       # stop
  omniroute status
  ```
- **Your Claude Code traffic is NOT routed through this.** Installing it changed nothing
  about how Claude Code talks to Anthropic. Pointing a client at `/v1` is a deliberate,
  separate step — and it would send those prompts to third-party providers.

### Remaining manual step: MCP
You asked for the MCP server registered. It isn't, for two reasons:

1. The stdio transport (`omniroute --mcp`) is **broken in v3.8.49** — the bundled
   `dist/open-sse/mcp-server/server.js` throws `SyntaxError: Unexpected reserved word` on a
   top-level `await`. That's an upstream build bug, not a config problem.
2. The HTTP transport works but returns `AUTH_001 Authentication required`, and OmniRoute
   has no account yet. Creating one means setting a password at http://localhost:20128/login,
   which is yours to do, not mine.

Once you've created the account and generated a key (`omniroute keys list` to check):
```bash
claude mcp add omniroute --scope user --transport http \
  http://localhost:20128/api/mcp/stream \
  --header "Authorization: Bearer <YOUR_OMNIROUTE_KEY>"
claude mcp list   # confirm it connects
```

### Also worth knowing
npm **blocked OmniRoute's postinstall scripts** (default `allow-scripts` policy). Ten packages
were affected including native modules — `koffi`, `sharp`, `onnxruntime-node`, `keytar`,
`@parcel/watcher`. The server starts fine, but features depending on those may fail. If you
hit that, `omniroute runtime repair` is the intended fix. I did not override the script
policy — allowing arbitrary postinstall scripts from a 290-provider gateway is a call you
should make knowingly, not one I should make for you.

## Headroom

**Skipped, per your call.** macOS menu bar app that proxies Claude Code / Codex through a
local compression pipeline, claiming ~50% token savings.

- Repo: https://github.com/gglucass/headroom-desktop · latest v0.7.6
- Desktop shell is MIT, but the app **requires a paid subscription** — from $3/mo, 7-day trial.
- `brew install --cask headroom` from the README **does not work** — no such cask exists in
  any tapped repo as of 2026-08-08. Use the `.dmg` from
  https://github.com/gglucass/headroom-desktop/releases/latest
- Requires macOS 14+ on Apple Silicon. This machine is macOS 26.4 / arm64 — compatible.

---

## Bulk-installed skills (2026-08-16)

Installed in bulk from `obra/superpowers-lab`, `jthack/ffuf_claude_skill`, `chrisvoncsefalvay/claude-d3js-skill`, and `K-Dense-AI/claude-scientific-skills` (via `travisvn/awesome-claude-skills`). Same symlink convention as above: real files live in `skills/<name>/`, `~/.claude/skills/<name>` is a symlink.

| Skill | Source | Description |
|---|---|---|
| adaptyv | K-Dense-AI/claude-scientific-skills | How to use the Adaptyv Bio Foundry API and Python SDK for protein experiment design, submission, and results retrieval. Use this skill wh... |
| aeon | K-Dense-AI/claude-scientific-skills | This skill should be used for time series machine learning tasks including classification, regression, clustering, forecasting, anomaly d... |
| analytical-method-validation | K-Dense-AI/claude-scientific-skills | Plan, execute, and document validation, verification, and transfer of analytical procedures under the governing framework - ICH Q2(R2) an... |
| anndata | K-Dense-AI/claude-scientific-skills | Data structure for annotated matrices in single-cell analysis. Use when working with .h5ad files or integrating with the scverse ecosyste... |
| arbor | K-Dense-AI/claude-scientific-skills | Autonomously improve a real artifact (code, training recipe, agent harness, data pipeline, prompt) against an objective and an evaluator,... |
| arboreto | K-Dense-AI/claude-scientific-skills | Infer gene regulatory networks (GRNs) from gene expression data using scalable algorithms (GRNBoost2, GENIE3). Use when analyzing transcr... |
| astropy | K-Dense-AI/claude-scientific-skills | Core Python library for astronomy and astrophysics workflows that need Astropy APIs, including units/quantities, coordinates, FITS I/O, t... |
| autoskill | K-Dense-AI/claude-scientific-skills | Observe the user's screen via screenpipe, detect repeated research workflows, match them against existing scientific-agent-skills, and dr... |
| benchling-integration | K-Dense-AI/claude-scientific-skills | Benchling Python SDK and REST API integration for registry entities, inventory, ELN entries, workflows, Benchling Apps, and Data Warehous... |
| bgpt-paper-search | K-Dense-AI/claude-scientific-skills | Search scientific papers and retrieve structured experimental data extracted from full-text studies via the BGPT MCP server. Returns 25+ ... |
| bids | K-Dense-AI/claude-scientific-skills | > |
| biopython | K-Dense-AI/claude-scientific-skills | Comprehensive molecular biology toolkit. Use for sequence manipulation, file parsing (FASTA/GenBank/PDB), phylogenetics, and programmatic... |
| bioservices | K-Dense-AI/claude-scientific-skills | Unified Python interface to 40+ bioinformatics services. Use when querying multiple databases (UniProt, KEGG, ChEMBL, Reactome) in a sing... |
| bulk-rnaseq | K-Dense-AI/claude-scientific-skills | End-to-end bulk RNA-seq orchestrator — takes raw FASTQ reads through QC and trimming (FastQC, fastp/Trim Galore), alignment and quantific... |
<!-- BULK_SKILLS_ROWS -->

## Bulk-installed plugins (2026-08-16)

Installed via `claude plugin install` from marketplaces added the same day (superpowers, ai-toolkit, mattpocock, terrashark, anthropic-agent-skills, conorluddy, playwright-skill, web-asset-generator-marketplace, frontend-slides, expo-plugins, trailofbits, claude-plugins-official). Code isn't copied here — same convention as claude-mem/claude-code-setup above: this is just the index. Run `claude plugin list` for live status.

| Plugin | Marketplace | Description |
|---|---|---|
<!-- BULK_PLUGINS_ROWS -->

## Maintenance

```bash
# update everything
cd ~/claude-toolkit/skills/task-observer && git pull   # task-observer
# humanizer / ste-writing have no upstream — edit skills/*/SKILL.md directly
claude plugin update claude-mem@thedotmack
claude plugin update claude-code-setup@claude-plugins-official
npm update -g omniroute

# health check — covers skills, plugins, services, and MCP in one shot
./status.sh

# restart the services after a reboot (neither autostarts)
npx claude-mem start
omniroute serve --daemon --no-open
```

Restart Claude Code after plugin changes — they load at session start.

### Adding a skill
```bash
mkdir -p ~/claude-toolkit/skills/<name>          # or git clone straight into skills/
ln -sfn ~/claude-toolkit/skills/<name> ~/.claude/skills/<name>
```
Name the folder to match the `name:` in its frontmatter. Then add a row to the table at the
top and a section saying what it is, where it came from, and anything that bit you.
If you cloned it from GitHub, add it as a submodule instead — see below.

## This folder is a git repo

Synced to a **private** GitHub repo so it survives a machine wipe.

```bash
cd ~/claude-toolkit
git add -A && git commit -m "..." && git push
```

`skills/task-observer` is a **submodule** pointing at the upstream project — its code isn't
copied into this repo, just a pointer to a commit. Practical consequences:

```bash
# cloning this toolkit onto a new machine
git clone --recurse-submodules <this repo> ~/claude-toolkit
# ...then relink the skills, since symlinks into ~/.claude aren't tracked:
for s in ~/claude-toolkit/skills/*/; do ln -sfn "$s" ~/.claude/skills/"$(basename "$s")"; done

# pulling upstream updates to task-observer
git submodule update --remote skills/task-observer
git add skills/task-observer && git commit -m "bump task-observer"
```

If you forget `--recurse-submodules` on clone, `skills/task-observer` shows up empty —
`git submodule update --init` fixes it.
