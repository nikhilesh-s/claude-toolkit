# Plan: second-brain command

Source: metakaihos reel (Instagram, 2026-08) — a cautionary tale, not a recipe.
Its actual lesson: Claude Code + Obsidian + many skills produces thousands of
unorganized files; ideas never resurface; the AI always agrees; you hoard
articles you never use. So the command to build is not "capture more" — it is
**resurface and prune**.

## What to build

A `second-brain` skill that manages a single Obsidian-compatible vault with
three verbs:

1. `capture` — one inbox note per item (idea, link, article), frontmatter:
   `type`, `project`, `captured`, `status: inbox`. No folder taxonomy beyond
   `inbox/`, `notes/`, `archive/` — tags and links over hierarchy.
2. `resurface` (the core, per the reel's "DAILY RESURFACE" screen) — on run:
   pick 3–5 stale-but-relevant notes (match to active projects by tag/link;
   staleness = not touched in N days), show them, and force a decision per
   note: use (link into a project note), keep (snooze with a date), or archive.
   No decision = it counts as hoarding and gets said out loud.
3. `prune` — weekly: list notes never linked and never resurfaced-used;
   propose archive. Report vault stats (total, inbox age, orphan ratio) so
   growth is visible.

Anti-sycophancy rule baked into the skill prompt: when the user files yet
another article into a topic with >10 unused notes, say so instead of praising
the capture.

## Deliberately not building

- No new note format, no plugin ecosystem, no Hermes-style completion system —
  the reel shows exactly this collapsing under its own weight.
- No auto-summarize-everything pass (cost, and it removes the reading signal).
- No sync/DB; plain markdown files in one vault dir, git for history.

## Steps when green-lit

1. Ask for vault path (or create `~/second-brain`).
2. Write `skills/second-brain/SKILL.md` with the three verbs + report formats.
3. Optional: schedule `resurface` as a morning cron via the schedule skill.
4. Symlink into both config homes; README row + regen categories.

Effort: one session. Depends on nothing new.
