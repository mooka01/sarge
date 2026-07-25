# SARGE — Project Brief & Design Rationale

Founding design brief, written before implementation. Records the analysis
behind the architecture so later decisions can be checked against it.
(Original working title: "M1083A1 Service Bay.")

---

## 1. Mission

Build an owner-technician diagnostic and reference system for a 2003
M1083A1 FMTV truck. The system helps the owner find authoritative
information fast, diagnose faults with professional discipline, and
document all work — without ever letting an AI model become the authority.

**Governing rule:** The applicable technical manual and actual measurements
are authoritative. AI interpretation is advisory. This rule is enforced
*architecturally*, not just by prompting.

## 2. The Vehicle (As-Built Context)

- 2003 M1083A1 FMTV
- Cat 3126E engine
- Allison MD3070PT transmission
- 2.97:1 axle ratio
- **Eco-Hub / direct-drive conversion** — stock geared reduction hubs
  REMOVED. Any analysis touching wheel torque, driveline loading, effective
  gearing, grade performance, shift behavior, or hub service must account
  for this.
- CTIS retained
- Owner preference: retain stock axle, brakes, suspension, CTIS where
  practical; reversible, minimally invasive modifications.
- Full as-built dossier is maintained as `AS_BUILT_CONFIGURATION.md` — the
  single canonical copy lives in this repo; all copies elsewhere are dated
  exports.

## 3. Architecture

Three layers:

### 3.1 Structured Intake (web front end)
- Form-driven diagnostic intake; no free-text "truck won't start" allowed.
- Fields: complaint category, symptom description, onset,
  intermittent/constant, conditions (engine temp, ambient, RPM, air
  pressure, battery voltage), warning lights/codes, recent work, what still
  works, measurements taken (with meter lead locations and test
  conditions), photo uploads.
- Form is adaptive: complaint category surfaces relevant measurement fields.
- As-built profile is auto-stamped onto every session.

### 3.2 Tiered Retrieval Backend
Authority is enforced by source tiering. Every indexed chunk carries a tier
tag.

| Tier | Sources | Authority |
|------|---------|-----------|
| 1 — Controlling | OCR'd TMs, RPSTL, Cat 3126E docs, Allison docs, measured data | Specs, torques, procedures, safety steps come ONLY from here |
| 2 — Corroborating | Steel Soldiers & military-vehicle forum archive (respectful crawl per ToS + live search) | May suggest causes, known failure patterns, field shortcuts |
| 3 — Anecdotal | Facebook group posts, manually captured (screenshot + text) into a "field reports" folder — no scraping automation | Hints only, always labeled |

- **Numeric specs always resolve to the original page IMAGE, never OCR
  text.** OCR fails worst exactly where it matters most (tables, torque
  charts, wiring labels).
- Part numbers are never trusted without confirmation from the RPSTL page
  image or a supplier listing (highest hallucination-risk category).

### 3.3 Validation Pipeline
- After the diagnostic model drafts a response, a second pass checks: does
  every cited page exist in the index? Does every number appear verbatim in
  the cited Tier 1 pages? Does the answer account for as-built deviations?
- Failing claims are stripped or flagged.
- UI renders every numeric spec alongside the actual manual page — the
  human eyeballs the source. This is the single highest-value safety
  feature.

### 3.4 Output Format
Stop-and-report test cards: one test group at a time, exact lead/gauge
placement, expected values with page-image citations, meaning of each
possible result. Results feed the next round and auto-draft the work order.

Confidence labels (communication convention, NOT a safety guarantee —
models are unreliable self-assessors):
- **A** — Directly specified by an applicable manual (must be
  human-verified against the page image before wrenching)
- **B** — Supported by manual information and measured evidence
- **C** — Diagnostic inference requiring confirmation
- **D** — Speculation or insufficient evidence

## 4. Deployment Modes

Data layer (indexed corpus + as-built dossier) is identical across all
three; different "brains" point at it.

1. **Phone (offline, no AI required):** manual lookup, spec viewer with
   page images, intake capture, photo/work-order logging. Highest-value
   features need zero AI.
2. **Laptop (local model):** 7–14B quantized model via Ollama for grounded
   Q&A and work-order drafting. Small models suffice because grounded RAG
   over a curated corpus doesn't require domain knowledge — only faithful
   reading of retrieved chunks.
3. **Cloud (frontier model):** hard diagnostic reasoning — complex
   intermittent faults, competing hypotheses, catching as-built
   implications several steps back.

Small-model weakness is acceptable ONLY because no model is ever the
authority.

## 5. Known Risks & Mitigations

- **Fabricated citations:** citations can look plausible and be wrong.
  Mitigation: validation pass + human verification of every A-label spec
  against the page image.
- **OCR errors in tables/specs:** numeric values read from scan images
  only.
- **Sync drift:** one canonical as-built file in this repo; everything
  uploaded elsewhere is a dated disposable copy.
- **Platform ToS:** no Facebook scraping automation; forum crawling
  respects robots.txt/ToS.

## 6. Proof of Concept — Scope (shipped in v0.1)

**One vertical slice, not one layer built wide.**

- **Subsystem:** Air system (well-documented, safety-relevant, discrete
  testable components).
- **Pipeline:** ingest (PDF → page images + OCR text + metadata: manual
  number, printed page number, work package/paragraph, tier) → local
  hybrid index (SQLite FTS5 + embeddings; no heavy infra) → adaptive
  intake form → grounded lookup returning spec text **plus the rendered
  image of the actual manual page** → grounded model answers with
  citation-existence validation.

### POC success criteria
- Ask "what is the air governor cutout pressure?" offline → correct spec +
  actual page image + printed page reference, in under 5 seconds.
- Submit a structured "slow air buildup" intake → system retrieves the
  applicable troubleshooting procedure section.
- Every numeric value shown is traceable to a page image with one
  click/tap.

### Explicitly OUT of POC scope
- Forum crawling (Tier 2/3)
- Validation pipeline beyond citation-existence
- Phone packaging
- Multi-subsystem coverage
- Work-order system (intake sessions log to JSON for now)

## 7. Build Order (post-POC)

1. ~~Extend Tier 1 corpus to full manual set~~ (done — full A0 TM set,
   split at work-package boundaries, printed page/WP/figure references
   preserved)
2. Work-order records + service history.
3. Steel Soldiers archive (Tier 2; live search shipped in `diagnose.py
   --forums`).
4. Validation pipeline hardening.
5. Local model integration (laptop mode).
6. Phone packaging (lookup + intake + logging only).
