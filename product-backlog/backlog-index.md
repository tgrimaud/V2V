# Backlog Index

## V1 Epics

| Key | Title | Classification | Status | Priority |
|-----|-------|---|--------|----------|
| EPIC-001 | Identify the customer and retrieve billing context | V1 core | Ready for review | High |
| EPIC-002 | Compare two invoices or billing periods | V1 core | Ready for delivery split | High |
| EPIC-003 | Explain invoice deltas with evidence | V1 core | Ready for review | High |
| EPIC-004 | Deliver the phone Voice2Voice journey | V1 core | Ready for review | High |
| EPIC-005 | Deliver the web Voice2Voice journey | V1 core | Ready for review | High |
| EPIC-006 | Escalate to a human advisor | V1 core | Ready for review | High |
| EPIC-007 | Provide web synthesis and evidence | V1 enabler | Ready for review | Medium |
| EPIC-008 | Guarantee trust, security and auditability | V1 enabler | Ready for review | High |
| EPIC-009 | Measure conversational quality and V1 performance | V1 pilot gate | Ready for review | High |
| EPIC-010 | Validate the BSS/PDF evidence fixture path | V1 enabler | Draft | High |

## V1 Delivery Backlog

| Key | Title | Classification | Status | Priority |
|-----|-------|---|--------|----------|
| US-001 | Identify the customer at the start of the exchange | V1 core | Ready for review | High |
| US-002 | Retrieve available invoices and billing periods | V1 core | Ready for review | High |
| US-003 | Detect insufficient BSS evidence | V1 core | Ready for review | High |
| US-004 | Select two invoices or billing periods to compare | V1 core | Ready for delivery split | High |
| US-005 | Identify changed invoice lines and amounts | V1 core | Ready for delivery split | High |
| US-006 | Identify the main business causes | V1 core | Ready for delivery split | High |
| US-007 | Receive a synthesis of increase or decrease causes | V1 core | Ready for review | High |
| US-008 | Obtain evidence for each cause | V1 core | Ready for review | High |
| US-009 | Explain the billing rule behind a delta | V1 core | Ready for review | Medium |
| US-010 | Handle invoice extraction status | V1 enabler | Draft | High |
| US-011 | Use realistic BSS/PDF fixtures for V1 validation | V1 enabler | Draft | High |
| US-012 | Call the bot for a spoken invoice explanation | V1 core | Ready for review | High |
| US-013 | Receive a quick spoken acknowledgement during long analysis | V1 core | Ready for review | Medium |
| US-014 | Ask orally for transfer to an advisor | V1 core | Ready for review | High |
| US-015 | Ask from a web voice chat | V1 core | Ready for review | High |
| US-016 | Read the synthesis on the web page | V1 enabler | Ready for review | Medium |
| US-017 | Use text to complement a voice question | V1 enabler | Ready for review | Low |
| US-018 | Be transferred on explicit request | V1 core | Ready for review | High |
| US-019 | Be transferred when the bot lacks enough certainty | V1 core | Ready for review | High |
| US-020 | Provide the advisor with usable context | V1 core | Ready for review | High |
| US-021 | Consult the global delta | V1 enabler | Ready for review | Medium |
| US-022 | Consult cause details | V1 enabler | Ready for review | Medium |
| US-023 | See evidence and analysis limits | V1 enabler | Ready for review | Medium |
| US-024 | Protect personal data exposed to the customer | V1 enabler | Ready for review | High |
| US-025 | Audit sensitive consultations | V1 enabler | Ready for review | High |
| US-026 | Disclose analysis limits | V1 core | Ready for review | High |
| US-027 | Measure key voice journey timings | V1 pilot gate | Ready for review | High |
| US-028 | Track escalations and their reasons | V1 pilot gate | Ready for review | Medium |
| US-029 | Track unresolved questions | V1 pilot gate | Ready for review | Medium |
| US-030 | Consult line-by-line invoice differences | V1 enabler | Draft | Medium |
| US-031 | Validate billing and pricing KB content for V1 | V1 enabler | Draft | Medium |
| US-032 | Measure invoice comparison response time | V1 pilot gate | Draft | Medium |

## Post-MVP / Roadmap

| Item | Reason |
|---|---|
| Generic PDF / Confluence / database KB connectors | Useful for knowledge enrichment, but not required for the first billing V1 if Markdown pricing rules and invoice PDF extraction are available |
| WhatsApp production channel | Future asynchronous adapter gated by channel contracts, quotas, observability and degraded modes |
| Genesys production connector | Future contact-center integration; V1 needs the handoff contract, not the full platform connector |
| GPU/self-hosting | Sovereignty or latency optimization option, not a V1 prerequisite |
| Custom brand voice | Product polish after the billing journey is reliable |

## Alignment Notes

Moved into the explicit V1 backlog:

- invoice PDF extraction status handling;
- realistic BSS/PDF fixture validation;
- voice latency pilot measurement;
- escalation handoff context and reason tracking;
- billing security, audit and evidence-limit disclosure.

Moved out of the V1 prerequisite set:

- generic KB connectors for Confluence, generic PDF ingestion and databases;
- WhatsApp and Genesys production connectors;
- GPU/self-hosting;
- custom brand voice;
- advanced admin analytics beyond the minimum pilot review needs.

## Open Questions

| Key | Topic | Owner | Status |
|-----|-------|-------|--------|
| OQ-001 | Customer identification by phone and web voice channel | Product / BSS / Security | Open |
| OQ-002 | Minimum proof threshold for answering without escalation | Product / Billing SME / Legal | Open |
| OQ-003 | BSS data availability and granularity | BSS owner | Open |
| OQ-004 | Invoice PDF extraction reliability and fixture coverage | Product / BSS / QA | Open |
| OQ-005 | Pilot latency acceptance context | Product / Architecture / Operations | Open |

## Decisions

| Key | Decision | Status |
|-----|----------|--------|
| DEC-001 | V1 focuses on invoice explanation while the product remains extensible to general support | Accepted via ADR-0017 |
| DEC-002 | BSS evidence is the source of truth and the LLM only words the explanation | Accepted via ADR-0003 |
| DEC-003 | Invoice PDFs are a V1 evidence source until structured lines are validated | Accepted via ADR-0005 |
| DEC-004 | Voice2Voice is mandatory in V1 | Accepted in `v1-scope.md` |
| DEC-005 | Gradium and Pipecat are the reference starting point | Accepted via ADR-0002 |
| DEC-006 | Human escalation is required | Accepted via ADR-0019 |
| DEC-007 | Java owns business logic and Python owns the voice edge | Accepted via ADR-0001 and ADR-0011 |
| DEC-008 | V1 routing prioritizes billing explanation while support/sales agents remain foundation capabilities | Accepted via ADR-0017 and ADR-0015 |
