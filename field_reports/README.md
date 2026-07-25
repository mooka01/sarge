# Field Reports — Tier 3 (anecdotal)

Manually captured posts from Facebook groups and other closed communities.
**No scraping automation, ever** (platform ToS + PROJECT_BRIEF.md §5). Capture
by hand: screenshot the post, save the text, note where it came from.

One report per folder:

```
field_reports/
  2026-07-21-slow-buildup-governor-line/
    report.md        <- the template below, filled in
    screenshot-1.png <- optional images
```

`report.md` template:

```markdown
---
captured: 2026-07-21
source: Facebook group "FMTV Owners" (manual capture)
vehicle: M1083A1, 3126E, ~12k mi
symptom-tags: slow-buildup, governor
---

## What they reported
(paraphrase or quote the post)

## What fixed it (per the poster)
(their claimed fix — unverified)

## Assessment
(does it apply to our as-built config? anything contradicting Tier 1?)
```

These are **hints only**. They never supply specs or procedures, and anything
promising must be verified against the TM before acting on it. A future ingest
pass can index these folders with tier=3 tags.
