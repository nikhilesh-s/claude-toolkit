---
name: final-check
description: Pre-launch audit for a web app or site. Runs a 40-point checklist — 20 security items (secrets, auth, injection, headers, dependencies) and 20 site-content items (404 page, CTAs, SEO metadata, legal pages, analytics) — against the actual codebase, with file:line evidence for every finding. Use when the user says "final check", "/final-check", "pre-launch check", "is this ready to launch/ship/deploy", or asks to audit an app before going live.
---

# final-check

Audit a project before launch. Verify each item against the real code — never
assume, never report a pass without evidence. Sources: two launch checklists
(millee.md and yatesvids, Instagram 2026) merged and made verifiable.

## How to run

1. Detect the project type first (5 min max): web app with backend, static
   site, API only, or something else. Skip whole sections that cannot apply
   and say so — an API has no "sticky mobile CTA". N/A is a valid verdict;
   an unverifiable item is reported as UNKNOWN, never silently passed.
2. For each applicable item, find evidence: a `file:line`, a config value, a
   dependency entry, or command output. One grep beats an opinion.
3. Output a report in three blocks: **FAIL** (with fix, ordered by risk),
   **UNKNOWN** (what to check by hand), **PASS/N-A** (one line each).
4. Offer to fix the FAILs, highest risk first. Do not auto-fix without asking.

## Part A — Security (items 1–20)

| # | Item | How to verify |
|---|---|---|
| 1 | No API keys in client code | grep client bundles/src for `sk-`, `key=`, `apiKey` literals; keys only in server env |
| 2 | No secrets in git history | `git log -p --all -S` for known key patterns, check `.env` never committed; recommend gitleaks/trufflehog if present |
| 3 | Only publishable/public DB keys client-side | Supabase/Firebase: anon/public key in client, service key server-only |
| 4 | Row-level security enabled | Supabase: RLS policies exist per table; Firebase: security rules not `allow read, write: if true` |
| 5 | Sensitive data encrypted at rest | PII columns/fields: check for plaintext storage of tokens, SSNs, health data |
| 6 | Auth checks server-side | Every mutating route/handler re-checks session/role; client-only guards = FAIL |
| 7 | Record access scoped to owner | Queries filter by user id from the session, not from request params (IDOR) |
| 8 | Field tampering blocked | Mass-assignment: allowlist of updatable fields; `role`, `price`, `isAdmin` not client-settable |
| 9 | Session cookies secure | `httpOnly`, `secure`, `sameSite` set on session cookies |
| 10 | Passwords hashed | bcrypt/argon2/scrypt, never md5/sha1/plaintext; or auth fully delegated |
| 11 | Login rate-limited | Rate limiter on auth endpoints (middleware, Redis counter, or platform-level) |
| 12 | Bot protection on public forms | CAPTCHA/turnstile/honeypot on signup, contact, comment forms |
| 13 | Queries parameterized | No string-built SQL; ORM or placeholders everywhere; grep for template literals feeding query calls |
| 14 | All input validated | Schema validation (zod/joi/pydantic) at API boundaries |
| 15 | User content escaped | No `dangerouslySetInnerHTML`/`innerHTML`/`v-html` with user data unless sanitized |
| 16 | File uploads restricted | Type + size checks server-side, stored outside web root or in object storage |
| 17 | API responses trimmed | No password hashes, tokens, or internal fields in JSON responses; explicit select/serializer |
| 18 | Security headers set | CSP, `X-Content-Type-Options`, `X-Frame-Options`/`frame-ancestors`, `Referrer-Policy` |
| 19 | HTTPS forced | Redirect or HSTS at host/middleware level |
| 20 | Dependencies scanned | Run `npm audit`/`pip-audit`/`cargo audit`; report criticals |

## Part B — Site content & SEO (items 21–40)

Skip this whole part for API-only projects.

| # | Item | How to verify |
|---|---|---|
| 21 | Custom 404 page | 404 route/page exists and links back home |
| 22 | CTA above the fold | Landing page has a visible action before scroll |
| 23 | Internal links between pages | Pages cross-link; no orphan pages |
| 24 | Thank-you page after forms | Form submit lands on confirmation (also enables conversion tracking) |
| 25 | Breadcrumbs on deep pages | Multi-level sites only |
| 26 | Case studies / proof of work | At least one concrete example, not lorem ipsum |
| 27 | FAQ section (~5 questions) | Real questions, ideally with FAQ schema |
| 28 | Response-time promise | Contact page states when users hear back |
| 29 | Sticky mobile CTA | Action reachable on mobile without scrolling back up |
| 30 | robots.txt | Exists, does not block the whole site, points at sitemap |
| 31 | Unique page titles | `<title>` per page, no duplicates |
| 32 | Meta descriptions | Per page, unique, non-empty |
| 33 | Social share image | `og:image` + `twitter:card` set and file exists |
| 34 | Maps + directions | Local/physical business only |
| 35 | Real reviews/testimonials | No fabricated ones — fabricated testimonials are also a vibe-coding tell |
| 36 | Alt text on images | Meaningful `alt` on content images |
| 37 | Local business schema | JSON-LD if local business; skip otherwise |
| 38 | Privacy policy page | Exists and linked in footer — legally required if any data is collected |
| 39 | Analytics installed | GA4/Plausible/PostHog snippet or SDK present |
| 40 | Real team/owner photo | Humans build trust; stock photos are a tell |

## Report format

```
# final-check — <project> — <date>
Type: <web app / static site / API> · Items run: N of 40 (M skipped as N/A)

## FAIL (fix before launch)
1. [S6] Auth check client-side only — src/api/orders.ts:41 trusts `req.body.userId`. Fix: read user from session.
...

## UNKNOWN (verify by hand)
- [S5] Can't confirm encryption at rest — DB is remote. Check provider settings.

## PASS / N-A
[S1] no client-side keys · [S19] HSTS via Vercel · [B34] N/A not a local business ...
```

Related: run `ai-vibe-coding-check` after this for design/copy slop; `security-review` for a deeper security-only pass.
