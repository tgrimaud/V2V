# Sprint 3 — TTS / Voice-out (batch)

## Sprint Objective

Deliver the **voice-out half** of US-019: turn a response text into speech through a
Gradium TTS provider and play it back in the web page, **symmetric to the STT path**.
This closes the first visible **voice-in → voice-out loop** by speaking an echo of the
STT transcript, with no Java backend and no streaming.

This sprint stays strictly within batch (non-streaming) TTS scope: no backend/LLM
answer (TASK-WEB-003, Sprint 5), no streaming playback (TASK-WEB-004, Sprint 6), no
barge-in (US-021).

## Status

**Status:** Done (2026-07-13) — TASK-WEB-002 (batch TTS voice-out) delivered; ST-1..ST-8 complete plus post-review follow-ups (pipeline_timing moved to `voice_common`, runner refactor, `asyncio` live-path fix, `websockets` pin widened), 130 unit tests + 4 behave features green, echo loop MCP-validated + live Gradium demo validated by the user. **Merged (fast-forward) into `feat/restart-from-scratch`.**
**Created:** 2026-07-13
**Predecessor:** [`sprint-2-stt-hardening.md`](sprint-2-stt-hardening.md) (Sprint 2 — Done, 2026-07-13)
**Working branch:** `feat/sprint-3-tts-voice-out` (from `feat/restart-from-scratch`)
**Final validator:** User
**Merge rule:** no branch is merged unless the user explicitly asks.

## Roadmap Context

| Sprint | Theme | State |
|---|---|---|
| Sprint 1 | STT validation (fixtures → Gradium transcript, timing, QA) | ✅ Done |
| Sprint 2 | STT hardening (quality gate, sanitization, UNAVAILABLE, end-of-turn) | ✅ Done |
| **Sprint 3** | **TTS / voice-out (batch, non-streaming) → first end-to-end voice loop (this sprint)** | ✅ Done (merged → `feat/restart-from-scratch`) |
| Sprint 4 | Pipecat runtime migration (batch parity, pipeline-only) | ✅ Done |
| Sprint 5 | Backend answer bridge (echo → real answer, US-019 close) | Planned |
| Sprint 6 | Latency optimization: streaming STT (TASK-STT-010) + streaming TTS (TASK-WEB-004) + streaming VAD (TASK-STT-012) | Planned |

## Included Tickets

| Ticket | Title | Type | Priority | Story | Sprint role |
|---|---|---|---|---|---|
| TASK-WEB-002 | Speak the bot response on the web page (TTS half) | Technical task | High | US-019 (TTS half), US-036 | Batch Gradium TTS provider + web playback; measures `tts_first_audio` + `channel_egress` slices |

## Design Decisions (locked with the user)

- **Scope: TASK-WEB-002 only.** The spoken text is an **echo/stub** (repeat the STT
  transcript) — a visible voice→voice loop without a Java backend. Real answers
  (TASK-WEB-003) and streaming (TASK-WEB-004) are out of sprint.
- **Transport: Gradium TTS WebSocket** (`wss://api.gradium.ai/api/speech/tts`) — the
  only known Gradium TTS contract (no REST batch endpoint). "Batch" = collect all
  audio chunks until `end_of_stream`, then play once. Streaming playback is Sprint 6.
- **Live spike first** to confirm the real WebSocket contract before building the
  provider (same discipline used for the Gradium STT adapter).
- **Playback:** Gradium PCM16 → 44-byte WAV header → browser `decodeAudioData` +
  a single `AudioBufferSourceNode`.
- **STT/TTS are two separate routes.** `tts_synthesis/` MUST NOT import
  `stt_validation/` and vice versa (only stateless shared utilities: `telemetry`,
  `sanitization`, `ChannelEnvelope`, and the read-only `pipeline_timing` aggregator).
  Enforced by an architecture test. Either direction can evolve/be swapped/be tested
  independently; TTS is testable without a Gradium key via `FixtureTtsProvider`.

## Delivery Order

1. **Phase 0 — Gradium TTS spike:** live WebSocket probe to lock the contract.
2. **Phase 1 — TTS provider layer:** `tts_synthesis/` (models, `TtsProvider` protocol
   + `EmptyTextError`, `FixtureTtsProvider`, `GradiumTtsProvider`, factory).
3. **Phase 2 — Runner + telemetry:** `TtsSynthesisRunner`; register
   `tts_first_audio` + `channel_egress` in `pipeline_timing.py`.
4. **Phase 3 — Web egress + playback:** `WebVoiceEgress`, `POST /api/voice/tts` (WAV),
   playback + echo loop in the web page.
5. **Phase 4 — Tests/QA/docs:** unit (fake WS transport) + behave + architecture
   separation test + QA harness + fixtures + docs.

## Branch Plan

The sprint branch `feat/sprint-3-tts-voice-out` is cut from `feat/restart-from-scratch`.
Ticket work is developed on its own branch cut from the sprint branch and merged back
once validated (per the repository branching strategy).

| Ticket | Branch | Status |
|---|---|---|
| TASK-WEB-002 | `task/TASK-WEB-002-tts-voice-out` | Done (delivered on the sprint branch) |

## Out Of Sprint

| Ticket | Reason |
|---|---|
| TASK-WEB-003 (backend bridge) | Real LLM/RAG answer generation — needs a backend; Sprint 3 speaks an echo/stub text instead. |
| TASK-WEB-004 (streaming TTS) | Incremental playback (time-to-first-audio lever) — **Sprint 6** (latency optimization). |
| US-020 (quick acknowledgement), US-021 (barge-in) | Depend on streaming and/or backend orchestration. |
| Twilio / ulaw egress | Telephony channel — not the web voice slice. |

## Sprint Acceptance Criteria

```gherkin
Scenario: The bot response is spoken on the web page
  Given a response text is available for the customer turn
  When the web voice page receives the response
  Then the text is synthesized by the TTS provider
  And the audio is played back to the customer
  And the TTS slice latency and outcome are observable via OpenTelemetry
```

```gherkin
Scenario: STT and TTS are independent routes
  Given the STT route and the TTS route
  When the TTS provider or endpoint changes
  Then the STT route is unaffected
  And each route can be tested independently, TTS without a live Gradium key
```

## Open Questions (resolved)

- **Is `GRADIUM_VOICE_ID=default` a valid voice, or is a catalog voice id required?**
  Resolved (ST-1 spike): a **real catalog voice id is required**; `default` is
  rejected by the Gradium TTS WebSocket. The provider factory normalizes/validates
  the voice id and the README/`docs/qa/gradium-tts-contract.md` document it.
- **Should `FixtureTtsProvider` return a committed clip or a generated tone?**
  Resolved (ST-2): **generated deterministic tone** (PCM16 keyed by text length) —
  avoids committing binary audio fixtures while keeping the offline path realistic
  and reproducible. Reference *texts* (not clips) live in `fixtures/tts/`.
