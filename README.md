# Claude Toolkit

This file lists everything related to Claude Code on this machine, in one place. Setup date: 2026-08-08.

```
~/claude-toolkit/
├── README.md          you are here — what each thing is and how to fix it
├── status.sh          ./status.sh → health check for all of it
├── scripts/           categorize_skills.py → regenerates "All skills" below
└── skills/            the real files; ~/.claude/skills/ just symlinks in here
    ├── ste-writing/
    ├── task-observer/     (a git repo — `git pull` to update)
    └── ...172 more        see "All skills" below (172 bulk + these 2)
```

| Thing | Type | Status |
|---|---|---|
| [ste-writing](#ste-writing) | Skill | ✅ active |
| [task-observer](#task-observer) | Skill | ✅ active |
| [claude-mem](#claude-mem) | Plugin + daemon | ✅ active |
| [claude-code-setup](#claude-code-setup) | Plugin | ✅ active |
| [OmniRoute](#omniroute) | Standalone gateway | ⚠️ running, MCP not wired |
| [Headroom](#headroom) | macOS app | ⛔ not installed |
| [Serena](#serena) | MCP server (code intel) | ✅ active, auto-starts |
| [status.sh](#statussh) | Script | ✅ working |
| [Instagram-sourced tools](#instagram-sourced-2026-08-16) | CLI tools + apps | ✅ mostly active |
| [What runs on its own](#what-runs-on-its-own-and-what-needs-setup) | Reference table | — |

**Skills** live here. `~/.claude/skills/` holds only symlinks that point back into `skills/`.
Edit a file here, and the change takes effect right away.

**Plugins and OmniRoute do not live here.** They install into `~/.claude/plugins/` or into
global npm. This README only lists them. Do not expect to find their code in this folder.

Run `./status.sh` at any time to check the current state.

---

## task-observer

**One Skill to Rule Them All.** This is a meta-skill. It watches your sessions, notices
corrections and repeated patterns, and proposes new or updated skills. The author reports
about 900 improvements across 50 skills in six months.

- Source: https://github.com/rebelytics/one-skill-to-rule-them-all (CC BY 4.0)
- The skill is installed as a symlink. Run `git pull` in the repo to update the live skill:
  ```bash
  cd ~/claude-toolkit/skills/task-observer && git pull
  ```
- Claude loads it as `task-observer@skills-dir`. Its own description says to invoke it at the
  start of every task-oriented session. If it fires too often, shorten the `description:`
  field in `SKILL.md` instead of deleting the skill.
- Read `USER-GUIDE.md` in the repo before you rely on this skill. It expects an observation log.

## humanizer (moved)

This skill used to live here, at `skills/humanizer/SKILL.md`. It was installed on 2026-08-08
from a loose file in `~/Downloads`, and its origin was **not known**.

On 2026-08-16, `blader/humanizer` turned up in the `charliehills` Instagram list. A diff showed
it was byte-identical to the untracked copy. This confirms the real source.

The skill is no longer worth keeping as an origin-unknown raw file. It was removed from
`skills/`, and is now tracked as the `humanizer@humanizer` plugin instead (see
[Bulk-installed plugins](#bulk-installed-plugins-2026-08-16)). It behaves the same way, but now
has a real, known source. Update it with `claude plugin update humanizer@humanizer`.

## ste-writing

This skill rewrites prose into ASD-STE100 Simplified Technical English. Use it for docs,
READMEs, pull-request text, error messages, and release notes. Do not use it for code,
marketing copy, or any text that needs a distinct voice — STE removes voice by design. It has
a strict mode and an STE-flavored mode.

- Installed from `ste-writing-skill.md` in `~/Downloads` on 2026-08-08.
- The source of truth is `skills/ste-writing/SKILL.md` here.
- Self-contained. It links to the free standard at https://asd-ste100.org. That standard is
  copyrighted, so the skill correctly avoids pasting it in full.

**humanizer and ste-writing conflict.** Both fight AI-sounding prose, but in opposite
directions. `humanizer` adds voice and personality. `ste-writing` removes voice. Choose one on
purpose. Do not let both act on the same text.

## claude-mem

This plugin keeps memory across Claude Code sessions. It captures tool usage, summarizes it
with the Agent SDK, and adds context from your last 10 sessions in a project.

- Docs: https://docs.claude-mem.ai/introduction. Repo: `thedotmack/claude-mem`.
- Version 13.14.0. Data and config live in `~/.claude-mem` (local only).
- Worker interface: http://127.0.0.1:37701
- The worker does **not** start on its own. After a reboot, run:
  ```bash
  npx claude-mem start
  ```
- Memory injection starts on your *second* session in a project. To ingest a whole repo once,
  run `/learn-codebase` inside that project. This takes about 5 minutes.
- Privacy: wrap any text you do not want captured in `<private>` tags. Native Claude Code
  memory stays enabled alongside claude-mem.
- Note: claude-mem watches everything you do in Claude Code. That is its purpose, but you
  should know it is on.

### Gotcha, already fixed
`npx claude-mem install` registered its marketplace by copying the npm package. This placed
`marketplace.json` at `.agents/plugins/` instead of `.claude-plugin/`. Claude Code then
reported `failed to load: cache-miss`. The fix below is already applied. Redo it only if the
problem returns after an upgrade:
```bash
claude plugin marketplace remove thedotmack
claude plugin marketplace add thedotmack/claude-mem
claude plugin install claude-mem@thedotmack
```

## claude-code-setup

This is Anthropic's official plugin. It audits a repo in **read-only** mode and recommends
hooks, skills, MCP servers, subagents, and slash commands.

- It comes from the official marketplace, already known to this machine.
- To use it, go to a project root and ask it to recommend automations for this project.
- Safety note, from https://aident.ai/blog/use-claude-code-setup-plugin-safely: recommendation
  and implementation are separate steps. After an audit, confirm it stayed read-only with
  `git status`. Then adopt suggestions **one at a time**, and verify each one. Judge each
  suggestion on its evidence, scope, permissions, and how you would check it.

## OmniRoute

OmniRoute is a local AI gateway. It gives one OpenAI-compatible endpoint that fronts more
than 290 providers, with fallback routing and token compression.

- Repo: https://github.com/diegosouzapw/OmniRoute (MIT). Version 3.8.49, installed with
  `npm i -g omniroute`.
- Dashboard: http://localhost:20128. API base: http://localhost:20128/v1
- OmniRoute **runs as a daemon** right now. Control it with:
  ```bash
  omniroute serve --daemon --no-open   # start
  omniroute stop                       # stop
  omniroute status
  ```
- **Claude Code traffic does not go through OmniRoute.** Installing it changed nothing about
  how Claude Code talks to Anthropic. Pointing a client at `/v1` is a separate, deliberate
  step, and it would send those prompts to third-party providers.

### Remaining manual step: MCP
The MCP server is not registered yet, for two reasons:

1. The stdio transport (`omniroute --mcp`) is **broken in v3.8.49**. The bundled
   `dist/open-sse/mcp-server/server.js` throws `SyntaxError: Unexpected reserved word` on a
   top-level `await`. This is an upstream build bug, not a config problem.
2. The HTTP transport works, but it returns `AUTH_001 Authentication required`. OmniRoute has
   no account yet. To create one, set a password at http://localhost:20128/login. This step
   is yours to do.

After you create the account and generate a key (check with `omniroute keys list`), run:
```bash
claude mcp add omniroute --scope user --transport http \
  http://localhost:20128/api/mcp/stream \
  --header "Authorization: Bearer <YOUR_OMNIROUTE_KEY>"
claude mcp list   # confirm it connects
```

### Also worth knowing
npm **blocked OmniRoute's postinstall scripts**, under its default `allow-scripts` policy. Ten
packages were affected, including native modules: `koffi`, `sharp`, `onnxruntime-node`,
`keytar`, `@parcel/watcher`. The server still starts, but features that depend on those
packages may fail. If you hit that, run `omniroute runtime repair`. The script policy was not
overridden on purpose. Allowing arbitrary postinstall scripts from a gateway that touches 290
providers is a decision you should make yourself, with full knowledge of the risk.

## Headroom

**Not installed, by your choice.** Headroom is a macOS menu bar app. It proxies Claude Code
and Codex through a local compression pipeline, and claims about 50% token savings.

- Repo: https://github.com/gglucass/headroom-desktop. Latest version: v0.7.6.
- The desktop shell is MIT-licensed, but the app **requires a paid subscription**. Price
  starts at $3 per month, with a 7-day trial.
- The README's `brew install --cask headroom` command **does not work**. No such cask exists
  in any tapped repo, as of 2026-08-08. Use the `.dmg` file from
  https://github.com/gglucass/headroom-desktop/releases/latest instead.
- Headroom requires macOS 14 or later, on Apple Silicon. This machine runs macOS 26.4 on
  arm64, so it is compatible.

## status.sh

This is the toolkit's own health check. It is read-only and changes nothing. It walks every
symlink in `skills/` and confirms each one resolves and loads (`<name>@skills-dir`). It lists
installed plugins, with enabled or disabled status, using `claude plugin list`. It checks the
claude-mem worker (port 37701) and OmniRoute (port 20128) over HTTP. It confirms OmniRoute is
registered as an MCP server. Run it at any time:

```bash
~/claude-toolkit/status.sh
```

There is nothing to install or configure. This is the only script at the repo root. Every
other executable file lives inside its own skill folder, for example
`skills/ffuf-web-fuzzing/ffuf_helper.py`. Those files are not tracked here one by one.

## Serena

Serena ([oraios/serena](https://github.com/oraios/serena)) is a semantic code-navigation MCP
server. It gives LSP-backed symbol tools — `find_symbol`, `find_referencing_symbols`,
`replace_symbol_body`, and others — that stand in for grep, Read, and Edit on coding tasks. It
was not installed on purpose. The `zeroize-audit` plugin, from the `trailofbits` marketplace,
pulls it in and starts it automatically.

**How it is used:** you do not call it directly. Its own instructions (the "Serena
Instructions Manual," fetched with `initial_instructions`) tell Claude to prefer its tools
over the built-in ones, once loaded:
- **Reading**: use `get_symbols_overview` for a file's structure. Then use `find_symbol` with
  `include_body=True` for a specific symbol. Serena's own rules call plain `Read` "forbidden
  for discovery."
- **Editing**: use `replace_symbol_body`, `insert_after_symbol`, or `insert_before_symbol` for
  symbol-level changes. Use `rename_symbol` or `safe_delete_symbol` for reference-aware
  refactors. Use `replace_content` for smaller, sub-symbol edits. Plain `Edit` is "forbidden"
  once Serena's tools load for that turn.
- **Cross-reference**: use `find_referencing_symbols` to see what calls or imports a symbol,
  before you change it.
- Serena activates automatically for whichever project directory Claude runs in. It builds an
  LSP index and, per project, optional "memories" through `read_memory` and `write_memory`.
  These memories are unrelated to claude-mem — they cover code symbols, not conversations.
  Serena stores this state in `.serena/` inside the project root. Serena's own nested
  `.serena/.gitignore` file excludes the regenerable LSP `cache/` folder and the
  machine-specific `project.local.yml` file. The file `.serena/project.yml` holds plain
  settings (language servers, encoding, tool options) with no secrets, so this repo tracks it
  like any other project setting.

- Serena runs through `uvx --from git+https://github.com/oraios/serena serena start-mcp-server
  --context claude-code --project-from-cwd`. This spawns a background process, with one
  language server per configured language. This repo configures only `bash`.
- **Dashboard**: http://127.0.0.1:24282/dashboard/index.html. It shows a live log of every
  tool call the server makes, plus a shutdown button. A macOS menu-bar tray icon
  (`SerenaDashboardTrayManager`) mirrors the same dashboard.
- To stop Serena, find and kill the `serena start-mcp-server` process and the
  `SerenaDashboardTrayManager` process. Run `pgrep -fl serena` to find them. Or simply avoid
  any skill or plugin that depends on Serena — right now, only `zeroize-audit` does.

---

## All skills (175)

Every skill in `skills/`, grouped by what it's for — machine-generated from each `SKILL.md`'s frontmatter. Regenerate after adding or removing a skill:
```bash
uv run python scripts/categorize_skills.py --check   # flags anything uncategorized, exits 1 if so
uv run python scripts/categorize_skills.py            # prints the replacement section
```
It reads `skills/*/SKILL.md` directly, so it's always ground truth, not a stale snapshot — a new skill shows up as "uncategorized" in `--check` rather than silently missing from this list. `ste-writing` and `task-observer` also have full write-ups above; `humanizer` moved from a raw skill here to the `humanizer@humanizer` plugin once its real source (`blader/humanizer`) was confirmed. Same symlink convention as everything else: real files live in `skills/<name>/`, `~/.claude/skills/<name>` is a symlink — confirm with `./status.sh`. Categories are one judgment call per skill, not an upstream standard.

- [Core & Meta Skills](#core--meta-skills) (3)
- [Developer & Agent Tooling](#developer--agent-tooling) (9)
- [Security & Pentesting](#security--pentesting) (1)
- [Documents, Slides & Reports](#documents-slides--reports) (10)
- [Data Visualization & Graphics](#data-visualization--graphics) (8)
- [Research, Literature & Writing](#research-literature--writing) (19)
- [Statistics, Experimental Design & Reasoning](#statistics-experimental-design--reasoning) (19)
- [Bioinformatics & Genomics](#bioinformatics--genomics) (48)
- [Chemistry, Drug Discovery & Materials](#chemistry-drug-discovery--materials) (13)
- [Machine Learning & Compute Infrastructure](#machine-learning--compute-infrastructure) (18)
- [Quantum Computing & Physics](#quantum-computing--physics) (9)
- [Clinical & Healthcare](#clinical--healthcare) (7)
- [Lab Operations & Automation](#lab-operations--automation) (7)
- [Geospatial & Earth Science](#geospatial--earth-science) (2)
- [Media & Content Creation](#media--content-creation) (1)
- [Design & Frontend](#design--frontend) (1)

### Core & Meta Skills

| Skill | Source | Description |
|---|---|---|
| `autoskill` | K-Dense-AI/claude-scientific-skills | Observe the user's screen via screenpipe, detect repeated research workflows, match them against existing scientific-agent-skil... |
| `ste-writing` | loose file, ~/Downloads (2026-08-08) | Rewrite prose (docs, READMEs, PR descriptions, error messages, release notes, comments — never code) into ASD-STE100 Simplified... |
| `task-observer` | rebelytics/one-skill-to-rule-them-all (submodule) | Monitors task execution for skill improvement opportunities. Use this skill during ANY multi-step task, agentic workflow, or su... |

### Developer & Agent Tooling

| Skill | Source | Description |
|---|---|---|
| `find-skills` | vercel-labs/skills (find-skills) | Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a s... |
| `finding-duplicate-functions` | obra/superpowers-lab | Use when auditing a codebase for semantic duplication - functions that do the same thing but have different names or implementa... |
| `get-available-resources` | K-Dense-AI/claude-scientific-skills | Detect host inventory and effective CPU, memory, disk, scheduler, container, and accelerator limits when a user asks for resour... |
| `gstack` | garrytan/gstack | Router for the gstack skill suite. (gstack) |
| `mcp-cli` | obra/superpowers-lab | Use MCP servers on-demand via the mcp CLI tool - discover tools, resources, and prompts without polluting context with pre-load... |
| `pi-agent` | K-Dense-AI/claude-scientific-skills | Build with and use Pi, the minimal terminal coding harness. Use for installing Pi, configuring providers/models/settings/enviro... |
| `using-tmux-for-interactive-commands` | obra/superpowers-lab | Use when you need to run interactive CLI tools (vim, git rebase -i, Python REPL, etc.) that require real-time input/output - pr... |
| `which-skill` | written for this repo, 2026-08-16 | Use when unsure which of the many installed skills or plugins fits a request. Runs a fast local index search instead of reasoni... |
| `windows-vm` | obra/superpowers-lab | Create, manage, or connect to a headless Windows 11 VM running in Docker with SSH access. Use when the user wants to spin up, s... |

### Security & Pentesting

| Skill | Source | Description |
|---|---|---|
| `ffuf-web-fuzzing` | jthack/ffuf_claude_skill | Expert guidance for ffuf web fuzzing during penetration testing, including authenticated fuzzing with raw requests, auto-calibr... |

### Documents, Slides & Reports

| Skill | Source | Description |
|---|---|---|
| `docx` | K-Dense-AI/claude-scientific-skills | Use this skill whenever the user wants to create, read, edit, or manipulate Word documents (.docx files) or Word templates (.do... |
| `latex-posters` | K-Dense-AI/claude-scientific-skills | Create professional research posters in LaTeX using beamerposter, tikzposter, or baposter. Support for conference presentations... |
| `liteparse` | K-Dense-AI/claude-scientific-skills | Local document and PDF parsing that returns spatial text with bounding boxes. Use for extracting text from PDFs, DOCX, Office f... |
| `markitdown` | K-Dense-AI/claude-scientific-skills | Convert heterogeneous documents and selected URIs to Markdown with Microsoft MarkItDown for text analysis, search, and LLM/RAG ... |
| `pdf` | K-Dense-AI/claude-scientific-skills | Use this skill whenever the user wants to do anything with PDF files. This includes reading or extracting text/tables from PDFs... |
| `pptx` | K-Dense-AI/claude-scientific-skills | Use this skill any time a .pptx or .potx file is involved in any way — as input, output, or both. This includes: creating slide... |
| `pptx-posters` | K-Dense-AI/claude-scientific-skills | Create and audit editable scientific posters in macro-free PowerPoint (.pptx) from author-approved local content and assets. Us... |
| `scientific-slides` | K-Dense-AI/claude-scientific-skills | Build slide decks and presentations for research talks. Use this for making PowerPoint slides, conference presentations, semina... |
| `venue-templates` | K-Dense-AI/claude-scientific-skills | Prepare journal manuscripts, conference papers, research posters, and grant documents using venue-specific formatting guidance ... |
| `xlsx` | K-Dense-AI/claude-scientific-skills | Create, edit, analyze, or convert Excel spreadsheets (.xlsx, .xlsm, .xltx) where the workbook file is the primary deliverable. ... |

### Data Visualization & Graphics

| Skill | Source | Description |
|---|---|---|
| `d3-viz` | chrisvoncsefalvay/claude-d3js-skill | Creating interactive data visualisations using d3.js. This skill should be used when creating custom charts, graphs, network di... |
| `generate-image` | K-Dense-AI/claude-scientific-skills | Generate or edit images with AI models through the OpenRouter Image API (Gemini, Seedream, Recraft, GPT-Image, Riverflow). Use ... |
| `infographics` | K-Dense-AI/claude-scientific-skills | Create professional infographics using Nano Banana Pro AI with smart iterative refinement. Uses Gemini 3.6 Flash for quality re... |
| `matplotlib` | K-Dense-AI/claude-scientific-skills | Low-level plotting library for full customization. Use when you need fine-grained control over every plot element, creating nov... |
| `networkx` | K-Dense-AI/claude-scientific-skills | Create, analyze, and visualize complex networks and graphs in Python with NetworkX. Use when working with network/graph data st... |
| `scientific-schematics` | K-Dense-AI/claude-scientific-skills | Create publication-quality scientific diagrams using Nano Banana 2 AI with smart iterative refinement. Uses Gemini 3.6 Flash fo... |
| `scientific-visualization` | K-Dense-AI/claude-scientific-skills | Create and audit truthful, accessible, publication-ready scientific figures with Matplotlib, Seaborn, or Plotly. Use for figure... |
| `seaborn` | K-Dense-AI/claude-scientific-skills | Statistical visualization with pandas integration. Use for quick exploration of distributions, relationships, and categorical c... |

### Research, Literature & Writing

| Skill | Source | Description |
|---|---|---|
| `bgpt-paper-search` | K-Dense-AI/claude-scientific-skills | Search scientific papers and retrieve structured experimental data extracted from full-text studies via the BGPT MCP server. Re... |
| `citation-management` | K-Dense-AI/claude-scientific-skills | Comprehensive citation management for academic research. Search OpenAlex, PubMed, and Google Scholar for papers, extract accura... |
| `database-lookup` | K-Dense-AI/claude-scientific-skills | Query documented public database APIs with explicit endpoints, filters, pagination, and provenance. Use when a scientific, regu... |
| `exa-search` | K-Dense-AI/claude-scientific-skills | Web toolkit powered by Exa, tuned for scientific and technical content. Use this skill when the user needs to search the web or... |
| `literature-review` | K-Dense-AI/claude-scientific-skills | Conduct comprehensive, systematic literature reviews using multiple academic databases (PubMed, arXiv, bioRxiv, Semantic Schola... |
| `markdown-mermaid-writing` | K-Dense-AI/claude-scientific-skills | Comprehensive markdown and Mermaid diagram writing skill. Use when creating any scientific document, report, analysis, or visua... |
| `market-research-reports` | K-Dense-AI/claude-scientific-skills | Build evidence-traceable market research reports and assumption-driven market sizing or forecast scenarios. Use for market defi... |
| `open-notebook` | K-Dense-AI/claude-scientific-skills | Self-hosted, open-source alternative to Google NotebookLM for AI-powered research and document analysis. Use when organizing re... |
| `paper-lookup` | K-Dense-AI/claude-scientific-skills | Search 11 academic literature APIs for papers, preprints, citations, and open-access full text, and return results with reprodu... |
| `paperclip` | K-Dense-AI/claude-scientific-skills | Search and read full-text biomedical papers, FDA/PMDA/EMA regulatory documents, clinical trial registries, and UniProt/PDB/ChEM... |
| `paperzilla` | K-Dense-AI/claude-scientific-skills | Chat with your agent about projects, recommendations, and canonical papers in Paperzilla. Use when users ask for recent project... |
| `parallel-web` | K-Dense-AI/claude-scientific-skills | Use Parallel CLI for web search, URL extraction, deep research, structured data enrichment, entity discovery, and recurring web... |
| `peer-review` | K-Dense-AI/claude-scientific-skills | Prepare evidence-bounded, constructive peer-review drafts and structured manuscript assessments. Use for authorized review of s... |
| `pyzotero` | K-Dense-AI/claude-scientific-skills | Interact with Zotero reference management libraries using the pyzotero Python client. Retrieve, create, update, and delete item... |
| `research-grants` | K-Dense-AI/claude-scientific-skills | Write competitive research proposals for NSF, NIH, DOE, DARPA, and Taiwan NSTC. Agency-specific formatting, review criteria, bu... |
| `research-lookup` | K-Dense-AI/claude-scientific-skills | Compile current scholarly evidence for a scientific manuscript or research brief. Use when the user explicitly asks to gather l... |
| `scholar-evaluation` | K-Dense-AI/claude-scientific-skills | Provide qualitative-first, evidence-traceable developmental review of scholarly works and audit low-stakes research-assessment ... |
| `scientific-writing` | K-Dense-AI/claude-scientific-skills | Draft, revise, and audit scientific manuscripts or reports with explicit evidence provenance, reporting-guideline coverage, aut... |
| `usfiscaldata` | K-Dense-AI/claude-scientific-skills | Query the U.S. Treasury Fiscal Data REST API for federal financial data. No API key required. Use for national debt (Debt to th... |

### Statistics, Experimental Design & Reasoning

| Skill | Source | Description |
|---|---|---|
| `analytical-method-validation` | K-Dense-AI/claude-scientific-skills | Plan, execute, and document validation, verification, and transfer of analytical procedures under the governing framework - ICH... |
| `consciousness-council` | K-Dense-AI/claude-scientific-skills | Run a multi-perspective Mind Council deliberation on any question, decision, or creative challenge. Use this skill whenever the... |
| `dhdna-profiler` | K-Dense-AI/claude-scientific-skills | Extract cognitive patterns and thinking fingerprints from any text. Use this skill when the user wants to analyze how someone t... |
| `experimental-design` | K-Dense-AI/claude-scientific-skills | Design experiments and studies BEFORE data is collected — choosing a design, randomizing, blocking, and laying out treatment co... |
| `exploratory-data-analysis` | K-Dense-AI/claude-scientific-skills | Perform bounded, local exploratory analysis of explicitly supported scientific files. Use for redacted CSV/TSV/JSON profiles; o... |
| `hypogenic` | K-Dense-AI/claude-scientific-skills | Plans and audits use of ChicagoHAI HypoGeniC/HypoRefine for LLM-assisted hypothesis generation from labeled text datasets. Use ... |
| `hypothesis-generation` | K-Dense-AI/claude-scientific-skills | Formulate evidence-bounded scientific questions, candidate hypotheses, rival explanations, causal or associational claims, disc... |
| `pymc` | K-Dense-AI/claude-scientific-skills | Bayesian modeling with PyMC. Build hierarchical models, MCMC (NUTS), variational inference, LOO/WAIC comparison, posterior chec... |
| `pymoo` | K-Dense-AI/claude-scientific-skills | Multi-objective optimization framework. NSGA-II, NSGA-III, MOEA/D, Pareto fronts, constraint handling, benchmarks (ZDT, DTLZ), ... |
| `relsa-severity-assessment` | K-Dense-AI/claude-scientific-skills | Multivariate severity assessment and humane endpoint prediction for laboratory animal studies using the RELSA (RELative Severit... |
| `scientific-brainstorming` | K-Dense-AI/claude-scientific-skills | Facilitates evidence-aware scientific ideation with independent generation, structured discussion, explicit assumptions, transp... |
| `scientific-critical-thinking` | K-Dense-AI/claude-scientific-skills | Evaluate scientific claims and evidence quality. Use for assessing experimental design validity, identifying biases and confoun... |
| `scikit-survival` | K-Dense-AI/claude-scientific-skills | Build, evaluate, and audit right-censored or competing-risk survival workflows with scikit-survival, including leakage-safe pre... |
| `simpy` | K-Dense-AI/claude-scientific-skills | Build, inspect, test, and analyze bounded process-based discrete-event simulations with SimPy, including events, resources, int... |
| `statistical-analysis` | K-Dense-AI/claude-scientific-skills | Guided statistical analysis for research data - test selection, assumption checking, effect sizes, power analysis, Bayesian alt... |
| `statistical-power` | K-Dense-AI/claude-scientific-skills | Sample-size and statistical power calculations for planning studies. Use whenever someone asks "how many subjects/samples/repli... |
| `statsmodels` | K-Dense-AI/claude-scientific-skills | Statistical models library for Python. Use when you need specific model classes (OLS, GLM, mixed models, ARIMA) with detailed d... |
| `uncertainty-and-units` | K-Dense-AI/claude-scientific-skills | Track physical units and propagate measurement uncertainty in scientific calculations using pint and uncertainties. Use for uni... |
| `what-if-oracle` | K-Dense-AI/claude-scientific-skills | Run structured What-If scenario analysis with 4–6 branch possibility exploration (best, likely, worst, wild card, contrarian, s... |

### Bioinformatics & Genomics

| Skill | Source | Description |
|---|---|---|
| `adaptyv` | K-Dense-AI/claude-scientific-skills | How to use the Adaptyv Bio Foundry API and Python SDK for protein experiment design, submission, and results retrieval. Use thi... |
| `anndata` | K-Dense-AI/claude-scientific-skills | Data structure for annotated matrices in single-cell analysis. Use when working with .h5ad files or integrating with the scvers... |
| `arboreto` | K-Dense-AI/claude-scientific-skills | Infer gene regulatory networks (GRNs) from gene expression data using scalable algorithms (GRNBoost2, GENIE3). Use when analyzi... |
| `bids` | K-Dense-AI/claude-scientific-skills | Use this skill when working with Brain Imaging Data Structure (BIDS) datasets: organizing neuroscience and biomedical data (MRI... |
| `biopython` | K-Dense-AI/claude-scientific-skills | Comprehensive molecular biology toolkit. Use for sequence manipulation, file parsing (FASTA/GenBank/PDB), phylogenetics, and pr... |
| `bioservices` | K-Dense-AI/claude-scientific-skills | Unified Python interface to 40+ bioinformatics services. Use when querying multiple databases (UniProt, KEGG, ChEMBL, Reactome)... |
| `bulk-rnaseq` | K-Dense-AI/claude-scientific-skills | End-to-end bulk RNA-seq orchestrator — takes raw FASTQ reads through QC and trimming (FastQC, fastp/Trim Galore), alignment and... |
| `cellxgene-census` | K-Dense-AI/claude-scientific-skills | Query the CZ CELLxGENE Census programmatically for versioned public single-cell and spatial transcriptomics data. Use when you ... |
| `cobrapy` | K-Dense-AI/claude-scientific-skills | Constraint-based metabolic modeling (COBRA). FBA, FVA, gene knockouts, flux sampling, SBML models, for systems biology and meta... |
| `deepspot-m` | K-Dense-AI/claude-scientific-skills | Generate transcriptome-wide virtual spatial transcriptomics from H&E histology with DeepSpot-M. Use when you need spatial gene ... |
| `deeptools` | K-Dense-AI/claude-scientific-skills | NGS analysis toolkit. BAM to bigWig conversion, QC (correlation, PCA, fingerprints), heatmaps/profiles (TSS, peaks), for ChIP-s... |
| `depmap` | K-Dense-AI/claude-scientific-skills | Query the Cancer Dependency Map (DepMap) for cancer cell line gene dependency scores (CRISPR Chronos), drug sensitivity data, a... |
| `dnanexus-integration` | K-Dense-AI/claude-scientific-skills | Build and operate reproducible genomics workloads on DNAnexus with the dx CLI, dxpy, apps/applets, native workflows, dxCompiler... |
| `esm` | K-Dense-AI/claude-scientific-skills | Use when working directly with the `esm` Python SDK, ESM3 or ESMC model IDs, Forge/Biohub inference clients, or ESMFold2 foldin... |
| `etetoolkit` | K-Dense-AI/claude-scientific-skills | Analyze, manipulate, compare, annotate, and visualize phylogenetic or other hierarchical trees with ETE 4. Use for Newick/Nexus... |
| `flowio` | K-Dense-AI/claude-scientific-skills | Read, inspect, and write Flow Cytometry Standard (FCS) 2.0, 3.0, and 3.1 files with FlowIO. Use for low-level FCS metadata and ... |
| `geniml` | K-Dense-AI/claude-scientific-skills | Use Geniml for audited local genomic-interval workflows: validate BED and universe contracts, plan Region2Vec or scEmbed runs, ... |
| `genomic-coordinates` | K-Dense-AI/claude-scientific-skills | Convert genomic intervals between coordinate conventions, normalise and compare variant representations, and detect assembly or... |
| `genomic-intelligence` | K-Dense-AI/claude-scientific-skills | Predict regulatory features, gene structure, and expression directly from DNA sequence using Genomic Intelligence's hosted tran... |
| `gget` | K-Dense-AI/claude-scientific-skills | Fast CLI/Python queries to 20+ bioinformatics databases. Use for quick lookups: gene info, BLAST/BLAT, viral sequence downloads... |
| `glycoengineering` | K-Dense-AI/claude-scientific-skills | Analyze and engineer protein glycosylation. Scan sequences for N-glycosylation sequons (N-X-S/T), predict O-glycosylation hotsp... |
| `gtars` | K-Dense-AI/claude-scientific-skills | Use Gtars for local genomic interval models and set algebra, overlaps and counts, consensus and coverage, tokenization, fragmen... |
| `histolab` | K-Dense-AI/claude-scientific-skills | Lightweight WSI tile extraction and preprocessing. Use for basic slide processing, tissue detection, tile extraction, and stain... |
| `imaging-data-commons` | K-Dense-AI/claude-scientific-skills | Query and download public cancer imaging data from NCI Imaging Data Commons. Invoke for any question about IDC collections, can... |
| `lamindb` | K-Dense-AI/claude-scientific-skills | Use when working with LaminDB, the open-source lineage-native lakehouse for biological datasets and models. Covers setup, artif... |
| `latchbio-integration` | K-Dense-AI/claude-scientific-skills | Build, register, debug, and operate bioinformatics workflows on Latch using the Python SDK, CLI, Latch Data and Registry, Nextf... |
| `molecular-dynamics` | K-Dense-AI/claude-scientific-skills | Run and analyze molecular dynamics simulations with OpenMM and MDAnalysis. Set up protein/small molecule systems, define force ... |
| `ncats-arax` | K-Dense-AI/claude-scientific-skills | Queries the NCATS Translator ARAX production API for bounded, typed, provenance-rich one-hop and endpoint-pinned two-hop biomed... |
| `neurokit2` | K-Dense-AI/claude-scientific-skills | Use NeuroKit2 to build or audit reproducible research workflows for physiological time-series preprocessing, event/interval ana... |
| `neuropixels-analysis` | K-Dense-AI/claude-scientific-skills | Analyze Neuropixels extracellular recordings end-to-end with SpikeInterface. Covers loading SpikeGLX/Open Ephys/NWB data, prepr... |
| `nextflow` | K-Dense-AI/claude-scientific-skills | Build, run, and debug Nextflow data pipelines and nf-core workflows end to end. Use whenever the user mentions Nextflow, nf-cor... |
| `omero-integration` | K-Dense-AI/claude-scientific-skills | Securely inspect and automate microscopy data workflows against OMERO.server with omero-py, BlitzGateway, OMERO CLI, tables, an... |
| `onekgpd` | K-Dense-AI/claude-scientific-skills | Query the 1000 Genomes Project dataset (3,202 whole-genome-sequenced individuals, GRCh38) at the level of individual participan... |
| `ontology-term-resolution` | K-Dense-AI/claude-scientific-skills | Resolve free-text scientific labels to ontology term IDs and validate existing CURIEs against the EBI Ontology Lookup Service (... |
| `pacsomatic` | K-Dense-AI/claude-scientific-skills | Operator toolkit for nf-core/pacsomatic matched tumor-normal workflows from BAM inputs. Use this skill when the user needs to v... |
| `pathml` | K-Dense-AI/claude-scientific-skills | Use PathML for local, research-only computational pathology workflows: load and tile slides, build preprocessing and QC pipelin... |
| `pathogen-variant-surveillance` | K-Dense-AI/claude-scientific-skills | Query live pathogen genomic surveillance data through the GenSpectrum LAPIS API to find which viral lineages are circulating no... |
| `pathway-enrichment` | K-Dense-AI/claude-scientific-skills | Run pathway and gene-set enrichment analysis on gene lists or ranked gene data, then interpret the results. Use whenever the us... |
| `phylogenetics` | K-Dense-AI/claude-scientific-skills | Build and analyze phylogenetic trees using MAFFT (multiple alignment), IQ-TREE 2 (maximum likelihood), and FastTree (fast NJ/ML... |
| `polars-bio` | K-Dense-AI/claude-scientific-skills | High-performance genomic interval operations and bioinformatics file I/O on Polars DataFrames. Overlap, nearest, merge, coverag... |
| `primekg` | K-Dense-AI/claude-scientific-skills | Query the Precision Medicine Knowledge Graph (PrimeKG) for multiscale biological data including genes, drugs, diseases, phenoty... |
| `pydeseq2` | K-Dense-AI/claude-scientific-skills | Differential gene expression analysis for bulk RNA-seq with PyDESeq2, including formulaic designs, Wald tests, FDR correction, ... |
| `pysam` | K-Dense-AI/claude-scientific-skills | Python/HTSlib workflows for genomic files. Use when reading, querying, filtering, or writing SAM/BAM/CRAM, VCF/BCF, FASTA/FASTQ... |
| `scanpy` | K-Dense-AI/claude-scientific-skills | Standard single-cell RNA-seq analysis pipeline. Use for QC, normalization, dimensionality reduction (PCA/UMAP/t-SNE), clusterin... |
| `scikit-bio` | K-Dense-AI/claude-scientific-skills | Biological data toolkit. Sequence analysis, alignments, phylogenetic trees, diversity metrics (alpha/beta, UniFrac), ordination... |
| `scvelo` | K-Dense-AI/claude-scientific-skills | RNA velocity analysis with scVelo. Estimate cell state transitions from unspliced/spliced mRNA dynamics, infer trajectory direc... |
| `scvi-tools` | K-Dense-AI/claude-scientific-skills | Deep generative models for single-cell omics. Use when you need probabilistic batch correction (scVI), transfer learning, diffe... |
| `tiledbvcf` | K-Dense-AI/claude-scientific-skills | Efficient storage and retrieval of genomic variant data using TileDB. Scalable VCF/BCF ingestion, incremental sample addition, ... |

### Chemistry, Drug Discovery & Materials

| Skill | Source | Description |
|---|---|---|
| `datamol` | K-Dense-AI/claude-scientific-skills | Pythonic wrapper around RDKit with simplified interface and sensible defaults. Preferred for standard drug discovery including ... |
| `deepchem` | K-Dense-AI/claude-scientific-skills | Molecular ML with diverse featurizers and pre-built datasets. Use for property prediction (ADMET, toxicity) with traditional ML... |
| `diffdock` | K-Dense-AI/claude-scientific-skills | DiffDock and DiffDock-L molecular docking. Use for protein-small-molecule pose prediction from PDB or sequence plus SMILES/SDF/... |
| `matchms` | K-Dense-AI/claude-scientific-skills | Process, clean, compare, and search tandem mass spectra with matchms. Use for MS/MS file I/O, metadata harmonization, peak filt... |
| `medchem` | K-Dense-AI/claude-scientific-skills | Medicinal chemistry filters for compound triage. Apply drug-likeness rules (Lipinski, Veber, CNS), structural alert catalogs (P... |
| `molfeat` | K-Dense-AI/claude-scientific-skills | Molecular featurization for ML (100+ featurizers). ECFP, MACCS, descriptors, pretrained models (ChemBERTa), convert SMILES to f... |
| `pymatgen` | K-Dense-AI/claude-scientific-skills | Analyze, validate, convert, and transform materials structures and computed materials data with current pymatgen APIs, includin... |
| `pyopenms` | K-Dense-AI/claude-scientific-skills | Complete mass spectrometry analysis platform. Use for proteomics and metabolomics workflows—feature detection, peptide/protein ... |
| `pytdc` | K-Dense-AI/claude-scientific-skills | Use Therapeutics Data Commons through the PyTDC Python package for registry discovery, approved dataset access, task-aware spli... |
| `rdkit` | K-Dense-AI/claude-scientific-skills | Cheminformatics toolkit for fine-grained molecular control. SMILES/SDF parsing, descriptors (MW, LogP, TPSA), fingerprints, sub... |
| `rowan` | K-Dense-AI/claude-scientific-skills | Rowan is a cloud-native molecular modeling and medicinal-chemistry workflow platform with a Python API. Use for pKa and macropK... |
| `tamarind` | K-Dense-AI/claude-scientific-skills | Access a collection of open-source molecular design and structural biology tools on the Tamarind Bio platform, via its REST API... |
| `torchdrug` | K-Dense-AI/claude-scientific-skills | Build and troubleshoot TorchDrug 0.2.1 workflows for molecular graphs, property prediction, self-supervised pretraining, molecu... |

### Machine Learning & Compute Infrastructure

| Skill | Source | Description |
|---|---|---|
| `aeon` | K-Dense-AI/claude-scientific-skills | This skill should be used for time series machine learning tasks including classification, regression, clustering, forecasting,... |
| `arbor` | K-Dense-AI/claude-scientific-skills | Autonomously improve a real artifact (code, training recipe, agent harness, data pipeline, prompt) against an objective and an ... |
| `dask` | K-Dense-AI/claude-scientific-skills | Distributed computing for larger-than-RAM pandas/NumPy workflows. Use when you need to scale existing pandas/NumPy code beyond ... |
| `hugging-science` | K-Dense-AI/claude-scientific-skills | Use when the user is doing AI/ML work in a scientific domain such as biology, chemistry, physics, astronomy, climate, genomics,... |
| `modal` | K-Dense-AI/claude-scientific-skills | Modal is a serverless cloud platform for running Python on demand, including on-demand GPUs. Use when deploying or serving AI/M... |
| `optimize-for-gpu` | K-Dense-AI/claude-scientific-skills | GPU-accelerates scientific Python on NVIDIA hardware and verifies that the result is correct and faster. Use for CUDA/GPU optim... |
| `polars` | K-Dense-AI/claude-scientific-skills | High-performance DataFrame library for Python ETL, analytics, and pandas migration. Use for expression-based data manipulation ... |
| `pufferlib` | K-Dense-AI/claude-scientific-skills | Version-aware guidance for PufferLib reinforcement-learning environments, vectorization, policies, PuffeRL training, evaluation... |
| `pytorch-lightning` | K-Dense-AI/claude-scientific-skills | Deep learning framework (PyTorch Lightning / lightning package). Organize PyTorch code into LightningModules, configure Trainer... |
| `scikit-learn` | K-Dense-AI/claude-scientific-skills | Machine learning in Python with scikit-learn. Use when working with supervised learning (classification, regression), unsupervi... |
| `shap` | K-Dense-AI/claude-scientific-skills | Explain and audit machine-learning predictions with SHAP. Use for selecting SHAP explainers and maskers, computing and validati... |
| `stable-baselines3` | K-Dense-AI/claude-scientific-skills | Production-ready reinforcement learning algorithms (PPO, SAC, DQN, TD3, DDPG, A2C) with scikit-learn-like API. Use for standard... |
| `timesfm-forecasting` | K-Dense-AI/claude-scientific-skills | Zero-shot time series forecasting with Google's TimesFM foundation model. Use for any univariate time series (sales, sensors, e... |
| `torch-geometric` | K-Dense-AI/claude-scientific-skills | PyTorch Geometric (PyG) for graph neural networks — node/link/graph classification, message passing (GCN, GAT, GraphSAGE, GIN),... |
| `transformers` | K-Dense-AI/claude-scientific-skills | Hugging Face Transformers for loading Hub models, running pipeline inference, text generation, and Trainer fine-tuning on NLP, ... |
| `umap-learn` | K-Dense-AI/claude-scientific-skills | Use UMAP-learn for nonlinear dimensionality reduction, 2D/3D embeddings, clustering preprocessing, supervised or semi-supervise... |
| `vaex` | K-Dense-AI/claude-scientific-skills | Use this skill for processing and analyzing large tabular datasets (billions of rows) that exceed available RAM. Vaex excels at... |
| `zarr-python` | K-Dense-AI/claude-scientific-skills | Chunked N-D arrays for cloud storage (Zarr-Python 3). Compressed arrays, parallel I/O, S3/GCS via fsspec, NumPy/Dask/Xarray com... |

### Quantum Computing & Physics

| Skill | Source | Description |
|---|---|---|
| `astropy` | K-Dense-AI/claude-scientific-skills | Core Python library for astronomy and astrophysics workflows that need Astropy APIs, including units/quantities, coordinates, F... |
| `cirq` | K-Dense-AI/claude-scientific-skills | Google quantum computing framework. Use when targeting Google Quantum AI hardware, designing noise-aware circuits, or running q... |
| `fluidsim` | K-Dense-AI/claude-scientific-skills | Plan, configure, inspect, restart, and analyze bounded FluidSim computational-fluid-dynamics simulations with explicit numerica... |
| `matlab` | K-Dense-AI/claude-scientific-skills | Build, review, migrate, and safely plan MATLAB or GNU Octave numerical workflows, including arrays, tabular/time data, tests, p... |
| `openpiv` | K-Dense-AI/claude-scientific-skills | Particle Image Velocimetry (PIV) analysis with OpenPIV. Use when extracting velocity fields from PIV image pairs, analyzing flu... |
| `pennylane` | K-Dense-AI/claude-scientific-skills | Hardware-agnostic quantum ML framework with automatic differentiation. Use when training quantum circuits via gradients, buildi... |
| `qiskit` | K-Dense-AI/claude-scientific-skills | Build, simulate, transpile, and execute quantum circuits with Qiskit and IBM Quantum Runtime. Use for Qiskit 2.x circuits and o... |
| `qutip` | K-Dense-AI/claude-scientific-skills | Simulate and audit closed and open quantum-system models with QuTiP 5, including deterministic, trajectory, steady-state, spect... |
| `sympy` | K-Dense-AI/claude-scientific-skills | Use when you need exact symbolic math in Python — algebra, calculus, equation solving, symbolic linear algebra, or code generat... |

### Clinical & Healthcare

| Skill | Source | Description |
|---|---|---|
| `clinical-decision-support` | K-Dense-AI/claude-scientific-skills | Prepare and validate research-only clinical decision-support evaluation, evidence-profile, cohort, survival, biomarker/model, p... |
| `clinical-reports` | K-Dense-AI/claude-scientific-skills | Create safety-bounded draft structures and run local deterministic checks for clinical case, diagnostic, trial, safety, and agg... |
| `iso-standards-readiness` | K-Dense-AI/claude-scientific-skills | Prepares and structurally reviews readiness evidence for ISO management-system and laboratory-competence standards - ISO 13485 ... |
| `pkpd-modeling` | K-Dense-AI/claude-scientific-skills | Pharmacokinetic and pharmacodynamic modelling and simulation - non-compartmental analysis, compartmental and population PK, PK/... |
| `pydicom` | K-Dense-AI/claude-scientific-skills | Use pydicom to read, inspect, write, transform, and safely preflight local DICOM datasets and pixel data. Applies to DICOM meta... |
| `pyhealth` | K-Dense-AI/claude-scientific-skills | Build clinical/healthcare deep-learning pipelines with PyHealth — loading EHR/signal/imaging datasets (MIMIC-III/IV, eICU, OMOP... |
| `treatment-plans` | K-Dense-AI/claude-scientific-skills | Format and structurally validate local treatment-plan documentation after clinical decisions have already been supplied and ver... |

### Lab Operations & Automation

| Skill | Source | Description |
|---|---|---|
| `benchling-integration` | K-Dense-AI/claude-scientific-skills | Benchling Python SDK and REST API integration for registry entities, inventory, ELN entries, workflows, Benchling Apps, and Dat... |
| `ginkgo-cloud-lab` | K-Dense-AI/claude-scientific-skills | Submit and manage protocols on Ginkgo Bioworks Cloud Lab (cloud.ginkgo.bio), a web-based interface for autonomous lab execution... |
| `lab-hardware-cad` | K-Dense-AI/claude-scientific-skills | Design custom laboratory hardware as parametric build123d models and export fabrication-ready STEP, STL, and DXF files - microf... |
| `labarchive-integration` | K-Dense-AI/claude-scientific-skills | Securely integrate with the official LabArchives ELN REST-like API and Inventory API v1. Use for regional endpoint selection, s... |
| `opentrons-integration` | K-Dense-AI/claude-scientific-skills | Author, review, migrate, simulate, and troubleshoot official Opentrons Python Protocol API v2 protocols for Flex and OT-2 robot... |
| `protocolsio-integration` | K-Dense-AI/claude-scientific-skills | Read, validate, and safely export protocols.io data with current official REST/MCP contracts, or create non-executing mutation ... |
| `pylabrobot` | K-Dense-AI/claude-scientific-skills | Develop and review PyLabRobot lab-automation resources, liquid-handling plans, offline simulations, and supported-device integr... |

### Geospatial & Earth Science

| Skill | Source | Description |
|---|---|---|
| `geomaster` | K-Dense-AI/claude-scientific-skills | Comprehensive geospatial science skill covering remote sensing, GIS, spatial analysis, machine learning for earth observation, ... |
| `geopandas` | K-Dense-AI/claude-scientific-skills | Guidance and local audit tools for Python workflows that directly use GeoPandas GeoSeries, GeoDataFrame, spatial operations, or... |

### Media & Content Creation

| Skill | Source | Description |
|---|---|---|
| `video-use` | browser-use/video-use | Edit any video by conversation. Transcribe, cut, color grade, generate overlay animations, burn subtitles — for talking heads, ... |

### Design & Frontend

| Skill | Source | Description |
|---|---|---|
| `emil-design-eng` | emilkowalski/skills (emil-design-eng) | This skill encodes Emil Kowalski's philosophy on UI polish, component design, animation decisions, and the invisible details th... |

## Bulk-installed plugins (2026-08-16)

These plugins were installed with `claude plugin install`, from marketplaces added the same
day: superpowers, ai-toolkit, mattpocock, terrashark, anthropic-agent-skills, conorluddy,
playwright-skill, web-asset-generator-marketplace, frontend-slides, expo-plugins, trailofbits,
and claude-plugins-official. Their code is not copied here, the same way as claude-mem and
claude-code-setup above. This table is only an index. Run `claude plugin list` for live status.

| Plugin | Marketplace | Description |
|---|---|---|
| agentic-actions-auditor | trailofbits | Audits GitHub Actions workflows for security vulnerabilities in AI agent integrations (Claude Code Action, Gemini CLI, OpenAI Codex, GitHub AI Inference) |
| brag | brag | Turn the current project's website into a short, shareable launch video using HyperFrames |
| ai-toolkit | spartan-marketplace | Engineering discipline layer for Claude Code — workflows, rules, skills, agents organized in modular packs |
| audit-context-building | trailofbits | Understand a codebase before looking for bugs in it. Reads it function by function, records what each one assumes and depends on, and saves the write-ups to files instead of filling up the conversation. |
| building-secure-contracts | trailofbits | Comprehensive smart contract security toolkit based on Trail of Bits' Building Secure Contracts framework. Includes vulnerability scanners for 6 blockchains and 5 development guideline assistants. |
| burpsuite-project-parser | trailofbits | Search and extract data from Burp Suite project files (.burp) for security analysis |
| c-review | trailofbits | Comprehensive C/C++ security code review with specialized bug-finding agents covering memory safety, type safety, concurrency, and Linux/Windows userspace-specific issues |
| claude-api | anthropic-agent-skills | Claude API and SDK documentation skill for building LLM-powered applications |
| claude-code-setup | claude-plugins-official | Analyze codebases and recommend tailored Claude Code automations such as hooks, skills, MCP servers, and subagents. |
| claude-in-chrome-troubleshooting | trailofbits | Diagnose and fix Claude in Chrome MCP extension connectivity issues |
| claude-mem | thedotmack | Persistent memory system for Claude Code - context compression across sessions |
| code-simplifier | claude-plugins-official | Agent that simplifies and refines code for clarity, consistency, and maintainability while preserving functionality. Focuses on recently modified code. |
| constant-time-analysis | trailofbits | Detect compiler-induced timing side-channels in cryptographic code |
| culture-index | trailofbits | Interprets Culture Index survey results for individuals and teams |
| devcontainer-setup | trailofbits | Create pre-configured devcontainers with Claude Code and language-specific tooling |
| differential-review | trailofbits | Security-focused differential review of code changes with git history analysis and blast radius estimation |
| dimensional-analysis | trailofbits | Annotates codebases with dimensional analysis comments documenting units, dimensions, and decimal scaling. Use when someone asks to annotate units in a codebase, perform a dimensional analysis, or find vulnerabilities in a DeFi protocol. Prevents dimensional mismatches and catches formula bugs early. |
| document-skills | anthropic-agent-skills | Collection of document processing suite including Excel, Word, PowerPoint, and PDF capabilities |
| dwarf-expert | trailofbits | Analyze DWARF debug information: parse and search DIEs with dwarfdump and readelf, verify debug info integrity, and write DWARF parsing code |
| entry-point-analyzer | trailofbits | Analyzes smart contract codebases to identify state-changing entry points for security auditing. Detects externally callable functions that modify state, categorizes them by access level, and generates structured audit reports. |
| example-skills | anthropic-agent-skills | Collection of example skills demonstrating various capabilities including skill creation, MCP building, visual design, algorithmic art, internal communications, web testing, artifact building, Slack GIFs, and theme styling |
| expo | expo-plugins | Official Expo skills for building, deploying, upgrading, and debugging Expo apps. |
| expo-experiments | expo-plugins | Experimental Expo skills for APIs that are not finalized. Skills graduate to the expo plugin when stable. |
| firebase-apk-scanner | trailofbits | Scan Android APKs for Firebase security misconfigurations including open databases, storage buckets, authentication issues, and exposed cloud functions. For authorized security research only. |
| fp-check | trailofbits | Systematic false positive verification for security bug analysis with mandatory gate reviews |
| frontend-slides | frontend-slides | Zero-dependency HTML presentation generator with safe presets, bold template-library styles, PPT conversion, and anti-AI-slop design philosophy. |
| gh-cli | trailofbits | Intercepts GitHub URL fetches and curl/wget commands, redirecting to the authenticated gh CLI. |
| git-cleanup | trailofbits | Safely analyzes and cleans up local git branches and worktrees by categorizing them as merged, squash-merged, superseded, or active work. |
| github-triage | trailofbits | Triages a repository's open GitHub issues and pull requests via the gh CLI: optionally merges ready bot and maintainer-approved PRs and spawns review subagents for unreviewed ones, closes already-resolved issues with referenced explanations, cross-links issues with pending fix PRs, and assigns local-only priority and change-size estimates. |
| insecure-defaults | trailofbits | Detects insecure default configurations including hardcoded credentials, fallback secrets, weak authentication defaults, and dangerous values in production |
| ios-simulator-skill | conorluddy | 29 production-ready scripts for iOS app testing, building, and automation |
| let-fate-decide | trailofbits | Draws the 12 Houses of the Zodiac Tarot spread using cryptographic randomness to add 100+ bits of entropy to vague or underspecified planning. Interprets the spread to guide next steps. Use when feeling lucky, invoking heart-of-the-cards energy, or when prompts are ambiguous. |
| mattpocock-skills | mattpocock | Matt Pocock's agent skills for real engineering — grilling, spec/ticket flows, TDD, code review, domain modelling and more. |
| modern-python | trailofbits | Modern Python best practices. Use when creating new Python projects, and writing Python scripts, or migrating existing projects from legacy tools. |
| mutation-testing | trailofbits | Configures mewt or muton mutation testing campaigns — scopes targets, tunes timeouts, and optimizes long-running runs. Use when the user mentions mewt, muton, mutation testing, or wants to configure or optimize a mutation testing campaign. |
| open-sourcing | trailofbits | Prepares a repository for public open-source release: secrets-history hygiene, license selection, documentation and CI readiness checks, and language-specific packaging and release guidance. |
| playwright-skill | playwright-skill | Agent Skill for general-purpose browser automation with Playwright. The agent writes and executes custom scripts for testing pages, validating UX, and automating browser tasks. |
| property-based-testing | trailofbits | Property-based testing guidance for multiple languages and smart contracts |
| pyright-lsp | claude-plugins-official | Python language server (Pyright) for type checking and code intelligence |
| rust-review | trailofbits | Comprehensive Rust security code review with specialized bug-finding agents covering the safe/unsafe boundary, memory safety in unsafe blocks, concurrency, panic-induced DoS, recursion-induced stack overflow, FFI, and async runtime hazards |
| second-opinion | trailofbits | Runs code reviews using external LLM CLIs (OpenAI Codex, Google Gemini) on uncommitted changes, branch diffs, or specific commits. Bundles Codex's built-in MCP server for direct tool access. |
| semgrep-rule-creator | trailofbits | Create custom Semgrep rules for detecting bug patterns and security vulnerabilities |
| semgrep-rule-variant-creator | trailofbits | Creates language variants of existing Semgrep rules with proper applicability analysis and test-driven validation |
| sharp-edges | trailofbits | Identify error-prone APIs, dangerous configurations, and footgun designs that enable security mistakes |
| skill-improver | trailofbits | Automatically reviews and fixes Claude Code skills through iterative refinement until they meet quality standards. Requires plugin-dev plugin. |
| spec-to-code-compliance | trailofbits | Check code against the documentation that specifies it: one agent per requirement, divergences refuted before they are reported, evidence cited to the line |
| static-analysis | trailofbits | Static analysis toolkit with CodeQL, Semgrep, and SARIF parsing for security vulnerability detection |
| superpowers | superpowers-dev | Core skills library for Claude Code: TDD, debugging, collaboration patterns, and proven techniques |
| supply-chain-risk-auditor | trailofbits | Audit a project's npm, PyPI, and Go dependencies for supply-chain risk: version-matched advisories for direct dependencies and the full lockfile tree, abandoned upstreams, npm publisher concentration, and install scripts |
| terrashark | terrashark | Terraform/OpenTofu Guardrails |
| testing-handbook-skills | trailofbits | Skills from the Trail of Bits Application Security Testing Handbook (appsec.guide) |
| trailmark | trailofbits | Builds multi-language source and binary code graphs for security analysis: call graphs, attack surface mapping, blast radius, taint propagation, complexity hotspots, entry point enumeration, proxy/unresolved-call tracking, type/reference analysis, and structural diffs. Creates bounded, graph-informed source packets for delegating focused work to constrained subagents. Generates Mermaid diagrams, runs graph-informed mutation testing triage (genotoxic), generates mutation-driven test vectors (vector-forge), extracts crypto protocol message flows, converts Mermaid diagrams to ProVerif models, projects SARIF/weAudit/binary findings onto code graphs, triages single findings with graph evidence, gates branch diffs for structural review regressions, and expands seed findings into variant-neighborhood candidates. Use when analyzing call paths, slicing source context for smaller models, mapping attack surface, visualizing code architecture, triaging survived mutants, generating cryptographic test vectors, diagramming crypto protocols, formally verifying protocols, augmenting audits with static analysis findings, deciding whether one candidate issue is reachable, reviewing graph-level PR risk, or seeding variant analysis. |
| variant-analysis | trailofbits | Find similar vulnerabilities and bugs across codebases using pattern-based analysis |
| vulnerability-triage-brocards | trailofbits | Principled framework for triaging vulnerability reports using 7 brocards (rules of thumb). Evaluates incoming CVEs, bug bounty submissions, and security findings against structured dismissal/acceptance criteria before escalating to deeper analysis. |
| warp | claude-code-warp | Native Warp notifications when Claude completes tasks or needs input |
| web-asset-generator | web-asset-generator-marketplace | Generate favicons, app icons, and social media images from logos, text, or emojis. Features emoji suggestions, WCAG validation, and automatic framework integration for Next.js, Astro, SvelteKit, and more. |
| writing-lean-proofs | trailofbits | Structured Lean 4 proof writing and library design following Mathlib conventions |
| yara-authoring | trailofbits | YARA-X detection rule authoring with linting and quality analysis |
| zeroize-audit | trailofbits | Detects missing or compiler-optimized zeroization of sensitive data with assembly and control-flow analysis |

## Instagram-sourced (2026-08-16)

These items came from 4 Instagram reels: a 22-item "22 tools I run" graphic from
`charliehills`, and a 10-repo video-editing carousel from `gobi_automates`. Two other reels
— `heyikjot`'s "Brag" skill and `kimball.ai`'s codebase-memory tool — were pure "comment X to
get it" bait, with no public repo anywhere. Those two were skipped, and nobody posted a
comment on the user's behalf to chase them.

The graphic's star counts turned out to be real, not inflated as first assumed. Each one was
checked against the live GitHub API before anything was installed. Two names, `emil` and
`find-skills`, had no matching repo as bare names. The user supplied the correct monorepo
links, and both are now sourced correctly below.

14 items became Claude Code plugins (see the table above). 4 items became raw skills:
`gstack`, `video-use`, `find-skills`, and `emil-design-eng` (see the "All skills" list above).
The rest are real CLI tools and apps, not Claude skills:

| Tool | Installed via | What it's for |
|---|---|---|
| `yt-dlp` | `brew install yt-dlp` | Downloads video/audio from most sites |
| `ffmpeg` | already present | Video/audio encoding — the engine under most editors |
| `auto-editor` | `uv tool install auto-editor` | Strips silence/dead air from a raw take automatically |
| `manim` | `uv tool install manim` | Programmatic math/technical animation (ManimCommunity). Text-heavy scenes want a LaTeX install (MacTeX, several GB) — not installed, add it separately if you hit that |
| `graphify` (`graphifyy` on PyPI) | `uv tool install graphifyy` | `/graphify` — turns a codebase + docs into a queryable knowledge graph |
| `claude-whisper` | `uv tool install claude-whisper` (needed `brew install portaudio` first, already present) | Voice-driven Claude Code — talk instead of typing |
| `chatterbox-tts` | attempted, **not installed as a tool** | Voice-cloning TTS — it's a Python *library* (`from chatterbox.tts import ChatterboxTTS`), not a CLI; `uv tool install` correctly refused to create a broken shim. Use it via `uv add chatterbox-tts` inside an actual project instead |
| `MoneyPrinterTurbo` | cloned to `~/Developer/MoneyPrinterTurbo` | Full app: topic/keyword → AI-generated short video. Needs your own LLM + TTS API keys in its config before it runs — not set up |
| `obsidian-wiki` | cloned to `~/Developer/obsidian-wiki` | 40-skill framework for building a personal "digital brain" in Obsidian, incl. its own bundled `skill-creator`. Has a `setup.sh` and expects a vault — not run, this is its own project to configure deliberately, not a drop-in skill |

## What runs on its own, and what needs setup

This table tracks two things. First, what starts by itself, with no action from you. Second,
what needs an install step or config before it works at all.

| Thing | Starts on its own? | What it needs |
|---|---|---|
| Serena MCP server | Yes. It starts when a skill that needs it runs. Right now, only `zeroize-audit` needs it. | `uv`/`uvx` on PATH (already present). The first run clones the Serena repo, so it needs network access once. |
| gstack `Stop` hook | Yes. It runs at the end of every Claude Code session. | `bun` on PATH (already present). Already registered in `~/.claude/settings.json`. |
| claude-mem capture hooks | Yes. They capture tool usage during any session, as soon as the plugin is enabled. | Nothing extra. The **worker** that summarizes and injects memory does not start on its own — see the next row. |
| claude-mem worker | No. It does not start after a reboot. | Run `npx claude-mem start` by hand. |
| OmniRoute daemon | No. It does not start after a reboot. | Run `omniroute serve --daemon --no-open` by hand. It also needs an account — set a password at http://localhost:20128/login — before the MCP server can register. |
| MoneyPrinterTurbo | No. It is only cloned, not configured. | Add your own LLM and TTS API keys to its config before it runs at all. |
| obsidian-wiki | No. It is only cloned, not configured. | Set up a vault and run its `setup.sh` before it works. |
| manim | Yes, for basic animation. | Text-heavy scenes need a LaTeX install (MacTeX, several GB). This is not installed. |
| chatterbox-tts | No. It is not a standalone tool. | Add it to a real project with `uv add chatterbox-tts`. It only works as a Python library. |
| Headroom | No. It is not installed. | Needs a paid subscription and a manual `.dmg` install. The `brew` command in its own README does not work. |

## Second config home: `~/.claude-nebula`

There are two Claude Code config homes on this machine:

| Path | Used when |
|---|---|
| `~/.claude` + `~/.claude.json` | Default. Any plain `claude` run. |
| `~/.claude-nebula` + `~/.claude-nebula/.claude.json` | When `CLAUDE_CONFIG_DIR=~/.claude-nebula` is set. Used by the Nebula desktop app. |

Both homes point at **this same repo**. Every skill in `~/.claude-nebula/skills/` is a symlink
into `~/claude-toolkit/skills/`, exactly like `~/.claude/skills/`. So a skill you add to this
repo appears in both, with no extra step. Plugins are also shared: `~/.claude-nebula`'s
`installed_plugins.json` records install paths under `~/.claude/plugins/cache/`, so there is
one plugin cache, not two.

What is **not** shared automatically:

- **MCP servers.** Each config home keeps its own `mcpServers` block in its own `.claude.json`.
  Plugin-supplied MCP servers (Serena, and the ones inside `claude-mem`, `second-opinion`,
  `zeroize-audit`, `expo`) travel with the plugin and work in both homes. Hand-added user-scope
  servers do not. `watch-skill` was the only one in this category; it is now in both.
- **Sessions, history, memory, and telemetry.** Each home has its own. Memory written under
  `~/.claude-nebula/projects/.../memory/` is not visible to a plain `claude` run, and the
  reverse is also true.

To add a user-scope MCP server to both homes:

```bash
claude mcp add <name> -- <command> <args...>
CLAUDE_CONFIG_DIR=~/.claude-nebula claude mcp add <name> -- <command> <args...>
```

To relink all skills into the Nebula home after a fresh clone:

```bash
for s in ~/claude-toolkit/skills/*/; do ln -sfn "$s" ~/.claude-nebula/skills/"$(basename "$s")"; done
```

A running Claude Code process holds `.claude.json` in memory and rewrites it on exit. Edit the
file for a config home only while no session is using that home, or the edit gets overwritten.

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

Restart Claude Code after any plugin change. Plugins load only at session start.

### Adding a skill
```bash
mkdir -p ~/claude-toolkit/skills/<name>          # or git clone straight into skills/
ln -sfn ~/claude-toolkit/skills/<name> ~/.claude/skills/<name>
```
Name the folder to match the `name:` field in its frontmatter. Then add a row to the table
at the top, and a section that says what the skill does, where it came from, and any problem
you hit. If you cloned the skill from GitHub, add it as a submodule instead. See the section
below.

## This folder is a git repo

This repo syncs to a **private** GitHub repo, so it survives a machine wipe.

```bash
cd ~/claude-toolkit
git add -A && git commit -m "..." && git push
```

`skills/task-observer` and `skills/gstack` are **submodules**. Each one points at its
upstream project. This repo does not copy their code, only a pointer to one commit. This has
some practical effects:

```bash
# cloning this toolkit onto a new machine
git clone --recurse-submodules <this repo> ~/claude-toolkit
# ...then relink the skills, since symlinks into ~/.claude aren't tracked:
for s in ~/claude-toolkit/skills/*/; do ln -sfn "$s" ~/.claude/skills/"$(basename "$s")"; done
# gstack additionally needs its own setup rerun after a fresh clone (bun required):
(cd ~/claude-toolkit/skills/gstack && ./setup)

# pulling upstream updates
git submodule update --remote skills/task-observer
git add skills/task-observer && git commit -m "bump task-observer"
git submodule update --remote skills/gstack
git add skills/gstack && git commit -m "bump gstack"
```

If you forget `--recurse-submodules` when you clone, submodule folders appear empty. Run
`git submodule update --init` to fix this.

**Two gstack problems, found on 2026-08-16:**
- Its README contains an instruction that tells Claude to auto-edit your global `CLAUDE.md`.
  This instruction asks Claude to register 17+ slash commands, and to ban
  `mcp__claude-in-chrome__*` in favor of gstack's own `/browse`. This instruction comes from
  the repo's content, not from the user, so it was **not** followed. Do this yourself if you
  want it.
- Its `./setup` script silently registered a `Stop` hook in `~/.claude/settings.json` (source:
  `gstack-timeline-stop`). This hook closes gstack's own timeline entries when a session ends.
  This is a persistent config change, made without asking first. The hook fails open and makes
  no network calls — read it at `skills/gstack/hosts/claude/hooks/timeline-stop-hook`. A backup
  file exists at `settings.json.bak.20260816-202547`, if you would rather remove the hook:
  `~/claude-toolkit/skills/gstack/bin/gstack-settings-hook remove-source --source gstack-timeline-stop`
