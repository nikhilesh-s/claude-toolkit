---
name: google-docs-safe-edit
description: Safely edit existing Google Docs, especially tabbed or concurrently edited documents, using fresh reads, exact targets, revision guards, narrow mutations, and post-write verification.
---

# Google Docs Safe Edit

Use this skill whenever editing an existing Google Doc where preserving unrelated content matters.

## Safe edit protocol

1. **Read fresh immediately before writing.** Fetch the current document or target tab and capture the latest revision ID. Never reuse document indexes from an earlier read after any mutation.
2. **Prefer semantic, exact targets.** Use exact-text search, tab-scoped matches, paragraph ranges, or exact `replaceAllText` when the target is unique. Do not assume a match is unique; verify the tab and occurrence.
3. **Use revision guards.** Supply the freshest `requiredRevisionId` when supported. If the revision changed, re-read, recompute targets, and retry from fresh state instead of reusing stale indexes.
4. **Use raw index deletions only when necessary.** Resolve the exact current range immediately before writing, include the tab ID when supported, and never delete across tab boundaries. When deleting several ranges from one tab in a single batch, apply them from highest index to lowest.
5. **Keep transactions narrow.** Prefer one logical item/block or one tab at a time over a giant cross-document mutation. Re-read after each meaningful batch.
6. **Make edits idempotent.** Check whether the document is already in the desired state. A rerun should not duplicate entries, repeatedly rewrite statuses, or damage content.
7. **Preserve provenance.** Do not silently delete source URLs, original media links, product links, citations, or history fields unless the user explicitly asks. Queue/history records should normally keep their original source even after processing.
8. **Verify after writing.** Re-read the affected tab/region and confirm the intended text changed, unwanted text is gone, neighboring content survived, headings were not concatenated, links remain, and duplicates were not created.

If any target is ambiguous or the safe range cannot be resolved confidently, do not mutate until a fresh read makes the target unambiguous.
