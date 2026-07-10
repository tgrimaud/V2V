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
| US-019 | Ask from a web voice chat | V1 core | In progress | High |
| US-020 | Receive a quick spoken acknowledgement during long analysis | V1 core | Draft | Medium |
| US-021 | Interrupt the bot during a spoken answer | V1 core | Draft | Medium |
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
| US-036 | Measure key voice journey timings by pipeline slice | V1 pilot gate | Done (STT sprint scope) | High |
| US-037 | Measure invoice comparison response time | V1 pilot gate | Draft | Medium |
| US-038 | Track escalations and their reasons | V1 pilot gate | Draft | Medium |
| US-039 | Track unresolved questions | V1 pilot gate | Draft | Medium |
| US-040 | Produce the pilot readiness report | V1 pilot gate | Draft | High |

## Technical Tasks

| Key | Title | Classification | Status | Priority |
|-----|-------|---|--------|----------|
| TASK-STT-001 | Create the voice runtime STT validation scaffold | V1 enabler | Done | High |
| TASK-STT-002 | Validate STT transcription quality with audio fixtures | V1 pilot gate | Done | High |
| TASK-STT-003 | Add OpenTelemetry instrumentation for STT validation | V1 pilot gate | Done | High |
| TASK-STT-004 | Produce the STT QA report and Gherkin scenarios | V1 pilot gate | Done | High |
| TASK-STT-005 | Redact bare sensitive identifiers in failure sanitization (closes RF-001) | V1 pilot gate | Done (Sprint 2) | Medium |
| TASK-STT-006 | Add a dedicated UNAVAILABLE STT outcome | V1 pilot gate | Planned (Sprint 2) | Low |
| TASK-STT-007 | Expand the STT fixture set with multiple samples per category (closes RF-003, RF-005) | V1 pilot gate | Done (Sprint 2) | Medium |
| TASK-STT-008 | Connect the Gradium STT provider (fresh implementation) | V1 pilot gate | Done (STT sprint scope) | High |
| TASK-STT-009 | Detect and instrument end-of-turn for the voice journey (US-036 `end_of_turn` slice) | V1 pilot gate | Planned (Sprint 2) | Medium |
| TASK-STT-010 | Stream partial STT transcripts to cut perceived latency (closes RF-007) | V1 pilot gate | Planned (Sprint 4) | High |
| TASK-STT-011 | Normalize transcripts (case/punctuation/accents) before WER scoring (closes RF-008) | V1 pilot gate | Done (Sprint 2) | Medium |
| TASK-WEB-001 | Capture web voice and transcribe through Gradium STT (US-019 STT half) | V1 core | In progress | High |
| TASK-WEB-002 | Speak the bot response on the web page (US-019 TTS half) | V1 core | Draft | High |
| TASK-WEB-003 | Orchestrate transcript to backend answer (US-019 STT/TTS bridge) | V1 core | Draft | High |
| TASK-WEB-004 | Stream the bot voice response — incremental TTS playback (US-036 `tts_first_audio` slice) | V1 core | Draft | High |

## Planned Sprints

| Key | Title | Status | Goal |
|-----|-------|--------|------|
| SPRINT-STT | STT Validation | ✅ Done (2026-07-10) | Validate fixture-based speech-to-text transcription, timing, OpenTelemetry evidence and QA readiness |
| SPRINT-2-STT-HARDENING | STT Hardening | Planned | Make the WER quality gate usable (normalization) and complete STT observability (fixtures, sanitization, UNAVAILABLE outcome, end-of-turn) — `sprints/sprint-2-stt-hardening.md` |
| SPRINT-3-TTS | TTS / Voice-out (batch) | Planned | Speak the bot response and close the first end-to-end voice loop (no streaming yet) |
| SPRINT-4-STREAMING | Latency optimization (streaming) | Planned | Streaming STT (TASK-STT-010) + streaming TTS (TASK-WEB-004) for the low-latency voice loop |

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
| OQ-005 | Pilot latency acceptance context | Product / Architecture / Operations | Open |
| OQ-006 | Genesys handoff integration shape | Product / Contact Center / Architecture / Security | Open |

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
