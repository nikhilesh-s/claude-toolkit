# Nik's Claude Toolkit

**Branch: `nik-claude-toolkit`. Private. Do not make this repo or this branch public.**

This README describes **this machine** — Nik's MacBook Air (M4, 13-inch), macOS 26.6.1,
`arm64`, user `niks`, GitHub `nikhilesh-s`. It is not upstream's README. Upstream's README
describes Arnav's machine, and most of what it claims is installed is *not* installed here.
See [What upstream's README claims that is not true here](#what-upstreams-readme-claims-that-is-not-true-here).

Everything below was verified by reading the live files on this machine on **2026-08-16**,
not copied from a snapshot. The tables under [Machine inventory](#machine-inventory) are
regenerated from disk by a script — they cannot drift into being wrong without someone
editing them by hand.

---

## The one-minute version

| Question | Answer |
|---|---|
| Where does this repo live? | `~/claude-toolkit` |
| Where does it back up to? | `nikhilesh-s/claude-toolkit` — **private**, default branch is yours |
| What branch am I on? | `nik-claude-toolkit` — never commit to `main` |
| Where do the skills go? | `~/.claude/skills/` **and** `~/.claude-nebula/skills/`, as symlinks back into this repo |
| How many skills does this repo give me? | 230, all wired up, 0 broken |
| How many more come from plugins? | 47 (28 Vercel + 19 claude-mem) |
| How do I get Arnav's new skills? | Automatically, 11:00 + 23:00. See [Daily automatic sync](#daily-automatic-sync) |
| Do his new **plugins** arrive too? | **No.** Git cannot carry a plugin. See [Plugins do not arrive through git](#plugins-do-not-arrive-through-git) |
| Will that overwrite this README? | No. See [Staying in sync](#staying-in-sync-with-arnav) |
| Does any of this work in both Claude apps? | Yes for skills — they are linked into both. Plugins must be installed twice. See [Two apps, two accounts](#two-apps-two-accounts-what-carries-over) |
| What is actually running right now? | Very little. See [What is running](#what-is-running-and-what-is-not) |

```bash
cd ~/claude-toolkit
./scripts/nik_sync_upstream.sh --preview   # see what Arnav added, change nothing
./scripts/nik_sync_upstream.sh             # merge it in, relink, regenerate this README
```

---

## Why there are two Claude config directories

This is the single most important thing to know about this machine, and the thing most likely
to waste an hour later.

`claude-multiprofile` (installed globally through npm) runs **two separate Claude profiles**:

| Profile | Desktop data | Claude Code config | Notes |
|---|---|---|---|
| `default` | `~/Library/Application Support/Claude` | `~/.claude` | The plain `claude` CLI in a terminal |
| `nebula` | `~/Library/Application Support/Claude-Nebula` | `~/.claude-nebula` | Launched from `~/Applications/Claude Nebula.app` |

Both profiles share **one** `claude` binary (`/opt/homebrew/bin/claude`, v2.1.229) and share
`~/.claude/plugins/`. But each profile keeps its **own** `skills/` folder and its **own**
`claude_desktop_config.json`.

The consequence: **a skill linked into only one of them is invisible in the other.** The
Claude Desktop app exports `CLAUDE_CONFIG_DIR=/Users/niks/.claude-nebula`, so a session
started from the app cannot see anything that lives only in `~/.claude/skills/`.

`scripts/nik_install_skills.sh` links into **both**, every time. That is why it exists. Do not
hand-link a skill into one directory and assume it is installed.

---

## Two apps, two accounts: what carries over

There are two separate things here that are easy to conflate.

**Your Claude account** (personal vs Nebula Max) is a login. It decides which models you can
reach, your rate limits, and your billing. It has nothing to do with which skills or plugins
are on disk.

**Your profile** (`default` vs `nebula`) is a folder. It decides which skills and plugins the
agent can see. This is the one that matters here.

So the rule is:

> Skills and plugins follow the **profile folder**, not the account. Signing into a different
> account in the same app changes nothing about what is installed. Opening the *other app*
> changes everything, because it reads a different folder.

What that means in practice on this machine:

| Thing | Personal app (`~/.claude`) | Nebula app (`~/.claude-nebula`) | Kept in sync by |
|---|---|---|---|
| The 230 repo skills | yes | yes | `nik_install_skills.sh`, automatically |
| `humanizer`, `parametric-3d-printing` | yes | yes | installed in both already |
| Plugins (`brag`, `vercel`, `claude-mem`) | yes | yes | **you, by hand — twice** |
| Plugin marketplaces | yes | yes | **you, by hand — twice** |
| MCP servers from plugins | yes | yes | follows the plugin |
| `blender` MCP server | yes | **no** | Desktop config, per profile |

Arnav is right that it works for both — but only because that is what the install script was
built to do. It is not automatic in Claude Code itself. Left alone, a skill linked into one
profile is invisible in the other.

**Plugins are the gap.** `claude plugin install` writes to whichever profile is active. There
is no "install for both" flag. Install a plugin the normal way and it lands in exactly one
profile, and you will be confused later when the other app cannot find it. Do this instead:

```bash
CB=/opt/homebrew/bin/claude    # not the `claude` shell alias — it expands to `claude code`
                               # and silently swallows the `plugin` subcommand

for D in "$HOME/.claude" "$HOME/.claude-nebula"; do
  CLAUDE_CONFIG_DIR="$D" $CB plugin marketplace add <owner>/<repo>
  CLAUDE_CONFIG_DIR="$D" $CB plugin install <name>@<marketplace>
done
```

That loop is how `brag@brag` got into both. Use it for every plugin from now on.

---

## Three different things called "skills"

The word covers three kinds of thing on this machine, and they update in three different ways.
Mixing them up is how a skill ends up edited in a place that gets wiped on the next update.

### 1. Repo skills — 230 of them

The real files live in `~/claude-toolkit/skills/<name>/`. `~/.claude/skills/<name>` and
`~/.claude-nebula/skills/<name>` are **symlinks** pointing back here.

- Edit a file in this repo and the live skill changes immediately. No reinstall.
- These are the only skills this repo owns, and the only ones `git pull` can change.
- 54 of them are not really files here at all — they are symlinks into the `gstack`
  submodule. See [gstack](#gstack-54-skills-half-wired).

### 2. Plugin skills — 47 of them

Bundled inside an installed plugin under `~/.claude/plugins/cache/`. They arrive and leave
with the plugin.

- **Do not edit these.** `claude plugin update` overwrites the whole folder.
- They are not in this repo and never will be. This README only lists them.
- A plugin can also ship slash commands, subagents, and MCP servers — Vercel ships all three.

### 3. Skills installed by other tools — 2 of them

`humanizer` was installed by an agent-skills installer into `~/.agents/skills/` and is
symlinked in. `parametric-3d-printing` is a plain git clone sitting directly in the skills
folder. Neither is in this repo, and `git pull` will never touch either one.

---

## Skills vs MCP servers

These are not the same thing, and the difference decides what needs an account.

**A skill is a folder with a `SKILL.md` in it.** It is instructions — text telling Claude how
to do something, sometimes with helper scripts next to it. A skill installs by existing on
disk. It needs no account, no key, and no network. Loading it costs nothing but context.

**An MCP server is a running process or a remote endpoint** that hands Claude extra tools.
It has to be registered, it usually has to start, and it is the part that tends to need an
account, an OAuth grant, or an API key.

The two get confused because **a skill can depend on an MCP server**. When it does, the skill
still loads fine — Claude reads it, follows it, and then fails at the step that calls a tool
that is not there. On this machine that is not hypothetical:

> **42 of the 230 skills call an MCP server that is not registered here.** Almost all are
> gstack skills calling `conductor` or `gbrain`. They load, then fail partway. Full list in
> [Skills that call an MCP server](#skills-that-call-an-mcp-server).

### What actually needs an account or a key

| Thing | Needs | Status right now |
|---|---|---|
| Any of the 230 repo skills, just to load | nothing | all 230 load |
| `mcp-search` (claude-mem MCP server) | nothing — local stdio process | works |
| `vercel` (Vercel MCP server) | **OAuth to Vercel** | **not authorized.** A non-interactive session cannot run the flow — authorize from an interactive `claude` session |
| claude-mem memory sync | Claude Desktop OAuth token | **expired** — re-login via Claude Desktop |
| `blender` MCP server | nothing, but needs Blender running | `default` profile only; absent in `nebula` |
| `brag@brag` — the launch-video plugin | Node 22+, FFmpeg, `npx hyperframes` | **installed in both profiles.** FFmpeg 9.0.1 installed 2026-08-16. `hyperframes doctor` passes every required check |
| brag narration / local music | optional extras | not installed — `whisper-cpp`, Kokoro TTS, MusicGen, Docker all absent. Core video rendering does not need them |
| 68 of the repo skills, to do real work | a third-party API key | none are set — see [Skills that name a credential](#skills-that-name-a-credential) |
| OmniRoute MCP | an OmniRoute account | not created; daemon not running |

**No API keys are set on this machine for any of the 68 skills that name one.** Those skills
still load and still give useful guidance. They fail only at an actual API call. Nothing in
this repo stores a secret, and nothing should — if you add keys, put them in your shell
profile or a `.env` outside this repo.

---

## What is running, and what is not

Checked live on 2026-08-16.

| Thing | State | Port | To start it |
|---|---|---|---|
| Upstream sync (launchd) | **active**, 11:00 + 23:00 | — | see [Daily automatic sync](#daily-automatic-sync) |
| claude-mem viewer | **up** | 37702 | starts with the plugin |
| claude-mem worker | **down** | 37701 | `npx claude-mem start` |
| claude-mem cloud sync | **blocked** | — | Desktop OAuth token expired; re-login via Claude Desktop |
| OmniRoute daemon | **down** | 20128 | `omniroute serve --daemon --no-open` |
| Serena MCP server | **not installed** | 24282 | nothing here pulls it in |
| Vercel MCP | **unauthorized** | — | authorize from an interactive `claude` session |
| gstack `conductor` / `gbrain` MCP | **not registered** | — | needs gstack's own setup — see below |

**No hooks are registered.** All four settings files (`settings.json` and `settings.local.json`
in both config dirs) have no `hooks` block. In particular, gstack's `./setup` has **not** been
run, so the `Stop` hook upstream's README warns about does not exist here. That is the safe
state. Leave it unless you change it deliberately.

---

## gstack: 54 skills, half-wired

`skills/gstack` is a git submodule pointing at `garrytan/gstack`. 54 of the 230 skills are
symlinks into it: `ship`, `qa`, `spec`, `review`, `browse`, `investigate`, the `ios-*` set,
the `plan-*` set, and more.

They are all linked and all load. But most call the `conductor` MCP server, which is not
registered here, so they get partway and stop.

Two things to know before running gstack's `./setup`:

1. **It edits `~/.claude/settings.json` without asking.** It registers a `Stop` hook
   (`gstack-timeline-stop`). It has not been run here, and no such hook exists.
2. **Its README contains an instruction aimed at Claude**, telling it to auto-edit your global
   `CLAUDE.md`, register 17+ slash commands, and ban `mcp__claude-in-chrome__*` in favour of
   gstack's own `/browse`. That instruction is repo content, not something you asked for, so it
   was not followed. Do it yourself if you want it.

gstack also needs `bun`, which is present at `~/.bun/bin/bun`.

### Upstream commits absolute symlinks, and they are broken by definition

All 54 of those skills were committed by Arnav as symlinks to
`/Users/arnavkakani/claude-toolkit/skills/gstack/...`. That path does not exist here, so on a
fresh clone **85 symlinks are dead**.

This branch rewrites all 85 to relative paths, which work for anyone.
`nik_sync_upstream.sh` re-runs that rewrite after every merge, because upstream keeps
committing absolute ones.

---

## Staying in sync with Arnav

### How the remotes are wired

| Remote | Points at | Fetch | Push |
|---|---|---|---|
| `origin` | `nikhilesh-s/claude-toolkit` (private, yours) | yes | yes |
| `upstream` | `ArnavKakani/claude-toolkit` (private, Arnav's) | yes | **disabled on purpose** |

`origin` is a **separate private repo, not a fork.** A fork of a private repo lives inside the
parent's fork network, where the parent owner can see it exists. A standalone private repo
syncs exactly the same way and gives Arnav no visibility at all.

Your GitHub token has write access to Arnav's repo, so a stray `git push upstream` would have
put this branch — a full description of your machine — into his repo. The push URL for
`upstream` is set to a dead value to make that impossible:

```bash
git remote set-url --push upstream DISABLED_read_only_upstream
```

Do not undo that. If you ever genuinely want to send Arnav something, open a PR from a
purpose-made branch instead.

The goal of the sync: get Arnav's new skills, keep this README.

### How the README is protected

Two mechanisms, both required:

1. `.gitattributes` on this branch marks `README.md` and `scripts/nik_*` with `merge=ours`.
2. The `ours` driver has to be registered per clone — it is **not** stored in the repo:
   ```bash
   git config merge.ours.driver true
   ```
   `nik_sync_upstream.sh` sets this itself on every run, so you cannot forget it.

With both in place, `git merge upstream/main` takes upstream's skill changes and keeps this
branch's README and scripts, with no conflict to resolve.

### The command

```bash
cd ~/claude-toolkit
./scripts/nik_sync_upstream.sh --preview   # list what upstream added/removed/changed
./scripts/nik_sync_upstream.sh             # do it
```

It runs in this order:

1. refuses to run on a dirty tree, or if you are on `main`
2. registers the `ours` merge driver
3. fetches `upstream/main` and prints exactly which skill folders were added, removed, changed
4. merges — README and `nik_*` scripts survive untouched
5. updates the `gstack` and `task-observer` submodules
6. rewrites upstream's absolute `/Users/arnavkakani/...` symlinks to relative ones
7. relinks every skill into **both** config dirs, and prunes links to skills upstream deleted
8. regenerates the inventory tables in this README from the new state

Then commit, and **restart Claude Code** — skills load only at session start.

### Daily automatic sync

A launchd job runs `scripts/nik_daily_sync.sh` **twice a day, at 11:00 and 23:00**.

Every run emails a report to `niksuravarjjala@gmail.com` — see
[Email reports](#email-reports).

`~/Library/LaunchAgents/com.nik.claude-toolkit-sync.plist` — the copy in
`scripts/` is the tracked original.

**launchd, not cron.** cron on macOS silently skips a job whose time passed while the machine
was asleep. A laptop shut at 23:00 would just never sync. launchd runs a missed
`StartCalendarInterval` job as soon as the machine wakes.

It is deliberately timid, because unattended git that fights you is worse than none:

| Situation | What it does |
|---|---|
| Another copy still running | exits |
| Uncommitted work in the tree | exits, touches nothing |
| Not on `nik-claude-toolkit` | exits |
| Merge conflicts | **aborts the merge, restores the previous commit**, notifies you |
| Push fails | keeps the local commit, notifies you |
| Success | commits, pushes to `origin`, notifies you if skills changed |

On success it also re-fixes upstream's absolute symlinks, relinks skills into both profiles,
prunes links for skills upstream deleted, and regenerates the inventory below.

```bash
# check on it
cat ~/Library/Logs/claude-toolkit/last-run.txt     # one-line verdict from the last run
tail -40 ~/Library/Logs/claude-toolkit/sync.log    # full history, auto-rotated at 1 MB

# run it now instead of waiting for the next run
launchctl kickstart -p gui/$(id -u)/com.nik.claude-toolkit-sync
./scripts/nik_daily_sync.sh --dry-run              # report only, change nothing

# turn it off / back on
launchctl bootout gui/$(id -u)/com.nik.claude-toolkit-sync
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.nik.claude-toolkit-sync.plist
```

To change the time, edit `Hour`/`Minute` in the plist, copy it to `~/Library/LaunchAgents/`,
then bootout and bootstrap again. launchd does not reread a plist in place.

### Plugins do not arrive through git

**This is the one real limit of the daily sync, and it is worth understanding properly.**

Arnav's repo contains skills as *files*. Plugins are not files — they install from a separate
marketplace into `~/.claude/plugins/`. When Arnav installs one, the only thing that reaches
his repo is **a line of text saying he installed it**: a row in his README table and a row in
`scripts/skill_index.tsv`.

So a daily pull hands you a perfect copy of a note about a plugin, and none of the plugin.

The gap is not small. Arnav's index lists **73 plugins**. Without intervention you would have
had 2, and the sync would report "up to date" every morning while you were missing the rest.
`humanizer@humanizer` — the humanizing tool — is one of the missing ones.

### Email reports

Every non-dry run emails a report: sync result, repo commit, both profiles' skill
and plugin counts, whether the profiles are identical, broken-link count, and the
log tail for that run. Subject line carries the state, with `[ATTENTION]` appended
when it is anything other than `SYNCED` or `UP TO DATE`.

**The password is not in this repo and never will be.** It lives in the macOS
Keychain and is read at send time. Set it up once:

```bash
security add-generic-password -a nebula.markdown@gmail.com -s claude-toolkit-smtp -w
```

That prompts for the password without echoing it. For Gmail this must be an **app
password** from <https://myaccount.google.com/apppasswords>, not the account
password — Gmail rejects the account password over SMTP.

Send a test:

```bash
python3 scripts/nik_mail_report.py --test
```

If no credential is stored the mailer prints a hint and exits 0. A missing email
can never turn a good sync into a failed one.

To change the recipient, edit `TO` at the top of `scripts/nik_mail_report.py`.

### Plugin parity is now automatic — and what that means

As of 2026-08-16 the daily job **installs** Arnav's plugins, it does not just report them.
`AUTO_INSTALL_PLUGINS=1` in `scripts/nik_daily_sync.sh` controls this.

The bulk catch-up ran on 2026-08-16: **3 plugins → 69**, in both profiles.

Two did not make it, both explainable:

| Plugin | Why |
|---|---|
| `ai-toolkit@spartan-marketplace` | that marketplace is not public any more — only Arnav knows where it moved |
| `claude-hud@claude-hud` | one flaky install out of ~140; landed in `.claude`, missed `.claude-nebula`. Re-run the installer, it is idempotent |

**Be clear about the trade you made.** Every morning, whatever Arnav installs gets downloaded
from its marketplace, installed into both your profiles, and enabled — with nobody reading it
first. You are trusting one person's curation across ~29 third-party marketplaces, on a timer.
That is a standing decision, not a one-time one, and the blast radius is your agent sessions.

To go back to review-first, set `AUTO_INSTALL_PLUGINS=0` in `scripts/nik_daily_sync.sh`. The
job then notifies you and logs the command instead of running it. Nothing else changes.

```bash
# what is missing right now, install nothing
./scripts/nik_daily_sync.sh --report-plugins
./scripts/nik_install_plugins.sh --dry-run

# install everything missing, into both profiles (idempotent)
./scripts/nik_install_plugins.sh
```

Never use a bare `claude plugin install` — it reaches one profile only. See
[Two apps, two accounts](#two-apps-two-accounts-what-carries-over).

### Blocking a plugin you do not want

`scripts/plugin_blocklist.txt` lists plugins the daily job must never install,
one `name@marketplace` per line. Without it the 21:00 job reinstalls anything you
remove, that same night.

Currently blocked:

| Plugin | Why |
|---|---|
| `zeroize-audit@trailofbits` | pulls in the Serena MCP server (`oraios/serena`), which auto-starts a background process per project, opens a dashboard on `127.0.0.1:24282`, and adds a macOS menu-bar tray icon. Removed 2026-08-17 |

To remove a plugin properly:

```bash
echo 'name@marketplace' >> scripts/plugin_blocklist.txt   # stop it coming back
for D in "$HOME/.claude" "$HOME/.claude-nebula"; do
  CLAUDE_CONFIG_DIR="$D" /opt/homebrew/bin/claude plugin uninstall name@marketplace
done
```

Blocklist first, then uninstall — otherwise the next sync undoes you.

**Watch for project-scope leftovers.** `plugin uninstall` can report success while
leaving a `scope: project` entry in `plugins/installed_plugins.json`. Check with:

```bash
/usr/bin/python3 -c "import json;print(list(json.load(open('$HOME/.claude-nebula/plugins/installed_plugins.json'))['plugins']))"
```

### A plugin shimmed `python3`, and it broke these scripts

`modern-python@trailofbits` installs a shim that rewrites `python3` to
`uv run python`. Outside a uv project that fails and returns nothing — so
`nik_install_plugins.sh` read *every* plugin as missing and would have reinstalled
all 69 nightly.

Every `nik_*` script now resolves a real interpreter up front:

```bash
PY="$(command -v /opt/homebrew/bin/python3 || command -v /usr/bin/python3 || command -v python3)"
```

The general lesson: plugins can change how your shell behaves. If a script starts
misreading state for no obvious reason, check whether something shimmed the tool
it depends on.

### How marketplace names get resolved

Upstream records a plugin as `<name>@<marketplace>`, but installing needs `owner/repo`, and
the two often differ — `brag` → `latent-spaces/brag`, `humanizer` → `blader/humanizer`,
`trailofbits` → `trailofbits/skills`.

`scripts/nik_resolve_marketplaces.sh` searches GitHub for a candidate and then **verifies that
its `.claude-plugin/marketplace.json` actually declares that marketplace name** before
accepting it. Guessing from the name alone is how you would end up installing a stranger's
same-named repo. Verified results are cached in `scripts/marketplace_sources.tsv` (28 of 29
resolved) and pinned entries are never re-guessed.

### Rules for this branch

- **Never commit to `main`.** `main` tracks Arnav's. Keep it clean so merges stay trivial.
- **Never push this branch anywhere public.** It is a description of your machine —
  what is installed, what is running, and which services are unauthenticated.
- **Never make `nikhilesh-s/claude-toolkit` public**, and do not re-enable the `upstream`
  push URL.
- After a sync, `git push origin nik-claude-toolkit` to back it up.
- To add a skill of your own, put it in `skills/` and run `nik_install_skills.sh`. It lives on
  this branch only; upstream never sees it.
- If upstream edits a file you also changed, the merge stops and tells you. Only `README.md`
  and `scripts/nik_*` are auto-protected.

---

## What upstream's README claims that is not true here

Upstream's README was written about Arnav's machine. Read as a description of this one, it is
wrong in these specific ways. That is not a criticism of it — it was never about this machine.

| Upstream says | Actually here |
|---|---|
| Repo lives at `~/claude-toolkit`, set up 2026-08-08 | Right path, but this clone is from 2026-08-16 |
| `ste-writing` and `task-observer` are the notable skills | Both present, plus 228 more |
| `humanizer` is installed as the `humanizer@humanizer` plugin | It is **not** a plugin here. It is a symlink to `~/.agents/skills/humanizer` |
| `claude-code-setup` plugin is active | **Not installed** |
| ~72 bulk-installed plugins | **2 plugins installed**: Vercel and claude-mem |
| Serena MCP server is active and auto-starts | **Not installed.** Nothing here pulls it in |
| OmniRoute runs as a daemon | **Installed but not running.** No account, no MCP registration |
| `yt-dlp`, `ffmpeg`, `auto-editor`, `manim`, `graphify`, `claude-whisper` installed | **None are installed** |
| `MoneyPrinterTurbo` and `obsidian-wiki` cloned to `~/Developer` | **`~/Developer` does not exist** |
| gstack `Stop` hook registered in `~/.claude/settings.json` | **No hooks are registered anywhere** |
| `./status.sh` checks everything | It exists, but only knows `~/.claude` — it is blind to `~/.claude-nebula` |
| One Claude config directory | **Two** — see [above](#why-there-are-two-claude-config-directories) |

`status.sh` is upstream's file, left as-is so it does not conflict on merge. For an accurate
picture of this machine, use `python3 scripts/nik_inventory.py`.

---

## The cost of having 277 skills loaded

Claude Code loads the name and description of every installed skill into context at the start
of every session. That is fixed, and no skill can opt out.

With 230 repo skills plus 47 plugin skills, that is roughly **20–30k tokens of skill
descriptions before you type anything**, in every session, in both profiles.

That is a real trade, worth knowing you made. Most of these skills are computational biology,
chemistry, and lab automation — genuinely useful if that is the work, pure overhead if the
day's work is a Next.js site.

Two ways to cut it:

```bash
# find the right skill without reasoning over the whole catalogue
./scripts/which-skill.sh rnaseq differential expression

# park a group of skills without deleting them: unlink, keep the files
for s in adaptyv benchling-integration ginkgo-cloud-lab latchbio-integration; do
  rm -f ~/.claude/skills/$s ~/.claude-nebula/skills/$s
done
```

Unlinking is safe and reversible — the files stay in the repo. But note the reverse:
`./scripts/nik_install_skills.sh` relinks **all** skills, so it undoes any parking you did. For
a permanent subset, keep the list in a file on this branch and re-apply it after each sync.

---

## Maintenance

```bash
cd ~/claude-toolkit

# pull Arnav's new skills (README safe)
./scripts/nik_sync_upstream.sh

# relink skills into both config dirs after any manual change
./scripts/nik_install_skills.sh
./scripts/nik_install_skills.sh --dry-run    # say what would change, change nothing

# refresh the inventory tables in this README
python3 scripts/nik_inventory.py
python3 scripts/nik_inventory.py --check     # exit 1 if stale, for a pre-commit check

# update the two plugins
claude plugin update claude-mem@thedotmack
claude plugin update vercel@claude-plugins-official

# start the things that do not autostart
npx claude-mem start                          # worker on 37701
omniroute serve --daemon --no-open            # gateway on 20128
```

Restart Claude Code after any skill or plugin change.

### Adding your own skill

```bash
mkdir -p ~/claude-toolkit/skills/<name>
$EDITOR ~/claude-toolkit/skills/<name>/SKILL.md   # needs name: and description: frontmatter
./scripts/nik_install_skills.sh
python3 scripts/nik_inventory.py
git add -A && git commit -m "add <name> skill"
```

The folder name should match the `name:` in the frontmatter. Claude Code loads a skill under
its frontmatter name, not its folder name — if they differ, the inventory flags it.

### Restoring what was replaced during install

Installing moved one real folder aside rather than deleting it:

- `~/.claude-nebula/backups/skills-replaced/task-observer` — the standalone copy from
  2026-08-08, replaced by this repo's submodule version
- `~/.claude/backups/skills.before-toolkit-install/` — the state of `~/.claude/skills/`
  before any of this

---

## Machine inventory

Generated from disk. Do not edit by hand — run `python3 scripts/nik_inventory.py`.

<!-- BEGIN GENERATED INVENTORY -->

<!-- Generated by scripts/nik_inventory.py — do not edit by hand. -->
<!-- Regenerate:  python3 scripts/nik_inventory.py  -->

### At a glance

| | Count |
|---|---|
| Skills shipped by this repo | 230 |
| …wired into every config dir (`.claude-nebula` + `.claude`) | 230 |
| …broken symlinks | 0 |
| …present in repo but not installed | 0 |
| …that come from the gstack submodule | 54 |
| Skills installed outside this repo | 28 |
| Plugins installed | 69 (69 enabled) |
| Skills naming a credential env var | 68 |
| Skills naming an MCP server | 42 |

### Skills installed outside this repo

These live in `~/.claude/skills/` but this repo does not own them. A `git pull`
from upstream will never touch them.

| Skill | How it is installed | Present in | Real location | What it does |
|---|---|---|---|---|
| `captions-overlay` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/captions-overlay` | Overlay doctrine for the embedded-captions workflow — the caption MODEL (drop /… |
| `changelog-video` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/changelog-video` | Turn a weekly changelog .md into a finished branded changelog video (square 108… |
| `cut-the-curve` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/cut-the-curve` | The technique catalog: five velocity-matched SEAMS (zoom-through, INVERSE zoom-… |
| `embedded-captions` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/embedded-captions` | Add captions or subtitles to an existing single-subject talking-head video with… |
| `faceless-explainer` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/faceless-explainer` | Turn arbitrary text — an article, notes, a topic, a brief — into a faceless exp… |
| `figma` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/figma` | Import Figma content into a HyperFrames composition — rendered assets, brand to… |
| `general-video` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/general-video` | Author or edit a custom HyperFrames composition when no specialized workflow fi… |
| `humanizer` | symlink | `.claude-nebula`, `.claude` | `~/.agents/skills/humanizer` | Remove signs of AI-generated writing from text. Use when editing or reviewing t… |
| `hyperframes` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/hyperframes` | Mandatory entry point: read this first for any request to make, create, edit, a… |
| `hyperframes-animation` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/hyperframes-animation` | All animation knowledge for HyperFrames — atomic motion rules, multi-phase scen… |
| `hyperframes-audio` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/hyperframes-audio` | Use when audio already placed in a HyperFrames composition needs to be mixed: a… |
| `hyperframes-cli` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/hyperframes-cli` | Use the HyperFrames CLI development loop: init, add, catalog, capture, lint, ch… |
| `hyperframes-core` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/hyperframes-core` | The HyperFrames composition contract — build one renderable project. Use for co… |
| `hyperframes-creative` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/hyperframes-creative` | Non-animation creative direction for HyperFrames videos. Use for design spec (f… |
| `hyperframes-keyframes` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/hyperframes-keyframes` | Use when a HyperFrames composition needs seek-safe 2D/3D keyframes, GSAP timeli… |
| `hyperframes-registry` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/hyperframes-registry` | Install, discover, and wire registry blocks and components into HyperFrames com… |
| `media-use` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/media-use` | Agent Media OS, the single skill for every media need in a HyperFrames project.… |
| `motion-doctrine` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/motion-doctrine` | GATEWAY — load FIRST before composing any HyperFrames animation or video. The h… |
| `motion-graphics` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/motion-graphics` | A short, design-led motion graphic where motion is the message — kinetic typogr… |
| `music-to-video` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/music-to-video` | Turn a music track (an audio file, a video to pull audio from, or a track gener… |
| `oversized-cursor` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/oversized-cursor` | House-style oversized macOS cursor technique for HyperFrames launch videos. Loa… |
| `parametric-3d-printing` | real folder | `.claude-nebula`, `.claude` | `~/.claude-nebula/skills/parametric-3d-printing` | Use this skill when the user wants to design a 3D-printable physical object the… |
| `pr-to-video` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/pr-to-video` | Turn a GitHub pull request (a PR URL, owner/repo#N, or 'this PR' in a checked-o… |
| `product-launch-video` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/product-launch-video` | Turn a product or marketing URL, pasted script, or brief into a product launch… |
| `remotion-to-hyperframes` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/remotion-to-hyperframes` | Port an existing Remotion (React) composition''s source to HyperFrames HTML. Us… |
| `seam-craft` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/seam-craft` | Render-correctness doctrine for scene-to-scene seams in HyperFrames launch vide… |
| `slideshow` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/slideshow` | Author a HyperFrames slideshow — a presentation, pitch deck, or interactive dec… |
| `talking-head-recut` | symlink | `.claude-nebula`, `.claude` | `~/.claude/skills/talking-head-recut` | Package an existing talking-head / interview / podcast video with timed, design… |

### Plugins

Plugins do **not** live in this repo. They install into `~/.claude/plugins/`.
A plugin can carry its own skills, its own slash commands, and its own MCP servers.

| Plugin | Version | Enabled | Marketplace repo | Auto-update | Skills | Commands | Agents | MCP servers it brings |
|---|---|---|---|---|---|---|---|---|
| `agent-browser@agent-browser` | 548b159b30ee | yes | `vercel-labs/agent-browser` | no | 1 | 0 | 0 | — |
| `agentic-actions-auditor@trailofbits` | 1.2.1 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `audit-context-building@trailofbits` | 2.0.0 | yes | `trailofbits/skills` | no | 1 | 0 | 1 | — |
| `brag@brag` | 0.2.2 | yes | `latent-spaces/brag` | no | 1 | 0 | 0 | — |
| `building-secure-contracts@trailofbits` | 1.1.2 | yes | `trailofbits/skills` | no | 11 | 0 | 0 | — |
| `burpsuite-project-parser@trailofbits` | 1.0.1 | yes | `trailofbits/skills` | no | 1 | 1 | 0 | — |
| `c-review@trailofbits` | 1.2.0 | yes | `trailofbits/skills` | no | 1 | 0 | 3 | — |
| `caveman@caveman` | 766dce6b1394 | yes | `JuliusBrussee/caveman` | no | 20 | 5 | 5 | — |
| `claude-api@anthropic-agent-skills` | f6656c1256d5 | yes | `anthropics/skills` | no | 17 | 0 | 0 | — |
| `claude-code-setup@claude-plugins-official` | 1.0.0 | yes | `anthropics/claude-plugins-official` | no | 1 | 0 | 0 | — |
| `claude-hud@claude-hud` | 0.7.1 | yes | `jarrodwatts/claude-hud` | no | 0 | 2 | 0 | — |
| `claude-in-chrome-troubleshooting@trailofbits` | 1.1.1 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `claude-mem@thedotmack` | 13.14.0 | yes | `thedotmack/claude-mem` | yes | 19 | 0 | 0 | `mcp-search` |
| `code-simplifier@claude-plugins-official` | 1.0.0 | yes | `anthropics/claude-plugins-official` | no | 0 | 0 | 1 | — |
| `codex@openai-codex` | 1.0.6 | yes | `openai/codex-plugin-cc` | no | 3 | 8 | 1 | — |
| `constant-time-analysis@trailofbits` | 0.2.0 | yes | `trailofbits/skills` | no | 1 | 1 | 0 | — |
| `culture-index@trailofbits` | 1.1.1 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `devcontainer-setup@trailofbits` | 0.2.1 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `differential-review@trailofbits` | 1.1.1 | yes | `trailofbits/skills` | no | 1 | 1 | 1 | — |
| `dimensional-analysis@trailofbits` | 3.0.1 | yes | `trailofbits/skills` | no | 1 | 0 | 5 | — |
| `document-skills@anthropic-agent-skills` | f6656c1256d5 | yes | `anthropics/skills` | no | 17 | 0 | 0 | — |
| `dwarf-expert@trailofbits` | 1.1.0 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `entry-point-analyzer@trailofbits` | 1.0.1 | yes | `trailofbits/skills` | no | 1 | 1 | 0 | — |
| `example-skills@anthropic-agent-skills` | f6656c1256d5 | yes | `anthropics/skills` | no | 17 | 0 | 0 | — |
| `firebase-apk-scanner@trailofbits` | 2.1.1 | yes | `trailofbits/skills` | no | 1 | 1 | 0 | — |
| `fp-check@trailofbits` | 1.0.3 | yes | `trailofbits/skills` | no | 1 | 0 | 3 | — |
| `frontend-slides@frontend-slides` | 2.1.0 | yes | `zarazhangrui/frontend-slides` | no | 1 | 0 | 0 | — |
| `gh-cli@trailofbits` | 1.5.1 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `git-cleanup@trailofbits` | 1.0.1 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `github-triage@trailofbits` | 0.1.0 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `gsap-skills@gsap-skills` | 1.0.0 | yes | `greensock/gsap-skills` | no | 8 | 0 | 0 | — |
| `humanizer@humanizer` | 2.9.1 | yes | `blader/humanizer` | no | 0 | 0 | 0 | — |
| `i-have-adhd@i-have-adhd` | 0.1.0 | yes | `ayghri/i-have-adhd` | no | 1 | 0 | 0 | — |
| `impeccable@impeccable` | 4.1.1 | yes | `pbakaus/impeccable` | no | 1 | 0 | 4 | — |
| `insecure-defaults@trailofbits` | 2.0.0 | yes | `trailofbits/skills` | no | 0 | 1 | 0 | — |
| `ios-simulator-skill@conorluddy` | e0ee87a884b4 | yes | `conorluddy/ios-simulator-skill` | no | 1 | 0 | 0 | — |
| `last30days@last30days-skill` | 3.21.0 | yes | `mvanhorn/last30days-skill` | no | 1 | 0 | 0 | — |
| `let-fate-decide@trailofbits` | 1.2.2 | yes | `trailofbits/skills` | no | 1 | 0 | 1 | — |
| `marketing-skills@marketingskills` | 2.10.0 | yes | `coreyhaines31/marketingskills` | no | 49 | 0 | 0 | — |
| `mattpocock-skills@mattpocock` | 1.2.3 | yes | `mattpocock/skills` | no | 0 | 0 | 0 | — |
| `modern-python@trailofbits` | 1.5.3 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `mutation-testing@trailofbits` | 1.0.1 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `open-sourcing@trailofbits` | 0.1.0 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `playwright-skill@playwright-skill` | 5.0.0 | yes | `lackeyjb/playwright-skill` | no | 1 | 0 | 0 | — |
| `ponytail@ponytail` | 4.9.0 | yes | `DietrichGebert/ponytail` | no | 6 | 0 | 0 | — |
| `property-based-testing@trailofbits` | 1.1.1 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `pyright-lsp@claude-plugins-official` | 1.0.0 | yes | `anthropics/claude-plugins-official` | no | 0 | 0 | 0 | — |
| `rust-review@trailofbits` | 1.0.0 | yes | `trailofbits/skills` | no | 1 | 0 | 3 | — |
| `second-opinion@trailofbits` | 1.7.0 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | `codex` |
| `semgrep-rule-creator@trailofbits` | 1.2.2 | yes | `trailofbits/skills` | no | 1 | 1 | 0 | — |
| `semgrep-rule-variant-creator@trailofbits` | 1.1.0 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `sharp-edges@trailofbits` | 1.1.1 | yes | `trailofbits/skills` | no | 1 | 0 | 1 | — |
| `skill-improver@trailofbits` | 1.1.0 | yes | `trailofbits/skills` | no | 1 | 1 | 0 | — |
| `social-media-skills@social-media-skills` | 1.0.0 | yes | `charlie947/social-media-skills` | no | 17 | 0 | 0 | — |
| `spec-to-code-compliance@trailofbits` | 2.0.0 | yes | `trailofbits/skills` | no | 1 | 0 | 1 | — |
| `static-analysis@trailofbits` | 1.3.1 | yes | `trailofbits/skills` | no | 3 | 0 | 0 | — |
| `superpowers@superpowers-dev` | 6.3.0 | yes | `obra/superpowers` | no | 14 | 0 | 0 | — |
| `supply-chain-risk-auditor@trailofbits` | 2.0.0 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `taste-skill@taste-skill` | 1.0.0 | yes | `Leonxlnx/taste-skill` | no | 13 | 0 | 0 | — |
| `terrashark@terrashark` | 2.3.0 | yes | `LukasNiessen/terrashark` | no | 0 | 0 | 0 | — |
| `testing-handbook-skills@trailofbits` | 1.0.2 | yes | `trailofbits/skills` | no | 15 | 0 | 0 | — |
| `trailmark@trailofbits` | 0.10.0 | yes | `trailofbits/skills` | no | 14 | 0 | 1 | — |
| `variant-analysis@trailofbits` | 2.0.1 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `vercel@claude-plugins-official` | 0.44.0 | yes | `anthropics/claude-plugins-official` | no | 28 | 5 | 3 | `vercel` |
| `vulnerability-triage-brocards@trailofbits` | 0.1.0 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `warp@claude-code-warp` | 2.2.0 | yes | `warpdotdev/claude-code-warp` | no | 0 | 0 | 0 | — |
| `web-asset-generator@web-asset-generator-marketplace` | 1.0.0 | yes | `alonw0/web-asset-generator` | no | 1 | 0 | 0 | — |
| `writing-lean-proofs@trailofbits` | 0.1.0 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |
| `yara-authoring@trailofbits` | 2.1.0 | yes | `trailofbits/skills` | no | 1 | 0 | 0 | — |

That is **315 more skills** on top of the 230 in this repo. Plugin skills are versioned with their plugin — `claude plugin update` changes them, this repo never does.

### MCP servers

#### From plugins

| Server | Comes from | Transport | Endpoint / command | Credential needed |
|---|---|---|---|---|
| `mcp-search` | `claude-mem@thedotmack` | stdio | `node` | none |
| `codex` | `second-opinion@trailofbits` | stdio | `codex` | none |
| `vercel` | `vercel@claude-plugins-official` | http | `https://mcp.vercel.com` | OAuth |

#### Registered through the Claude Code CLI

None. `~/.claude.json` has an empty `mcpServers` block, and no project in it
registers a project-scoped server.

#### From the Claude Desktop app

`claude-multiprofile` gives each Desktop profile its own data folder and its own MCP
config. These belong to the Desktop app, not to Claude Code, and this repo does not
manage them.

| Profile | Config file | Server | Command |
|---|---|---|---|
| `default` | `~/Library/Application Support/Claude/claude_desktop_config.json` | `blender` | `uvx blender-mcp` |
| `nebula` | `~/Library/Application Support/Claude-Nebula/claude_desktop_config.json` | *(none)* | — |

### Skills that name a credential

Each row lists the environment variables the skill's own files mention. Naming a
variable is not the same as needing it for every task — some skills only use one for
an optional higher rate limit. Treat this as the list to check before you trust a
skill to run unattended, not as a shopping list.

| Skill | Env vars it names | Source |
|---|---|---|
| `adaptyv` | `ADAPTYV_API_KEY`, `FOUNDRY_API_TOKEN` | K-Dense-AI/claude-scientific-skills |
| `autoplan` | `CODEX_API_KEY` | garrytan/gstack (submodule) |
| `autoskill` | `ANTHROPIC_API_KEY`, `AWS_SECRET_ACCESS_KEY`, `DEEPGRAM_API_KEY`, `FOUNDRY_API_KEY`, `GITHUB_TOKEN`, `GOOGLE_API_KEY`, `HF_TOKEN`, `OPENAI_API_KEY`, `SCREENPIPE_TOKEN`, `SLACK_TOKEN` | K-Dense-AI/claude-scientific-skills |
| `benchling-integration` | `BENCHLING_API_KEY`, `BENCHLING_CLIENT_SECRET`, `BENCHLING_PROD_API_KEY`, `BENCHLING_STAGING_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `benchmark-models` | `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` | garrytan/gstack (submodule) |
| `biopython` | `NCBI_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `browse` | `BROWSE_TERMINAL_INTERNAL_TOKEN`, `GITHUB_TOKEN`, `GSTACK_SKILL_TOKEN`, `GSTACK_TOKEN`, `NPM_TOKEN`, `OPENAI_API_KEY`, `TERMINAL_AGENT_INTERNAL_TOKEN` | garrytan/gstack (submodule) |
| `cirq` | `AQT_TOKEN`, `IONQ_API_KEY`, `PASQAL_TOKEN` | K-Dense-AI/claude-scientific-skills |
| `citation-management` | `NCBI_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `codex` | `CODEX_API_KEY`, `OPENAI_API_KEY` | garrytan/gstack (submodule) |
| `cso` | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | garrytan/gstack (submodule) |
| `database-lookup` | `ADDGENE_API_KEY`, `ALPHAVANTAGE_API_KEY`, `BEA_API_KEY`, `BIOGRID_API_KEY`, `BLS_API_KEY`, `CENSUS_API_KEY`, `CLUE_API_KEY`, `DATACOMMONS_API_KEY`, `DISGENET_API_KEY`, `FRED_API_KEY`, `MP_API_KEY`, `NASA_API_KEY`, `NCBI_API_KEY`, `NOAA_API_KEY`, `OMIM_API_KEY`, `OPENFDA_API_KEY`, `OPENWEATHERMAP_API_KEY`, `PATENTSVIEW_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `datamol` | `AWS_SECRET_ACCESS_KEY` | K-Dense-AI/claude-scientific-skills |
| `dnanexus-integration` | `DX_API_TOKEN`, `DX_AUTH_TOKEN` | K-Dense-AI/claude-scientific-skills |
| `document-release` | `CODEX_API_KEY` | garrytan/gstack (submodule) |
| `esm` | `ESM_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `exa-search` | `EXA_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `generate-image` | `OPENROUTER_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `genomic-intelligence` | `GI_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `gget` | `OPENAI_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `gstack` | `ANTHROPIC_API_KEY`, `CODEX_API_KEY`, `GBRAIN_MCP_TOKEN`, `GEMINI_API_KEY`, `GH_TOKEN`, `GSTACK_ANTHROPIC_API_KEY`, `GSTACK_FOO_API_KEY`, `GSTACK_OPENAI_API_KEY`, `GSTACK_SKILL_TOKEN`, `GSTACK_TOKEN`, `OPENAI_API_KEY`, `SUPABASE_ACCESS_TOKEN`, `VOYAGE_API_KEY` | garrytan/gstack (submodule) |
| `hugging-science` | `HF_TOKEN` | K-Dense-AI/claude-scientific-skills |
| `hypogenic` | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `infographics` | `OPENROUTER_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `investigate` | `ROOT_CAUSE_KEY` | garrytan/gstack (submodule) |
| `ios-qa` | `STATE_SERVER_TOKEN` | garrytan/gstack (submodule) |
| `lamindb` | `AWS_SECRET_ACCESS_KEY` | K-Dense-AI/claude-scientific-skills |
| `latex-posters` | `OPENROUTER_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `literature-review` | `OPENROUTER_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `markitdown` | `AZURE_API_KEY`, `AZURE_DOCUMENT_INTELLIGENCE_KEY` | K-Dense-AI/claude-scientific-skills |
| `mcp-cli` | `BRAVE_API_KEY`, `GITHUB_PERSONAL_ACCESS_TOKEN`, `GITHUB_TOKEN` | obra/superpowers-lab |
| `modal` | `AWS_SECRET_ACCESS_KEY`, `GITHUB_TOKEN`, `HF_TOKEN`, `MODAL_TOKEN_SECRET`, `OPENAI_API_KEY`, `WANDB_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `neuropixels-analysis` | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `nextflow` | `TOWER_ACCESS_TOKEN` | K-Dense-AI/claude-scientific-skills |
| `omero-integration` | `OMERO_SESSION_KEY` | K-Dense-AI/claude-scientific-skills |
| `open-notebook` | `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `OPENAI_API_KEY`, `OPEN_NOTEBOOK_ENCRYPTION_KEY` | K-Dense-AI/claude-scientific-skills |
| `optimize-for-gpu` | `AWS_SECRET_ACCESS_KEY` | K-Dense-AI/claude-scientific-skills |
| `paper-lookup` | `CORE_API_KEY`, `NCBI_API_KEY`, `OPENALEX_API_KEY`, `S2_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `paperclip` | `PAPERCLIP_API_KEY`, `PAPERCLIP_BEARER_TOKEN` | K-Dense-AI/claude-scientific-skills |
| `parallel-web` | `PARALLEL_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `pi-agent` | `AI_GATEWAY_API_KEY`, `ANTHROPIC_API_KEY`, `ANT_LING_API_KEY`, `ANYSEARCH_API_KEY`, `AWS_SECRET_ACCESS_KEY`, `AZURE_OPENAI_API_KEY`, `BASETEN_API_KEY`, `BOCHA_API_KEY`, `BRAVE_API_KEY`, `BRIGHTDATA_API_KEY`, `CEREBRAS_API_KEY`, `CLOUDFLARE_API_KEY`, `DATALAB_API_KEY`, `DEEPSEEK_API_KEY`, `EXA_API_KEY`, `FIRECRAWL_API_KEY`, `FIREWORKS_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `HF_TOKEN`, `JINA_API_KEY`, `KAGI_API_KEY`, `KIMI_API_KEY`, `LLAMA_API_KEY`, `MINIMAX_API_KEY`, `MINIMAX_CN_API_KEY`, `MISTRAL_API_KEY`, `NVIDIA_API_KEY`, `OLLAMA_API_KEY`, `OPENAI_API_KEY`, `OPENCODE_API_KEY`, `OPENROUTER_API_KEY`, `PARALLEL_API_KEY`, `PERPLEXITY_API_KEY`, `QUERIT_API_KEY`, `QWEN_TOKEN_PLAN_API_KEY`, `QWEN_TOKEN_PLAN_CN_API_KEY`, `RADIUS_API_KEY`, `SEARCH1API_KEY`, `SEARCHINFINITY_API_KEY`, `SERPBASE_API_KEY`, `SERPDIVE_API_KEY`, `TAVILY_API_KEY`, `TINYFISH_API_KEY`, `TOGETHER_API_KEY`, `XAI_API_KEY`, `XIAOMI_API_KEY`, `XIAOMI_TOKEN_PLAN_AMS_API_KEY`, `XIAOMI_TOKEN_PLAN_CN_API_KEY`, `XIAOMI_TOKEN_PLAN_SGP_API_KEY`, `ZAI_API_KEY`, `ZAI_CODING_CN_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `plan-ceo-review` | `CODEX_API_KEY` | garrytan/gstack (submodule) |
| `plan-devex-review` | `CODEX_API_KEY` | garrytan/gstack (submodule) |
| `plan-eng-review` | `CODEX_API_KEY` | garrytan/gstack (submodule) |
| `polars-bio` | `AWS_SECRET_ACCESS_KEY` | K-Dense-AI/claude-scientific-skills |
| `protocolsio-integration` | `PROTOCOLS_IO_ACCESS_TOKEN` | K-Dense-AI/claude-scientific-skills |
| `pufferlib` | `NEPTUNE_API_TOKEN`, `WANDB_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `pydicom` | `FRAME_TOKEN` | K-Dense-AI/claude-scientific-skills |
| `pymatgen` | `MP_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `pyzotero` | `ZOTERO_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `qiskit` | `IBM_QUANTUM_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `research-grants` | `OPENROUTER_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `research-lookup` | `OPENROUTER_API_KEY`, `PARALLEL_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `review` | `CODEX_API_KEY` | garrytan/gstack (submodule) |
| `rowan` | `ROWAN_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `scholar-evaluation` | `JSON_DUPLICATE_KEY` | K-Dense-AI/claude-scientific-skills |
| `scientific-critical-thinking` | `OPENROUTER_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `scientific-schematics` | `OPENROUTER_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `scientific-slides` | `OPENROUTER_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `setup-deploy` | `RENDER_API_KEY` | garrytan/gstack (submodule) |
| `setup-gbrain` | `ANTHROPIC_API_KEY`, `GBRAIN_MCP_TOKEN`, `OPENAI_API_KEY`, `SUPABASE_ACCESS_TOKEN`, `VOYAGE_API_KEY` | garrytan/gstack (submodule) |
| `ship` | `CODEX_API_KEY` | garrytan/gstack (submodule) |
| `sync-gbrain` | `VOYAGE_API_KEY` | garrytan/gstack (submodule) |
| `tamarind` | `TAMARIND_API_KEY` | K-Dense-AI/claude-scientific-skills |
| `tiledbvcf` | `TILEDB_REST_TOKEN` | K-Dense-AI/claude-scientific-skills |
| `transformers` | `HF_HUB_DISABLE_IMPLICIT_TOKEN`, `HF_TOKEN` | K-Dense-AI/claude-scientific-skills |
| `treatment-plans` | `JSON_DUPLICATE_KEY` | K-Dense-AI/claude-scientific-skills |
| `video-use` | `ELEVENLABS_API_KEY` | browser-use/video-use |

### Skills that call an MCP server

These skills reference `mcp__<server>__*` tools. If the server is not registered,
the skill loads but its MCP steps fail.

| Skill | MCP servers it calls | Registered here? |
|---|---|---|
| `autoplan` | `conductor` ✗ | no |
| `canary` | `conductor` ✗ | no |
| `codex` | `conductor` ✗ | no |
| `context-restore` | `conductor` ✗ | no |
| `context-save` | `conductor` ✗ | no |
| `cso` | `conductor` ✗ | no |
| `design-consultation` | `conductor` ✗ | no |
| `design-html` | `conductor` ✗ | no |
| `design-review` | `conductor` ✗ | no |
| `design-shotgun` | `conductor` ✗ | no |
| `devex-review` | `conductor` ✗ | no |
| `document-generate` | `conductor` ✗ | no |
| `document-release` | `conductor` ✗ | no |
| `gstack` | `claude-in-chrome` ✗, `conductor` ✗, `gbrain` ✗ | no |
| `health` | `conductor` ✗ | no |
| `imaging-data-commons` | `claude_ai_IDC_MCP_prod` ✗, `idc` ✗ | no |
| `investigate` | `conductor` ✗ | no |
| `ios-clean` | `conductor` ✗ | no |
| `ios-design-review` | `conductor` ✗ | no |
| `ios-fix` | `conductor` ✗ | no |
| `ios-qa` | `conductor` ✗ | no |
| `ios-sync` | `conductor` ✗ | no |
| `land-and-deploy` | `conductor` ✗ | no |
| `landing-report` | `conductor` ✗ | no |
| `learn` | `conductor` ✗ | no |
| `office-hours` | `conductor` ✗, `gbrain` ✗ | no |
| `pair-agent` | `conductor` ✗ | no |
| `plan-ceo-review` | `conductor` ✗, `gbrain` ✗ | no |
| `plan-design-review` | `conductor` ✗, `gbrain` ✗ | no |
| `plan-devex-review` | `conductor` ✗, `gbrain` ✗ | no |
| `plan-eng-review` | `conductor` ✗, `gbrain` ✗ | no |
| `plan-tune` | `conductor` ✗, `gbrain` ✗ | no |
| `qa` | `conductor` ✗ | no |
| `qa-only` | `conductor` ✗ | no |
| `retro` | `conductor` ✗ | no |
| `review` | `conductor` ✗ | no |
| `setup-deploy` | `conductor` ✗ | no |
| `setup-gbrain` | `conductor` ✗, `gbrain` ✗ | no |
| `ship` | `conductor` ✗ | no |
| `skillify` | `conductor` ✗ | no |
| `spec` | `conductor` ✗ | no |
| `sync-gbrain` | `conductor` ✗, `gbrain` ✗ | no |

### Every skill in this repo

All 230 skill folders, alphabetical. **Wired** means `~/.claude/skills/<name>`
points back here, so editing the file in this repo changes the live skill immediately.

| Skill | Wired | Source | Needs a credential | Needs MCP | What it does |
|---|---|---|---|---|---|
| `_gstack-command` | linked | garrytan/gstack (vendored router) | no | no | Router for the gstack skill suite. (gstack) |
| `adaptyv` | linked | K-Dense-AI/claude-scientific-skills | yes | no | How to use the Adaptyv Bio Foundry API and Python SDK for protein experiment design, submission, and results… |
| `aeon` | linked | K-Dense-AI/claude-scientific-skills | no | no | This skill should be used for time series machine learning tasks including classification, regression, cluste… |
| `analytical-method-validation` | linked | K-Dense-AI/claude-scientific-skills | no | no | Plan, execute, and document validation, verification, and transfer of analytical procedures under the governi… |
| `anndata` | linked | K-Dense-AI/claude-scientific-skills | no | no | Data structure for annotated matrices in single-cell analysis. Use when working with .h5ad files or integrati… |
| `arbor` | linked | K-Dense-AI/claude-scientific-skills | no | no | Autonomously improve a real artifact (code, training recipe, agent harness, data pipeline, prompt) against an… |
| `arboreto` | linked | K-Dense-AI/claude-scientific-skills | no | no | Infer gene regulatory networks (GRNs) from gene expression data using scalable algorithms (GRNBoost2, GENIE3)… |
| `astropy` | linked | K-Dense-AI/claude-scientific-skills | no | no | Core Python library for astronomy and astrophysics workflows that need Astropy APIs, including units/quantiti… |
| `autoplan` | linked | garrytan/gstack (submodule) | yes | yes | Auto-review pipeline — reads the full CEO, design, eng, and DX review skills from disk and runs them sequenti… |
| `autoskill` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Observe the user's screen via screenpipe, detect repeated research workflows, match them against existing sci… |
| `benchling-integration` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Benchling Python SDK and REST API integration for registry entities, inventory, ELN entries, workflows, Bench… |
| `benchmark` | linked | garrytan/gstack (submodule) | no | no | Performance regression detection using the browse daemon. (gstack) |
| `benchmark-models` | linked | garrytan/gstack (submodule) | yes | no | Cross-model benchmark for gstack skills. (gstack) |
| `bgpt-paper-search` | linked | K-Dense-AI/claude-scientific-skills | no | no | Search scientific papers and retrieve structured experimental data extracted from full-text studies via the B… |
| `bids` | linked | K-Dense-AI/claude-scientific-skills | no | no | Use this skill when working with Brain Imaging Data Structure (BIDS) datasets: organizing neuroscience and bi… |
| `biopython` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Comprehensive molecular biology toolkit. Use for sequence manipulation, file parsing (FASTA/GenBank/PDB), phy… |
| `bioservices` | linked | K-Dense-AI/claude-scientific-skills | no | no | Unified Python interface to 40+ bioinformatics services. Use when querying multiple databases (UniProt, KEGG,… |
| `browse` | linked | garrytan/gstack (submodule) | yes | no | Fast headless browser for QA testing and site dogfooding. (gstack) |
| `bulk-rnaseq` | linked | K-Dense-AI/claude-scientific-skills | no | no | End-to-end bulk RNA-seq orchestrator — takes raw FASTQ reads through QC and trimming (FastQC, fastp/Trim Galo… |
| `canary` | linked | garrytan/gstack (submodule) | no | yes | Post-deploy canary monitoring. (gstack) |
| `careful` | linked | garrytan/gstack (submodule) | no | no | Safety guardrails for destructive commands. (gstack) |
| `cellxgene-census` | linked | K-Dense-AI/claude-scientific-skills | no | no | Query the CZ CELLxGENE Census programmatically for versioned public single-cell and spatial transcriptomics d… |
| `cirq` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Google quantum computing framework. Use when targeting Google Quantum AI hardware, designing noise-aware circ… |
| `citation-management` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Comprehensive citation management for academic research. Search OpenAlex, PubMed, and Google Scholar for pape… |
| `clinical-decision-support` | linked | K-Dense-AI/claude-scientific-skills | no | no | Prepare and validate research-only clinical decision-support evaluation, evidence-profile, cohort, survival,… |
| `clinical-reports` | linked | K-Dense-AI/claude-scientific-skills | no | no | Create safety-bounded draft structures and run local deterministic checks for clinical case, diagnostic, tria… |
| `cobrapy` | linked | K-Dense-AI/claude-scientific-skills | no | no | Constraint-based metabolic modeling (COBRA). FBA, FVA, gene knockouts, flux sampling, SBML models, for system… |
| `codex` | linked | garrytan/gstack (submodule) | yes | yes | OpenAI Codex CLI wrapper — three modes. (gstack) |
| `connect-chrome` | linked | garrytan/gstack | no | no | Launch GStack Browser — AI-controlled Chromium with the sidebar extension baked in. |
| `consciousness-council` | linked | K-Dense-AI/claude-scientific-skills | no | no | Run a multi-perspective Mind Council deliberation on any question, decision, or creative challenge. Use this… |
| `context-restore` | linked | garrytan/gstack (submodule) | no | yes | Restore working context saved earlier by /context-save. (gstack) |
| `context-save` | linked | garrytan/gstack (submodule) | no | yes | Save working context. (gstack) |
| `cso` | linked | garrytan/gstack (submodule) | yes | yes | Chief Security Officer mode. (gstack) |
| `d3-viz` | linked | chrisvoncsefalvay/claude-d3js-skill | no | no | Creating interactive data visualisations using d3.js. This skill should be used when creating custom charts,… |
| `dask` | linked | K-Dense-AI/claude-scientific-skills | no | no | Distributed computing for larger-than-RAM pandas/NumPy workflows. Use when you need to scale existing pandas/… |
| `database-lookup` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Query documented public database APIs with explicit endpoints, filters, pagination, and provenance. Use when… |
| `datamol` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Pythonic wrapper around RDKit with simplified interface and sensible defaults. Preferred for standard drug di… |
| `deepchem` | linked | K-Dense-AI/claude-scientific-skills | no | no | Molecular ML with diverse featurizers and pre-built datasets. Use for property prediction (ADMET, toxicity) w… |
| `deepspot-m` | linked | K-Dense-AI/claude-scientific-skills | no | no | Generate transcriptome-wide virtual spatial transcriptomics from H&E histology with DeepSpot-M. Use when you… |
| `deeptools` | linked | K-Dense-AI/claude-scientific-skills | no | no | NGS analysis toolkit. BAM to bigWig conversion, QC (correlation, PCA, fingerprints), heatmaps/profiles (TSS,… |
| `depmap` | linked | K-Dense-AI/claude-scientific-skills | no | no | Query the Cancer Dependency Map (DepMap) for cancer cell line gene dependency scores (CRISPR Chronos), drug s… |
| `design-consultation` | linked | garrytan/gstack (submodule) | no | yes | Design consultation: understands your product, researches the landscape, proposes a complete design system (a… |
| `design-html` | linked | garrytan/gstack (submodule) | no | yes | Design finalization: generates production-quality Pretext-native HTML/CSS. (gstack) |
| `design-review` | linked | garrytan/gstack (submodule) | no | yes | Designer's eye QA: finds visual inconsistency, spacing issues, hierarchy problems, AI slop patterns, and slow… |
| `design-shotgun` | linked | garrytan/gstack (submodule) | no | yes | Design shotgun: generate multiple AI design variants, open a comparison board, collect structured feedback, a… |
| `devex-review` | linked | garrytan/gstack (submodule) | no | yes | Live developer experience audit. (gstack) |
| `dhdna-profiler` | linked | K-Dense-AI/claude-scientific-skills | no | no | Extract cognitive patterns and thinking fingerprints from any text. Use this skill when the user wants to ana… |
| `diagram` | linked | garrytan/gstack (submodule) | no | no | Turn an English description (or mermaid source) into a diagram triplet: the source, an editable .excalidraw f… |
| `diffdock` | linked | K-Dense-AI/claude-scientific-skills | no | no | DiffDock and DiffDock-L molecular docking. Use for protein-small-molecule pose prediction from PDB or sequenc… |
| `dnanexus-integration` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Build and operate reproducible genomics workloads on DNAnexus with the dx CLI, dxpy, apps/applets, native wor… |
| `document-generate` | linked | garrytan/gstack (submodule) | no | yes | Generate missing documentation from scratch for a feature, module, or entire project. (gstack) |
| `document-release` | linked | garrytan/gstack (submodule) | yes | yes | Post-ship documentation update. (gstack) |
| `docx` | linked | K-Dense-AI/claude-scientific-skills | no | no | Use this skill whenever the user wants to create, read, edit, or manipulate Word documents (.docx files) or W… |
| `emil-design-eng` | linked | emilkowalski/skills | no | no | This skill encodes Emil Kowalski's philosophy on UI polish, component design, animation decisions, and the in… |
| `esm` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Use when working directly with the `esm` Python SDK, ESM3 or ESMC model IDs, Forge/Biohub inference clients,… |
| `etetoolkit` | linked | K-Dense-AI/claude-scientific-skills | no | no | Analyze, manipulate, compare, annotate, and visualize phylogenetic or other hierarchical trees with ETE 4. Us… |
| `exa-search` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Web toolkit powered by Exa, tuned for scientific and technical content. Use this skill when the user needs to… |
| `experimental-design` | linked | K-Dense-AI/claude-scientific-skills | no | no | Design experiments and studies BEFORE data is collected — choosing a design, randomizing, blocking, and layin… |
| `exploratory-data-analysis` | linked | K-Dense-AI/claude-scientific-skills | no | no | Perform bounded, local exploratory analysis of explicitly supported scientific files. Use for redacted CSV/TS… |
| `ffuf-web-fuzzing` | linked | jthack/ffuf_claude_skill | no | no | Expert guidance for ffuf web fuzzing during penetration testing, including authenticated fuzzing with raw req… |
| `find-skills` | linked | vercel-labs/skills | no | no | Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for… |
| `finding-duplicate-functions` | linked | obra/superpowers-lab | no | no | Use when auditing a codebase for semantic duplication - functions that do the same thing but have different n… |
| `flowio` | linked | K-Dense-AI/claude-scientific-skills | no | no | Read, inspect, and write Flow Cytometry Standard (FCS) 2.0, 3.0, and 3.1 files with FlowIO. Use for low-level… |
| `fluidsim` | linked | K-Dense-AI/claude-scientific-skills | no | no | Plan, configure, inspect, restart, and analyze bounded FluidSim computational-fluid-dynamics simulations with… |
| `freeze` | linked | garrytan/gstack (submodule) | no | no | Restrict file edits to a specific directory for the session. (gstack) |
| `generate-image` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Generate or edit images with AI models through the OpenRouter Image API (Gemini, Seedream, Recraft, GPT-Image… |
| `geniml` | linked | K-Dense-AI/claude-scientific-skills | no | no | Use Geniml for audited local genomic-interval workflows: validate BED and universe contracts, plan Region2Vec… |
| `genomic-coordinates` | linked | K-Dense-AI/claude-scientific-skills | no | no | Convert genomic intervals between coordinate conventions, normalise and compare variant representations, and… |
| `genomic-intelligence` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Predict regulatory features, gene structure, and expression directly from DNA sequence using Genomic Intellig… |
| `geomaster` | linked | K-Dense-AI/claude-scientific-skills | no | no | Comprehensive geospatial science skill covering remote sensing, GIS, spatial analysis, machine learning for e… |
| `geopandas` | linked | K-Dense-AI/claude-scientific-skills | no | no | Guidance and local audit tools for Python workflows that directly use GeoPandas GeoSeries, GeoDataFrame, spat… |
| `get-available-resources` | linked | K-Dense-AI/claude-scientific-skills | no | no | Detect host inventory and effective CPU, memory, disk, scheduler, container, and accelerator limits when a us… |
| `gget` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Fast CLI/Python queries to 20+ bioinformatics databases. Use for quick lookups: gene info, BLAST/BLAT, viral… |
| `ginkgo-cloud-lab` | linked | K-Dense-AI/claude-scientific-skills | no | no | Submit and manage protocols on Ginkgo Bioworks Cloud Lab (cloud.ginkgo.bio), a web-based interface for autono… |
| `glycoengineering` | linked | K-Dense-AI/claude-scientific-skills | no | no | Analyze and engineer protein glycosylation. Scan sequences for N-glycosylation sequons (N-X-S/T), predict O-g… |
| `gstack` | linked | garrytan/gstack (submodule) | yes | yes | Router for the gstack skill suite. (gstack) |
| `gstack-upgrade` | linked | garrytan/gstack (submodule) | no | no | Upgrade gstack to the latest version. |
| `gtars` | linked | K-Dense-AI/claude-scientific-skills | no | no | Use Gtars for local genomic interval models and set algebra, overlaps and counts, consensus and coverage, tok… |
| `guard` | linked | garrytan/gstack (submodule) | no | no | Full safety mode: destructive command warnings + directory-scoped edits. (gstack) |
| `health` | linked | garrytan/gstack (submodule) | no | yes | Code quality dashboard. (gstack) |
| `histolab` | linked | K-Dense-AI/claude-scientific-skills | no | no | Lightweight WSI tile extraction and preprocessing. Use for basic slide processing, tissue detection, tile ext… |
| `hugging-science` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Use when the user is doing AI/ML work in a scientific domain such as biology, chemistry, physics, astronomy,… |
| `hypogenic` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Plans and audits use of ChicagoHAI HypoGeniC/HypoRefine for LLM-assisted hypothesis generation from labeled t… |
| `hypothesis-generation` | linked | K-Dense-AI/claude-scientific-skills | no | no | Formulate evidence-bounded scientific questions, candidate hypotheses, rival explanations, causal or associat… |
| `imaging-data-commons` | linked | K-Dense-AI/claude-scientific-skills | no | yes | Query and download public cancer imaging data from NCI Imaging Data Commons. Invoke for any question about ID… |
| `infographics` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Create professional infographics using Nano Banana Pro AI with smart iterative refinement. Uses Gemini 3.6 Fl… |
| `investigate` | linked | garrytan/gstack (submodule) | yes | yes | Systematic debugging with root cause investigation. (gstack) |
| `ios-clean` | linked | garrytan/gstack (submodule) | no | yes | Remove the DebugBridge SPM package and all #if DEBUG wiring from an iOS app. (gstack) |
| `ios-design-review` | linked | garrytan/gstack (submodule) | no | yes | Visual design audit for iOS apps on real hardware. (gstack) |
| `ios-fix` | linked | garrytan/gstack (submodule) | no | yes | Autonomous iOS bug fixer. (gstack) |
| `ios-qa` | linked | garrytan/gstack (submodule) | yes | yes | Live-device iOS QA for SwiftUI apps. (gstack) |
| `ios-sync` | linked | garrytan/gstack (submodule) | no | yes | Regenerate the iOS debug bridge against the latest upstream gstack templates. (gstack) |
| `iso-standards-readiness` | linked | K-Dense-AI/claude-scientific-skills | no | no | Prepares and structurally reviews readiness evidence for ISO management-system and laboratory-competence stan… |
| `lab-hardware-cad` | linked | K-Dense-AI/claude-scientific-skills | no | no | Design custom laboratory hardware as parametric build123d models and export fabrication-ready STEP, STL, and… |
| `labarchive-integration` | linked | K-Dense-AI/claude-scientific-skills | no | no | Securely integrate with the official LabArchives ELN REST-like API and Inventory API v1. Use for regional end… |
| `lamindb` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Use when working with LaminDB, the open-source lineage-native lakehouse for biological datasets and models. C… |
| `land-and-deploy` | linked | garrytan/gstack (submodule) | no | yes | Land and deploy workflow. (gstack) |
| `landing-report` | linked | garrytan/gstack (submodule) | no | yes | Read-only queue dashboard for workspace-aware ship. (gstack) |
| `latchbio-integration` | linked | K-Dense-AI/claude-scientific-skills | no | no | Build, register, debug, and operate bioinformatics workflows on Latch using the Python SDK, CLI, Latch Data a… |
| `latex-posters` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Create professional research posters in LaTeX using beamerposter, tikzposter, or baposter. Support for confer… |
| `learn` | linked | garrytan/gstack (submodule) | no | yes | Manage project learnings. |
| `liteparse` | linked | K-Dense-AI/claude-scientific-skills | no | no | Local document and PDF parsing that returns spatial text with bounding boxes. Use for extracting text from PD… |
| `literature-review` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Conduct comprehensive, systematic literature reviews using multiple academic databases (PubMed, arXiv, bioRxi… |
| `make-pdf` | linked | garrytan/gstack (submodule) | no | no | Turn any markdown file into a publication-quality PDF. (gstack) |
| `markdown-mermaid-writing` | linked | K-Dense-AI/claude-scientific-skills | no | no | Comprehensive markdown and Mermaid diagram writing skill. Use when creating any scientific document, report,… |
| `market-research-reports` | linked | K-Dense-AI/claude-scientific-skills | no | no | Build evidence-traceable market research reports and assumption-driven market sizing or forecast scenarios. U… |
| `markitdown` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Convert heterogeneous documents and selected URIs to Markdown with Microsoft MarkItDown for text analysis, se… |
| `matchms` | linked | K-Dense-AI/claude-scientific-skills | no | no | Process, clean, compare, and search tandem mass spectra with matchms. Use for MS/MS file I/O, metadata harmon… |
| `matlab` | linked | K-Dense-AI/claude-scientific-skills | no | no | Build, review, migrate, and safely plan MATLAB or GNU Octave numerical workflows, including arrays, tabular/t… |
| `matplotlib` | linked | K-Dense-AI/claude-scientific-skills | no | no | Low-level plotting library for full customization. Use when you need fine-grained control over every plot ele… |
| `mcp-cli` | linked | obra/superpowers-lab | yes | no | Use MCP servers on-demand via the mcp CLI tool - discover tools, resources, and prompts without polluting con… |
| `medchem` | linked | K-Dense-AI/claude-scientific-skills | no | no | Medicinal chemistry filters for compound triage. Apply drug-likeness rules (Lipinski, Veber, CNS), structural… |
| `modal` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Modal is a serverless cloud platform for running Python on demand, including on-demand GPUs. Use when deployi… |
| `molecular-dynamics` | linked | K-Dense-AI/claude-scientific-skills | no | no | Run and analyze molecular dynamics simulations with OpenMM and MDAnalysis. Set up protein/small molecule syst… |
| `molfeat` | linked | K-Dense-AI/claude-scientific-skills | no | no | Molecular featurization for ML (100+ featurizers). ECFP, MACCS, descriptors, pretrained models (ChemBERTa), c… |
| `ncats-arax` | linked | K-Dense-AI/claude-scientific-skills | no | no | Queries the NCATS Translator ARAX production API for bounded, typed, provenance-rich one-hop and endpoint-pin… |
| `networkx` | linked | K-Dense-AI/claude-scientific-skills | no | no | Create, analyze, and visualize complex networks and graphs in Python with NetworkX. Use when working with net… |
| `neurokit2` | linked | K-Dense-AI/claude-scientific-skills | no | no | Use NeuroKit2 to build or audit reproducible research workflows for physiological time-series preprocessing,… |
| `neuropixels-analysis` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Analyze Neuropixels extracellular recordings end-to-end with SpikeInterface. Covers loading SpikeGLX/Open Eph… |
| `nextflow` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Build, run, and debug Nextflow data pipelines and nf-core workflows end to end. Use whenever the user mention… |
| `office-hours` | linked | garrytan/gstack (submodule) | no | yes | YC Office Hours — two modes. (gstack) |
| `omero-integration` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Securely inspect and automate microscopy data workflows against OMERO.server with omero-py, BlitzGateway, OME… |
| `onekgpd` | linked | K-Dense-AI/claude-scientific-skills | no | no | Query the 1000 Genomes Project dataset (3,202 whole-genome-sequenced individuals, GRCh38) at the level of ind… |
| `ontology-term-resolution` | linked | K-Dense-AI/claude-scientific-skills | no | no | Resolve free-text scientific labels to ontology term IDs and validate existing CURIEs against the EBI Ontolog… |
| `open-gstack-browser` | linked | garrytan/gstack (submodule) | no | no | Launch GStack Browser — AI-controlled Chromium with the sidebar extension baked in. |
| `open-notebook` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Self-hosted, open-source alternative to Google NotebookLM for AI-powered research and document analysis. Use… |
| `openpiv` | linked | K-Dense-AI/claude-scientific-skills | no | no | Particle Image Velocimetry (PIV) analysis with OpenPIV. Use when extracting velocity fields from PIV image pa… |
| `opentrons-integration` | linked | K-Dense-AI/claude-scientific-skills | no | no | Author, review, migrate, simulate, and troubleshoot official Opentrons Python Protocol API v2 protocols for F… |
| `optimize-for-gpu` | linked | K-Dense-AI/claude-scientific-skills | yes | no | GPU-accelerates scientific Python on NVIDIA hardware and verifies that the result is correct and faster. Use… |
| `pacsomatic` | linked | K-Dense-AI/claude-scientific-skills | no | no | Operator toolkit for nf-core/pacsomatic matched tumor-normal workflows from BAM inputs. Use this skill when t… |
| `pair-agent` | linked | garrytan/gstack (submodule) | no | yes | Pair a remote AI agent with your browser. (gstack) |
| `paper-lookup` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Search 11 academic literature APIs for papers, preprints, citations, and open-access full text, and return re… |
| `paperclip` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Search and read full-text biomedical papers, FDA/PMDA/EMA regulatory documents, clinical trial registries, an… |
| `paperzilla` | linked | K-Dense-AI/claude-scientific-skills | no | no | Chat with your agent about projects, recommendations, and canonical papers in Paperzilla. Use when users ask… |
| `parallel-web` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Use Parallel CLI for web search, URL extraction, deep research, structured data enrichment, entity discovery,… |
| `pathml` | linked | K-Dense-AI/claude-scientific-skills | no | no | Use PathML for local, research-only computational pathology workflows: load and tile slides, build preprocess… |
| `pathogen-variant-surveillance` | linked | K-Dense-AI/claude-scientific-skills | no | no | Query live pathogen genomic surveillance data through the GenSpectrum LAPIS API to find which viral lineages… |
| `pathway-enrichment` | linked | K-Dense-AI/claude-scientific-skills | no | no | Run pathway and gene-set enrichment analysis on gene lists or ranked gene data, then interpret the results. U… |
| `pdf` | linked | K-Dense-AI/claude-scientific-skills | no | no | Use this skill whenever the user wants to do anything with PDF files. This includes reading or extracting tex… |
| `peer-review` | linked | K-Dense-AI/claude-scientific-skills | no | no | Prepare evidence-bounded, constructive peer-review drafts and structured manuscript assessments. Use for auth… |
| `pennylane` | linked | K-Dense-AI/claude-scientific-skills | no | no | Hardware-agnostic quantum ML framework with automatic differentiation. Use when training quantum circuits via… |
| `phylogenetics` | linked | K-Dense-AI/claude-scientific-skills | no | no | Build and analyze phylogenetic trees using MAFFT (multiple alignment), IQ-TREE 2 (maximum likelihood), and Fa… |
| `pi-agent` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Build with and use Pi, the minimal terminal coding harness. Use for installing Pi, configuring providers/mode… |
| `pkpd-modeling` | linked | K-Dense-AI/claude-scientific-skills | no | no | Pharmacokinetic and pharmacodynamic modelling and simulation - non-compartmental analysis, compartmental and… |
| `plan-ceo-review` | linked | garrytan/gstack (submodule) | yes | yes | CEO/founder-mode plan review. (gstack) |
| `plan-design-review` | linked | garrytan/gstack (submodule) | no | yes | Designer's eye plan review — interactive, like CEO and Eng review. (gstack) |
| `plan-devex-review` | linked | garrytan/gstack (submodule) | yes | yes | Interactive developer experience plan review. (gstack) |
| `plan-eng-review` | linked | garrytan/gstack (submodule) | yes | yes | Eng manager-mode plan review. (gstack) |
| `plan-tune` | linked | garrytan/gstack (submodule) | no | yes | Self-tuning question sensitivity + developer psychographic for gstack (v1: observational). (gstack) |
| `polars` | linked | K-Dense-AI/claude-scientific-skills | no | no | High-performance DataFrame library for Python ETL, analytics, and pandas migration. Use for expression-based… |
| `polars-bio` | linked | K-Dense-AI/claude-scientific-skills | yes | no | High-performance genomic interval operations and bioinformatics file I/O on Polars DataFrames. Overlap, neare… |
| `pptx` | linked | K-Dense-AI/claude-scientific-skills | no | no | Use this skill any time a .pptx or .potx file is involved in any way — as input, output, or both. This includ… |
| `pptx-posters` | linked | K-Dense-AI/claude-scientific-skills | no | no | Create and audit editable scientific posters in macro-free PowerPoint (.pptx) from author-approved local cont… |
| `primekg` | linked | K-Dense-AI/claude-scientific-skills | no | no | Query the Precision Medicine Knowledge Graph (PrimeKG) for multiscale biological data including genes, drugs,… |
| `protocolsio-integration` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Read, validate, and safely export protocols.io data with current official REST/MCP contracts, or create non-e… |
| `pufferlib` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Version-aware guidance for PufferLib reinforcement-learning environments, vectorization, policies, PuffeRL tr… |
| `pydeseq2` | linked | K-Dense-AI/claude-scientific-skills | no | no | Differential gene expression analysis for bulk RNA-seq with PyDESeq2, including formulaic designs, Wald tests… |
| `pydicom` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Use pydicom to read, inspect, write, transform, and safely preflight local DICOM datasets and pixel data. App… |
| `pyhealth` | linked | K-Dense-AI/claude-scientific-skills | no | no | Build clinical/healthcare deep-learning pipelines with PyHealth — loading EHR/signal/imaging datasets (MIMIC-… |
| `pylabrobot` | linked | K-Dense-AI/claude-scientific-skills | no | no | Develop and review PyLabRobot lab-automation resources, liquid-handling plans, offline simulations, and suppo… |
| `pymatgen` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Analyze, validate, convert, and transform materials structures and computed materials data with current pymat… |
| `pymc` | linked | K-Dense-AI/claude-scientific-skills | no | no | Bayesian modeling with PyMC. Build hierarchical models, MCMC (NUTS), variational inference, LOO/WAIC comparis… |
| `pymoo` | linked | K-Dense-AI/claude-scientific-skills | no | no | Multi-objective optimization framework. NSGA-II, NSGA-III, MOEA/D, Pareto fronts, constraint handling, benchm… |
| `pyopenms` | linked | K-Dense-AI/claude-scientific-skills | no | no | Complete mass spectrometry analysis platform. Use for proteomics and metabolomics workflows—feature detection… |
| `pysam` | linked | K-Dense-AI/claude-scientific-skills | no | no | Python/HTSlib workflows for genomic files. Use when reading, querying, filtering, or writing SAM/BAM/CRAM, VC… |
| `pytdc` | linked | K-Dense-AI/claude-scientific-skills | no | no | Use Therapeutics Data Commons through the PyTDC Python package for registry discovery, approved dataset acces… |
| `pytorch-lightning` | linked | K-Dense-AI/claude-scientific-skills | no | no | Deep learning framework (PyTorch Lightning / lightning package). Organize PyTorch code into LightningModules,… |
| `pyzotero` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Interact with Zotero reference management libraries using the pyzotero Python client. Retrieve, create, updat… |
| `qa` | linked | garrytan/gstack (submodule) | no | yes | Systematically QA test a web application and fix bugs found. (gstack) |
| `qa-only` | linked | garrytan/gstack (submodule) | no | yes | Report-only QA testing. (gstack) |
| `qiskit` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Build, simulate, transpile, and execute quantum circuits with Qiskit and IBM Quantum Runtime. Use for Qiskit… |
| `qutip` | linked | K-Dense-AI/claude-scientific-skills | no | no | Simulate and audit closed and open quantum-system models with QuTiP 5, including deterministic, trajectory, s… |
| `rdkit` | linked | K-Dense-AI/claude-scientific-skills | no | no | Cheminformatics toolkit for fine-grained molecular control. SMILES/SDF parsing, descriptors (MW, LogP, TPSA),… |
| `relsa-severity-assessment` | linked | K-Dense-AI/claude-scientific-skills | no | no | Multivariate severity assessment and humane endpoint prediction for laboratory animal studies using the RELSA… |
| `research-grants` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Write competitive research proposals for NSF, NIH, DOE, DARPA, and Taiwan NSTC. Agency-specific formatting, r… |
| `research-lookup` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Compile current scholarly evidence for a scientific manuscript or research brief. Use when the user explicitl… |
| `retro` | linked | garrytan/gstack (submodule) | no | yes | Weekly engineering retrospective. (gstack) |
| `review` | linked | garrytan/gstack (submodule) | yes | yes | Pre-landing PR review. (gstack) |
| `rowan` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Rowan is a cloud-native molecular modeling and medicinal-chemistry workflow platform with a Python API. Use f… |
| `scanpy` | linked | K-Dense-AI/claude-scientific-skills | no | no | Standard single-cell RNA-seq analysis pipeline. Use for QC, normalization, dimensionality reduction (PCA/UMAP… |
| `scholar-evaluation` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Provide qualitative-first, evidence-traceable developmental review of scholarly works and audit low-stakes re… |
| `scientific-brainstorming` | linked | K-Dense-AI/claude-scientific-skills | no | no | Facilitates evidence-aware scientific ideation with independent generation, structured discussion, explicit a… |
| `scientific-critical-thinking` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Evaluate scientific claims and evidence quality. Use for assessing experimental design validity, identifying… |
| `scientific-schematics` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Create publication-quality scientific diagrams using Nano Banana 2 AI with smart iterative refinement. Uses G… |
| `scientific-slides` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Build slide decks and presentations for research talks. Use this for making PowerPoint slides, conference pre… |
| `scientific-visualization` | linked | K-Dense-AI/claude-scientific-skills | no | no | Create and audit truthful, accessible, publication-ready scientific figures with Matplotlib, Seaborn, or Plot… |
| `scientific-writing` | linked | K-Dense-AI/claude-scientific-skills | no | no | Draft, revise, and audit scientific manuscripts or reports with explicit evidence provenance, reporting-guide… |
| `scikit-bio` | linked | K-Dense-AI/claude-scientific-skills | no | no | Biological data toolkit. Sequence analysis, alignments, phylogenetic trees, diversity metrics (alpha/beta, Un… |
| `scikit-learn` | linked | K-Dense-AI/claude-scientific-skills | no | no | Machine learning in Python with scikit-learn. Use when working with supervised learning (classification, regr… |
| `scikit-survival` | linked | K-Dense-AI/claude-scientific-skills | no | no | Build, evaluate, and audit right-censored or competing-risk survival workflows with scikit-survival, includin… |
| `scrape` | linked | garrytan/gstack (submodule) | no | no | Pull data from a web page. (gstack) |
| `scvelo` | linked | K-Dense-AI/claude-scientific-skills | no | no | RNA velocity analysis with scVelo. Estimate cell state transitions from unspliced/spliced mRNA dynamics, infe… |
| `scvi-tools` | linked | K-Dense-AI/claude-scientific-skills | no | no | Deep generative models for single-cell omics. Use when you need probabilistic batch correction (scVI), transf… |
| `seaborn` | linked | K-Dense-AI/claude-scientific-skills | no | no | Statistical visualization with pandas integration. Use for quick exploration of distributions, relationships,… |
| `setup-browser-cookies` | linked | garrytan/gstack (submodule) | no | no | Import cookies from your real Chromium browser into the headless browse session. (gstack) |
| `setup-deploy` | linked | garrytan/gstack (submodule) | yes | yes | Configure deployment settings for /land-and-deploy. |
| `setup-gbrain` | linked | garrytan/gstack (submodule) | yes | yes | Set up gbrain for this coding agent: install the CLI, initialize a local PGLite or Supabase brain, register M… |
| `shap` | linked | K-Dense-AI/claude-scientific-skills | no | no | Explain and audit machine-learning predictions with SHAP. Use for selecting SHAP explainers and maskers, comp… |
| `ship` | linked | garrytan/gstack (submodule) | yes | yes | Ship workflow: detect + merge base branch, run tests, review diff, bump VERSION, update CHANGELOG, commit, pu… |
| `simpy` | linked | K-Dense-AI/claude-scientific-skills | no | no | Build, inspect, test, and analyze bounded process-based discrete-event simulations with SimPy, including even… |
| `skillify` | linked | garrytan/gstack (submodule) | no | yes | Codify the most recent successful /scrape flow into a permanent browser-skill on disk. (gstack) |
| `spec` | linked | garrytan/gstack (submodule) | no | yes | Turn vague intent into a precise, executable spec in five phases. (gstack) |
| `stable-baselines3` | linked | K-Dense-AI/claude-scientific-skills | no | no | Production-ready reinforcement learning algorithms (PPO, SAC, DQN, TD3, DDPG, A2C) with scikit-learn-like API… |
| `statistical-analysis` | linked | K-Dense-AI/claude-scientific-skills | no | no | Guided statistical analysis for research data - test selection, assumption checking, effect sizes, power anal… |
| `statistical-power` | linked | K-Dense-AI/claude-scientific-skills | no | no | Sample-size and statistical power calculations for planning studies. Use whenever someone asks "how many subj… |
| `statsmodels` | linked | K-Dense-AI/claude-scientific-skills | no | no | Statistical models library for Python. Use when you need specific model classes (OLS, GLM, mixed models, ARIM… |
| `ste-writing` | linked | loose file (~/Downloads) | no | no | Rewrite prose (docs, READMEs, PR descriptions, error messages, release notes, comments — never code) into ASD… |
| `sympy` | linked | K-Dense-AI/claude-scientific-skills | no | no | Use when you need exact symbolic math in Python — algebra, calculus, equation solving, symbolic linear algebr… |
| `sync-gbrain` | linked | garrytan/gstack (submodule) | yes | yes | Keep gbrain current with this repo's code and refresh agent search guidance in CLAUDE.md. (gstack) |
| `tamarind` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Access a collection of open-source molecular design and structural biology tools on the Tamarind Bio platform… |
| `task-observer` | linked | rebelytics/one-skill-to-rule-them-all (submodule) | no | no | Monitors task execution for skill improvement opportunities. Use this skill during ANY multi-step task, agent… |
| `tiledbvcf` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Efficient storage and retrieval of genomic variant data using TileDB. Scalable VCF/BCF ingestion, incremental… |
| `timesfm-forecasting` | linked | K-Dense-AI/claude-scientific-skills | no | no | Zero-shot time series forecasting with Google's TimesFM foundation model. Use for any univariate time series… |
| `torch-geometric` | linked | K-Dense-AI/claude-scientific-skills | no | no | PyTorch Geometric (PyG) for graph neural networks — node/link/graph classification, message passing (GCN, GAT… |
| `torchdrug` | linked | K-Dense-AI/claude-scientific-skills | no | no | Build and troubleshoot TorchDrug 0.2.1 workflows for molecular graphs, property prediction, self-supervised p… |
| `transformers` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Hugging Face Transformers for loading Hub models, running pipeline inference, text generation, and Trainer fi… |
| `treatment-plans` | linked | K-Dense-AI/claude-scientific-skills | yes | no | Format and structurally validate local treatment-plan documentation after clinical decisions have already bee… |
| `umap-learn` | linked | K-Dense-AI/claude-scientific-skills | no | no | Use UMAP-learn for nonlinear dimensionality reduction, 2D/3D embeddings, clustering preprocessing, supervised… |
| `uncertainty-and-units` | linked | K-Dense-AI/claude-scientific-skills | no | no | Track physical units and propagate measurement uncertainty in scientific calculations using pint and uncertai… |
| `unfreeze` | linked | garrytan/gstack (submodule) | no | no | Clear the freeze boundary set by /freeze, allowing edits to all directories again. (gstack) |
| `usfiscaldata` | linked | K-Dense-AI/claude-scientific-skills | no | no | Query the U.S. Treasury Fiscal Data REST API for federal financial data. No API key required. Use for nationa… |
| `using-tmux-for-interactive-commands` | linked | obra/superpowers-lab | no | no | Use when you need to run interactive CLI tools (vim, git rebase -i, Python REPL, etc.) that require real-time… |
| `vaex` | linked | K-Dense-AI/claude-scientific-skills | no | no | Use this skill for processing and analyzing large tabular datasets (billions of rows) that exceed available R… |
| `venue-templates` | linked | K-Dense-AI/claude-scientific-skills | no | no | Prepare journal manuscripts, conference papers, research posters, and grant documents using venue-specific fo… |
| `video-use` | linked | browser-use/video-use | yes | no | Edit any video by conversation. Transcribe, cut, color grade, generate overlay animations, burn subtitles — f… |
| `what-if-oracle` | linked | K-Dense-AI/claude-scientific-skills | no | no | Run structured What-If scenario analysis with 4–6 branch possibility exploration (best, likely, worst, wild c… |
| `which-skill` | linked | written for this repo | no | no | Use when unsure which of the many installed skills or plugins fits a request. Runs a fast local index search… |
| `windows-vm` | linked | obra/superpowers-lab | no | no | Create, manage, or connect to a headless Windows 11 VM running in Docker with SSH access. Use when the user w… |
| `xlsx` | linked | K-Dense-AI/claude-scientific-skills | no | no | Create, edit, analyze, or convert Excel spreadsheets (.xlsx, .xlsm, .xltx) where the workbook file is the pri… |
| `zarr-python` | linked | K-Dense-AI/claude-scientific-skills | no | no | Chunked N-D arrays for cloud storage (Zarr-Python 3). Compressed arrays, parallel I/O, S3/GCS via fsspec, Num… |

<!-- END GENERATED INVENTORY -->
