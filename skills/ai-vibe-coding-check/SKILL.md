---
name: ai-vibe-coding-check
description: Detect and fix the visual/copy tells that make a site look AI-generated ("vibe-coded"). Scans code and rendered pages for 30 known tells — purple-black palettes, harsh gradients, glassmorphism, bento grids, sparkle icons, em-dash copy, "it's not X, it's Y" lines, fake testimonials, missing legal pages — and reports each with file:line evidence plus a concrete replacement. Use when the user says "/ai-vibe-coding-check", "does this look vibe coded", "make this not look AI generated", "de-slop this site", or before shipping any AI-assisted frontend.
---

# ai-vibe-coding-check

Find the tells that scream "AI made this", with evidence, and propose specific
fixes. Source: "30 reasons your site looks vibecoded" (aj.on.ai, Instagram
2026), turned into verifiable checks.

A tell is not automatically a bug — a deliberate, consistent design choice can
keep any of these. Flag it, say why it reads as AI-default, and let the user
decide. The failure mode is the *combination*: five or more tells together is
the vibe-coded look.

## How to run

1. Locate the styling ground truth: global CSS/tokens, tailwind config, the
   main layout, landing page, and marketing copy files.
2. Check each tell below via grep/read. If a browser tool is available, also
   screenshot the rendered page — some tells (radial orbs, glass) only show
   rendered.
3. Score: count of tells found. 0–2 fine · 3–5 noticeable · 6+ vibe-coded.
4. Report FOUND items with file:line + fix; then the score; then the top 5
   fixes by visual impact. Offer to apply fixes — don't restyle unasked.

## The 30 tells

**Color & surface**
| # | Tell | Detect | Fix direction |
|---|---|---|---|
| 1 | Harsh gradients | `linear-gradient` with saturated multi-hue stops on heroes/buttons | One brand hue, subtle or none |
| 2 | Default Lucide icons | `lucide-react` imports everywhere, stock stroke icons | Custom set, or fewer icons entirely |
| 3 | Pure white background | `#fff`/`bg-white` as page ground | Slight tint (warm gray, off-white) |
| 4 | Rainbow coloring | >3 accent hues across sections | One accent + neutrals |
| 5 | Drop shadows on everything | `box-shadow`/`shadow-*` on most cards | Borders or spacing for separation |
| 8 | Liquid glass | `backdrop-filter: blur` + translucent fills | Solid surfaces |
| 19 | Same soft corner radius | one `rounded-xl`-ish value on every element | Vary by element role, or sharpen |
| 20 | Purple and black | violet/indigo accents on near-black — the default AI palette | Literally any other palette |
| 22 | Radial orbs | blurred radial-gradient glow blobs behind heroes | Remove; real content instead |
| 23 | Dot grids | dotted/grid background patterns | Plain ground |
| 29 | Neon colors | high-saturation cyan/magenta/green accents | Desaturate |
| 30 | Default pastel set | untouched pastel token palette | Derive palette from brand/content |

**Layout & components**
| # | Tell | Detect | Fix direction |
|---|---|---|---|
| 6 | 3 feature cards in a row | `grid-cols-3` feature sections | Uneven layouts, real screenshots |
| 11 | Colored left-stripe cards | `border-l-4 border-<accent>` callouts | Full border or none |
| 13 | Bento grids | mixed-span "bento" showcase grid | Only if content genuinely fits it |
| 14 | Fake terminal window | decorative macOS-dots terminal with `npx ... init` | Show the real product |
| 16 | Checkmark bullet lists | ✓-prefixed feature lists | Prose, or real spec table |
| 17 | Exactly 3 pricing tiers | Starter/Pro/Enterprise with middle highlighted | Price from actual segmentation |
| 18 | No real product demos | screenshots absent or mocked | Real screenshots/recordings |
| 21 | No skeleton loaders | spinners or nothing while loading | Skeletons matching layout |
| 25 | Animated arrows | bouncing scroll arrows, arrow-on-hover links | Cut them |
| 28 | Hover animations everywhere | `hover:scale-*`, lift-on-hover on every card | Reserve motion for primary actions |

**Copy & trust**
| # | Tell | Detect | Fix direction |
|---|---|---|---|
| 7 | Emojis as UI | 🚀✨💡 in headings/features | Icons with meaning, or text |
| 9 | Em dashes everywhere | ` — ` density in marketing copy | Shorter sentences |
| 10 | Inter/Geist/Space Grotesk | the 3 default AI fonts in config | Any deliberate type choice |
| 12 | Fake testimonials | invented names/companies/avatars | Remove — real quotes or nothing (legal risk too) |
| 15 | "It's not X, it's Y" | grep copy for the pattern; also "Everything, everywhere", "X, reimagined" | Say what the product does |
| 24 | Sparkle icons | ✨/`Sparkles` icon marking "AI features" | Name the feature |
| 26 | No terms of service | `/terms` missing | Add TOS page |
| 27 | No privacy policy | `/privacy` missing | Add — legally required if collecting data |

## Report format

```
# ai-vibe-coding-check — <project> — <date>
Score: 9/30 tells — vibe-coded range

## FOUND
1. [#20] Purple-on-black palette — tailwind.config.ts:14 `violet` accent, `zinc-950` ground. Fix: ...
...
## TOP 5 FIXES BY IMPACT
...
## CLEAN
#12 testimonials are real (linked LinkedIn) · #17 single price ...
```

Overlap note: #26/#27 also appear in `final-check` Part B — run both before
launch; this skill covers the look, final-check covers readiness. For a full
rewrite of AI-sounding prose, hand copy findings to `humanizer` or `ste-writing`.
