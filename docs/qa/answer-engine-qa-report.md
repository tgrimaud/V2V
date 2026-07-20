# QA Functional And Latency Report — Java Answer Engine (Sprint 7 close, TASK-BE-010)

**Ticket:** TASK-BE-010 — QA functional + latency report + adversarial review
**Branch:** `task/TASK-BE-010-qa-latency`
**Stories / tickets validated:** BE-004 (RAG + guardrails), BE-005 (LLM wording),
BE-006 (conversation endpoint + memory), BE-007 (streaming SSE), BE-009
(observability), BE-012 (error contract + LLM timeout), BE-008 (voice-agent wiring)
**Decisions/ADRs:** ADR-0021 (answer contract), ADR-0013 (streaming), ADR-0014
(guardrails), ADR-0018 (latency gate `time_to_first_audio` p95 < 800 ms), ADR-0028
(observability), DEC-002 (never voice an ungrounded amount)
**Run date:** 2026-07-20 (warm live sample)
**Environment:** local; pgvector (`pgvector/pgvector:pg16`, port 5433) + Ollama
(`nomic-embed-text`, 768d) + **real Mistral** (`mistral-small-latest`); backend on
`:8080`; warm (process pre-warmed, KB already ingested); co-located.

---

## Executive Summary

- **Functional readiness: GO.** All six BE-010 behaviors pass, verified twice —
  automated (158 backend tests incl. 17 Cucumber scenarios; 315 voice-agent
  unittests + 26 Behave scenarios) **and** first-hand live against the real
  RAG+LLM backend (KB-grounded answer, off-topic refusal, degraded on LLM failure,
  no invented amount, multi-turn memory, confidence handling).
- **Pilot latency readiness: NO-GO on the ADR-0018 gate with the real backend.**
  The real answer engine adds `backend_first_token` **p50 453 / p95 789 ms** (vs
  ~0 ms for the Sprint-6 stub). Folded into the ADR-0018 composite this projects a
  `time_to_first_audio` **p95 ≈ 1.54 s**, ~1.9× the **800 ms** pilot criterion. This
  is a measured backend cost, not a silent pass — the stub-backend voice path still
  meets the gate (761.5 ms); the RAG+LLM answer is a separate, now-quantified budget
  line dominated by the Mistral cloud LLM first token.
- **Defect found and fixed during QA:** the `web_voice` metric channel was
  collapsing to `other` at runtime (an incomplete BE-008 change). Fixed and
  re-verified (see Defects).
- **Residual risks:** the end-to-end streaming composite with the real backend is
  **projected** (measured backend slice + gated Sprint-6 STT/TTS baseline), not
  re-measured over WebRTC; OQ-002 confidence threshold still provisional (0.5);
  OQ-005 (is 800 ms a hard pilot gate) is a Product decision.

---

## Scope Tested

- **Epics / stories:** EPIC answer engine — BE-004…BE-009, BE-012, BE-008.
- **Channels:** `web_voice` (batch `/api/conversation/converse` + streaming
  `/api/conversation/converse-stream`).
- **Providers:** real Mistral chat (`mistral-small-latest`), Ollama embeddings
  (`nomic-embed-text`), pgvector retrieval. Voice-agent bridge uses the real
  `HttpBackendAdapter` (BE-008).
- **Fakes:** unit + BDD suites use manual fakes (no Spring context, no network).
- **Environment:** warm, co-located dev host.

---

## Functional Results

| # | Behavior | Status | Live evidence (real backend) | Automated evidence |
|---|---|---|---|---|
| 1 | KB-grounded answer | Pass | `converse` → grounded FR billing answer, `confidence≈0.75`, `[CONVERSE] grounded=true` | `conversation-grounding.feature` #1/#6, `answer-wording.feature` #1, `RetrievalGroundingServiceTest`, `AnswerServiceTest`, `AbstractChatClientAnswerAdapterTest` |
| 2 | Off-topic / domain refusal | Pass | "Quel temps fait-il demain à Paris ?" → off-topic refusal, `confidence=null`, no retrieval | `conversation-grounding.feature` #2/#3, `InputGuardrailTest`, `AnswerServiceTest` (blocked path) |
| 3 | Degraded on LLM failure | Pass | bad Mistral key → **503 `ERR_UPSTREAM`**, sanitized generic message, `X-Correlation-Id` echoed, **no key in any app log**, `llm_wording`/`backend_request` `outcome=error` | `ConverseDegradedTest`; voice-agent `test_http_backend`, `test_answer_processor`, `web_voice.feature` (spoken safe fallback); BE-012 live `SocketTimeout`→503 |
| 4 | No invented amount (DEC-002) | Pass | "Combien vais-je payer exactement le mois prochain ?" → no fabricated amount; offers a human advisor | `answer-wording.feature` #2, `OutputGuardrailTest`, `GuardedSentenceEmitterTest`, `StreamingConversationServiceTest` (mid-stream ungrounded amount stops) |
| 5 | Multi-turn conversation memory | Pass | same `conversation_id`: elliptical follow-up "Et comment puis-je **la** réduire ?" resolved to *facture* using turn-1 context | `conversation-memory.feature` (3 scenarios), `ConversationServiceTest`, `InMemoryConversationMemoryAdapterTest` |
| 6 | Confidence handling | Pass | grounded answers carry `confidence` (0.68–0.75); refusals return `confidence=null`; weak evidence → low-confidence refusal | `conversation-grounding.feature` #5, `RetrievalConfidenceGuardrailTest` |

**Regression net:** backend `mvn test` **158 green** (17 Cucumber scenarios across
`conversation-grounding`, `answer-wording`, `conversation-memory`,
`knowledge-ingestion`); voice-agent **315 unittest + 26 Behave scenarios** green.

---

## Latency Results

Warm, `channel=web_voice`, real backend. Backend per-slice figures read from the
Micrometer `voice_support.slice` timer via `/actuator/metrics` (client-side
percentile buckets — p99 is coarse and tail-sensitive at this sample size).

### Backend slices — batch `/converse` (N=27 warm)

| Slice | p50 | p95 | p99 | mean | Notes |
|---|---:|---:|---:|---:|---|
| `retrieval` | 59 ms | 65 ms | 115 ms | 60 ms | pgvector + Ollama embed; cheap and stable |
| `llm_wording` | 956 ms | 1393 ms | 1460 ms | 909 ms | Mistral cloud full completion — dominant |
| `backend_request` | 990 ms | 1460 ms | 1527 ms | 971 ms | composite (retrieval + LLM full); LLM-bound |

### Backend slices — streaming `/converse-stream` (N=26 warm)

| Slice | p50 | p95 | p99 | mean | Notes |
|---|---:|---:|---:|---:|---|
| `llm_first_token` | 294 ms | 696 ms | 2676 ms | 414 ms | time to first LLM token (p99 skewed by one ~2.6 s outlier) |
| `backend_first_token` | 453 ms | 789 ms | 2936 ms | 561 ms | **real backend contribution to time-to-first-audio** = retrieval + LLM-first-token + guardrail buffering |

**Streaming already halves the backend cost:** `backend_first_token` p95 **789 ms**
vs full `backend_request` p95 **1460 ms** — BE-007 guarded sentence streaming lets
the runtime start speaking at roughly half the full-answer latency while preserving
DEC-002 (no ungrounded amount is ever emitted).

### Composite `time_to_first_audio` — stub baseline vs real backend

ADR-0018 composite (post end-of-turn) = `stt` + `backend_first_token` +
`tts_first_audio`. STT/TTS slices are unchanged since Sprint 6 and are taken from
the gated warm baseline (`streaming-voice-qa-report.md`, N=8, pre-warmed).

| Composite input | Stub baseline (measured, Sprint 6) | Real backend (this run) |
|---|---:|---:|
| `stt` p95 | 373 ms | 373 ms (unchanged, gated) |
| `backend_first_token` p95 | ~0 ms (stub) | **789 ms (measured)** |
| `tts_first_audio` p95 | 381 ms | 381 ms (unchanged, gated) |
| **`time_to_first_audio` p95** | **761.5 ms (measured — GO)** | **≈ 1.54 s (projected — NO-GO)** |
| ADR-0018 gate (`p95 < 800 ms`) | PASS (+38.5 ms) | **FAIL (≈ −743 ms, ~1.9×)** |

The real-backend composite is a **projection**: the new backend slice is measured
first-hand this run; STT and TTS reuse the Sprint-6 measured baseline (unchanged
code). The dominant new cost is the Mistral cloud LLM first token.

---

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| RAG retrieval (pgvector + Ollama) | Pass | Cheap and stable (p95 65 ms); not a latency concern | — |
| LLM wording (Mistral) | Pass | Correct + grounded; dominant latency (first token p95 696 ms, full p95 1393 ms) | Latency lever for the pilot gate (provider/model/streaming tuning) |
| Guardrails (input/output/confidence) | Pass | Off-topic/unsafe refused pre-retrieval; DEC-002 enforced; low-confidence refusal | OQ-002 (real threshold) still open |
| Conversation memory | Pass | Multi-turn context resolved live; bounded LRU | — |
| Streaming (`/converse-stream`) | Pass | First chunk at ~half the full-answer latency; DEC-002 preserved | Fully-measured end-to-end streaming composite with `--backend http` (follow-up) |
| Error/degraded path | Pass | LLM failure → sanitized 503 `ERR_UPSTREAM`, no leak, `outcome=error` timed | — |
| Observability | Pass | One correlation id across `retrieval`/`llm_wording`/`llm_first_token`/`backend_request`/`backend_first_token` + `[CONVERSE]`; `web_voice` now first-class channel (after fix) | — |

---

## Defects And Gaps

| Severity | Finding | Impact | Status / Owner |
|---|---|---|---|
| **Medium** | `web_voice` metric channel collapsed to `other` at runtime: BE-008 added `web_voice` only to the Java `@Value` default, but `application.yml` explicitly set `allowed-channels: web,phone,whatsapp,api`, which overrides. So per-channel latency reporting for the real voice channel was impossible. | Observability gap on the exact channel the pilot cares about | **Fixed in this ticket** — `application.yml` default now `web,web_voice,phone,whatsapp,api`; re-verified: `voice_support.slice` `channel` tag = `web_voice` for all live samples. Backend test `keepsWebVoiceChannelFirstClass` guards the Java default. |
| **High** | `time_to_first_audio` p95 ≈ 1.54 s with the real backend > 800 ms ADR-0018 gate | Pilot latency criterion not met once a real RAG+LLM answer is in the loop | QA / Architecture / Product (measured backend slice; composite projected). Lever: LLM first-token (Mistral). |
| Info | End-to-end streaming composite with `--backend http` not re-measured over WebRTC (STT/TTS reused from gated Sprint-6 baseline; only backend re-measured) | Composite is a projection, not a single measured session | Follow-up: capture a warm WebRTC sample with `--backend http` + `streaming_latency_report.py` |
| Info | Sample sizes N≈24–27 warm; client-side percentile buckets are coarse (p99 tail-sensitive) | Directional p99 | Larger warm sample when tuning the LLM lever |

---

## Open Questions

- **Product (OQ-005):** is `time_to_first_audio` p95 < 800 ms a **hard** pilot gate,
  or is a functional pilot acceptable at ~1.5 s while the LLM first-token lever is
  tuned? The backend is the dominant slice now.
- **Product (OQ-002):** the definitive proof/confidence threshold (provisional 0.5).
- **Architecture:** target LLM first-token budget to bring the composite under
  800 ms (retrieval is already ~65 ms; STT/TTS are gated at ~373/381 ms, leaving
  virtually no room for a ~700–800 ms backend first token).

---

## Recommendation

- **Functional: GO.** The real answer engine satisfies all six BE-010 behaviors
  live and under regression, with correlation-id continuity and no sensitive-data
  leakage.
- **Pilot latency: NO-GO against the ADR-0018 800 ms gate** once the real backend is
  in the loop (projected p95 ≈ 1.54 s). This is now quantified honestly: the
  backend contributes `backend_first_token` p95 789 ms; guarded streaming (BE-007)
  already halves it vs the full answer. Escalated to Product (OQ-005) and
  Architecture for a gate decision and the LLM latency lever.
- **Required before an SLO claim (ADR-0010):** per-channel dashboards, alerting,
  degraded-mode + provider-outage tests, and a fully-measured end-to-end streaming
  composite with the real backend.

## Addendum — TASK-BE-011 latency reduction (2026-07-20)

Follow-up to the BE-010 NO-GO. Backend-only levers (top-K, prompt, telemetry); the
800 ms gate decision stays OQ-005.

**Changes.** Retrieval top-K made configurable (`voice-support.conversation.retrieval.top-k`,
default 4) on `/converse[-stream]`; system prompt trimmed ~989 → ~593 chars (all
DEC-002 rules + the exact `transfère à un conseiller` hand-off sentence preserved);
prompt-size telemetry added (`voice_support.prompt_chars` summary + `[PROMPT]` log
with system/context/history chars + chunk count, correlation id, **no content**).

**Remeasured** (real Mistral, warm, `web_voice`, fresh conversation per call, server-side
`[TELEMETRY]` slices):

| Config | prompt system_chars | backend_first_token p50/p95/p99 | llm_first_token p50/p95/p99 | N |
|---|---:|---:|---:|---:|
| **top-K 4, trimmed** | 2111 | **444 / 653 / 680 ms** | 334 / 582 / 585 ms | 25 |
| BE-010 baseline (top-K 4, old prompt) | ~2507 | 453 / 789 / 2936 ms | 294 / 696 / 2676 ms | 26 |

top-K sweep (N=12): `backend_first_token` p95 — k4 474 / k3 559 / k2 491 ms → **within
noise; no reliable TTFT gain below top-K 4**, so the default stays 4 (top-K is an ops
dial, not a latency fix).

**Findings.**
- The trimmed prompt reduced prompt size ~16 % and tightened the tail
  (`backend_first_token` p95 789 → 653 ms, p99 2936 → 680 ms).
- The **~330 ms LLM median TTFT is a Mistral-cloud network/prefill floor** — not
  reducible by backend prompt levers; prompt size only moves the tail.
- Composite `time_to_first_audio` p95 ≈ **1.41 s** (was ~1.54 s): improved but still
  **NO-GO vs 800 ms**. Closing the gap requires a faster provider/model (DEC-011
  benchmark) and/or the STT/TTS path — not further backend prompt trimming — plus the
  OQ-005 gate decision. Cross-session comparison caveat: BE-010 and this run were
  measured at different times, so treat the tail deltas as indicative, not exact.

**Recommendation: GO for BE-011 as a backend latency improvement + observability
enabler.** It does not, and was not scoped to, close the 800 ms gate (OQ-005).
