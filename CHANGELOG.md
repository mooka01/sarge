# Changelog

## v0.2.0 — 2026-07-25 · The Tactical Board

The board becomes the product. One interface, one theme, voice on top —
same governing rule underneath: the page image is the authority, AI is
advisory.

### Tactical board (new default interface)
- Evidence wall driven by the conversation: every page the AI cites can
  deploy as the actual page image; inline `[[SHOW:MANUAL|PAGE]]` /
  `[[CLEAR]]` directives are executed server-side, validated against the
  index (a SHOW of a nonexistent page is refused and flagged), and
  stripped from display. Tap any citation chip to deploy manually.
- Panels: pin / sweep / auto-layout (1–6), tap to bring a page forward
  full screen — zoom (scroll / pinch / double-tap) and turn real manual
  pages (swipe, edge arrows, arrow keys). `?xpage=MANUAL|PAGE` deep-links
  the viewer.
- Multi-screen: any number of browsers (wall tablet, phone, laptop) join
  a session over SSE and mirror comms + panels live. Panel state persists
  per session (`sessions/board-*.json`) across restarts.
- Drill-sergeant comms persona on the board — attitude never overrides
  citations, confidence labels, or verbatim safety briefs.
- Sessions drawer, mission config (brain / retrieval scope / Tier-2
  forums toggle / intake attach), photo attach, help-post drafting — the
  classic chat page is retired (`/classic` redirects).
- Draggable, collapsible comms/evidence split; app-style mobile: full
  screen COMMS ↔ BOARD views on a bottom tab bar with live evidence
  badge, MORE sheet for navigation and utilities.
- Whole app re-skinned to the tactical theme (search / intake /
  knowledge / my-truck / page viewer). Boot ceremony at most once per
  day per browser.

### Voice (design doc phases 2–3)
- Push-to-talk, open-mic **full duplex**, or wake word ("SARGE, …").
  Open mic survives browser silence timeouts, filters out SARGE's own
  TTS echo, ignores sub-2-word noise, and obeys "stop".
- Barge-in: speaking mid-reply aborts the stream (partial kept, marked
  interrupted) and asks the new question.
- Two-channel replies: a short spoken brief (what was found, what's on
  the board, the one next step — safety lines verbatim) plus a
  screen-only detailed workup. **The spoken channel never carries a
  spec number** — SARGE deploys the page and the human reads the value.
- $0 default stack: browser speech recognition + browser TTS. Optional
  premium voice: ElevenLabs through a local relay — key in the
  `ELEVENLABS_API_KEY` env var, never sent to the browser, graceful
  fallback without it. Measurement read-back, spoken validation-flag
  warnings, per-device voice/rate/policy settings.

### Fixes and hardening
- Insecure-context UUID fallback (plain-HTTP LAN/Tailscale clients);
  boot-screen failsafe surfaces script faults instead of stranding the
  operator.
- Mobile overflow fixes (panel headers, viewer header); grid panels can
  never push controls off screen.
- `/api/pagemeta`, `/api/board/*/state` endpoints; `shot=1` render mode
  for tests/screenshots.

## v0.1.0 — 2026-07 · SARGE

Initial public release: tiered retrieval over locally indexed TM PDFs
(FTS5 + local embeddings), page-image authority layer, citation +
number validation, structured intake, as-built dossier, Claude / Ollama
backends, prebuilt public-domain indexes (6x6 + LMTV) on the Releases
page.
