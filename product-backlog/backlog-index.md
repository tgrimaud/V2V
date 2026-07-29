# Backlog Index

## Restart Baseline

This branch restarts implementation from scratch (previous implementation kept on
`main` as backup/reference). **EPIC** rows below stay at product-level `Draft` on
purpose — they are re-accepted by Product/Architecture/Security/Delivery, not by
delivery progress. **Delivery has, however, progressed:** through **Sprint 9** the
web Voice2Voice loop, the Java RAG answer engine, streaming/WebRTC/barge-in and
observability are built and validated. The authoritative *delivered* state is the
**Sprint registry** and the **story/task Status columns** below (e.g. US-003, US-019,
US-036, US-041 and Sprints STT→9 marked Done), not the epic rows. Epics whose
stories are largely delivered (notably EPIC-006 Voice2Voice foundation for the web
channel) remain `Draft` only for want of a formal product re-acceptance pass.

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
| EPIC-011 | Multi-agent orchestration / domain routing (rebuild the query-time router: intent classification reusing the ingestion `DomainClassifier`, `AgentProfile` per domain, dispatch + session stickiness) | V1 core | Draft (2026-07-21) — sprint after Sprint 8; depends on Sprint 8 domain tags | High |

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
| US-020 | Receive a quick spoken acknowledgement during long analysis | V1 core | Planned (Sprint 10 — pilot-latency, via TASK-WEB-019) | Medium |
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
| TASK-STT-012 | Streaming VAD-based end-of-turn detection (drop-in replacing the TASK-STT-009 batch detector) | V1 pilot gate | ✅ Done (merged Sprint 6, 2026-07-16; review 93/100 + QA Go) — on `feat/restart-from-scratch` | Medium |
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
| TASK-WEB-007 | WebRTC transport (SmallWebRTCTransport + Pipecat JS client) driving the pipeline on one long-lived async loop (closes RF-012) | V1 core | ✅ Merged (Sprint 6, `5669d85`) | High |
| TASK-WEB-008 | Barge-in during a spoken answer (US-021) — VAD onset stops playback, starts a new turn | V1 core | ✅ Validated by user (2026-07-16), merged into `feat/sprint-6-streaming` (branch deleted) | Medium |
| TASK-WEB-009 | Streaming QA + `time_to_first_audio` p95 < 800 ms latency report + ADR-0018 evidence (Sprint 6 close) | V1 pilot gate | ✅ Done (Sprint 6, 2026-07-16; review 92/100, QA functional Go). Baseline surfaced p95 1698 ms → gap **closed by TASK-STT-013** (final p95 761.5 ms, gate MET) | High |
| TASK-WEB-010 | End the call on a customer closing formula (US-041) — detect closing intent on final transcript, speak a closing, end the session; false-positive guard + end-of-call reason telemetry | V1 core | ✅ Done (2026-07-27, Sprint 9, ADR-0035) — merged into `feat/restart-from-scratch` (`task/TASK-WEB-010-call-end-farewell`); adversarial review ≥90% + QA + **user live validation** passed | Medium |
| TASK-ENV-001 | Standardize the voice-agent test virtualenv (fix `pipecat` `ModuleNotFoundError`) | Developer experience | ✅ Done (Sprint 5, 2026-07-15) | Medium |
| TASK-WEB-006 | Genericize voice error responses — stop echoing raw provider error text in `/stt` `/tts` `/turn` 502 bodies; return error_code + correlation id, keep full reason server-side (closes RF-013) | V1 hardening | ✅ Validated + merged into `feat/sprint-6-streaming` (2026-07-16) | Low |
| TASK-DOC-001 | Refresh stale "current-state" docs after Sprint 5 (README, CLAUDE.md, architecture spine, dev guide, docs/README, backlog statuses, ADR index, `.env.example`) — from the full-branch code review | Documentation | Done (2026-07-15) | Medium |
| TASK-DOC-002 | Reconcile "current-state" docs after Sprint 9 (README, CLAUDE.md, architecture spine, ADR index + ADR-0032 row, docs/README, dev guide, operations/backlog, v1-scope, functional spec, KB guide/technical, channel-identity-boundary, backlog-index epic note) — from the full adversarial code+doc review drift register D1–D14 | Documentation | ✅ Done (2026-07-28) — merged into `feat/restart-from-scratch` (ff `24995a9..4770ee0`, 15 files); branch deleted. Source review: `docs/architecture/reviews/full-adversarial-review-2026-07-28.md`. Spawned follow-up tickets TASK-BE-019, TASK-WEB-018, TASK-OBS-001 | Medium |
| TASK-WEB-012 | Confidence policy for billing answers — treat a `SUCCESS` answer with no confidence as degraded, or require the HTTP backend to emit confidence (closes RF-022, DEC-002) | V1 hardening | ✅ Implemented (2026-07-27) — three-band backend confidence policy + env-tunable Python client floor (RF-022); ADR-0034. Definitive threshold value still gated by OQ-002 | Medium |
| TASK-WEB-013 | Unify telemetry imports in `web_voice` — point `ingress.py` at `voice_common.telemetry` for symmetry with `egress.py` (closes RF-023) | V1 hardening | ✅ Merged into `feat/sprint-9-hardening` (2026-07-23, ff; branch deleted) — one-line import change, 334 unittest + 26 behave green. Not runtime-affecting (same classes via shim) | Low |
| TASK-WEB-014 | Instrument true mouth-to-ear latency — fold `channel_egress` (WebRTC) + end-of-turn hold into a perceived-latency metric and evaluate vs ADR-0029 (closes the ADR-0018/TASK-WEB-009 known gap) | V1 pilot gate | ✅ Merged into `feat/restart-from-scratch` (2026-07-23) — `voice_to_first_audio` composite + `ChannelEgressProbe` (WebRTC egress) + ADR-0029 gate + client first-audible proxy; unittest 334 / behave 26 green; docs updated. Remaining before pilot: warm live sample vs real backend + adversarial/QA → **scheduled in Sprint 10 (pilot-latency)** | High |
| TASK-WEB-015 | Perceived-latency optimization levers — backend-stream-to-TTS (first sentence, ~−700-900 ms), connect-time STT/LLM warm-up (~−450 ms turn 1), end-of-turn hold tuning (~−150 ms); baseline measured at the Sprint 7 demo (cold ~2.95 s / warm ~2.50 s to first audio) | V1 pilot gate | Planned (**Sprint 10 — pilot-latency**, promoted 2026-07-29; baseline from Sprint 7 demo); depends on TASK-WEB-014 (optimize against a measured baseline) | High |
| TASK-WEB-019 | Spoken filler / acknowledgement while the answer is being prepared (delivers US-020) — short neutral holding phrase on the voice channel when backend+LLM+TTS exceed a perceived-wait threshold, so the caller knows the turn is still progressing; barge-in preserved, no fabricated billing content (DEC-002), one acknowledgement per turn | V1 pilot gate (perceived latency) | Merge-ready — V1 generic filler on `task/TASK-WEB-019-filler-phrase` (2026-07-29); adversarial review 92/100 (barge-in cleanup fixed); QA GO (filler +~5 ms to the answer, concurrent); trigger = runtime `AnswerProcessor` timer, plain `TextFrame`, **no broker** (ADR-0036); telemetry `voice.filler.spoken`; `docs/qa/task-web-019-filler-qa-report.md`; merge on user request | Medium |
| TASK-WEB-016 | OpenAPI YAML for the Python voice runtime (`web_voice` `/api/voice/*`, stdlib no framework) — hand-written spec from the HTTP contract doc, served/versioned | V1 hardening | Implemented (2026-07-28, Sprint 9) — `web_voice/openapi.yaml` (3.0.3) covers stt/tts/turn/webrtc + meta route, served at `GET /api/voice/openapi.yaml`; 5 tests incl. drift guard vs server routes; unittest 390 green; adversarial ~95/100 | Medium |
| TASK-WEB-017 | Per-turn identity on WebRTC streaming telemetry — add a per-turn id (`message_id`/turn index) to streaming spans while keeping the stable per-conversation `correlation_id`, so per-turn latency (p50/p95/p99) can be derived from live/browser sessions (streaming emitters currently propagate only `correlation_id`; one envelope per session → turns overwrite) | V1 hardening (observability) | Implemented (2026-07-23, Sprint 9) — per-turn baggage on `TelemetryRecorder.begin_turn`, `(correlation_id, turn_index)` bucketing + `per_turn` report section; unittest 346 (+12) + behave 27 green; adversarial 93/100; QA passed (`docs/qa/task-web-017-per-turn-telemetry-qa.md`); warm **live** Gradium+Mistral multi-turn WebRTC sample captured (`turn_index` 1/2/3, 3 distinct `message_id`/one `conversation_id`, every slice span once per turn; real per-turn `time_to_first_audio` 5154/5740/5350 ms); branch `task/TASK-WEB-017-streaming-per-turn-telemetry-id`. Done (SLO latency = separate STT-finalize concern, TASK-STT-010/011) | Medium |
| TASK-BE-001 | Decide the backend answer-engine framework (Spring AI vs LangChain4J vs other) + ADR (closes OQ-007) | Decision / Architecture | ✅ Done (2026-07-18) — Spring Boot + Spring AI (ADR-0026) + Hive-light decomposition (ADR-0027); OpenJDK 17 baseline | High |
| TASK-BE-002 | Scaffold the Java backend module on the restart branch (hexagonal skeleton, build + ArchUnit green) | V1 enabler | ✅ Merged into `feat/restart-from-scratch` (2026-07-18, `f12e4be`) — context-first ADR-0027 scaffold, 19 tests green on OpenJDK 17, review 94/100 + QA PASS + user validation | High |
| TASK-BE-003 | Knowledge-base ingestion socle (pivot + Markdown connector + idempotent sync + pgvector 768 + swappable embedding adapter) | V1 enabler | ✅ Merged (Sprint 7, 2026-07-18, `4c01e60`) | High |
| TASK-BE-004 | RAG retrieval + domain guardrails before/after (ADR-0014) | V1 core | ✅ Validated + merged into sprint (2026-07-19, ff) — review 93/100 + QA GO; `mvn test` 86 green; live RAG retrieval p95 37 ms warm | High |
| TASK-BE-005 | Provider-agnostic LLM wording (Mistral API default, Ollama alt), grounded + no invented amounts (DEC-002) | V1 core | ✅ Merged (Sprint 7, 2026-07-19, `02ce524`) | High |
| TASK-BE-006 | Conversation endpoint implementing the ADR-0021 contract + short conversation memory | V1 core | ✅ Merged (Sprint 7, `1980ff6`) | High |
| TASK-BE-007 | Streaming-token answer (SSE) per ADR-0013 — `backend.first_token` ≠ `backend.request` (RF-021) | V1 core | ✅ Merged (Sprint 7, `1749e7e`) | Medium |
| TASK-BE-008 | Wire `voice-agent --backend http` end to end to the real endpoint (stub → real) | V1 core | ✅ Merged (Sprint 7, `28950d7`) | High |
| TASK-BE-009 | Backend observability: OTel traces/metrics/logs across guardrails, retrieval, LLM (DEC-010, ADR-0010) | V1 pilot gate | ✅ Merged (Sprint 7, `fe7e0fc`) — Micrometer/logs baseline; OTLP export added later by TASK-OBS-001 | High |
| TASK-BE-010 | QA functional + latency report (RAG + LLM slices; composite with real backend) + adversarial review | V1 pilot gate | ✅ Merged (Sprint 7, `3a14da4`) | High |
| TASK-BE-012 | Backend REST error contract (`GlobalExceptionHandler` + `ErrorResponse`, sanitized, correlation id) | V1 hardening | ✅ Merged (Sprint 7, `fe7e0fc`) | High |
| TASK-BE-013 | `CsvArticleConnector` + embedding `DomainClassifier` — bulk KB ingestion from `articles.csv` (CommonsCSV, jsoup HTML→text, `language=en`, domain classified vs anchors) | V1 core (KB content) | ✅ Validated + merged (Sprint 8, 2026-07-21) — adversarial 92/100, QA PASS, live (threshold 0.55) | High |
| TASK-BE-014 | Batch embedding/insert — `VectorStorePort.storeChunks` + sync progress metrics/logs (perf, anti-timeout for bulk CSV) | V1 core (KB content) | ✅ Validated + merged (Sprint 8, 2026-07-21) — adversarial 93/100, QA PASS, live (full corpus ~73s, idempotent re-sync) | High |
| TASK-BE-015 | Answer language handling — bot answers in the customer's question language (FR/EN), consistently across answers/fallbacks/refusal/escalation; configurable default (EN for Eir pilot); per-turn + session stickiness | V1 core (answer quality) | ✅ Validated + merged (Sprint 8, 2026-07-23) — FR/EN answers/fidelity/telemetry live; QA-found **BUG-002** (fallback language stickiness) fixed + live QA retest PASS | High |
| TASK-BE-016 | OpenAPI/Swagger for the Java backend — `springdoc-openapi` + `/swagger-ui` + `/v3/api-docs`, `@Tag`/`@Operation` on controllers | V1 hardening | ✅ Done (2026-07-28, Sprint 9) — merged into `feat/restart-from-scratch`; springdoc 2.8.14 pinned, live OpenAPI 3.1; `mvn test` 305 green (Sprint 9 closure) | Medium |
| TASK-BE-018 | Concise voice-first answers — cap answer length via LLM prompt budget to cut TTS synthesis time (batch `/turn` ≈14 s, live tail); no grounding regression (BUG-004) | V1 answer quality / latency | ✅ Merged into `feat/restart-from-scratch` (2026-07-23, ff `f5467c4..e662f79`) — adversarial 92/100 + QA **Go** (live A/B: answer chars p50 −33 %/p95 −63 %, `llm_wording` p50 −30 %/p95 −34 %, 0 regression); `mvn test` 229 green. ADR-0033/ADR-0029 | High |
| TASK-BE-019 | Authenticate/isolate the unauthenticated backend endpoints (`/api/knowledge/ingest`, `/sync`, `/api/conversation/answer`, `/retrieve`) — same `x-api-key` gate as `/converse` or internal-only binding; fail-closed + security tests | V1 security hardening | 🚧 Implemented (2026-07-28) on `task/TASK-BE-019-endpoint-auth` — central `ApiKeyAuthInterceptor` gates the 4 endpoints, sanitized 401 `ERR_401`, pilot semantics kept (empty key = open, enforced when set); `mvn test` **312** green (+7). ✅ Adversarial review 93/100 + QA GO (live gate smoke on :8081, `ProtectedEndpointsApiKeyTest` 7/7) — ✅ Merged into `feat/restart-from-scratch` (2026-07-28, `e5cb64a`) — `tasks/backend-hardening-tasks.md` | High |
| TASK-WEB-018 | Speak a degraded fallback on streaming STT failure (WebRTC) — parity with the batch `/turn` 502; no silent call, no fabricated transcript (DEC-002) | V1 hardening (degraded mode) | 🚧 Implemented (2026-07-28) on `task/TASK-WEB-018-streaming-stt-degraded-fallback` — `StreamingSttProcessor` speaks `DEGRADED_FALLBACK_TEXT` (plain TextFrame, no transcript) on finalize error/timeout + `voice.stt.degraded_spoken` event; unittest 391 + behave 31 scenarios green. ✅ Adversarial review + QA GO (failure→spoken-fallback, DEC-002, barge-in intact; live Gradium deferred to pilot) — ✅ Merged into `feat/restart-from-scratch` (2026-07-28, `62fce07`) — `tasks/web-voice-tasks.md` | Medium |
| TASK-OBS-001 | OpenTelemetry export (OTLP) for backend + voice runtime (currently Micrometer + stderr spans), or record the accepted residual risk in ADR-0028 | V1 hardening (observability) | ✅ Merged into `feat/restart-from-scratch` (2026-07-29, ff `bfde816..e79964b`; ticket branch deleted) — **hybrid**: ADR-0028 addendum accepts the pilot residual risk + mandatory-export trigger, AND env-gated OTLP wiring (default OFF) on both services + opt-in collector recipe (`deploy/observability/`). Backend `mvn test` 312 green + export-off startup clean; voice unittest 396 (+5) + behave 31 green; live backend→collector smoke exported real traces + metrics. Cross-service correlated-trace (traceparent) deferred behind the trigger. **Adversarial review 93/100 (Pass) + QA GO (2026-07-29)**: OTLP-specific tests 5 green, default-off gate inert, live backend→collector smoke exported real traces + metrics, telemetry attributes confirmed technical-only (no PII egress). — `tasks/observability-tasks.md` | Medium |

## Planned Sprints

| Key | Title | Status | Goal |
|-----|-------|--------|------|
| SPRINT-STT | STT Validation | ✅ Done (2026-07-10) | Validate fixture-based speech-to-text transcription, timing, OpenTelemetry evidence and QA readiness |
| SPRINT-2-STT-HARDENING | STT Hardening | ✅ Done (2026-07-13) | Make the WER quality gate usable (normalization) and complete STT observability (fixtures, sanitization, UNAVAILABLE outcome, end-of-turn) — `sprints/sprint-2-stt-hardening.md` |
| SPRINT-3-TTS | TTS / Voice-out (batch) | ✅ Done (2026-07-13, merged → `feat/restart-from-scratch`) | Speak the bot response and close the first end-to-end voice loop (no streaming yet) — `sprints/sprint-3-tts-voice-out.md` |
| SPRINT-4-PIPECAT | Pipecat runtime migration (batch parity) | ✅ Done (2026-07-14, merged → `feat/restart-from-scratch`) | Run the web voice batch loop (STT → echo → TTS) through a Pipecat pipeline (pipeline-only, no WebRTC/streaming), selectable via `--runtime` and shipped as the default, with the stdlib path kept as fallback/comparison (TASK-WEB-005) — `sprints/sprint-4-pipecat-batch.md` |
| SPRINT-5-BACKEND-BRIDGE | Backend answer bridge (US-019 close) | ✅ Done (2026-07-15) | Turn the echo loop into a real answer loop: transcript → `BackendAnswerPort` (stub default + HTTP) → response text → TTS, one correlation id end to end, closing US-019 and the US-036 `backend_first_token` gap (TASK-WEB-003 A…G) — `sprints/sprint-5-backend-bridge.md` |
| SPRINT-6-STREAMING | Streaming voice loop & latency (US-019 optimization, US-021) | ✅ Done (closed 2026-07-17, merged → `feat/restart-from-scratch`) — **ADR-0018 gate MET** (`time_to_first_audio` p95 761.5 ms < 800 ms) via TASK-STT-013 + TASK-WEB-011 | WebRTC transport (TASK-WEB-007, closes RF-012) + streaming VAD (TASK-STT-012) + streaming STT (TASK-STT-010) + streaming TTS (TASK-WEB-004) + barge-in (TASK-WEB-008 / US-021) + generic voice errors (TASK-WEB-006, closes RF-013) + QA/latency close (TASK-WEB-009) + finalize-tail reduction (TASK-STT-013), targeting `time_to_first_audio` p95 < 800 ms — `sprints/sprint-6-streaming.md` |
| SPRINT-7-ANSWER-ENGINE | Real conversation answer engine — RAG over the knowledge base (EPIC-005) | ✅ Done (closed 2026-07-20, merged → `feat/restart-from-scratch`, ff `49ded02..6ab8b78`) — 12 tickets (TASK-BE-001…012) validated; checks rerun green (backend 160, voice-agent 315 unittest + 26 Behave); latency fil closed by **ADR-0029** (OQ-005 resolved; TASK-WEB-014 out-of-sprint) | Turn the stub answer into a real, KB-grounded answer engine behind the ADR-0021 contract: framework decision (TASK-BE-001, closes OQ-007) → backend scaffold (TASK-BE-002) → KB ingestion/pgvector (TASK-BE-003) → RAG + guardrails (TASK-BE-004) → provider-agnostic LLM wording (TASK-BE-005) → conversation endpoint + memory (TASK-BE-006) → streaming tokens (TASK-BE-007) → wire `--backend http` (TASK-BE-008) → observability (TASK-BE-009) → QA + latency (TASK-BE-010) → error contract (TASK-BE-012) → latency levers (TASK-BE-011). Scoped to KB-grounded answers; customer identity/BSS/PDF/comparison stay gated (OQ-001/003/004) — `sprints/sprint-7-answer-engine.md` |
| SPRINT-8-CSV-KB-INGESTION | CSV knowledge-base ingestion (articles.csv) | ✅ Done (closed 2026-07-23, merged → `feat/restart-from-scratch`) — 3 tickets validated: TASK-BE-013 (`CsvArticleConnector` + embedding `DomainClassifier`) + TASK-BE-014 (batched embedding/insert) + TASK-BE-015 (answer language FR/EN) with QA-found **BUG-002** (fallback language stickiness) fixed + live QA retest PASS; closure checks green (backend 229, voice-agent 316 unittest + 26 Behave). BUG-001 (guardrail over-block) out-of-sprint P2 | Ingest the real operator KB CSV export (`articles.csv`, HTML `content`) via a new `CsvArticleConnector` on the BE-003 socle, with an embedding `DomainClassifier` to tag mixed content by domain (TASK-BE-013) and batched embedding/insert for the volume (TASK-BE-014); answer in the customer's FR/EN language (TASK-BE-015). Billing/identity theme shifts to Sprint 10, telephony/Genesys to Sprint 11 (Sprint 9 is a hardening/assainissement sprint) — `sprints/sprint-8-csv-kb-ingestion.md` |
| SPRINT-9-HARDENING | Hardening / assainissement — accumulated small improvements & set-aside debt | ✅ Done (2026-07-28) — all tickets merged into `feat/restart-from-scratch`: Tier A (TASK-WEB-013/017, RF-017, RF-019 live re-validated; TASK-ENV-001 + TASK-STT-012 reconciled as already-delivered), Tier B OpenAPI (TASK-BE-016 + TASK-WEB-016), TASK-WEB-010 (closing formula), functional debt (BUG-004, BUG-005, BUG-001, TASK-WEB-012). Post-close integration green: backend 305, voice-agent unittest 390, behave 30/140. Latency pilot-gate (TASK-WEB-014/015) stayed OUT → Sprint 10 (billing/identity), Sprint 11 (telephony/Genesys) — `sprints/sprint-9-hardening.md` |
| SPRINT-10-PILOT-LATENCY | Pilot-readiness latency & perceived latency (EPIC-010 + EPIC-006/US-020) | In progress (started 2026-07-29 with TASK-WEB-019) — pilot-readiness latency theme, promoted ahead of billing by user decision | Validate and reduce **perceived** voice latency before the billing theme: close TASK-WEB-014 with a warm live sample + adversarial/QA, land the TASK-WEB-015 optimization levers, and add spoken filler/acknowledgement phrases (TASK-WEB-019 / US-020) so waits feel responsive — `sprints/sprint-10-pilot-latency.md` |
| SPRINT-11-BILLING-IDENTITY | Customer identity + BSS/PDF evidence + deterministic comparison (EPIC-002/003/004) | Planned (tentative) — gated by OQ-001/003/004 (shifted from Sprint 10 on 2026-07-29) | Prove billing value with real customer identity and BSS/PDF evidence behind the answer engine |
| SPRINT-12-TELEPHONY-GENESYS | Telephony channel (US-018) + Genesys advisor handoff (EPIC-007) | Planned (tentative) — gated by OQ-006 (shifted from Sprint 11 on 2026-07-29) | Expose the journey over telephony and hand off to a Genesys advisor |

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
| OQ-005 | Pilot latency acceptance context | Product / Architecture / Operations | ✅ Decided (2026-07-20) — ADR-0029 (mouth-to-ear p95 ≤ 1.5 s / `time_to_first_audio` p95 ≤ 1.2 s; cascade reaffirmed; TASK-WEB-014 prerequisite) |
| OQ-006 | Genesys handoff integration shape | Product / Contact Center / Architecture / Security | Open |
| OQ-007 | Backend AI/RAG framework (Spring AI vs LangChain4J vs other) | Architecture / Backend | ✅ Decided (2026-07-17) — Spring Boot + Spring AI (ADR-0026); TASK-BE-001 implements |

## Review Findings

Non-blocking findings and their residual risk are tracked in
`product-backlog/review-findings.md` (RF-001 … RF-011 to date). Actionable ones are
ticketed as TASK-STT-005/006/007/008/010/011; gated ones link their blocking
dependency (RF-006 → OQ-001 / TASK-WEB-003). RF-003 became actionable once Gradium
was selected (DEC-005, TASK-STT-008); RF-007 (chunked/streaming ingress) → TASK-STT-010;
RF-008 (WER normalization, surfaced by the first live Gradium run) → TASK-STT-011.

## Bugs

| Bug | Title | Severity | Status | Notes |
|-----|-------|:--------:|--------|-------|
| [BUG-001](bugs/BUG-001-input-guardrail-blocks-legitimate-phishing-support.md) | Input guardrail refuses legitimate phishing/scam-call support questions | Medium | New (P2) — scheduled Sprint 9 | Surfaced in Sprint 8 live test; belongs to Sprint 7 guardrail (ADR-0014). Scheduled in Sprint 9 (hardening/assainissement). |
| [BUG-003](bugs/BUG-003-kb-chunking-brittle-retrieval-handoff.md) | Over-fragmented KB chunking evicts the answer chunk from top-K → LLM hand-off → "not enough info" on covered topics | High | Fixed — live-validated (P1) | `TextChunker` rewritten (contiguous hard-split, word boundaries, no header-only chunks, `###`), topK 4→8, clean re-ingest. Retrieval now reliably PASSES ≈0.85; live FR turn grounded. Residual LLM refusal split out to BUG-004. EPIC-005. |
| [BUG-004](bugs/BUG-004-llm-intermittent-handoff-despite-grounded-evidence.md) | LLM intermittently refuses ("transfer to advisor") despite passing evidence (≈0.85) → OutputGuardrail rewrites to low-confidence fallback (grounded=false) | High | ✅ Closed — live-validated (Sprint 9, 2026-07-27) | Fix `5fd6c21` (hand-off conditioned on unusable context + temp 0.3→0.2) already merged in `feat/sprint-9-hardening`. Live A/B on running fixed build: greeting variant **20/20 grounded** (was ~1/7), no-greeting 10/10, "ma box" 8/8, off-topic refused 3/3, DEC-002 preserved; backend log 41 grounded=true/3 false (=off-topic); `AnswerLanguageTest` 8/8 green. EPIC-005. |
| [BUG-005](bugs/BUG-005-internal-kb-content-leaked-to-end-user.md) | Internal agent-facing KB content (R6/ION, VAA) spoken to the end user on a vague turn ("vas-y"); confidence ≈0.52 still PASSES instead of asking to clarify | High | ✅ Implemented (P1, 2026-07-27) — pending live retest | Fixed on `fix/BUG-005-internal-kb-content-leak`: (1) `AudienceClassifier` tags articles `customer`/`internal` at ingestion + fail-closed `audience==customer` retrieval filter; (2) three-band confidence guardrail + vague-turn detection → `CLARIFY`. ADR-0034; adversarial 92/100; Java 262 / Python 353 + behave 27 green. Requires KB re-sync on deploy. |

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
