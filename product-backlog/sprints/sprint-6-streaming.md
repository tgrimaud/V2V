# Sprint 6 — Streaming Voice Loop & Latency (US-019 optimization, US-021)

## Sprint Objective

Turn the **batch** Voice2Voice loop delivered in Sprints 1–5 into a **streaming,
full-duplex** loop so the conversation feels natural and fast: partial STT while
the customer speaks, incremental TTS that starts on the first audio chunk, a
real-time VAD end-of-turn, and a **WebRTC transport** driving the Pipecat pipeline
on a single long-lived async loop. The headline deliverable is a measured
**`time_to_first_audio` p95 < 800 ms** on the web voice channel (ADR-0018 pilot
acceptance criterion), plus **barge-in** (US-021): the customer can interrupt the
bot mid-answer.

This is the **latency + realtime** sprint that Sprints 4/5 explicitly deferred. It
is **not** a billing-reasoning sprint (the answer engine stays the Sprint 5
stub/http backend) and **not** an identity sprint (ingress auth stays gated by
OQ-001 / RF-006 / RF-014).

## Status

**Status:** Planned (scope validated by user 2026-07-15; no development started yet)
**Created:** 2026-07-15
**Predecessor:** [`sprint-5-backend-bridge.md`](sprint-5-backend-bridge.md) (Sprint 5 — ✅ Done, closed 2026-07-15)
**Working branch:** `feat/sprint-6-streaming` (to be cut from `feat/restart-from-scratch`)
**Final validator:** User
**Merge rule:** no branch is merged unless the user explicitly asks.

## Roadmap Context

| Sprint | Theme | State |
|---|---|---|
| Sprint 1 | STT validation (fixtures → Gradium transcript, timing, QA) | ✅ Done |
| Sprint 2 | STT hardening (quality gate, sanitization, UNAVAILABLE, end-of-turn) | ✅ Done |
| Sprint 3 | TTS / voice-out (batch) → first end-to-end voice loop | ✅ Done |
| Sprint 4 | Pipecat runtime migration (batch parity, pipeline-only) | ✅ Done |
| Sprint 5 | Backend answer bridge (echo → real answer, US-019 close) | ✅ Done |
| **Sprint 6** | **Streaming voice loop + latency (streaming STT/TTS/VAD + WebRTC transport + barge-in) — this sprint** | Planned |
| Sprint 7 (tentative) | Telephony channel (US-018) + Genesys handoff (EPIC-007) | Planned |

## Why now (baseline that justifies the sprint)

Live Gradium QA measured the loop in **batch** mode
(`docs/qa/web-voice-qa-report.md`): STT slice **~2.3 s** for a 3.4 s utterance
(latency scales with audio length), TTS synthesized whole-clip before playback, and
`POST /api/voice/turn` runs synchronously with `asyncio.run(...)` per request
(RF-012). None of this can reach the ADR-0018 pilot target. Streaming is the
primary lever; a WebRTC full-duplex transport is the enabler for both low latency
and barge-in.

## Included Tickets

| Ticket | Title | Role | Priority | Status |
|---|---|---|---|---|
| TASK-WEB-007 | WebRTC transport (SmallWebRTCTransport + Pipecat JS client) on a single long-lived async loop | Transport/Enabler | High | ✅ Done (merged 2026-07-16) |
| TASK-STT-012 | Streaming VAD-based end-of-turn detection | Turn detection | Medium | Merged into `feat/sprint-6-streaming` (2026-07-16, ff) — validated (review 93/100 + QA Go) |
| TASK-STT-010 | Streaming STT (partial + final transcripts) | STT | High | ✅ Validated by user (2026-07-16) — merged into `feat/sprint-6-streaming`; live tail 818 ms vs ~3.4 s batch; RF-007 closed |
| TASK-WEB-004 | Streaming TTS (incremental playback, time-to-first-audio) | TTS | High | ✅ Validated by user (2026-07-16) — merged into `feat/sprint-6-streaming`; live first-audio 363 ms vs ~1.59 s batch; review 96/100 (open()/allowlist/timeout hardening) |
| TASK-WEB-008 | Barge-in during a spoken answer (US-021) | Realtime UX | Medium | ✅ Validated by user (2026-07-16) — merged into `feat/sprint-6-streaming` (no-ff; branch deleted). Live full-stack: barge-in cuts the answer, resumes the new turn; anti-echo gate (amplitude threshold + N-frame confirmation) fixed without-headphones self-interruption |
| TASK-WEB-006 | Genericize voice error responses (no raw provider text in 502 bodies, RF-013) | Hardening | Low | Planned |
| TASK-WEB-009 | Streaming QA + `p95 < 800 ms` latency report + ADR update (sprint close) | QA / Docs | High | Planned |

### Out of scope (confirmed with the user, 2026-07-15)

| Item | Reason |
|---|---|
| US-020 (quick spoken acknowledgement during long analysis) | Backend-timing behaviour (fast ack while evidence is verified), not a transport/streaming concern — deferred to a later sprint. |

## Design Decisions (proposed — to confirm with the user)

- **WebRTC over the batch HTTP endpoints for the realtime path.** Add a
  `SmallWebRTCTransport` (Pipecat) + a Pipecat JS client in the browser, driving the
  existing pipeline (`ingress → stt → answer → tts → egress`) on **one long-lived
  async event loop**. The Sprint 4/5 batch endpoints (`/api/voice/stt|tts|turn`)
  stay as the fallback/comparison path (ADR-0016). **Resolves RF-012** (`asyncio.run`
  per turn → awaited pipeline).
- **Streaming is additive, not a rewrite.** Streaming STT/TTS/VAD are new provider
  variants behind the existing `SttProvider` / `TtsProvider` / `EndOfTurnDetector`
  seams; the batch providers stay for fixtures/offline dev. No fork of the Gradium
  providers.
- **Answer engine unchanged.** The Sprint 5 `BackendAnswerPort` (stub/http) is
  reused as-is; a streaming backend (`backend.first_token` ≠ `backend.request`,
  RF-021) is out of scope this sprint.
- **Latency is measured per slice before any SLO claim** (ADR-0018 / DEC-010): the
  sprint reports p50/p95/p99 per slice and `time_to_first_audio` end-to-end, warm,
  per channel. `p95 < 800 ms` is a **pilot acceptance criterion**, not a production
  SLO (ADR-0010 gates remain).
- **Hard STT/TTS separation stays enforced** (`tests/test_architecture_separation.py`).
- **Safety invariants preserved:** no invented transcript/answer, no secret leak,
  safe degraded fallback (Sprint 5), no invented turn boundary on no-speech
  (TASK-STT-009 guarantee) carried into the streaming VAD.

## Target Streaming Loop (WebRTC, single async loop)

```
Browser (Pipecat JS client, mic + speaker, full-duplex)
   │  WebRTC audio frames (in)                     ▲ WebRTC audio frames (out)
   ▼                                               │
SmallWebRTCTransport ── Pipecat pipeline (one long-lived asyncio loop) ── SmallWebRTCTransport
   │            │              │                 │                │
   ▼            ▼              ▼                 ▼                ▼
streaming   streaming STT   BackendAnswerPort  streaming TTS   barge-in
  VAD       (partials +     (stub/http,        (incremental    (VAD interrupt
(end-of-    final)          Sprint 5)          first-audio)    cancels playback)
 turn)
```

New/added slice timings: `stt` reports **time-to-first-partial** and
**time-to-final**; `tts_first_audio` = first streamed chunk; a new
**`time_to_first_audio`** end-to-end measure (end-of-turn → first playable frame).

## Delivery Order (proposed)

Risk-first, each ticket one branch + `implement → test → commit` + adversarial
review (Sprint 3/4/5 discipline). A short **spike** opens the risky transport
ticket (mirrors the Sprint 4 Pipecat spike).

1. **TASK-WEB-007 — WebRTC transport** (spike first: lock the `SmallWebRTCTransport`
   + JS client handshake and the single-loop pipeline drive; then integrate). The
   foundation everything else rides on; resolves RF-012.
2. **TASK-STT-012 — Streaming VAD end-of-turn** (frame-incremental detector at the
   same injection point as the batch detector).
3. **TASK-STT-010 — Streaming STT** (partials during speech; closes RF-007).
4. **TASK-WEB-004 — Streaming TTS** (incremental playback; time-to-first-audio).
5. **TASK-WEB-008 — Barge-in** (US-021; integrates VAD interrupt + playback cancel).
6. **TASK-WEB-006 — Genericize voice error responses** (RF-013; low-priority
   hardening on the endpoints — can land any time, ideally before the QA close).
7. **TASK-WEB-009 — Streaming QA + latency report + ADR update** (measures
   `p95 < 800 ms`, publishes the per-slice baseline, updates ADR-0018 evidence).

> Streaming STT/TTS/VAD (2–4) can be developed against fake streaming transports in
> parallel with the WebRTC integration, then wired into the transport as they land.

## Out Of Sprint

| Item | Reason |
|---|---|
| Real billing reasoning (EPIC-002…005) | Needs identity (OQ-001), BSS (OQ-003), PDF extraction (OQ-004); stub/http backend stays. |
| Streaming backend answer (`first_token` ≠ `request`, RF-021) | Backend-side streaming; the answer engine is not built this sprint. |
| Telephony channel (US-018) + Genesys handoff (EPIC-007) | Separate channel/contact-center sprint. |
| Customer identity / ingress auth (OQ-001, RF-006/RF-014) | Deferred; the streaming ingress stays unauthenticated on the pilot host. |
| US-022 (text complement) | Independent web UX. |

## Sprint Acceptance Criteria

```gherkin
Scenario: The web voice loop streams end to end with low latency
  Given the streaming WebRTC voice runtime
  When the customer asks a question by voice
  Then partial transcripts appear while the customer is still speaking
  And the spoken answer begins on the first synthesized audio chunk
  And time_to_first_audio p95 is below 800 ms (warm, web channel), reported per slice
```

```gherkin
Scenario: The customer can interrupt the bot (barge-in)
  Given the assistant is playing a spoken answer
  When the customer starts speaking
  Then the assistant stops playback promptly
  And the interruption outcome is observable for pilot review
```

```gherkin
Scenario: The realtime path drives the pipeline on one async loop
  Given the WebRTC transport
  When a turn is processed
  Then the pipeline is awaited on a single long-lived event loop
  And no per-turn asyncio.run is used (RF-012 closed)
```

## Open Questions / Dependencies

- **OQ-001** (identity) — streaming ingress stays unauthenticated; gates RF-006/RF-014.
- **OQ-002** (confidence threshold) — unchanged from Sprint 5; degraded policy reused.
- **Provider capability** — confirm Gradium streaming ASR tokens (TASK-STT-008 spec)
  and streaming TTS chunking over the chosen transport; a spike de-risks this.
- **Browser/runtime** — Pipecat JS client + `SmallWebRTCTransport` version pinning
  and TURN/STUN needs for the pilot host.

## Definition Of Done (sprint)

- TASK-WEB-007, TASK-STT-012, TASK-STT-010, TASK-WEB-004, TASK-WEB-008, TASK-WEB-006
  and TASK-WEB-009 each pass adversarial review (≥ 90%) and QA.
- Streaming loop works over WebRTC on a single async loop (RF-012 closed);
  batch endpoints remain as fallback.
- `time_to_first_audio` p95 < 800 ms measured warm on the web channel, with the full
  per-slice baseline published (sample size, p50/p95/p99, min/max/mean, warm/cold).
- Barge-in stops playback and is observable (US-021).
- RF-007 closed (streaming ingress transport); RF-012 closed (awaited pipeline);
  RF-013 closed (generic client-safe voice error responses).
- OpenTelemetry updated: `time_to_first_partial`, `time_to_final`, streamed
  `tts_first_audio`, `time_to_first_audio`, barge-in event — all under one
  correlation id; docs + ADR-0018 evidence updated.
- **US-019 stays Done; US-021 → Done** once the user validates the live loop.
- Merge only when the user explicitly asks.

## Branch Plan

The sprint branch `feat/sprint-6-streaming` is cut from `feat/restart-from-scratch`.
Each ticket is developed on its own branch cut from the sprint branch and merged
back once validated.

| Ticket | Branch | Status |
|---|---|---|
| TASK-WEB-007 | `task/TASK-WEB-007-webrtc-transport` | ✅ Done (merged 2026-07-16, branch deleted) |
| TASK-STT-012 | `task/TASK-STT-012-streaming-vad-end-of-turn` | ✅ Merged into `feat/sprint-6-streaming` (2026-07-16, ff; branch deleted) |
| TASK-STT-010 | `task/TASK-STT-010-streaming-stt` | ✅ Validated + merged into `feat/sprint-6-streaming` (2026-07-16, no-ff; branch deleted) |
| TASK-WEB-004 | `task/TASK-WEB-004-streaming-tts` | ✅ Validated + merged into `feat/sprint-6-streaming` (2026-07-16, no-ff; branch deleted) |
| TASK-WEB-008 | `task/TASK-WEB-008-barge-in` | ✅ Validated + merged into `feat/sprint-6-streaming` (2026-07-16, no-ff; branch deleted) |
| TASK-WEB-006 | `task/TASK-WEB-006-generic-voice-errors` | Planned |
| TASK-WEB-009 | `task/TASK-WEB-009-streaming-qa-latency` | Planned |
