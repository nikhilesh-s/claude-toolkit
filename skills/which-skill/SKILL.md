---
name: which-skill
description: Use when unsure which of the many installed skills or plugins fits a request. Runs a fast local index search instead of reasoning over the full catalog. Trigger on "is there a skill for X", "which skill handles X", or an unfamiliar/specialized request that might already have a dedicated skill.
---

# which-skill

Find the right skill fast, without scanning the whole catalog by hand.

## Steps

1. Pick 2 to 4 keywords from the request. Use nouns, not filler words.
2. Run:
   ```bash
   ~/claude-toolkit/scripts/which-skill.sh <keyword> <keyword> ...
   ```
3. Read the top 1 to 3 results. Each line shows: kind (skill or plugin), name,
   source, description.
4. If a result is a strong match, use it directly:
   - A `skill` result: call `Skill(<name>)`.
   - A `plugin` result: its individual skills already appear in your
     available-skills list, under that plugin's namespace. Invoke the
     specific one that matches, not the plugin as a whole.
5. If nothing scores well, say so. Do not guess a name that did not appear
   in the results.

## Keep the index fresh

After you install or remove a skill or plugin, regenerate the index:
```bash
cd ~/claude-toolkit && uv run python scripts/build_skill_index.py > scripts/skill_index.tsv
```

## Why this exists

Claude Code loads every installed skill's name and description into context
on every turn. This skill does not shrink that list — a skill file cannot
control what the harness auto-loads. What it saves is the cost of reasoning
over that list by hand for an unclear request: one grep-based lookup,
instead of scanning many descriptions in turn.
