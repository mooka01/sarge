# M1083A1 Service Bay

Owner-technician diagnostic and reference system for a 2003 M1083A1 FMTV truck.
Full design rationale and POC spec: [PROJECT_BRIEF.md](PROJECT_BRIEF.md). Read it before making architectural decisions.

## Governing rule (non-negotiable)

The applicable technical manual and actual measurements are authoritative. AI interpretation is advisory. This is enforced architecturally:

- Specs, torques, procedures, and safety steps come ONLY from Tier 1 sources (TMs, RPSTL, Cat/Allison docs, measured data).
- Numeric specs always resolve to the original **page image**, never OCR text.
- Part numbers are never trusted without confirmation from the RPSTL page image or a supplier listing.
- Never state a spec value in output without a page-image citation. If it isn't in the indexed corpus, say so — do not fill the gap from model knowledge.

## The vehicle — as-built deviations matter

Canonical dossier: [AS_BUILT_CONFIGURATION.md](AS_BUILT_CONFIGURATION.md). Key deviation: **Eco-Hub / direct-drive conversion — stock geared reduction hubs are REMOVED.** Stock TM figures for wheel torque, effective gearing, grade performance, shift behavior, and hub service do NOT apply as printed. Always cross-check analysis against the as-built dossier.

## Conventions

- POC scope: air system vertical slice only (see brief §6). Don't build wide.
- Chunking splits at work-package boundaries, never page counts; preserve manual number, printed page number, WP/paragraph in metadata; every chunk carries a tier tag.
- SQLite + local embeddings; no heavy infrastructure.
- Downloaded TM PDFs and generated page images/OCR output live under `corpus/` and are gitignored (large binaries); the ingest scripts and metadata schemas are committed.
- Intake sessions log to JSON (no work-order system in POC).
- No Facebook scraping automation, ever. Forum crawling respects robots.txt/ToS.
