# Hyperframes Composition Brief: claude-toolkit

## Objective
Short launch-style brag video for claude-toolkit, a dotfiles repo tracking one dev's Claude Code setup.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 20 seconds

## Source Material
- Project root: `~/claude-toolkit`
- Primary files read: README.md (no index.html/styles.css — this is a dotfiles repo, not a site)
- Product name: claude-toolkit
- Tagline / strongest claim: 175 skills, 72 plugins, tracked from one README
- Key moment recreated: the terminal itself — typed commands, a stat count, a real diff from this session's own git history (the gstack vendoring bug: -376,132 / +126)
- Copy that must appear verbatim: `175`, `72`, `git push`, `main → main`

## Creative Direction
- Tone preset: yc-parody
- Creative direction: fake startup metrics slide, delivered completely straight, about a personal dotfiles repo
- Angle: total seriousness about a README file
- Hook: `$ ls skills | wc -l` → `175` slams in
- Outro: "my Claude Code setup got a little out of hand."

## Visual Identity
- Background: `#0d1117` (GitHub dark)
- Text: `#e6edf3`
- Accent: `#39d353` (terminal green)
- Font: monospace throughout (JetBrains Mono)

## Storyboard
1. Hook — 3s — command types, `175` slams in
2. Stat reveal — 5s — 3 cards arrive one by one: skills / plugins / README
3. The fix — 5s — real diff from this repo's git history, red strike then green land
4. Ship it — 4s — `git push` types, `main → main` confirms
5. Outro — 3s — punchline types, title card fades in

## Audio
- Role: sparse, motion-matched accents over a thin restrained synth bed
- Music: `happy-beats-business-moves-vol-10-by-ende-dot-app.mp3` (bundled, instrumental)
- Beat-locked: 2.9s (hook slam), 9.29s (diff fix) — off the track's own beat grid
- Beat-grid: stat cards at 3.55s / 4.64s / 5.74s
- SFX: pop on each reveal, one confirm chime on `git push`

Built directly against the hyperframes-core contract (standalone root, one paused GSAP timeline, declarative per-hit `<audio>` elements). `npx hyperframes check` passed clean before render.
