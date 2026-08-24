# Full Adversarial Review — Code & Documentation (whole application)

- **Date:** 2026-08-05
- **Branch:** `feat/sprint-11-remote-deployment`
- **Scope:** Java backend (`backend/`), Python voice runtime (`voice-agent/`), deployment + CI (`deploy/`, `.github/workflows/`, `docker-compose.yml`), documentation (`docs/`, `README.md`, `CLAUDE.md`, `AGENTS.md`), product backlog (`product-backlog/`).
- **Skills applied:** `adversarial-architecture-review` (scorecard /5) as the backbone + `adversarial-code-review` (code-level findings) folded in.
- **Code reality at review time:** `backend/` runs (**337** unit tests, ArchUnit-enforced hexagonal boundaries, no `@SpringBootTest`), `voice-agent/` runs (**462** unit tests, **13** Behave features / **36** scenarios), `deploy/` carries Ansible + HAProxy/keepalived + compose + CI for the eir-ai4cc-tst pilot, `frontend/` absent on this branch. Full web Voice2Voice loop + streaming + barge-in + RAG answer engine delivered; **billing V1 not started**.
- **Verification note:** the two headline claims below were confirmed directly in code (grep), not inferred from docs — `backend/src/main` has **zero** `BssBilling|InvoicePdf|Galaxion|bill-run` and **zero** `IntentClassifier|AgentProfile|EscalationDetector|Genesys` matches.

---

## Verdict

**Proceed with conditions — but re-baseline the product narrative first.**

What exists is a genuinely solid, well-instrumented **general-support RAG voice MVP**: a clean hexagonal Java conversation engine, a mature WebRTC Voice2Voice runtime (native barge-in, tested degraded modes), and a credible pilot deployment scaffold (vault-rendered env, rolling deploy, source-scoped firewall, the BUG-006 VRRP fix). It is **not** the "V1 billing / invoice-discrepancy" product the documentation describes, and it is **not live-pilot-ready**. Three hard facts drive the verdict:

1. **The V1 product core does not exist in code.** No `BssBillingPort`, `InvoicePdfExtractor`, Galaxion adapter, or comparison engine. The bot answers only from static KB articles via RAG, while `docs/product/v1-scope.md` and the cahier describe BSS→PDF→deterministic-delta→LLM explanation in the present tense.
2. **The pilot latency gate is FAILED, not pending.** ADR-0029 sets p95 mouth-to-ear ≤ 1.5 s; the backlog records p95 ≈ 2142 ms after both latency levers. Sprint 10 closed "on scope," not on the gate.
3. **The live pilot is blocked on unclosed inputs** (TLS cert, STUN/TURN, LB automation, SSH ingress), so the two-service stack cannot run on eir-ai4cc-tst yet.

Proceed as a **web-based general-support voice pilot**, not as a billing product, and only after the "Must fix" conditions below are met.

---

## Scorecard

| Dimension | Score /5 | Rationale |
|---|---:|---|
| NFR / SLA fitness | **2** | Excellent latency *measurement* model (6 canonical slices, p50/95/99), but the pilot gate is **FAILED** (p95 ≈ 2142 ms vs 1.5 s), OTLP export is **off** in prod templates (no aggregation → SLO unsubstantiable), streaming LLM path has **no timeout**, embeddings/pgvector have **no HTTP timeout**. |
| SLA failure modes | **3** | App-level degradation is real and *tested* (Redis outage → empty history; backend down → degraded answer; STT/TTS fail → fallback; barge-in cancel + `aclose`). Undermined by **zero retries/circuit-breakers**, single-node Postgres+Redis SPOFs, and no data backup/restore. |
| Modularity & boundaries | **4** | Hexagonal boundaries enforced by ArchUnit + Python architecture-separation tests; provider SDKs confined to adapters. Held back from 5 by **Gradium-locked streaming STT/TTS** on the latency-critical path and `BackendAnswerPort` not contracting streaming/warm-up. |
| External dependency replaceability | **3** | LLM (Mistral↔Ollama) and batch STT/TTS easy; pgvector moderate. **Streaming STT/TTS Hard (Gradium only)**; Twilio/Genesys/WhatsApp not present (target-only). |
| Evolvability & industrialization | **2** | Deployment packaged but pilot **blocked on open inputs**, **no centralized observability**, **SPOFs with no backup**, **failed latency gate**, only the web channel exists. A scaffold, not yet industrialized. |
| **Overall** | **≈2.6** | Strong MVP engineering and unusually honest tracking, but the documented V1 (billing) is unbuilt and pilot go-live is gated. **Proceed with conditions.** |

---

## Critical Risks

- **Product-vs-code gap (billing V1).** Readers of `v1-scope.md`/`cahier-des-charges-fonctionnel.md` will believe invoice-discrepancy explanation is delivered. It is not started. → **TASK-DOC-004**.
- **Latency gate failure treated as "on scope."** p95 ≈ 2142 ms vs 1.5 s (ADR-0029). Any pilot SLO claim is currently unsupportable. → **TASK-WEB-022**.
- **Live pilot cannot run.** TLS cert absent (`haproxy.cfg:40`), `VOICE_STUN=""` (WebRTC media won't traverse for Prodpriv clients), HAProxy/keepalived not Ansible-automated (`CHANGE_ME_VRRP`), SSH/ingress CIDR undocumented. → **TASK-INFRA-006**.
- **No production observability.** OTLP disabled in `backend.env.j2`/`voice.env.j2`; operators would `curl` per-node metrics with no aggregation. → **TASK-OPS-007**.
- **Data-tier SPOFs with no recovery.** Single Postgres (`.102`) and single Redis (`.107`), no replica, no `pg_dump`/AOF backup runbook. → **TASK-OPS-008**.
- **Streaming LLM hang path.** Sync generation is timeout-bounded; the SSE path calls `streamContent()` with no call-level timeout (`AbstractChatClientAnswerAdapter.java:122-139`). → **TASK-BE-025**.
- **Voice path bypasses domain filtering.** `/converse` + `/converse-stream` pass `domain=null` (`ConversationService.java:40-42`), searching all domains. → **BUG-007**.

---

## Hard Questions

1. Is V1 still "invoice-discrepancy explanation," or has it *de facto* become "general operator support RAG voice bot"? Code says the latter; docs say the former. Pick one and align both.
2. What is the realistic path to p95 ≤ 1.5 s given a cloud LLM + cloud STT/TTS + browser egress? If 1.5 s is not achievable, does the pilot proceed on a revised, signed-off number?
3. Who owns the open-input closure (TLS, TURN, LB, SSH) and by when? Without them there is no live pilot to review.
4. How will p95/p99 be *collected and aggregated* in the pilot? Local Micrometer endpoints are not an SLO strategy.
5. What RPO/RTO is acceptable for conversation memory (Redis) and KB/vector data (Postgres)? Today both are "loss on node failure."
6. Are Mistral (chat) and Gradium (STT/TTS) cloud egress, data-residency and cost acceptable for a telecom pilot handling billing conversations?

---

## Architecture Challenges

- **"Billing V1 sits on the general support foundation" (ADR-0017).** The foundation is built but the billing context has no ports, PDF pipeline, or comparison. This is "V1 not begun," not "V1 nearly done." *Alternative:* label the current deliverable a Support Assistant pilot and open an honestly-sized Billing epic gated on OQ-001/003/004.
- **Streaming STT/TTS is Gradium-locked (`server.py:351-363`).** The provider-agnostic goal holds only for the batch layer; the latency-critical path is the least replaceable. *Alternative:* define `StreamingSttProvider`/`StreamingTtsProvider` protocols now (even with one impl). → **TASK-WEB-023**.
- **No resilience layer (Java or Python).** Fail-fast is fine for a POC, but "real-time voice" + "no retry/circuit-breaker" + "single Redis/Postgres" is fragile. → **TASK-BE-026** (+ data resilience in TASK-OPS-008).
- **HAProxy backend health check is shallow.** It probes `/api/health` (static UP, `HealthController.java:17-21`) while Ansible uses `/actuator/health`; a backend with Redis/DB down stays in rotation. → **TASK-INFRA-007**.
- **Observability is designed but disabled.** The instrumentation is the project's best feature, yet OTLP is off and trace sampling is 0.0. → **TASK-OPS-007**.

---

## External Dependency Review

| Dependency | Current role | Replaceability | Concern | Recommendation |
|---|---|---|---|---|
| Mistral (chat) | LLM wording | Easy | Cloud egress + cost + no streaming timeout | Streaming call timeout (BE-025); confirm terms |
| Ollama (embeddings) | Vectorize KB/query | Easy | No HTTP timeout; sidecar-per-VM | Timeout on embedding client (BE-025) |
| pgvector / Postgres | Vector + KB store | Moderate | Spring AI coupling; single node, no backup | Backup/restore (OPS-008); OQ-008 later |
| Redis | Conversation memory | Easy | Single node, no HA, PII at rest | AOF backup + TTL (OPS-008) |
| Gradium (STT/TTS) | Batch + streaming | Batch Easy / streaming Hard | Streaming path vendor-locked | Streaming provider protocol (WEB-023) |
| Twilio (telephony) | — | Unknown | Not present; doc mentions it | Keep out of V1 scope (DOC-004) |
| Genesys CX | Handoff | Unknown | Target-only; no code | Mark "not implemented" (DOC-004) |

---

## NFR / SLA Gaps

- **Latency SLO unmet** (p95 2142 ms vs 1.5 s) and **latency levers ship OFF** (`VOICE_BACKEND_STREAM` default false, STT pre-warm opt-in) — the pilot would run slower than the measured numbers unless flags are set.
- **No SLO substantiation in prod** — OTLP off, no collector, no W3C traceparent voice→backend.
- **No throughput/concurrency ceiling tested** — unbounded WebRTC sessions on a single asyncio loop + threaded HTTP server (`webrtc_signaling.py:254`), 1 vCPU LB VMs vs `maxconn 20000`.
- **Failure-mode metric pollution** — failed/unavailable TTS still emits `voice.tts.first_audio` with total elapsed (`streaming_tts_processor.py:191-196, 218-223`); `pipeline_timing` doesn't filter by outcome. → **BUG-008**.
- **No live validation** of VRRP failover, voice rolling-deploy drain (empty hooks in `voice.yml:56-57`), or edge rate-limit burst.
- **Security defaults** — API key gate open when unset (`ApiKeyGuard`), voice HTTP layer has no auth/rate-limit of its own.

---

## Recommended Changes (→ tickets)

**1 — Must fix before any "pilot-ready" claim**

1. **TASK-DOC-004** — Truth-in-labeling: mark billing, multi-agent routing (F3), escalation, Genesys, telephony/WhatsApp as NOT IMPLEMENTED/target across cahier + v1-scope + relevant ADR impl notes.
2. **TASK-INFRA-006** — Close/track live-deploy open inputs (TLS cert + FQDN, STUN/TURN, HAProxy/keepalived Ansible automation + real VRRP secret, SSH/ingress CIDR).
3. **TASK-OPS-007** — Stand up centralized observability (OTLP collector in the pilot topology) and enable export in prod `.env` templates + traceparent voice→backend.
4. **TASK-WEB-022** — Latency gate remediation: enable the levers by default (after STT idle-socket validation), re-measure p95 vs 1.5 s, or produce a revised gate for sign-off.
5. **TASK-BE-025** — Streaming LLM call timeout + embedding/pgvector client timeout.

**2 — Should fix before pilot**

6. **TASK-INFRA-007** — Deploy release safety: HAProxy backend health → `/actuator/health` (deep) + wire voice drain hooks (`voice_lb_drain_cmd`/`enable_cmd`).
7. **TASK-OPS-008** — Data resilience: Redis AOF backup + Postgres `pg_dump` cron + restore runbook.
8. **BUG-007** — `/converse`+`/converse-stream` apply the domain filter (or document the cross-domain choice).
9. **BUG-008** — Filter TTS span emission by outcome so failed turns don't pollute p95.
10. **TASK-DOC-005** — Freshness & backlog integrity: refresh stale "Sprint 9 / STT-only" banners; fix ADR-0037 endpoint name + promote ADR-0036/0037; reconcile backlog-index orphans (US-041/042, BUG-001, OQ-008); French-in-`docs/` hygiene pass.

**3 — Can defer safely**

11. **TASK-BE-026** — Resilience: bounded retries on idempotent reads + circuit breaker on the LLM.
12. **TASK-WEB-023** — Streaming provider protocols (break the Gradium lock on the hot path).
13. **TASK-WEB-024** — WebRTC session caps/backpressure + migrate off per-turn `asyncio.run` batch path.
14. *(already ticketed)* **TASK-OPS-006** — SHA-pin third-party GitHub Actions + Dependabot.

---

## Strengths (do not regress these)

- Hexagonal boundaries **enforced by tests** (`HexagonalArchitectureTest`, `ContextBoundaryTest`, Python `test_architecture_separation.py`).
- DEC-002 no-fabricated-amount invariant enforced post-LLM + per streamed sentence (`OutputGuardrail`, `GuardedSentenceEmitter`).
- Privacy-aware logging (char counts, never transcript/answer) + log-injection sanitization (`CorrelationId.sanitize`).
- Voice runtime safety: native Pipecat barge-in with amplitude-gated anti-echo, `CancelledError` + `finally aclose()` cleanup, degraded mode that never invents billing content.
- Mature latency instrumentation model: canonical slices always emitted, missing ones flagged `"measured": false`.
- Deployment hygiene: vault-rendered `.env` (mode 0600, `no_log`), immutable-tag enforcement, registry logout, source-scoped firewalld, BUG-006 VRRP fix, test-gated image publish.
- Unusually honest tracking in `backlog-index.md` and the ADR README (built vs target).

---

## Downgraded / rejected sub-findings (strictness notes)

- **"CI never builds the sprint branch"** — downgraded from High: `images.yml` also triggers on `v*.*.*` tags, so releases publish via semantic tags by design; the mainline pointer is `feat/restart-from-scratch`. Not a blocking gap.
- Known production gaps (BSS/PDF, invoice comparison, escalation, Genesys, telephony) are **expected and roadmapped**, not defects — the defect is the documentation over-claiming them as present V1 scope (DOC-004).
