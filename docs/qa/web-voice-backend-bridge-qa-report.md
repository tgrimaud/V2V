# QA Functional And Latency Report - Web Voice Backend Bridge (TASK-WEB-003)

**Ticket:** TASK-WEB-003 - Answer the transcribed turn through a replaceable
conversation backend and speak it back (US-019 backend bridge).
**Sub-tasks covered:** A (contract/port), B (stub adapter), C (HTTP adapter +
`--backend`), D (answering loop), E (end-to-end telemetry), F (degraded fallback),
G (this QA + docs + ADR consolidation).
**Branch:** `task/TASK-WEB-003-G-qa-docs` (off `feat/sprint-5-backend-bridge`).
**Run date:** 2026-07-15
**Providers under test:** `stub-backend` + `http-backend` (injected transport);
STT/TTS via `fixture` providers offline. Live Gradium numbers reused from
TASK-WEB-001/002.

## Executive Summary

- **Overall readiness:** **GO** for the web Voice2Voice **answering loop** as an
  offline-proven, safe, observable slice: `POST /api/voice/turn` transcribes,
  answers through a replaceable backend, and speaks the answer, on **both**
  runtimes (`stdlib`, `pipecat`) with byte-identical audio.
- **Safe by construction:** a backend that is unavailable, unsure or empty never
  fails the turn and never invents billing content — it speaks a fixed, digit-free
  fallback and marks the turn `degraded` with a sanitized reason (DEC-002).
- **Contract documented:** the voice runtime HTTP API and the conversation
  answer contract are both written down (see Scope) — no code-only contract
  remains for the sprint.
- **Residual risks (gated, non-blocking):** live end-to-end latency with a real
  conversation endpoint not yet measured (needs the Java backend); `confidence`
  not range-validated (RF-015 / OQ-002); frontend degraded-badge rendering has no
  automated test (RF-019); ingress still unauthenticated (RF-006 / OQ-001).

## Scope Tested

- **Story:** US-019 backend bridge (the middle of the Voice2Voice loop).
- **Channel:** `web_voice` (`POST /api/voice/turn`, plus `/stt`, `/tts`).
- **Backends:** `stub` (deterministic) and `http` (injected transport, no network).
- **Runtimes:** `stdlib` and `pipecat` (parity).
- **Environment:** local, warm, offline (fixture STT/TTS, injected HTTP transport).
- **Contracts documented:**
  - HTTP API: [`docs/architecture/voice-runtime-http-contract.md`](../architecture/voice-runtime-http-contract.md)
  - Conversation contract + degraded policy: [ADR-0021](../architecture/adrs/ADR-0021-conversation-backend-answer-contract.md)
- **Automation backing this run:** 211 unit tests + 17 Behave scenarios (all green).

## Functional Results

| Area | Status | Evidence |
|---|---|---|
| Turn is transcribed, answered and spoken (not echoed) | PASS | `web_voice.feature` "The web voice loop answers instead of echoing"; `X-Answer-Provider`/`X-Answer-Outcome` headers on `audio/wav` |
| Backend is replaceable at runtime (`--backend {stub,http}`) | PASS | `test_backend_factory.py`, `conversation_backend.feature` "The runtime can target a real conversation endpoint" |
| HTTP adapter maps a real endpoint response safely | PASS | `test_http_backend.py` (success, `text`/`answer` alias, confidence, non-2xx, timeout, unparsable, empty → sanitized degraded) |
| Backend unavailable → safe spoken fallback, turn not failed | PASS | `web_voice.feature` "Safe fallback when the backend cannot answer"; `X-Answer-Outcome: degraded`, reason `backend_unavailable` |
| Low-confidence / empty answer → safe fallback | PASS | `test_answer_processor.py` (low_confidence, empty_answer); `confidence=None` not treated as low |
| Fallback text invents no amount (DEC-002) | PASS | `DEGRADED_FALLBACK_TEXT` asserted digit/currency-free in `test_answer_processor.py` |
| Empty transcript stays silent (nothing to answer) | PASS | `EmptyTranscriptError` → `unavailable`, no invented turn |
| No secret / raw text leak | PASS | key never in logs/telemetry/exceptions; `to_dict` exposes only `*_chars`; sanitized `error_reason` |
| STT/TTS hard separation preserved | PASS | `test_architecture_separation.py` (AST import scan, both directions, `voice_common` neutral) |
| Both runtimes byte-identical | PASS | `web_voice.feature` "Both voice runtimes produce identical audio"; `scripts/ab_parity.py` |

## Latency Results

Offline full-turn sample, `scripts/turn_latency_sample.py --iterations 30`
(stdlib runtime, fixture STT/TTS, stub/unavailable backend). **All six US-036
slices are measured** — the `backend_first_token` gap from earlier sprints is now
closed. Absolute values are fixture-fast and only prove wiring + measurement; real
p50/p95/p99 require live Gradium + a real conversation endpoint.

| Slice | p50 | p95 | p99 | Sample | Notes |
|---|---:|---:|---:|---:|---|
| channel_ingress | 0.00 ms | 0.00 ms | 0.00 ms | 30 | buffered upload |
| end_of_turn | 0.00 ms | 0.00 ms | 0.00 ms | 30 | trailing-silence/client-stop hold |
| stt | 0.00 ms | 0.00 ms | 0.00 ms | 30 | fixture stub (live Gradium ≈ 2.3 s, TASK-WEB-001) |
| backend_first_token | 0.002 ms | 0.003 ms | 0.004 ms | 30 | **now measured**; stub backend (live endpoint TBD) |
| tts_first_audio | 9.20 ms | 9.57 ms | 9.69 ms | 30 | fixture WAV synth (live Gradium TTS, TASK-WEB-002) |
| channel_egress | 0.00 ms | 0.00 ms | 0.00 ms | 30 | buffered write |

Degraded run (`--degraded`) measures the same six slices — the safe fallback is
still transcribed→answered→spoken (`backend_first_token` p50 ≈ 0.012 ms), so a
degraded turn is never a silent or unmeasured gap.

Live per-slice latency (real engines) is reported in `web-voice-qa-report.md`
(STT) and feeds the US-036 aggregate in
[`voice-journey-timing.md`](../observability/voice-journey-timing.md).

## Component Findings

| Brick | Status | Findings |
|---|---|---|
| `BackendAnswerPort` + models | PASS | neutral, privacy-safe `to_dict` (`*_chars`), `EmptyTranscriptError` mirrors STT/TTS empties |
| `StubBackendAdapter` | PASS | deterministic, digit-free |
| `HttpBackendAdapter` | PASS | injectable transport, sanitized degraded on every failure, key only in header |
| `answer_with_telemetry` (degraded policy + spans) | PASS | one policy for both runtimes; `backend.first_token`+`backend.request` spans, correlation id shared |
| `build_backend` / `--backend` | PASS | env fallback `VOICE_BACKEND`, clear error on unknown name |

## Defects And Gaps

| Severity | Finding | Impact | Disposition |
|---|---|---|---|
| Low | Live end-to-end latency with a real conversation endpoint not measured | No pilot SLO claim yet for the backend slice | Measure when the Java endpoint is available; slice is instrumented and ready |
| Low | `confidence` not range-validated (RF-015) | An out-of-range value could mis-trigger degrade | Gated by OQ-002 (proof/confidence rule) |
| Low | Frontend degraded-badge rendering has no automated test (RF-019) | UI regression risk on degraded turns | Manual Chrome DevTools check; add JS test when the web UI test harness lands |
| Low | Ingress unauthenticated (RF-006) | Open endpoint on pilot host | Gated by OQ-001 |

No blocking defect; no bug ticket opened.

## Open Questions

- **Product:** confidence/proof threshold that gates a trustworthy vs degraded
  answer (OQ-002)? Identity source for the web ingress (OQ-001)?
- **Architecture:** final wire shape of the real conversation endpoint (request
  fields, `text`/`answer`, `confidence`, streaming vs batch) — ADR-0021 is the
  provisional reference.

## Recommendation

- **Go / No-go:** **GO** to accept the TASK-WEB-003 backend bridge slice — the
  answering loop is functionally proven, safe-degrading, secret-free, observable
  and runtime-parity, with the HTTP API and conversation contract documented.
  Only user validation remains before merge.
- **Required before pilot:** live latency capture against the real conversation
  endpoint; resolve OQ-002 (confidence rule) and OQ-001 (identity).

## Reproduce

```bash
cd voice-agent
.venv/bin/python -m unittest discover tests          # 211 tests
.venv/bin/behave                                       # 17 scenarios
.venv/bin/python scripts/turn_latency_sample.py --iterations 30            # per-slice, success
.venv/bin/python scripts/turn_latency_sample.py --iterations 30 --degraded # per-slice, safe fallback

# live loop (needs a mic, a Gradium key and a real endpoint)
export GRADIUM_API_KEY=... VOICE_BACKEND_URL=...       # never commit these
.venv/bin/python -m web_voice.server --provider gradium --backend http
# open http://127.0.0.1:8090/ , ask a question, hear the answer
```
