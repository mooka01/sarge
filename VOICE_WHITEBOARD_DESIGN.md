# Voice + Whiteboard Design

Real-time voice troubleshooting with a multi-panel evidence display
("the whiteboard"). Design decisions recorded 2026-07-25; nothing here is
built yet. Read [PROJECT_BRIEF.md](PROJECT_BRIEF.md) first — every rule
there applies unchanged. This document only defines how voice and a
shared display are added on top of the existing retrieval, validation,
and citation pipeline.

---

## 1. Decisions (settled)

1. **Voice converses; the whiteboard is the authority.** The assistant
   never speaks a numeric spec, torque, or part number as an answer. It
   displays the page image on the whiteboard and refers to it by panel
   ("governor cutout is on the board, panel 2 — confirm the value before
   you set it"). Speech is the one medium that cannot carry a page-image
   citation, so the governing rule is preserved by routing all
   authoritative values to the visual channel. Spoken confidence labels
   (A/B/C/D) are mandatory for diagnostic claims.
2. **Cascade, not speech-to-speech.** Streaming ASR → existing grounded
   text agent (retrieval + validation, unchanged) → streaming TTS.
   Native speech-to-speech APIs (OpenAI Realtime, Gemini Live) are
   rejected: they emit audio directly, so the citation-existence /
   verbatim-number validation pass has nothing to intercept. The ~1–2 s
   cascade latency is acceptable for a conversation paced by wrenching.
   They are also the expensive path, so the cascade wins on both axes.
3. **Free and local is the default; quality is a paid, per-use upgrade.**
   The out-of-the-box configuration costs $0 and requires no account:
   browser Web Speech API (ASR) + a free-tier LLM + browser
   `speechSynthesis` (TTS). Better voices and better ears are optional
   adapters the user enables with their own API key. No subscription,
   no bundled credits, no SARGE-side billing of any kind.
4. **All providers, all tiers.** Each capability (ears / brain / mouth)
   is a pluggable adapter chosen in `config.json`. The LLM adapter
   speaks the OpenAI-compatible chat+tools format so any major provider,
   any aggregator, and local Ollama work without code changes; Anthropic
   keeps its native adapter (already in `backends.py`). Free tiers that
   give good results are first-class supported configurations, not
   degraded fallbacks.
5. **No middleman, ever.** SARGE never proxies, relays, or resells a
   paid service. The user's machine talks directly to the provider the
   user configured, billed on the user's key. The repo ships adapters
   and a config schema; it never ships a billing relationship.
6. **Page images never go to the cloud.** The whiteboard renders images
   from the local corpus. The LLM sees only OCR text and citation
   metadata, and emits display tool calls that the local hub resolves.
   This keeps every turn text-only (no vision-token cost) and keeps the
   human — not the model — as the reader of the authoritative page.

## 2. Architecture

```
 phone / tablet / laptop browser(s)          local SARGE process (app.py)
┌──────────────────────────────┐            ┌─────────────────────────────┐
│ mic ──► ASR adapter (browser │  WebSocket │  session hub                │
│         or streamed to hub)  ├───────────►│   ├─ retrieval (unchanged)  │
│ speaker ◄── TTS adapter      │◄───────────┤   ├─ validation (unchanged) │
│ whiteboard panels (images    │            │   ├─ LLM adapter ───────────┼──► cloud API
│  served from local corpus)   │            │   └─ display tool executor  │    (user's key)
└──────────────────────────────┘            └─────────────────────────────┘
```

- The **session hub** is a WebSocket endpoint in the existing web app.
  Multiple browser clients may join one session (wall tablet = board,
  phone = mic, laptop = full view); panel state lives server-side so
  every client renders the same board.
- **Audio stays at the edge.** In the default config, ASR and TTS both
  run inside the browser, so the hub only ever handles text. Paid
  ASR/TTS adapters either run browser-side (JS SDK) or stream audio
  through the hub to the provider — adapter's choice, hub is agnostic.
- No WebRTC infrastructure, no LiveKit/Pipecat cloud, no session fees.

### Display tools (LLM-callable)

Implemented as inline text directives rather than API tool calls, so
every backend (Claude, Ollama, any OpenAI-compatible adapter) can drive
the board with no tool-calling support required:

```
[[SHOW:MANUAL|PDFPAGE]]   deploy that corpus page image to a panel
[[CLEAR]]                 sweep unpinned panels on topic change
```

Directives are executed server-side against the index (a SHOW of a page
not in the index is refused and surfaces as a validation flag) and are
stripped from the visible/stored reply. Panel *gestures* — pin, close,
expand, zoom, manual deploy by tapping a citation chip — are human-side
UI actions, not model directives. Layout is automatic from panel count
(1–6, oldest unpinned evicted).

### Voice interaction contract

- Test cards map one-to-one to voice turns: one test group at a time,
  lead/gauge placement spoken, expected values shown on the board and
  read back by the *human* before the test runs.
- Every measurement the technician speaks is echoed back for
  confirmation before it is logged (ASR mishears "122" as "102").
  Confirmed values become measured data in the session JSON.
- Barge-in (user speech interrupts TTS) is required in half- and
  full-duplex modes.

## 3. Adapter matrix

| Capability | Default ($0, no key, no account) | Metered upgrades (BYO key, pay per use) |
|---|---|---|
| Ears (ASR) | Web Speech API (Chrome/Edge/Android) | Groq Whisper (free tier, then ~$0.02/hr), Deepgram (~$0.26/hr), OpenAI Whisper API |
| Brain (LLM) | Gemini Flash free tier; own Ollama | Claude (native adapter), any OpenAI-compatible endpoint: OpenAI, Gemini, Groq, Mistral, OpenRouter, … |
| Mouth (TTS) | Browser `speechSynthesis` | Edge TTS, OpenAI TTS, Cartesia, ElevenLabs (~$0.10–0.15 per 30-min session) |

Rules for the matrix:

- Adding a provider means adding one adapter file + a config entry —
  never touching the hub, retrieval, or validation.
- Free tiers with good results (Gemini Flash, Groq) are documented and
  tested as primary configurations.
- iOS Safari's Web Speech implementation is unreliable: the documented
  iPhone $0 path is push-to-talk through a free-tier ASR adapter
  instead of the browser engine.

### `config.json` extension (sketch)

```json
{
  "backend": "claude",
  "claude_model": "claude-opus-5",
  "ollama_url": "http://127.0.0.1:11434",
  "ollama_model": "qwen2.5:7b-instruct",

  "openai_compat": { "base_url": "", "api_key_env": "", "model": "" },

  "voice": {
    "asr": "browser",            
    "tts": "browser",            
    "asr_options": {},
    "tts_options": { "voice": "", "rate": 1.0 },
    "mode": "push_to_talk"       
  }
}
```

`asr`/`tts` name an adapter (`browser`, `groq`, `deepgram`, `openai`,
`edge`, `cartesia`, …). `mode` is `push_to_talk` (phase 2) or
`open_mic` (phase 3, VAD + barge-in + optional wake word). Keys are
referenced by environment-variable name, never stored in config.

## 4. Cost model (why "nearly free" holds)

A realistic 30-minute session ≈ 40–60 turns, ~300–500k input tokens
with retrieval context, ~20k output.

- Default config: **$0** (browser ASR/TTS, free-tier LLM).
- Cheap-metered config (Haiku or Flash + paid TTS): **≈ $0.50–0.75 per
  session**, billed directly by the providers.
- Frontier-brain config (hard intermittent faults): a few dollars per
  session — a knob the user turns, not a tier SARGE sells.
- Prompt caching is designed in from the start: stable system prompt +
  as-built dossier as the cached prefix, per-turn retrieval appended
  after. Cuts input cost several-fold on providers that support it.
- Page images render locally, so no vision tokens, ever (decision 6).

## 5. Deployment

- **Laptop:** full self-contained install; browser tab at localhost.
- **Phone as client (day one):** any phone browser on the LAN or
  Tailscale joins the session — mic, speaker, board mirror. No app, no
  store, just a URL. **Caveat:** browsers require HTTPS (or localhost)
  for microphone access, so remote clients need Tailscale's built-in
  HTTPS certs or a locally-trusted cert. This must be in setup docs —
  it is otherwise the #1 support complaint.
- **Phone standalone:** out of scope here; remains build-order item 6
  (offline lookup/intake packaging). Voice diagnosis is inherently a
  connected feature (cloud model APIs).
- Garage noise: primary mic is a Bluetooth headset with push-to-talk
  (or wake word in phase 3); tablet/phone far-field mic is fallback.

## 6. Build phases

1. **Whiteboard, no voice.** Display tool set + session hub +
   multi-client panel rendering, driven by the existing typed agent.
   Independently useful; this is where the safety mechanism lives.
   **SHIPPED 2026-07-25:** the "tactical board" — SSE session
   hub in `app.py` (no new dependencies, offline-capable), inline
   directive protocol above, drill-sergeant board persona (grounding
   rules unchanged), multi-client mirroring, self-contained HUD UI in
   `templates/board.html` (no external assets). `?shot=1` renders one
   state snapshot without the SSE stream (screenshots/tests).
   Later same day: the board became the DEFAULT interface at `/`
   (old chat kept at `/classic`; `/board` redirects), every classic
   page (search / intake / knowledge / config / page viewer) reskinned
   to the tactical theme, all chat features integrated into the board
   (sessions drawer, brain/scope/Tier-2 config, intake attach +
   auto-analyze handoff, photo attach, help-post drafting), and the
   comms/stage split made draggable and collapsible (full evidence-wall
   mode). Panel state persists per session in `sessions/board-*.json`.
   The classic chat was then retired outright (`/classic` → redirect to
   `/`; template deleted) and mobile was rebuilt app-style: one
   full-screen view at a time (COMMS ↔ BOARD) switched by a bottom tab
   bar with a live evidence-count badge (pulses when SARGE deploys a
   page while you're in comms; tapping a citation chip jumps to the
   board), plus a MORE sheet holding navigation and utilities.
   Safe-area insets respected for notched phones.
2. **Half-duplex voice.** Push-to-talk, browser ASR → existing agent →
   browser TTS. The complete $0 default path. Prove the grounding rules
   survive the medium (no spoken specs; board citations; measurement
   read-back).
   **SHIPPED 2026-07-25:** hold-to-talk mic (composer + floating mic on
   the mobile board view, live transcript toast), Web Speech ASR,
   `speechSynthesis` TTS streamed sentence-by-sentence as the reply
   arrives, voice/rate picker + spoken-reply policy in mission config
   (auto / always / never; browser-local prefs). Server `voice` flag
   appends a VOICE addendum: 2–6 spoken-prose sentences, echo heard
   measurements back, never speak a spec — deploy the page and have the
   owner read it off the board. Citations/labels stripped for speech
   ([A]–[D] spoken as confidence ALPHA–DELTA); validation problems
   spoken as a count with eyes-on-screen warning. PTT press cancels TTS
   (barge-in). Verified live: a wrong-retrieval turn produced echo-back,
   refusal to quote an absent spec [D], and one instruction — no bluff.
   Known limits: iOS Safari ASR unreliable (paid-adapter path later);
   mic needs HTTPS/localhost (Tailscale certs for phone); spoken number
   words ("one twenty two") weaken keyword retrieval — consider
   number-word normalization at intake.
3. **Full duplex + upgrades.** VAD, barge-in, wake word, headset
   tuning; paid ASR/TTS adapters; OpenAI-compatible LLM adapter and
   provider matrix docs.

## 7. Non-goals

- Speech-to-speech model integration (violates the validation
  architecture — see decision 2).
- Any hosted SARGE service, relay, account system, or payment flow.
- Voice control of anything destructive (sessions are advisory;
  the human wrenches).
