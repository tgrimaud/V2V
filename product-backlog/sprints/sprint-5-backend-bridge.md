# Sprint 5 — Backend Answer Bridge (US-019 close)

## Sprint Objective

Turn the current web voice **echo** loop into a real **answer** loop: route the STT
transcript to a backend conversation surface, get a response text, and hand it to
the TTS slice so the web page **answers by voice** — all under a single correlation
id from ingress to egress. This closes **US-019** and the last **US-036** gap (the
`backend_first_token` slice). The `US-003` boundary is preserved: the **backend owns
the answer, the voice runtime owns the media**.

This is **not** a billing-reasoning sprint (no real invoice calculation) and **not**
a latency sprint (streaming stays in Sprint 6). The value is closing the
Voice2Voice loop with a real, replaceable answer seam.

## Status

**Status:** Planned
**Created:** 2026-07-14
**Predecessor:** [`sprint-4-pipecat-batch.md`](sprint-4-pipecat-batch.md) (Sprint 4 — Done, 2026-07-14)
**Working branch:** `feat/sprint-5-backend-bridge` (from `feat/restart-from-scratch`)
**Final validator:** User
**Merge rule:** no branch is merged unless the user explicitly asks.

## Roadmap Context

| Sprint | Theme | State |
|---|---|---|
| Sprint 1 | STT validation (fixtures → Gradium transcript, timing, QA) | ✅ Done |
| Sprint 2 | STT hardening (quality gate, sanitization, UNAVAILABLE, end-of-turn) | ✅ Done |
| Sprint 3 | TTS / voice-out (batch) → first end-to-end voice loop | ✅ Done |
| Sprint 4 | Pipecat runtime migration (batch parity, pipeline-only) | ✅ Done |
| **Sprint 5** | **Backend answer bridge (echo → real answer, US-019 close) — this sprint** | Planned |
| Sprint 6 | Latency optimization: streaming STT (TASK-STT-010) + streaming TTS (TASK-WEB-004) + streaming VAD (TASK-STT-012) + WebRTC transport | Planned |

## Included Tickets

Parent: **TASK-WEB-003** — Orchestrate transcript to backend answer (US-019 middle).
Split into fine-grained sub-tickets for tracking; each is one branch and one
`implement → test → commit` slice with an adversarial review, mirroring the Sprint 3/4
discipline.

| Ticket | Title | Role | Priority |
|---|---|---|---|
| TASK-WEB-003-A | Conversation contract + `BackendAnswerPort` (seam, no provider) | Contract | High |
| TASK-WEB-003-B | Deterministic stub backend adapter (default, offline/dev + tests) | Provider | High |
| TASK-WEB-003-C | HTTP backend adapter + `--backend {stub,http}` selection (env `VOICE_BACKEND`) | Provider | High |
| TASK-WEB-003-D | Wire the bridge into the runtime: transcript → backend answer → TTS text, on both runtimes | Integration | High |
| TASK-WEB-003-E | End-to-end telemetry: `backend.request`/`backend.first_token` span + `BACKEND_FIRST_TOKEN` slice (closes US-036 gap) | Observability | High |
| TASK-WEB-003-F | Degraded mode: backend unavailable / low confidence → safe spoken fallback | Robustness | High |
| TASK-WEB-003-G | QA + behave (e2e loop + degraded) + per-slice latency table + docs + conversation-contract ADR | QA / Docs | High |

## Design Decisions (locked with the user)

- **Option A — contract-first, port + adapters.** Introduce a `BackendAnswerPort`
  seam in the voice runtime with two adapters: a **deterministic stub** (default,
  offline/dev + tests) and an **HTTP** adapter (calls a real conversation endpoint),
  selectable via `--backend {stub,http}` (env `VOICE_BACKEND`). The real Java
  billing/RAG backend later implements the same contract without touching the
  runtime. Mirrors the existing STT/TTS provider-adapter pattern (DEC-005, DEC-007).
- **Answer, not echo.** The pipeline/runtime step that produced the echo text is
  replaced by the backend answer text as the TTS input, on **both** runtimes
  (stdlib + pipecat). The echo processor is retired or repurposed as the answer step.
- **No fabricated billing content (DEC-002).** The stub returns a generic, neutral
  response and **never invents an amount or invoice content**. Real billing answers
  are gated by identity (OQ-001) and BSS availability (OQ-003) and stay out of this
  sprint.
- **Safe degraded mode.** Backend unavailable or low confidence → a **safe spoken
  fallback** (no invented content), a sanitized error and a degraded outcome
  attribute. No Genesys handoff this sprint (EPIC-007 out of scope); the real
  confidence threshold is gated by OQ-002.
- **Boundary stays hard.** The runtime does not embed conversation intelligence; the
  answer is owned by the port implementation. The stub is an explicit placeholder for
  the Java backend, not the product brain.
- **US-036 gap closed here.** The `backend_first_token` slice becomes measured once
  the backend span is emitted and registered in `voice_common/pipeline_timing.py`.

## Target Answer Loop (server-side, in-memory transport)

```
InMemoryFrameSource → GradiumSttService → BackendAnswerService → GradiumTtsService → InMemoryFrameSink
     (audio)            (wraps STT runner)   (transcript→answer text)  (wraps TTS runner)   (collect WAV)
                                                    │
                                            BackendAnswerPort
                                            ├── stub → StubBackendAdapter (deterministic, default)
                                            └── http → HttpBackendAdapter (real conversation endpoint)
```

Slices after this sprint (all measured):
`web.voice.ingress` → `voice.stt.*` → **`backend.first_token`** → `voice.tts.first_audio` → `web.voice.egress`.

## Delivery Order (sub-ticket breakdown)

- **TASK-WEB-003-A — Conversation contract + `BackendAnswerPort`.** Define the
  request/response shape (transcript, channel envelope, correlation id → response
  text, outcome, confidence/degraded reason) and the port protocol. No provider yet.
- **TASK-WEB-003-B — Stub backend adapter.** Deterministic, offline answer honoring
  DEC-002 (neutral text, no fabricated amounts). Default backend for dev/tests.
- **TASK-WEB-003-D — Wire the bridge (on the stub).** Insert the backend step between
  STT and TTS on both runtimes so the loop **answers** instead of echoing. *(Can run
  before C so the answering loop is visible ASAP.)*
- **TASK-WEB-003-E — End-to-end telemetry.** Emit `backend.request` /
  `backend.first_token`, register `BACKEND_FIRST_TOKEN` in
  `voice_common/pipeline_timing.py`, one correlation id across ingress→stt→backend→
  tts→egress. Closes the US-036 gap.
- **TASK-WEB-003-F — Degraded mode.** Backend unavailable / low confidence → safe
  spoken fallback, sanitized error, degraded outcome attribute.
- **TASK-WEB-003-C — HTTP backend adapter.** WebClient-style HTTP adapter + config
  selection (`--backend {stub,http}`, env `VOICE_BACKEND`), fake-transport tests, no
  live backend required.
- **TASK-WEB-003-G — QA + behave + latency + docs + ADR.** End-to-end and degraded
  behave scenarios, per-slice latency table, docs and a conversation-contract ADR.
  Also documents the sprint's two **currently code-only** contracts under `docs/`
  (linked from `docs/README.md`): the **voice runtime HTTP API**
  (`POST /api/voice/stt|tts|turn` — bodies, status codes, sanitized error shape,
  `--backend` selection) and the **conversation-contract surface**
  (`BackendAnswerPort` / `AnswerRequest` / `AnswerResult`). No code-only contract
  remains at sprint close.

## Runtime Selection

```
WebVoiceHTTPServer (--runtime {stdlib,pipecat}, --backend {stub,http})
        │
        ▼
 BackendAnswerPort.answer(transcript, envelope, correlation_id) → AnswerResult
        ├── stub → StubBackendAdapter   (deterministic, default)
        └── http → HttpBackendAdapter   (real conversation endpoint)
```

## Branch Plan

The sprint branch `feat/sprint-5-backend-bridge` is cut from
`feat/restart-from-scratch`. Each sub-ticket is developed on its own branch cut from
the sprint branch and merged back once validated.

| Ticket | Branch | Status |
|---|---|---|
| TASK-WEB-003-A | `task/TASK-WEB-003-A-conversation-contract` | Implemented (review 96/100; merge-ready, pending user validation) |
| TASK-WEB-003-B | `task/TASK-WEB-003-B-stub-backend` | Validated by user 2026-07-15 (review 96/100; merge-ready, merge on request) |
| TASK-WEB-003-C | `task/TASK-WEB-003-C-http-backend` | Planned |
| TASK-WEB-003-D | `task/TASK-WEB-003-D-wire-bridge` | Implemented (review 93/100; merge-ready, pending user validation) |
| TASK-WEB-003-E | `task/TASK-WEB-003-E-backend-telemetry` | Implemented (review 95/100; merge-ready, pending user validation) |
| TASK-WEB-003-F | `task/TASK-WEB-003-F-degraded-mode` | Planned |
| TASK-WEB-003-G | `task/TASK-WEB-003-G-qa-docs` | Planned |

## Out Of Sprint

| Ticket / Item | Reason |
|---|---|
| TASK-STT-010 (streaming STT) | Latency optimization — **Sprint 6**. |
| TASK-WEB-004 (streaming TTS) | Incremental playback — **Sprint 6**. |
| TASK-STT-012 (streaming VAD end-of-turn) | Real-time turn detection — **Sprint 6**. |
| SmallWebRTCTransport + Pipecat JS client | Coupled with streaming — **Sprint 6**. |
| Real billing reasoning (EPIC-002…005) | Needs identity (OQ-001), BSS (OQ-003) and PDF extraction (OQ-004); the stub honors DEC-002 in the meantime. |
| Genesys advisor handoff (EPIC-007) | Escalation content is out of scope; degraded mode only produces a safe spoken fallback. |
| Customer identity model (OQ-001) | Ingress stays unauthenticated (RF-006 / RF-014 remain gated). |
| US-020 (quick acknowledgement), US-021 (barge-in) | Depend on streaming and/or richer orchestration. |
| TASK-WEB-006 (generic voice errors) | Independent hardening; can ride along if convenient but not a sprint goal. |

## Sprint Acceptance Criteria

```gherkin
Scenario: End-to-end web Voice2Voice loop (answer, not echo)
  Given the customer asks a question by voice on the web page
  When the transcript is sent to the backend and a response is produced
  Then the response is spoken back to the customer
  And the full turn is traceable per pipeline slice via one correlation id
```

```gherkin
Scenario: Safe fallback when the backend cannot answer
  Given the backend is unavailable or not confident
  When the turn is processed
  Then no billing content is invented
  And a safe spoken fallback is rendered to the customer
  And the degraded outcome is observable without leaking secrets
```

```gherkin
Scenario: The answer engine is replaceable behind the contract
  Given the stub and http backend adapters
  When the runtime is started with --backend stub and with --backend http
  Then both drive the same voice loop through the same conversation contract
  And switching backend requires no code change, only the startup flag
```

## Open Questions / Dependencies

- **OQ-001** (customer identification) — gates real billing answers and authenticated
  ingress; the stub stays identity-agnostic and neutral for this sprint.
- **OQ-002** (proof / confidence threshold) — the degraded trigger is deterministic
  in the stub; the real threshold is deferred.
- **OQ-003 / OQ-004** (BSS data, PDF extraction) — gate the real answer engine that
  later implements the HTTP contract.
- **OQ-007** (backend AI/RAG framework: Spring AI vs LangChain4J vs other) —
  **deferred, does not block this sprint** (the stub needs no framework). Must be
  decided before the Java answer engine behind TASK-WEB-003-C is implemented.

## Definition Of Done (sprint)

- TASK-WEB-003-A…G each pass adversarial review (≥ 90%) and QA.
- The web loop answers by voice on both runtimes with the stub backend.
- `backend_first_token` is measured; US-036 has no remaining implemented-slice gap.
- Non-blocking findings logged in `review-findings.md`; docs, ADR and backlog updated.
- **US-019 → Done** and RF-002 closable once the user validates the live loop.
- Merge only when the user explicitly asks.
