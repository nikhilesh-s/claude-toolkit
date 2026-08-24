# Systems Document — Origin & Plan (chat log, 2026-08-22/23)

Record of the planning conversation between Nik and Claude that created this `systems/` directory. Kept so future sessions (and Arnau) have full context without the original chat.

---

## 1. Nik's brief (voice-dictated, condensed)

- Nik (Nikhilesh Suravarjjala) and Arnau (Arnav Kakani) work together; both have Claude toolkits with synced GitHub repos. VoiceOS typos: "Arnab" = Arnav, "Nick" = Nik.
- Goal: a **system document** capturing everything that makes their Macs theirs — apps (Thaw, Vorssaint, Shottr, Unsplash Wallpapers…), custom-built systems (G-Switch on Google Cloud), Claude Skills Toolkit, GPT automations, reminders automations, keyboard macros, small settings.
- End goals:
  1. **Migration**: on a new Mac/phone, unleash Claude or Codex on the repo to set everything up (or checklist what to do manually).
  2. **Explainability**: top layer = the stuff used all the time, explainable to friends, usable by others.
  3. **Content**: eventually YouTube videos, reels, maybe a podcast based on the document.
- Requirements Nik stressed:
  - Nik and Arnau have distinct lives — different browser profiles, different dev/design apps. Document must keep them separate.
  - Doubles as a **design inspiration board** — drag-drop links/photos.
  - A way to **queue reels/links** for later ingestion, with a pipeline that unpacks each item and files it in the right place.
  - Captures everything: tools both use, browser profiles to create, project ideas, startup ideas.
  - Reliability and longevity are the top priority; GitHub preferred alongside/over Google Docs.
  - **Minimal human effort**: Claude does the most; humans only answer questions about what apps they use, opinions, settings. Expect frequent archiving — need good layering: (a) queue of things to try, (b) migration pipeline for current setup, (c) top layer of daily-driver systems.

## 2. ChatGPT's original proposal (Nik pasted it in)

One Google Doc with tabs + nested tabs: 00 Start Here / 01 Applications / 02 Custom Systems / 03 AI Environment / 04 Automations / 05 Input System / 06 macOS Configuration / 07 Development Environment / 08 Browser System / 09 File-Information System / 10 Backup & Recovery / 11 New Mac Migration / 12 Wishlist-Experiments-Retired. A 17-field template per item (name, type, purpose, frequency, importance, location, install source, dependencies, configuration, permissions, data, secrets, setup, verification, backup, automation, screenshots, notes). Four conceptual classes: Tool / Configuration / Workflow / System. Start with an "audit inbox" dump, Google Docs now, GitHub later, ending with a `nik-mac/` repo and a Codex bootstrap instruction.

## 3. Claude's corrections to that plan

- ChatGPT designed for **one person, Google Doc first**. Nik+Arnau are **two people with an already-synced GitHub repo** (daily launchd sync job). So: **repo is source of truth from day one**; Google Doc only as a capture inbox / inspo board (drag-drop from phone), ingested into the repo on a schedule — never holding truth.
- Structure lives inside the existing `claude-toolkit` repo (no new repo — sync already solves the two-Mac problem):

  ```
  systems/
  ├── nik/      # Nik's apps, configs, macros, browser profiles
  ├── arnau/    # Arnau's
  ├── shared/   # gswitch, toolkit conventions, shared workflows
  ├── inbox/    # raw dumps + auto-ingested reels/links
  └── inspo/    # design inspiration
  ```

- Entry schema trimmed from 17 fields to 6: `name, type (tool|config|workflow|system), status, why, setup, backup`. Extra fields get added only when the migration doc actually needs them.
- **`status` is the layering**: `daily | active | trying | queued | retired | unknown`. "Explain to friends" view = everything `daily`. Migration doc = generated from `setup:` fields. Archive = `retired`, never deleted. Google-Doc tab hierarchy replaced by repo folders.

## 4. Division of labor

- **Claude does**: Mac audits, draft stub entries, regenerate indexes, weekly inbox classification, eventual MIGRATION.md + Brewfile generation.
- **Nik + Arnau do only**: answer short interview batches (~10 min: "Atoll — what is it, daily or dead?"), drag items into the inbox, glance at commits.

## 5. Execution order

1. **Done (2026-08-22)** — Claude scanned Nik's Mac: /Applications, login items, LaunchAgents, Homebrew, Shortcuts, cron, editor extensions, toolkit repo. Result: `nik/AUDIT-2026-08-22.md`.
2. **Done (2026-08-23)** — this branch: `systems/` scaffold, 41 stub entries for Nik, real entries for shared systems (gswitch, toolkit-sync), Arnau onboarding README with the exact audit prompt for his Claude.
3. **Interview passes** — Claude batch-asks 8–10 questions per sitting until `unknown` stubs are resolved. First batch queued: Atoll, eden, Vorssaint, finetune, Glaido LaunchAgent, Maccy-vs-Paste duplication, EPOMAKER macro list, Steam login item.
4. **Inbox pipeline** — one Google Doc "Inbox" (phone drag-drop works), scheduled Claude job reads it via workspace-mcp/gswitch, files each item (queued app idea / inspo image / reel link), clears the doc. Until then: `systems/inbox/INBOX.md`.
5. **Later, once entries stabilize** — generate MIGRATION.md + Brewfile; content scripts (YouTube/reels/podcast) pull from `daily` entries.

## 6. How the two repos combine

- Nik's repo: `nikhilesh-s/claude-toolkit` (origin). Arnau's repo: `ArnavKakani/claude-toolkit`, wired as read-only `upstream`.
- `claude-toolkit-sync` launchd job merges Arnau's main twice daily (hardened Aug 2026 for unrelated histories / hardcoded-path conflicts).
- Per-person folders mean the two never edit the same files, so syncs never conflict. Once this branch merges to main, the structure flows to Arnau; his audit entries flow back on the next sync.

## 7. Audit summary (Nik's Mac, 2026-08-22)

Full raw scan in `nik/AUDIT-2026-08-22.md`. Highlights: ~39 apps; login items Raycast, Paste, Steam, VoiceOS, SuperCmd, Warp, Shottr, ScreenZen, Notion, Dia; custom LaunchAgents gswitch, gswitchmenu, claude-toolkit-sync, Glaido(?); ~200 Claude skills (scientific-agent-skills pack, gstack suite, superpowers, custom); Cursor with 3 extensions; no cron jobs or macOS Shortcuts found; open questions listed in §5 step 3.
