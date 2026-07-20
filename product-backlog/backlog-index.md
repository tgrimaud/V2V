# Backlog Index

## Restart Baseline

This branch restarts implementation from scratch. The previous implementation is
kept on `main` as backup/reference. All V1 backlog items below are therefore
reset to `Draft` until Product, Architecture, Security and Delivery review them
against the new empty-codebase plan.

## V1 Epics

| Key | Title | Classification | Status | Priority |
|-----|-------|---|--------|----------|
| EPIC-001 | Product and architecture baseline | V1 foundation | Draft | High |
| EPIC-002 | Customer identity and billing evidence access | V1 core | Draft | High |
| EPIC-003 | BSS/PDF fixture and extraction path | V1 enabler | Draft | High |
| EPIC-004 | Deterministic invoice comparison | V1 core | Draft | High |
| EPIC-005 | Evidence-backed explanation engine | V1 core | Draft | High |
| EPIC-006 | Voice2Voice journey foundation | V1 core | Draft | High |
| EPIC-007 | Genesys advisor handoff | V1 core | Draft | High |
| EPIC-008 | Web synthesis and evidence view | V1 enabler | Draft | Medium |
| EPIC-009 | Trust, security and auditability | V1 enabler | Draft | High |
| EPIC-010 | Observability, latency and pilot validation | V1 pilot gate | Draft | High |

## V1 Delivery Backlog

| Key | Title | Classification | Status | Priority |
|-----|-------|---|--------|----------|
| US-001 | Reconfirm the V1 restart baseline | V1 foundation | Draft | High |
| US-002 | Define the delivery sequence for the empty codebase | V1 foundation | Draft | High |
| US-003 | Confirm the channel and identity boundary | V1 foundation | Done | High |
| US-004 | Identify the customer at the start of the exchange | V1 core | Draft | High |
| US-005 | Retrieve available invoices and billing periods | V1 core | Draft | High |
| US-006 | Detect insufficient BSS evidence | V1 core | Draft | High |
| US-007 | Use realistic BSS/PDF fixtures for V1 validation | V1 enabler | Draft | High |
| US-008 | Handle invoice extraction status | V1 enabler | Draft | High |
| US-009 | Validate billing and pricing knowledge for V1 | V1 enabler | Draft | Medium |
| US-010 | Select two invoices or billing periods to compare | V1 core | Draft | High |
| US-011 | Identify changed invoice lines and amounts | V1 core | Draft | High |
| US-012 | Identify the main business causes | V1 core | Draft | High |
| US-013 | Expose unresolved or unreconciled amounts | V1 core | Draft | High |
| US-014 | Receive a synthesis of increase or decrease causes | V1 core | Draft | High |
| US-015 | Obtain evidence for each cause | V1 core | Draft | High |
| US-016 | Explain the billing rule behind a delta | V1 core | Draft | Medium |
| US-017 | Disclose when no reliable explanation can be produced | V1 core | Draft | High |
| US-018 | Call the bot for a spoken invoice explanation | V1 core | Draft | High |
| US-019 | Ask from a web voice chat | V1 core | Done (Sprint 5, 2026-07-15; full Voice2Voice loop: STT → backend answer → TTS, stub + http backends) | High |
| US-020 | Receive a quick spoken acknowledgement during long analysis | V1 core | Draft | Medium |
| US-021 | Interrupt the bot during a spoken answer | V1 core | ✅ Validated by user (2026-07-16) — Sprint 6 (TASK-WEB-008 barge-in), merged into `feat/sprint-6-streaming` | Medium |
| US-022 | Use text to complement a voice question | V1 enabler | Draft | Low |
| US-023 | Be transferred on explicit request | V1 core | Draft | High |
| US-024 | Be transferred when the bot lacks enough certainty | V1 core | Draft | High |
| US-025 | Provide the advisor with usable context | V1 core | Draft | High |
| US-026 | Hand off to Genesys with advisor context | V1 core | Draft | High |
| US-027 | Validate whether full Genesys voice routing is required for the pilot | V1 pilot gate | Draft | Medium |
| US-028 | Read the synthesis on the web page | V1 enabler | Draft | Medium |
| US-029 | Consult the global delta | V1 enabler | Draft | Medium |
| US-030 | Consult cause details | V1 enabler | Draft | Medium |
| US-031 | See evidence and analysis limits | V1 enabler | Draft | Medium |
| US-032 | Consult line-by-line invoice differences | V1 enabler | Draft | Medium |
| US-033 | Protect personal data exposed to the customer | V1 enabler | Draft | High |
| US-034 | Audit sensitive consultations | V1 enabler | Draft | High |
| US-035 | Disclose analysis limits | V1 core | Draft | High |
| US-036 | Measure key voice journey timings by pipeline slice | V1 pilot gate | Done (all six slices measured incl. `backend_first_token` via TASK-WEB-003-E; full-turn sample `scripts/turn_latency_sample.py`) | High |
| US-037 | Measure invoice comparison response time | V1 pilot gate | Draft | Medium |
| US-038 | Track escalations and their reasons | V1 pilot gate | Draft | Medium |
| US-039 | Track unresolved questions | V1 pilot gate | Draft | Medium |
| US-040 | Produce the pilot readiness report | V1 pilot gate | Draft | High |
| US-041 | End the call when the customer signals they are done (e.g. "au revoir") | V1 core | Draft (proposed 2026-07-16) — EPIC-006 | Medium |

## Technical Tasks

| Key | Title | Classification | Status | Priority |
|-----|-------|---|--------|----------|
| TASK-STT-001 | Create the voice runtime STT validation scaffold | V1 enabler | Done | High |
| TASK-STT-002 | Validate STT transcription quality with audio fixtures | V1 pilot gate | Done | High |
| TASK-STT-003 | Add OpenTelemetry instrumentation for STT validation | V1 pilot gate | Done | High |
| TASK-STT-004 | Produce the STT QA report and Gherkin scenarios | V1 pilot gate | Done | High |
| TASK-STT-005 | Redact bare sensitive identifiers in failure sanitization (closes RF-001) | V1 pilot gate | Done (Sprint 2) | Medium |
| TASK-STT-006 | Add a dedicated UNAVAILABLE STT outcome | V1 pilot gate | ✅ Done (Sprint 2, 2026-07-13) | Low |
| TASK-STT-007 | Expand the STT fixture set with multiple samples per category (closes RF-003, RF-005) | V1 pilot gate | Done (Sprint 2) | Medium |
| TASK-STT-008 | Connect the Gradium STT provider (fresh implementation) | V1 pilot gate | Done (STT sprint scope) | High |
| TASK-STT-009 | Detect and instrument end-of-turn for the voice journey (US-036 `end_of_turn` slice) | V1 pilot gate | ✅ Done (Sprint 2, 2026-07-13) | Medium |
| TASK-STT-010 | Stream partial STT transcripts to cut perceived latency (closes RF-007) | V1 pilot gate | ✅ Validated + merged (Sprint 6, 2026-07-16 — live tail 818 ms; RF-007 closed) | High |
| TASK-STT-011 | Normalize transcripts (case/punctuation/accents) before WER scoring (closes RF-008) | V1 pilot gate | Done (Sprint 2) | Medium |
| TASK-STT-012 | Streaming VAD-based end-of-turn detection (drop-in replacing the TASK-STT-009 batch detector) | V1 pilot gate | Planned (Sprint 6) | Medium |
| TASK-STT-013 | Reduce STT post-EOT finalize tail to meet ADR-0018 (`time_to_first_audio` p95 < 800 ms) | V1 pilot gate | ✅ Done (Sprint 6, validated 2026-07-17) — finalize on Gradium `flushed` ack; STT tail p95 1389→373 ms; composite p95 761.5 ms < 800 ms (gate MET); review 93/100 + QA GO | High |
| TASK-WEB-001 | Capture web voice and transcribe through Gradium STT (US-019 STT half) | V1 core | Done (merged) | High |
| TASK-WEB-002 | Speak the bot response on the web page (US-019 TTS half) | V1 core | Done (Sprint 3, merged → `feat/restart-from-scratch`) | High |
| TASK-WEB-003 | Orchestrate transcript to backend answer (US-019 STT/TTS bridge) — split A…G | V1 core | Done (Sprint 5, 2026-07-15; A–G merged into `feat/restart-from-scratch`) | High |
| TASK-WEB-003-A | Conversation contract + `BackendAnswerPort` (seam, no provider) | V1 core | Merged into sprint (2026-07-15; review 96/100) | High |
| TASK-WEB-003-B | Deterministic stub backend adapter (default, offline/dev + tests) | V1 core | Merged into sprint (2026-07-15; review 96/100; RF-017/RF-018) | High |
| TASK-WEB-003-C | HTTP backend adapter + `--backend {stub,http}` selection | V1 core | Merged into sprint (2026-07-15; review 93/100; resolves RF-016) | High |
| TASK-WEB-003-D | Wire the bridge (transcript → backend answer → TTS) on both runtimes | V1 core | Merged into sprint (2026-07-15; review 93/100; RF-019/RF-020) | High |
| TASK-WEB-003-E | End-to-end backend telemetry + `BACKEND_FIRST_TOKEN` slice (closes US-036 gap) | V1 pilot gate | Validated by user (2026-07-15; review 95/100; RF-021) — merged into sprint | High |
| TASK-WEB-003-F | Degraded mode: backend unavailable / low confidence → safe spoken fallback | V1 core | Merged into sprint (2026-07-15; resolves RF-020) | High |
| TASK-WEB-003-G | QA + behave + latency table + docs + conversation-contract ADR | V1 core | ✅ Done (Sprint 5, 2026-07-15; review 95/100; ADR-0021 + HTTP contract + QA report + latency sample) | High |
| TASK-WEB-004 | Stream the bot voice response — incremental TTS playback (US-036 `tts_first_audio` slice) | V1 core | ✅ Done (Sprint 6, 2026-07-16 — validated + merged; live first-audio 363 ms; review 96/100) | High |
| TASK-WEB-005 | Introduce the Pipecat batch runtime — run the web voice loop through a Pipecat pipeline, selectable alongside the stdlib fallback (US-019 runtime, ADR-0002) | V1 enabler | Done (Sprint 4) | High |
| TASK-WEB-007 | WebRTC transport (SmallWebRTCTransport + Pipecat JS client) driving the pipeline on one long-lived async loop (closes RF-012) | V1 core | Planned (Sprint 6) | High |
| TASK-WEB-008 | Barge-in during a spoken answer (US-021) — VAD onset stops playback, starts a new turn | V1 core | ✅ Validated by user (2026-07-16), merged into `feat/sprint-6-streaming` (branch deleted) | Medium |
| TASK-WEB-009 | Streaming QA + `time_to_first_audio` p95 < 800 ms latency report + ADR-0018 evidence (Sprint 6 close) | V1 pilot gate | ✅ Done (Sprint 6, 2026-07-16; review 92/100, QA functional Go). Baseline surfaced p95 1698 ms → gap **closed by TASK-STT-013** (final p95 761.5 ms, gate MET) | High |
| TASK-WEB-010 | End the call on a customer closing formula (US-041) — detect closing intent on final transcript, speak a closing, end the session; false-positive guard + end-of-call reason telemetry | V1 core | Proposed (2026-07-16, unscheduled) | Medium |
| TASK-ENV-001 | Standardize the voice-agent test virtualenv (fix `pipecat` `ModuleNotFoundError`) | Developer experience | ✅ Done (Sprint 5, 2026-07-15) | Medium |
| TASK-WEB-006 | Genericize voice error responses — stop echoing raw provider error text in `/stt` `/tts` `/turn` 502 bodies; return error_code + correlation id, keep full reason server-side (closes RF-013) | V1 hardening | ✅ Validated + merged into `feat/sprint-6-streaming` (2026-07-16) | Low |
| TASK-DOC-001 | Refresh stale "current-state" docs after Sprint 5 (README, CLAUDE.md, architecture spine, dev guide, docs/README, backlog statuses, ADR index, `.env.example`) — from the full-branch code review | Documentation | Done (2026-07-15) | Medium |
| TASK-WEB-012 | Confidence policy for billing answers — treat a `SUCCESS` answer with no confidence as degraded, or require the HTTP backend to emit confidence (closes RF-022, DEC-002) | V1 hardening | Gated (OQ-002 + billing answer engine) | Medium |
| TASK-WEB-013 | Unify telemetry imports in `web_voice` — point `ingress.py` at `voice_common.telemetry` for symmetry with `egress.py` (closes RF-023) | V1 hardening | Planned (opportunistic) | Low |
| TASK-BE-001 | Decide the backend answer-engine framework (Spring AI vs LangChain4J vs other) + ADR (closes OQ-007) | Decision / Architecture | ✅ Done (2026-07-18) — Spring Boot + Spring AI (ADR-0026) + Hive-light decomposition (ADR-0027); OpenJDK 17 baseline | High |
| TASK-BE-002 | Scaffold the Java backend module on the restart branch (hexagonal skeleton, build + ArchUnit green) | V1 enabler | ✅ Validated by user (2026-07-18) — context-first ADR-0027 scaffold, 19 tests green on OpenJDK 17, review 94/100 + QA PASS; merge-ready | High |
| TASK-BE-003 | Knowledge-base ingestion socle (pivot + Markdown connector + idempotent sync + pgvector 768 + swappable embedding adapter) | V1 enabler | Planned (Sprint 7) | High |
| TASK-BE-004 | RAG retrieval + domain guardrails before/after (ADR-0014) | V1 core | ✅ Validated + merged into sprint (2026-07-19, ff) — review 93/100 + QA GO; `mvn test` 86 green; live RAG retrieval p95 37 ms warm | High |
| TASK-BE-005 | Provider-agnostic LLM wording (Mistral API default, Ollama alt), grounded + no invented amounts (DEC-002) | V1 core | Planned (Sprint 7) | High |
| TASK-BE-006 | Conversation endpoint implementing the ADR-0021 contract + short conversation memory | V1 core | Planned (Sprint 7) | High |
| TASK-BE-007 | Streaming-token answer (SSE) per ADR-0013 — `backend.first_token` ≠ `backend.request` (RF-021) | V1 core | Planned (Sprint 7; Medium, may defer) | Medium |
| TASK-BE-008 | Wire `voice-agent --backend http` end to end to the real endpoint (stub → real) | V1 core | Planned (Sprint 7) | High |
| TASK-BE-009 | Backend observability: OTel traces/metrics/logs across guardrails, retrieval, LLM (DEC-010, ADR-0010) | V1 pilot gate | Planned (Sprint 7) | High |
| TASK-BE-010 | QA functional + latency report (RAG + LLM slices; composite with real backend) + adversarial review | V1 pilot gate | Planned (Sprint 7) | High |
| TASK-BE-011 | CSV article connector — bulk KB ingestion from `articles.csv` (HTML→text, batch embedding) | V1 core (KB content) | Planned (out of Sprint 7 theme) | High |
| TASK-BE-012 | Backend REST error contract (`GlobalExceptionHandler` + `ErrorResponse`, sanitized, correlation id) | V1 hardening | Planned (out of Sprint 7 core theme) | Medium |

## Planned Sprints

| Key | Title | Status | Goal |
|-----|-------|--------|------|
| SPRINT-STT | STT Validation | ✅ Done (2026-07-10) | Validate fixture-based speech-to-text transcription, timing, OpenTelemetry evidence and QA readiness |
| SPRINT-2-STT-HARDENING | STT Hardening | ✅ Done (2026-07-13) | Make the WER quality gate usable (normalization) and complete STT observability (fixtures, sanitization, UNAVAILABLE outcome, end-of-turn) — `sprints/sprint-2-stt-hardening.md` |
| SPRINT-3-TTS | TTS / Voice-out (batch) | ✅ Done (2026-07-13, merged → `feat/restart-from-scratch`) | Speak the bot response and close the first end-to-end voice loop (no streaming yet) — `sprints/sprint-3-tts-voice-out.md` |
| SPRINT-4-PIPECAT | Pipecat runtime migration (batch parity) | ✅ Done (2026-07-14, merged → `feat/restart-from-scratch`) | Run the web voice batch loop (STT → echo → TTS) through a Pipecat pipeline (pipeline-only, no WebRTC/streaming), selectable via `--runtime` and shipped as the default, with the stdlib path kept as fallback/comparison (TASK-WEB-005) — `sprints/sprint-4-pipecat-batch.md` |
| SPRINT-5-BACKEND-BRIDGE | Backend answer bridge (US-019 close) | ✅ Done (2026-07-15) | Turn the echo loop into a real answer loop: transcript → `BackendAnswerPort` (stub default + HTTP) → response text → TTS, one correlation id end to end, closing US-019 and the US-036 `backend_first_token` gap (TASK-WEB-003 A…G) — `sprints/sprint-5-backend-bridge.md` |
| SPRINT-6-STREAMING | Streaming voice loop & latency (US-019 optimization, US-021) | ✅ Done (closed 2026-07-17, merged → `feat/restart-from-scratch`) — **ADR-0018 gate MET** (`time_to_first_audio` p95 761.5 ms < 800 ms) via TASK-STT-013 + TASK-WEB-011 | WebRTC transport (TASK-WEB-007, closes RF-012) + streaming VAD (TASK-STT-012) + streaming STT (TASK-STT-010) + streaming TTS (TASK-WEB-004) + barge-in (TASK-WEB-008 / US-021) + generic voice errors (TASK-WEB-006, closes RF-013) + QA/latency close (TASK-WEB-009) + finalize-tail reduction (TASK-STT-013), targeting `time_to_first_audio` p95 < 800 ms — `sprints/sprint-6-streaming.md` |
| SPRINT-7-ANSWER-ENGINE | Real conversation answer engine — RAG over the knowledge base (EPIC-005) | 📋 Planned (prep 2026-07-17; **not started**) — hard entry gate: Sprint 6 closed/validated (OQ-005) | Turn the stub answer into a real, KB-grounded answer engine behind the ADR-0021 contract: framework decision (TASK-BE-001, closes OQ-007) → backend scaffold (TASK-BE-002) → KB ingestion/pgvector (TASK-BE-003) → RAG + guardrails (TASK-BE-004) → provider-agnostic LLM wording (TASK-BE-005) → conversation endpoint + memory (TASK-BE-006) → streaming tokens (TASK-BE-007) → wire `--backend http` (TASK-BE-008) → observability (TASK-BE-009) → QA + latency (TASK-BE-010). Scoped to KB-grounded answers; customer identity/BSS/PDF/comparison stay gated (OQ-001/003/004) — `sprints/sprint-7-answer-engine.md` |

## Restart Delivery Notes

The recommended first implementation sequence is:

1. EPIC-001 to freeze the restart baseline and delivery slicing.
2. EPIC-002 and EPIC-003 to secure identity, evidence access and fixtures.
3. EPIC-004 and EPIC-005 to prove billing value before voice polish.
4. EPIC-006 and EPIC-007 to expose the value through Voice2Voice and Genesys
   advisor handoff.
5. EPIC-008, EPIC-009 and EPIC-010 to validate the web evidence view, trust
   controls and pilot observability.

## Post-MVP / Roadmap

| Item | Reason |
|---|---|
| Generic PDF / Confluence / database KB connectors | Useful for knowledge enrichment, but not required for the first billing V1 if Markdown pricing rules and invoice PDF extraction are available |
| WhatsApp production channel | Future asynchronous adapter gated by channel contracts, quotas, observability and degraded modes |
| Full Genesys voice routing | Useful for contact-center-native bot routing, but V1 requires Genesys advisor handoff only unless the pilot mandates Genesys voice entry |
| GPU/self-hosting | Sovereignty or latency optimization option, not a V1 prerequisite |
| Custom brand voice | Product polish after the billing journey is reliable |

## Open Questions

| Key | Topic | Owner | Status |
|-----|-------|-------|--------|
| OQ-001 | Customer identification by phone and web voice channel | Product / BSS / Security | Open |
| OQ-002 | Minimum proof threshold for answering without escalation | Product / Billing SME / Legal | Open |
| OQ-003 | BSS data availability and granularity | BSS owner | Open |
| OQ-004 | Invoice PDF extraction reliability and fixture coverage | Product / BSS / QA | Open |
| OQ-005 | Pilot latency acceptance context | Product / Architecture / Operations | ✅ Decided (2026-07-20) — ADR-0029 (mouth-to-ear p95 ≤ 1.5 s / `time_to_first_audio` p95 ≤ 1.2 s; cascade reaffirmed; TASK-WEB-009 prerequisite) |
| OQ-006 | Genesys handoff integration shape | Product / Contact Center / Architecture / Security | Open |
| OQ-007 | Backend AI/RAG framework (Spring AI vs LangChain4J vs other) | Architecture / Backend | ✅ Decided (2026-07-17) — Spring Boot + Spring AI (ADR-0026); TASK-BE-001 implements |

## Review Findings

Non-blocking findings and their residual risk are tracked in
`product-backlog/review-findings.md` (RF-001 … RF-011 to date). Actionable ones are
ticketed as TASK-STT-005/006/007/008/010/011; gated ones link their blocking
dependency (RF-006 → OQ-001 / TASK-WEB-003). RF-003 became actionable once Gradium
was selected (DEC-005, TASK-STT-008); RF-007 (chunked/streaming ingress) → TASK-STT-010;
RF-008 (WER normalization, surfaced by the first live Gradium run) → TASK-STT-011.

## Decisions

| Key | Decision | Status |
|-----|----------|--------|
| DEC-001 | V1 focuses on invoice explanation while the product remains extensible to general support | Accepted via ADR-0017 |
| DEC-002 | BSS evidence is the source of truth and the LLM only words the explanation | Accepted via ADR-0003 |
| DEC-003 | Invoice PDFs are a V1 evidence source until structured lines are validated | Accepted via ADR-0005 |
| DEC-004 | Voice2Voice is mandatory in V1 | Accepted in `v1-scope.md` |
| DEC-005 | Voice provider choices remain replaceable behind adapters | Accepted via ADR-0002 |
| DEC-006 | Human escalation is required | Accepted via ADR-0019 |
| DEC-007 | Backend owns conversation intelligence; voice runtime owns media orchestration | Accepted via ADR-0001 and ADR-0011 |
| DEC-008 | V1 routing prioritizes billing explanation while support/sales agents remain foundation capabilities | Accepted via ADR-0017 and ADR-0015 |
| DEC-009 | Genesys handoff is in V1, full Genesys voice routing remains optional | Accepted via ADR-0019 and ADR-0020 |
| DEC-010 | Pilot observability requires per-step latency traces before any production SLO claim | Accepted via ADR-0010 and ADR-0018 |
| DEC-011 | Chat LLM: Mistral API is the development default; OpenAI is the POC target (live validation gated on credentials); Ollama stays the local alternative. Embedding also stays behind its own replaceable adapter (default Ollama `nomic-embed-text` 768; dimension change ⇒ recreate `vector_store` + re-sync). All behind replaceable provider ports | Accepted (user, 2026-07-17) |
