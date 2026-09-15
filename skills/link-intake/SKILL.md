---
name: link-intake
description: Ingest almost any URL (Reel, TikTok, YouTube, article, PDF, Google Doc) with a destination and a one-line instruction, extract only what Nik cares about, and export a lightweight record to the Intake Master Google Doc plus a destination bank. Wraps Media Unlocker; never stores whole media.
---

# Link Intake

Use this skill when Nik pastes a link and says where it should go and what matters about it, or asks to
process a backlog of links. The implementation is code in `apps/link-intake/`; this file only tells you
how to drive it. Do not re-implement classification, media resolution, extraction, or Google writes here.

## The one command

```bash
linkintake ingest <url> --dest <destination> --instruction "<10-15 words>"        # review only
linkintake ingest <url> --dest <destination> --instruction "<...>" --save         # review + save + export
linkintake save <record-id> [--force]                                             # save a reviewed record
linkintake reprocess <record-id> [--instruction "..."] [--dest ...]
linkintake batch tests/urls.txt [--save]      # lines: URL | destination | instruction
linkintake exports | mark-exported <id> --master-url … --destination-url …
linkintake list | show <id> | doctor | config
```

Add `--json` before the subcommand for machine-readable output. Destinations: `wishlist`,
`supplement_ideas`, `design_inspo`, `scholarships`, `personal_ig` (Personal Instagram Inspiration), `inbox`.

## What it does (so you can explain or debug it)

1. **Router** canonicalizes the URL (strips tracking params, normalizes youtu.be/shorts, etc.) and assigns a
   source class: `google_workspace | social_media | video | web_page | direct_file | unknown`. Platform is metadata.
2. **Adapter** builds context: social/direct media via the existing Media Unlocker MCP
   (`unlock_media` → `job_status` → `get_contact_sheet`, see `skills/media-unlocker/SKILL.md`); video via
   yt-dlp metadata + subtitles (no download) plus a contact sheet when visuals matter; web pages via a plain
   fetch; Google Docs/Sheets/Slides via the Google API; PDFs are passed to the model as documents.
3. **Depth** is inferred from source + destination + instruction (visual? transcript? product research?).
   Not exposed in the UI.
4. **Extraction** is one structured-output model call through the `claude` CLI (your Claude login; the
   Anthropic SDK is used instead only if `ANTHROPIC_API_KEY` is set). The instruction is preserved verbatim.
   Output: short summary, 4-6 takeaways (first screen), full focused result, uncertainty, frame-by-frame visual
   notes with approximate timestamps, structured fields (Wishlist/Scholarships schemas; optional shooting fields
   for Personal Instagram Inspiration), and confidence = how well the evidence supports the answer. Stills-only
   evidence must not produce pacing or camera-motion claims; those land in `uncertainty`.
5. **Save** = local canonical record in `~/.link-intake/records/` (always), then media cleanup: heavy files
   of Media Unlocker jobs *this* intake created are deleted; manifest, metadata and contact sheet stay so the
   source can be re-downloaded. The record's `export.status` is `export_pending`.
6. **Google export is Claude's job, not the CLI's.** When you are in a session that has a Google Drive
   connector (check with the connectors list; none is installed as of 2026-09-14), run
   `linkintake --json exports`. Each payload gives you the master row (`master_columns` + `master_row`) for
   the **Intake Master** doc table, the destination target, and a ready `entry_block` (or `scholarship_row`).
   Write them with the connector, using the safe-edit protocol in `skills/google-docs-safe-edit/SKILL.md`,
   then `linkintake mark-exported <id> --master-url <url> --destination-url <url>`. Never re-export a record
   whose status is already `exported`. Without a Drive connector, leave records pending and say so.
   (Optional fallback: `google.export_mode=rest` + `linkintake export <id>` uses the stdlib REST client; it is
   not required and must not pull in gswitch credentials.)
7. **Duplicates**: identity = canonical URL + destination + normalized instruction. Same URL with a
   different intent is a legitimate second record. Exact duplicates need `--force`.

## Rules

- Never edit `apps/media-unlocker/test_wishlist_reels.sh`; it is the Reel regression manifest.
- Never commit cookies, tokens, downloaded media, `~/.link-intake`, `~/.media-unlocker`, or connector hostnames.
- If `linkintake doctor` shows no working LLM backend, tell Nik the fix is
  `CLAUDE_CONFIG_DIR=~/.claude-nebula claude login` and stop; do not fabricate an extraction. Records still
  save locally with `status: needs_review`.
- The Wishlist doc is not restructured: only its Media Queue tab receives staging blocks.
- Prefer reprocessing with a sharper instruction over hand-editing exported docs.

## Raycast

`apps/link-intake/raycast/` is the human front end ("Intake Link"). It calls the same CLI; keep them in sync.
