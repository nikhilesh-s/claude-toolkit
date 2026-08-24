---
name: college-wishlist-media
description: Turn social-media product links into evidence-backed College Wishlist entries by combining Media Unlocker with safe Google Docs editing while permanently preserving each original source URL.
---

# College Wishlist Media

Use this skill for Nik's College/Dorm Wishlist when a social-media link, Reel, short video, or other media item should be added, identified, or processed.

## Dependencies

Read and follow:
- `skills/media-unlocker/SKILL.md`
- `skills/google-docs-safe-edit/SKILL.md`

The default wishlist is the existing Google Doc:

`https://docs.google.com/document/d/17W59ZIgOeFVw3Wk-I1n8Jfjd_kcJ77GFqR9-tn3gW5Q`

Tabs:
- Overview: `t.0`
- Clothing & Shoes: `t.xh7ixeaejgb`
- Bags & Everyday Carry: `t.iwz5g1nis9c2`
- Dorm & Bedding: `t.2ba4or5py3vq`
- Desk, Tech & School: `t.euqgognqrl8d`
- Daily Essentials: `t.utp2lvg2x8mv`
- Decor & Extras: `t.qanldrldy2nc`
- Media Queue: `t.8rdi8wnl84he`

## Intake workflow

1. **Preserve the source first.** Add every new media URL to Media Queue immediately as the next queued item with `Status: Unprocessed`. Never remove the original source URL later.
2. **Unlock the media.** Use Media Unlocker: `unlock_media(url)` → `job_status(job_id)` when useful → `get_contact_sheet(job_id)`. Reuse an existing valid cached job/contact sheet instead of redownloading.
3. **Inspect before identifying.** Visually inspect the media/contact sheet. Use visible logos, text, labels, packaging, model numbers, distinctive design, color, and hardware as evidence.
4. **Research only to resolve evidence.** If exact identification is not obvious, do targeted web research from visible clues. Prefer official manufacturer pages and reputable retailers. Do not pick a vaguely similar model.
5. **Use confidence conservatively.** Never invent an exact model, colorway, size, dimensions, material, or price. If the product is recognizable but the exact model is not supported, use a descriptive name plus `exact model TBD`.
6. **Queue-only when uncertain.** If the product cannot be identified with reasonable confidence, leave it in Media Queue as `Status: Unprocessed — identification uncertain`. Do not add an uncertain item to Overview or a category tab.
7. **Update confirmed items safely.** For a confirmed item, use the Google Docs safe-edit protocol. Add/update one canonical item in the correct category tab and Overview, retain the original media URL as a source, and update the queue status to `Processed — <product>`.
8. **Replacement only when explicit.** Never infer that a new item replaces an existing wishlist item. Replace only when the user explicitly says so. When replacing, update the existing canonical item rather than creating a duplicate.
9. **Deduplicate exact matches only.** If the exact same product already exists, enrich that entry and preserve the new media URL as an additional source. Do not merge merely similar products.
10. **Verify after every write.** Re-read every modified tab plus Media Queue. Confirm the source URL remains, there is exactly one canonical item, uncertain items are queue-only, and no unrelated wishlist content changed.

## Category mapping

- **Clothing & Shoes:** clothing, jackets, pants, shoes, wearable items
- **Bags & Everyday Carry:** backpacks, totes, wallets, organizers, EDC accessories
- **Dorm & Bedding:** bedding, pillows, blankets, dorm storage tied to room/bed setup
- **Desk, Tech & School:** laptops, headphones, chargers, desk equipment, school/productivity gear
- **Daily Essentials:** water bottles, hygiene, personal daily-use items
- **Decor & Extras:** lighting, room decor, aesthetic accessories, miscellaneous extras

Prefer the closest existing category instead of creating a new tab unless the user explicitly wants a new category.

## Provenance rule

The Media Queue is permanent history. Processing changes the status; it does not destroy the original link. Processed category entries should also retain their source Reel/media URL whenever practical.

If Media Unlocker or Google Docs write access is unavailable, do not guess or fabricate completion. Preserve/return the pending source and clearly state the blocked step.
