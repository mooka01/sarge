# M1083A1 Service Bay — Project Brief & POC Specification

**Purpose of this document:** Founding brief for the Claude Code project. Captures the design analysis and decisions made prior to implementation. Place this in the repo root; reference it in CLAUDE.md.

---

## 1. Mission

Build an owner-technician diagnostic and reference system for a 2003 M1083A1 FMTV truck. The system helps the owner find authoritative information fast, diagnose faults with professional discipline, and document all work — without ever letting an AI model become the authority.

**Governing rule:** The applicable technical manual and actual measurements are authoritative. AI interpretation is advisory. This rule is enforced *architecturally*, not just by prompting.

## 2. The Vehicle (As-Built Context)

- 2003 M1083A1 FMTV
- Cat 3126E engine
- Allison transmission
- ~3.9:1 axle gearing
- **Eco-Hub / direct-drive conversion** — stock geared reduction hubs REMOVED. Any analysis touching wheel torque, driveline loading, effective gearing, grade performance, shift behavior, or hub service must account for this.
- CTIS retained
- Owner preference: retain stock axle, brakes, suspension, CTIS where practical; reversible, minimally invasive modifications.
- Full as-built dossier to be maintained as `AS_BUILT_CONFIGURATION.md` — the single canonical copy lives in this repo; all copies elsewhere are dated exports.

## 3. Architecture (Full System Vision)

Three layers:

### 3.1 Structured Intake (web front end)
- Form-driven diagnostic intake; no free-text "truck won't start" allowed.
- Fields: complaint category, symptom description, onset, intermittent/constant, conditions (engine temp, ambient, RPM, air pressure, battery voltage), warning lights/codes, recent work, what still works, measurements taken (with meter lead locations and test conditions), photo uploads.
- Form is adaptive: complaint category surfaces relevant measurement fields.
- As-built profile is auto-stamped onto every session.

### 3.2 Tiered Retrieval Backend
Authority is enforced by source tiering. Every indexed chunk carries a tier tag.

| Tier | Sources | Authority |
|------|---------|-----------|
| 1 — Controlling | OCR'd TMs, RPSTL, Cat 3126E docs, Allison docs, measured data | Specs, torques, procedures, safety steps come ONLY from here |
| 2 — Corroborating | Steel Soldiers & military-vehicle forum archive (respectful crawl per ToS + live search) | May suggest causes, known failure patterns, field shortcuts |
| 3 — Anecdotal | Facebook group posts, manually captured (screenshot + text) into a "field reports" folder — no scraping automation | Hints only, always labeled |

- **Numeric specs always resolve to the original page IMAGE, never OCR text.** OCR fails worst exactly where it matters most (tables, torque charts, wiring labels).
- Part numbers are never trusted without confirmation from the RPSTL page image or a supplier listing (highest hallucination-risk category).

### 3.3 Validation Pipeline
- After the diagnostic model drafts a response, an adversarial second pass checks: does every cited page contain the claim? Does every number appear verbatim in Tier 1? Does the answer account for as-built deviations?
- Failing claims are stripped or flagged.
- UI renders every numeric spec alongside a thumbnail of the actual manual page — the human eyeballs the source. This is the single highest-value safety feature.
- Start simple (citation-existence checking); get fancier later.

### 3.4 Output Format
Stop-and-report test cards: one test group at a time, exact lead/gauge placement, expected values with page-image citations, meaning of each possible result. Results feed the next round and auto-draft the work order.

Confidence labels (communication convention, NOT a safety guarantee — models are unreliable self-assessors):
- **A** — Directly specified by an applicable manual (must be human-verified against the page image before wrenching)
- **B** — Supported by manual information and measured evidence
- **C** — Diagnostic inference requiring confirmation
- **D** — Speculation or insufficient evidence

## 4. Deployment Modes

Data layer (indexed corpus + as-built dossier) is identical across all three; different "brains" point at it.

1. **Phone (offline, no AI required):** manual lookup, spec viewer with page images, intake capture, photo/work-order logging. Highest-value features need zero AI.
2. **Laptop (local model):** 7–14B quantized model (Qwen/Llama/Mistral class) via Ollama/Open WebUI for grounded Q&A and work-order drafting. Small models suffice because grounded RAG over a curated corpus doesn't require domain knowledge — only faithful reading of retrieved chunks.
3. **Cloud (frontier model):** hard diagnostic reasoning — complex intermittent faults, competing hypotheses, catching as-built implications several steps back.

Small-model weakness is acceptable ONLY because no model is ever the authority.

## 5. Known Risks & Mitigations

- **Fabricated citations:** citations can look plausible and be wrong. Mitigation: validation pass + human verification of every A-label spec against the page image.
- **OCR errors in tables/specs:** numeric values read from scan images only.
- **Sync drift:** one canonical as-built file in this repo; everything uploaded elsewhere is a dated disposable copy.
- **Platform ToS:** no Facebook scraping automation; forum crawling respects robots.txt/ToS.
- **Instruction drift in long AI sessions:** re-assert core rules in long diagnostic conversations.
- **Platform limits change:** verify current file/context limits rather than hard-coding them.

## 6. Proof of Concept — Scope

**One vertical slice, not one layer built wide.**

- **Subsystem:** Air system (well-documented, safety-relevant, discrete testable components).
- **Corpus:** One TM (air system coverage) downloaded from the owner's manual URLs.

### POC pipeline
1. **Ingest:** Download TM PDF → OCR (with per-page image extraction preserved) → chunk with metadata: manual number, printed page number, work package/paragraph, tier=1.
2. **Index:** Local search over chunks (keyword + semantic). SQLite + embeddings is sufficient; no heavy infra.
3. **Intake:** Minimal web form (single HTML page or small FastAPI/Flask app) for an air-system complaint with adaptive fields (buildup time, leak-down rate, governor cut-in/cut-out observed, gauge readings).
4. **Grounded lookup:** Query like "governor cutout pressure" returns the spec text **plus the rendered image of the actual manual page**, with printed page number.
5. **(Optional, last)** Small local model answers a diagnostic question grounded in retrieved chunks, with citations; a trivial validation check confirms cited pages exist and cited numbers appear in the source.

### POC success criteria
- Ask "what is the air governor cutout pressure?" offline → correct spec + actual page image + printed page reference, in under 5 seconds.
- Submit a structured "slow air buildup" intake → system retrieves the applicable troubleshooting procedure section.
- Every numeric value shown is traceable to a page image with one click/tap.

### Explicitly OUT of POC scope
- Forum crawling (Tier 2/3)
- Validation pipeline beyond citation-existence
- Phone packaging
- Multi-subsystem coverage
- Work-order system (log intake sessions to JSON for now)

## 7. Build Order (post-POC)

1. Extend Tier 1 corpus to full manual set (split at work-package boundaries, never page counts; preserve printed page/WP/figure references).
2. Work-order records + service history.
3. Steel Soldiers archive (Tier 2).
4. Validation pipeline hardening.
5. Local model integration (laptop mode).
6. Phone packaging (lookup + intake + logging only).

## 8. First Actions in Claude Code

1. Commit this brief and create `AS_BUILT_CONFIGURATION.md` (owner to fill).
2. Owner provides TM URLs; download the air-system manual.
3. Build ingest script (PDF → page images + OCR text + metadata JSON).
4. Build index + query CLI (prove retrieval before any UI).
5. Build minimal intake form + spec-viewer page.
