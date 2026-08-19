# Plan: vibe-coded video editing plugins

Source: tewiemakesmedia reel (Instagram, 2026-08) — DaVinci Resolve timeline
("FMTY FILM CHAL" project) running custom vibe-coded effects: glitch/datamosh,
pixel-mosaic, film grain B&W, picture-in-picture echo/zoom cascades.

## What the reel implies technically

Resolve effects plugins come in three buildable forms, cheapest first:
1. **DCTL** (DaVinci Color Transform Language) — single `.dctl` file, GPU
   color/pixel shader. Perfect for grain, pixelation, glitch color math.
   Drop into `LUT/DCTL` folder, no build step. Start here.
2. **Fuse** (Lua, Fusion page) — single `.fuse` file, full compositing node:
   PiP echo, displacement, time effects. No compiler needed either.
3. **OpenFX (C++)** — full plugin API, needed only for effects that read
   multiple frames with custom UI. Real build infra; do last, if ever.

## What to build

A `resolve-fx` skill (command: `/resolve-fx <effect description>`) that:
1. Asks which effect + target (DCTL vs Fuse, chosen by the rules above —
   pixel/color math = DCTL, layout/time = Fuse).
2. Generates the file from templates in `references/` (ship 4 seed templates
   matching the reel: `glitch.dctl`, `mosaic.dctl`, `grain.dctl`,
   `echo-pip.fuse`).
3. Installs to the Resolve user folder
   (`~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/`
   subdirs on macOS), tells the user where it appears in the UI.
4. Iterates: user describes what looks wrong, skill edits parameters/code.

Verification loop: Resolve has a scripting API (Python, `DaVinciResolveScript`)
— the skill can load a test project and render one frame to confirm the plugin
loads without a crash. Ship that as a smoke script, not a test suite.

## Prerequisites / risks

- Requires DaVinci Resolve installed (free version supports DCTL only in
  Studio for some GPU features — check at runtime, warn honestly).
- Effects quality is taste-driven; the loop matters more than the templates.
- Premiere/After Effects out of scope (different ecosystems entirely).

## Steps when green-lit

1. Confirm Resolve version installed (`ls /Applications/DaVinci Resolve*`).
2. Write the 4 seed templates and test each loads in Resolve by hand once.
3. Write `skills/resolve-fx/SKILL.md` + `references/` with the templates.
4. Symlink both homes; README row + regen categories.

Effort: 1–2 sessions (template validation is the slow part).
