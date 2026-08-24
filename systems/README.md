# Systems Document

Everything that makes our Macs ours: apps, custom systems, AI tooling, automations, input setups, configs. One markdown file per item. This is the source of truth — Google Docs and content scripts derive from here.

## Layout

- `nik/` — Nik's systems (Nikhilesh Suravarjjala)
- `arnau/` — Arnau's systems (Arnav Kakani)
- `shared/` — things we both run (gswitch, toolkit sync, conventions)
- `inbox/` — raw captures: links, reels, app ideas. Claude classifies these into entries later.
- `inspo/` — design inspiration (images, links)

Each person edits only their own folder plus `shared/`. Repos sync daily (Nik's origin ↔ Arnau's upstream), so keeping lanes separate means zero merge conflicts.

## Entry format

```yaml
---
name: Thaw
type: tool          # tool | config | workflow | system
status: unknown     # daily | active | trying | queued | retired | unknown
why: what problem it solves, in one line
setup: how to get it on a clean Mac
backup: where it survives losing the Mac (account / iCloud / this repo / local-only)
---
Free-form notes below.
```

## Status meanings

- **daily** — core setup, the stuff we explain to friends and make content about
- **active** — installed and used, not daily
- **trying** — testing, verdict pending
- **queued** — want to try, not installed yet
- **retired** — used to use it; kept for history, never deleted
- **unknown** — auto-audited stub, not yet interviewed

## Workflow

1. Claude audits the Mac → stubs with `status: unknown`
2. Human answers short interview batches → stubs become real entries
3. New finds go to `inbox/` → Claude files them
4. `MIGRATION.md` gets generated from `setup:` fields once entries stabilize
