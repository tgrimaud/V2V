# Full Adversarial Review — Code & Documentation (whole application)

- **Date:** 2026-07-28
- **Branch:** `feat/restart-from-scratch`
- **Scope:** Java backend (`backend/`), Python voice runtime (`voice-agent/`), documentation (`docs/`, `README.md`, `CLAUDE.md`), product backlog (`product-backlog/`).
- **Skills applied:** `adversarial-code-review` (score /100, QA gate) + `adversarial-architecture-review` (scorecard /5).
- **Code reality at review time:** `backend/` runs (**305** unit tests, PIT ~97%), `voice-agent/` runs (**390** unit tests, **11** Behave features / **30** scenarios), `docker-compose.yml` present (Postgres+Ollama), `frontend/` absent. Full web Voice2Voice loop + streaming + barge-in + RAG answer engine delivered through Sprint 9.

---

## Consolidated Verdict

**Proceed with conditions.** This is a genuinely solid, well-tested MVP with clean hexagonal boundaries, a real guardrail stack, the DEC-002 no-fabricated-amount invariant enforced at three layers, and privacy-aware observability. It is **not** industrialized, and — more urgently — **the top-level documentation lies about the current state of the system**: nearly every entry document still claims the backend, frontend and Docker Compose were removed and that "only the STT-validation slice is built," while the backend runs 305 tests and the full streaming voice loop exists. That drift is the single highest-value, lowest-cost fix.

Two condition categories before wider exposure:
1. **Documentation current-state reconciliation** (systemic drift; misleads every human and agent onboarding).
2. **Security exposure** of unauthenticated write/answer/retrieve endpoints before any non-localhost deployment.

Known production gaps (BSS/PDF, invoice comparison, escalation, Genesys, telephony) are **expected and roadmapped**, not defects.

---

# PART A — Adversarial Code Review

## Satisfaction Score

**Score: 88/100 — QA gate: Pass (with must-fix security item before non-localhost exposure).**

Backend and voice runtime are both strong individually (~88 / ~85). Points deducted mainly for: unauthenticated backend write/answer/retrieve endpoints, the streaming-STT-failure silent path (asymmetry vs batch 502), observability being Micrometer+structured-logs rather than true OpenTelemetry spans, and config/maintainability drift.

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| High (security) | `POST /api/knowledge/ingest` and `/sync` mutate the vector store with **no authentication**; `/api/conversation/answer` and `/retrieve` are also unauthenticated (only `/converse` + `/converse-stream` honor `x-api-key`, and only when a key is set). | `KnowledgeController`, `AnswerController`, `RetrievalController`; `ConverseController:94-96` (`authorized()` returns true when key empty) | Gate write + answer + retrieve behind the same `x-api-key`/auth as converse, or bind them to localhost/internal-only for the pilot and document the boundary. |
| Medium (functional/UX) | On the **streaming WebRTC** path, STT finalize timeout/error emits telemetry but does **not** push a `TranscriptionFrame`, so no degraded fallback is spoken — the call can go **silent**. Batch `/turn` correctly returns 502. | `voice-agent/web_voice/streaming_stt_processor.py:218-222,303-315` | Emit a safe spoken degraded fallback (or explicit end-of-call) on streaming STT failure so the two transports behave consistently. |
| Medium (observability vs rule) | Project rule mandates OpenTelemetry traces for runtime behavior; backend emits **Micrometer timers + structured logs only** (no distributed spans). Documented as deferred in ADR-0028, so it is an accepted deviation — but it remains a gap against the stated rule. | `BackendTelemetry.java:19-24`; voice runtime exports telemetry to **stderr only**, no OTLP exporter | Add an OTLP exporter/bridge (backend + voice), or formally record the residual risk in ADR-0028 as an accepted pilot limitation. |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Medium | **Energy-only VAD**; Silero not implemented despite `onnxruntime` in requirements. | `voice-agent/web_voice/end_of_turn.py:7-8`; `requirements.txt:16` | Keep energy detector for onset; land Silero as a drop-in verdict upgrade (ADR-0025) or drop the unused dep. |
| Medium | Default DB password `voicesupport` and empty default API keys ship as pilot defaults. | `backend/.../application.yml:8,29,143` | Require env-provided creds in any non-local profile; fail-fast if unset. |
| Medium | `asyncio.run()` created/torn down **per HTTP `/turn`** under `ThreadingHTTPServer`; no concurrency/stress test. | `voice-agent/web_voice/runtime.py:111-133` | Add a load test; consider a shared loop for batch HTTP as done for WebRTC. |
| Low | Conversation memory is process-local heap (full transcript+answer). | `InMemoryConversationMemoryAdapter` | Acceptable for pilot; move to Redis (ADR-0008) before multi-node. |
| Low | Input guardrail lets questions `< 3` chars **pass through** to retrieval instead of clarifying. | `InputGuardrail.java:118-119` | Add a short-input clarify branch + test. |
| Low | OutputGuardrail catches only **numeric/currency-regex** amounts; amounts in words ("ten euros") slip through; locale ambiguity in `canonical()` digit-strip. | `OutputGuardrail.java:20-23,74-76` | Extend detection to written amounts; add locale tests. |
| Low | Config duplication: vague-continuer markers defined in 3 places (constant / `ConversationConfig` / `application.yml`); FR `LISTEN_PROMPT` hardcoded, not language-aware. | `InputGuardrail.java:23-26`, `ConverseController.java:40` | Single source of truth; make prompts language-aware. |
| Low | Large composing files over the 200-line budget: `server.py` (490), `webrtc_signaling.py` (478); 5 backend methods >20 lines. | subagent evidence | Extract helpers when next touched. |
| Low | Pipecat pinned `<2` with deprecation warnings suppressed → migration debt. | `voice-agent/voice_pipeline/pipeline.py:15-19` | Track a Pipecat 2.x migration task. |
| Info | Backend `pom.xml` declares Java 17 while repo guidance references Java 21. | `backend/pom.xml:21` | Reconcile toolchain/doc. |

## Story / Feature Coverage (V1 intent)

| V1 capability | Built? | Evidence |
|---|---|---|
| Web Voice2Voice loop (mic→STT→backend→TTS→playback) | ✅ | `/api/voice/turn`, streaming WebRTC path |
| RAG retrieval (pgvector, Ollama embeddings) | ✅ | `PgVectorStoreAdapter`, audience+domain filters (ADR-0034) |
| Guardrails in/out + three-band confidence | ✅ | `InputGuardrail`, `OutputGuardrail`, `RetrievalConfidenceGuardrail` |
| DEC-002 no-fabricated-amount | ✅ (3 layers) | prompt + `OutputGuardrail` + `GuardedSentenceEmitter` |
| Degraded-mode safe spoken fallback | ✅ (batch) / ⚠️ (streaming STT-fail silent) | `conversation_backend/degraded.py`; gap at streaming STT fail |
| LLM/embedding provider swap | ✅ | `LlmConfig` conditional beans; Mistral/Ollama |
| Customer identity / billing evidence | ❌ (roadmapped) | OQ-001, EPIC-002/003 |
| BSS read-only + invoice PDF + comparison | ❌ (roadmapped) | ADR-0003/0004/0005, Sprint 10 |
| Escalation contract + Genesys handoff | ❌ (roadmapped) | ADR-0019/0020, Sprint 11 |
| Query-time multi-agent routing | ❌ (V1 has none; retrieval spans all domains) | `ConversationService:15-16` |

## Test Evidence

- **Backend:** 305 tests, manual fakes (no Mockito), no `@SpringBootTest`, ArchUnit (hexagonal + context boundary + naming), PIT ~97% on domain/application/classifiers, 7 Cucumber features.
- **Voice:** 390 unittest, 11 Behave features / 30 scenarios, architecture-separation import tests, OpenAPI drift guard.
- **Missing / weak:** full Spring-context wiring test; security tests for `/api/knowledge/*`; end-to-end HTTP assertion of `X-Answer-Degraded-Reason: low_confidence`; live-provider (Gradium) CI; browser-level WebRTC E2E (real ICE/media); concurrent `/turn` load.

## Observability & Latency

- **Present:** correlation-id propagation (backend MDC filter + voice envelope, echoed to backend via `X-Correlation-Id`), per-slice Micrometer timers with p50/p95/p99, guardrail/prompt/answer counters (lengths only, no text), voice per-turn timing (US-036) with explicit `"measured": false` for uninstrumented slices, sanitization/redaction.
- **Missing:** true OpenTelemetry spans / OTLP export (both sides); channel-separated live sample volume (mostly web).
- **Risk:** latency — real-backend live warm `time_to_first_audio` samples (~5.1–5.7 s per TASK-WEB-017 QA notes) are far from the ADR-0029 pilot gate (p95 ≤ 1.2 s TTFA, ≤ 1.5 s mouth-to-ear). Tracked, not silently ignored.

## Security & Privacy

- **Good:** no committed secrets (keys via env / gitignored `.env`); sanitized `ErrorResponse` (generic message + correlation id, upstream detail server-side only, verified by test); request-size guards (audio 25 MiB, text 5000 chars) with stable error codes; PII kept out of telemetry (lengths only); response headers carry transcript/answer to the same client only, never logged.
- **Risk:** unauthenticated write/answer/retrieve endpoints (see blocking); default DB creds; in-memory transcript retention.

## Required Developer Actions (code)

1. Authenticate or network-isolate `/api/knowledge/*`, `/api/conversation/answer`, `/api/conversation/retrieve` before any non-localhost deployment; add a security test.
2. Make streaming STT failure speak a degraded fallback (parity with batch 502).
3. Decide OpenTelemetry: add OTLP exporter/bridge or record accepted residual risk in ADR-0028.
4. Enforce non-default DB/API credentials outside local profile.
5. Add a concurrency/load test for the batch `/turn` `asyncio.run` model.

---

# PART B — Adversarial Architecture & Documentation Review

## Scorecard

| Dimension | Score /5 | Rationale |
|---|---:|---|
| NFR / SLA fitness | 3 | Strong latency taxonomy (ADR-0018/0029) and instrumented slices, but live real-backend latency **misses** the ADR-0029 pilot gate; production SLO explicitly deferred. |
| SLA failure modes | 2 | Degraded voice fallback + guardrails are good; but no provider-outage / Redis-failure / duplicate-message tests, no Genesys handoff, and a silent streaming-STT-failure path. |
| Modularity & boundaries | 4 | Clean hexagonal split, ArchUnit + context-boundary tests (ADR-0027), STT/TTS import isolation, LLM/KB behind ports. |
| External dependency replaceability | 3 | LLM swap is real; Gradium behind provider factories; pgvector behind a port. But embeddings use Spring AI `EmbeddingModel` in config (not a domain port), and BSS/Genesys are unbuilt/not adapterized. |
| Evolvability & industrialization | 3 | 35 ADRs, disciplined backlog/sprints, modular design; but no independent channel deployment yet, omnichannel envelope only partial (`/converse` MVP), delivery ahead of docs. |
| **Documentation quality / accuracy** | **2** | Broad coverage, English, strong ADR discipline — but **severe current-state drift**: entry docs claim backend/frontend/compose removed and "STT-only," contradicting a Sprint-9-complete system. |
| **Overall** | **~3/5** | Solid MVP foundation with a healthy target vision; not industrialized; dangerously stale current-state narrative. Consistent with the earlier 2.8/5 industrialization review. |

## Critical Risks

- **Documentation misrepresents reality.** A new engineer/agent reading `README.md`, `CLAUDE.md`, `architecture.md`, `docs/README.md`, `development-guide.md`, the ADR index, `v1-scope.md` or `operations/backlog.md` would conclude the Java backend does not exist and only STT is built. The backend runs 305 tests, the streaming voice loop and RAG engine exist, and `docker-compose.yml` is present. This is a correctness-of-record failure, not cosmetics.
- **Latency gate unmet on the real backend.** ADR-0029 target (TTFA p95 ≤ 1.2 s) vs live warm ~5 s. Blocks any pilot SLO claim.
- **Industrial failure modes untested.** Provider outage, Redis/DB failure, duplicate/late/out-of-order messages, channel isolation — specified in ADR-0010 but largely unbuilt/untested.
- **Escalation is documented but not implemented.** No structured escalation contract/event in backend code (only low-confidence wording). Genesys handoff contract exists on paper only.

## Documentation Drift Register (must-fix, doc-only)

| # | File | Stale claim | Reality |
|---|---|---|---|
| D1 | `README.md` (L20-25) | Backend, frontend, Docker Compose "removed" on this branch | `backend/` runs (305 tests); `docker-compose.yml` **exists** |
| D2 | `docs/architecture/architecture.md` (branch note L3-27) | "Not built yet: Java backend, RAG/pgvector, streaming/barge-in, billing"; "still no WebRTC (Sprint 6)" | All built through Sprint 9 |
| D3 | `docs/architecture/adrs/README.md` (L11) | "only the STT-validation slice is built" | Sprints 6-9 delivered |
| D4 | `docs/README.md` (L3-8) | Only runnable code is voice-agent Sprints 1-5 | Backend runnable; Sprint 9 done |
| D5 | `docs/engineering/development-guide.md` (L3-17) | Backend/frontend/`agent/bot.py`/`bridge_server.py` removed; only Python slice | Backend present & runnable |
| D6 | `docs/operations/backlog.md` (L7-12) | Only STT-validation slice delivered | Same drift |
| D7 | `docs/product/v1-scope.md` header | "Only STT validation built; no TTS" | TTS + full loop built |
| D8 | `docs/architecture/channel-identity-boundary.md` (L5-8) | "Only STT-in slice" | False |
| D9 | `CLAUDE.md` (L9-37) | "removed on restart branch" narrative | Contradicted by existing `backend/` |
| D10 | ADR index table | Jumps ADR-0030 → 0033, **omits ADR-0032** (Proposed) | Add 0032 row |
| D11 | Route drift: `architecture.md`, dev guide reference `GET /api/conversation/ask-stream`, `/ask`, `/seed` | Backend uses `POST /converse`, `/converse-stream`, `/answer`, `/retrieve` |
| D12 | Port drift: dev guide / KB docs say backend `:8081` | `application.yml` + voice README use `:8080` |
| D13 | References to `frontend/` `:5173`, Pipecat UI `:7860`, `agent/bot.py`, `bridge_server.py` as current | Not present on this branch (web path is `web_voice` on `:8090`) |
| D14 | All 11 EPICs still `Draft` in `backlog-index.md` | Delivery status not reconciled to product level |

## External Dependency Review

| Dependency | Current role | Replaceability | Concern | Recommendation |
|---|---|---|---|---|
| Gradium STT/TTS | Voice STT/TTS (batch+streaming) | Moderate | Provider factory + ports exist; live-provider not in CI | Add contract test against live Gradium behind a flag |
| Mistral (chat) | Default LLM | Easy | Conditional bean, port-based | Keep; document Ollama fallback runbook |
| Ollama embeddings | Vectorization (768d) | Moderate | Spring AI `EmbeddingModel` wired in config, not a domain port; dim change ⇒ recreate table | Consider an embedding domain port for symmetry |
| pgvector | Vector store | Moderate | Behind `VectorStorePort`; Qdrant swap gated by OQ-008 | Keep; ADR-0032 decision pending |
| Genesys | Contact-center SoR (target) | Unknown | No adapter; handoff contract paper-only | Build handoff adapter (Sprint 11) before claiming omnichannel |
| Twilio | Telephony (target) | Unknown | Not built | Roadmap (Sprint 11) |
| WhatsApp | Async channel (post-MVP) | Unknown | Not scheduled; must reuse backend contract | Do not fork routing/escalation |
| Redis | Active sessions (target) | Hard-ish | In-memory today | Introduce before multi-node |

## NFR / SLA Gaps

- Live real-backend latency far from ADR-0029 gate (must be closed or the gate re-negotiated with evidence).
- No OTLP export / distributed tracing; channel-separated p95/p99 has thin live sample volume.
- Missing degraded-mode tests for provider outage, Redis/DB failure, duplicate/late messages.
- No per-channel throttling / isolation strategy implemented (shared-backend bottleneck risk).

## Recommended Changes (prioritized)

**1. Must fix before production**
- Authenticate/isolate write+answer+retrieve endpoints (**TASK-BE-019**); non-default credentials.
- Close (or evidence-based re-negotiate) the ADR-0029 latency gate (**TASK-WEB-015**, existing).
- Implement + test industrial failure modes (provider outage, Redis/DB, duplicates); make streaming STT failure non-silent (**TASK-WEB-018**).
- Add distributed tracing/OTLP or formally accept the residual risk (**TASK-OBS-001**).

**2. Should fix before pilot**
- **Reconcile all current-state documentation** (drift register D1–D14) — done via **TASK-DOC-002** (merged 2026-07-28).
- Implement the escalation contract/event in the backend.
- Land Silero VAD verdict upgrade; add live-provider contract tests.

**3. Can defer safely**
- Redis session store, WhatsApp/Twilio/Genesys adapters (roadmapped), Pipecat 2.x migration, large-file refactors, config single-source-of-truth cleanup.

---

## Residual Risk If Accepted (pilot, localhost)

For a **localhost-only pilot** with a trusted operator, the current state is acceptable: the voice loop works, guardrails and DEC-002 hold, degraded mode is safe on the batch path, and observability is sufficient for QA. The accepted residuals are: unmet latency gate, energy-only VAD, in-memory memory, unauthenticated internal endpoints (localhost-bound), and — most importantly — documentation that must not be trusted for current-state facts until the drift register is cleared.
