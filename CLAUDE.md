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
- The web UI is the tactical board (`templates/board.html`, served raw at
  `/`): the model drives evidence panels with inline `[[SHOW:MANUAL|PAGE]]` /
  `[[CLEAR]]` directives (executed server-side, validated against the index,
  stripped from display), and voice replies speak a brief — never a spec
  number; specs go on the board. Full contract and shipped state:
  [VOICE_WHITEBOARD_DESIGN.md](VOICE_WHITEBOARD_DESIGN.md).
- Chunking splits at work-package boundaries, never page counts; preserve manual number, printed page number, WP/paragraph in metadata; every chunk carries a tier tag.
- SQLite + local embeddings; no heavy infrastructure.
- Downloaded TM PDFs and generated page images/OCR output live under `corpus/` and are gitignored (large binaries); the ingest scripts and metadata schemas are committed.
- Intake sessions log to JSON (no work-order system in POC).
- No Facebook scraping automation, ever. Forum crawling respects robots.txt/ToS.

## Export control and document acquisition

Distribution Statement A material is published information and outside the EAR ([15 CFR 734.7](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-734/section-734.7)) — the entire A0 corpus is this, and needs no handling restrictions. Unarmored FMTV maintenance data that is *not* public-release is EAR ECCN 0E606, not ITAR (USML Category VII covers armored/armed combat vehicles; Note 1 routes other ground vehicles to ECCN 0A606).

- **No community document intake exists, and none should be reintroduced.** The public A1 documentation request, the Dropbox file request, the GitHub-issue transfer fallback, and the earlier encrypted path were all removed (July 2026). A1-series documents are pursued through a FOIA request to TACOM instead (see `foia/`, local-only); FOIA-released records are public releases and corpus-eligible.
- **Restricted material is never handled.** Anything with a Distribution B–F statement, a CUI marking, or an export warning stays out of the corpus, the repo, releases, issues, and PRs.
- Owner-held restricted or copyrighted docs (Cat/Allison/WABCO) stay local: never committed, never in a release, never attached to an issue or PR. Publishing *is* the export, and GitHub attachment URLs survive issue deletion.
- Never solicit material on the basis of contributor anonymity — a documentation request must not read as encouraging anyone to defeat attribution or breach their own obligations.
