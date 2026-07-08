# Documentation Coherence Review - 2026-07-08

## Purpose

This document preserves the complete documentation coherence review performed on
2026-07-08 so the team can come back to the findings later and resolve them
incrementally.

The review covered:

- product documentation;
- architecture documentation;
- ADRs;
- Galaxion/BSS integration documentation;
- knowledge-base documentation;
- engineering and operations guides;
- repository guidance files.

## Executive Conclusion

The documentation now has a useful structure: `docs/README.md` indexes the main
areas, architecture decisions are collected under `docs/architecture/adrs/`, and
the repository has specialized documentation skills.

However, the corpus is not yet coherent. The main issue is not one isolated
mistake but a set of historical layers that now overlap:

- two competing product definitions for V1;
- two ADR registries;
- stale architecture sections that predate Pipecat as the V1 voice target;
- stale persistence documentation that still describes Redis/JPA as future work;
- stale streaming documentation that still mentions Reactor `Flux<String>`;
- inconsistent API field names;
- unresolved SLO language;
- inconsistent documentation language policy.

The next work should be a focused documentation consistency cleanup, not ad hoc
edits.

## Cleanup Checklist

### Product Scope And Roadmap

- [x] Decide the canonical product hierarchy: V1 billing/BSS invoice explanation
      vs broader general telecom support assistant.
- [x] Update `docs/README.md` so it links both product documents and explains
      their relationship.
- [x] Update `docs/product/v1-scope.md` to link to the functional specification,
      ADRs, and Galaxion integration docs.
- [x] Update `docs/product/cahier-des-charges-fonctionnel.md` to clarify whether
      it is the broad product vision, MVP scope, or target-state functional spec.
- [x] Align the product docs with ADR-0003, ADR-0004, and ADR-0005: BSS
      read-only source of truth, deterministic comparison, PDF extraction before
      LLM explanation.
- [x] Explicitly document that the broader support/RAG assistant is either the
      current MVP foundation or the long-term product vision, while billing/BSS is
      the V1 value focus if that remains the intended direction.
- [x] Add an ADR for the product pivot: "billing/BSS V1 vs general support MVP".

### ADR Governance

- [x] Remove or rename the inline ADR section from
      `docs/architecture/architecture.md`.
- [x] Make `docs/architecture/adrs/` the only canonical ADR registry.
- [x] Convert any still-relevant inline ADRs from `architecture.md` into formal
      ADR files.
- [x] Add supersession or migration notes if historical inline ADRs are kept for
      archive purposes.
- [x] Fix all references to inline `ADR-011` and point them to formal ADR-0007.
- [ ] Add missing ADRs for `TokenStream`, official voice SLO, legacy bridge
      retirement, guardrails, multi-agent routing, and modular STT-RAG-LLM-TTS
      vs realtime API if these decisions remain active. `TokenStream`,
      guardrails, multi-agent routing, modular pipeline, and legacy bridge status
      are now covered; official SLO and final bridge retirement remain open.

### Architecture Alignment

- [x] Replace all domain-streaming references to Reactor `Flux<String>` with the
      current `TokenStream` abstraction after verifying the code.
- [x] Update `docs/architecture/architecture.md` port tables and examples to
      reflect `TokenStream`.
- [x] Update `docs/engineering/development-guide.md` provider examples to use the
      current streaming contract.
- [x] Update `README.md` diagrams and class examples if they still show
      `Flux~String~`.
- [x] Replace stale `InMemoryConversationStore` / `InMemoryConversationEventStore`
      architecture statements with the accepted Redis active sessions +
      PostgreSQL/JPA durable events split.
- [x] Clarify which in-memory adapters remain available only for local/dev/tests.
- [x] Update `docs/architecture/architecture.md` so ADR-0008 is reflected in the
      port/adapters table and memory section.

### Voice Path And Runtime Topology

- [x] Make `voice-agent/agent/bot.py` and `streaming_rag_processor.py` the primary
      documented V1 voice path everywhere.
- [x] Mark `voice-agent/agent/bridge_server.py` consistently as
      legacy/fallback/comparison.
- [x] Update `README.md` sequence diagrams and ASCII diagrams that still describe
      WebSocket PCM as the main voice path.
- [x] Update `docs/architecture/infra-v1.md` terminology from "Voice bridge
      Python" to "Pipecat voice agent" where the target V1 path is meant.
- [x] Keep a separate explicit "legacy bridge" section for ports 8765/8766 and
      React POC behavior.
- [x] Correct any references to `voice-support-bot/bridge/`; the code lives under
      `voice-support-bot/voice-agent/`.
- [x] Review root workspace guidance files and Cursor rules that still present
      the bridge as the central architecture.
- [x] Decide and document the current legacy bridge policy through ADR-0016.

### SLOs And NFRs

- [ ] Choose the official voice latency SLO: 700 ms, 800 ms p95, or another
      measured target.
- [ ] Create a formal ADR for the SLO and its measurement conditions.
- [ ] Update `docs/product/v1-scope.md`, `docs/product/cahier-des-charges-fonctionnel.md`,
      `docs/architecture/architecture.md`, `docs/operations/backlog.md`, and
      `docs/engineering/development-guide.md` to use the same SLO language.
- [ ] Separate aspirational target, measured baseline, acceptance criterion, and
      production SLO.
- [ ] Ensure ADR-0010's industrialization gates are referenced from
      `architecture.md` and `infra-v1.md`.
- [ ] Add explicit observability requirements for every pipeline step and channel.

### Omnichannel, Genesys, WhatsApp, And Escalation

- [ ] Add a channel/backend contract section to `docs/architecture/architecture.md`.
- [ ] Include `channel`, `external_session_id`, `message_id`, `idempotency_key`,
      `reply_mode`, and escalation context in that contract.
- [ ] Clarify whether current routes `ask` and `ask-stream` are sufficient or
      whether a future channel-oriented API is required.
- [ ] Reflect ADR-0009 and ADR-0010 in the architecture spine, not only in ADRs.
- [ ] Clarify WhatsApp as a future asynchronous channel adapter, not a production
      channel available before the channel contracts and SLOs are formalized.
- [ ] Clarify Genesys Cloud CX as an optional contact-center and escalation layer,
      not the owner of RAG, billing reasoning, guardrails, or memory.
- [ ] Create or update escalation rules to include both generic support triggers
      and billing/BSS confidence failures.
- [ ] Add an ADR for escalation rules if they are treated as an architectural or
      product decision.

### BSS And Billing Integration

- [ ] Standardize the runtime BSS port name: prefer `BssBillingPort` if that is
      the intended canonical name.
- [ ] Replace or explain `BillingContextPort` references.
- [ ] Update `docs/integrations/galaxion/bss-integration-plan.md` to reference
      ADR-0004 explicitly.
- [ ] Make clear that MCP/ad hoc tools are for exploration only, not runtime
      customer flows.
- [ ] Clarify that `billing-api` is the V1 billing source and `billing-service`
      remains historical archive only.
- [ ] Move historical `billing-service` analysis to an archive section or file if
      it keeps causing confusion.
- [ ] Resolve the open question "Do invoice lines actually come from billing?"
      so it does not reopen the accepted PDF-first path.
- [ ] Make PDF extraction part of the product V1 scope, not only integration docs.
- [ ] Add `parseable`, `partial`, and `unusable` extraction statuses to product
      acceptance criteria or link to `invoice-extraction-json.md`.
- [ ] Propagate integer-cents rules into product examples, Galaxion mapping, and
      billing domain model notes.
- [ ] State unit uncertainty explicitly for Galaxion fields that are not known
      yet, and never mix unknown API units with internal cents contracts.

### API Contracts And Examples

- [ ] Standardize `conversation_id` vs `conversationId` across docs and examples.
- [ ] Verify the backend DTO contracts and update every curl example accordingly.
- [ ] Fix examples in `docs/engineering/development-guide.md` that use
      `conversationId` when the backend expects `conversation_id`.
- [ ] Add a small API contract table for sync POST, SSE GET, and seed endpoints.
- [ ] Document which field names are JSON body fields and which are query
      parameters.

### Knowledge Base Documentation

- [x] Fix the ADR reference in `knowledge-base-technical.md`: use formal ADR-0007,
      not inline ADR-011.
- [ ] Keep `knowledge-base-guide.md` and `knowledge-base-technical.md` as the
      source of truth for KB sync; they are currently coherent.
- [ ] Decide whether advanced KB connectors are V1 prerequisites or medium-term
      roadmap items, then align `v1-scope.md`, the functional spec, and backlog.
- [ ] Ensure KB docs state that the KB explains tariff/business rules but does
      not replace BSS evidence for billing deltas.

### Docker And Developer Guidance

- [x] Update Docker/dev docs so Pipecat is the default target V1 path.
- [x] Document how to start `pipecat-agent` with Docker Compose.
- [x] Clarify that legacy `voice-agent` WebSocket services are fallback or
      comparison paths.
- [x] Document that Ollama must be running for embeddings if it is not provided
      by Docker Compose.
- [ ] Add or document a `bss-mock` service only if it exists; otherwise mark it as
      planned.
- [x] Correct stale file names such as `ws_server.py` if they no longer represent
      the target path.

### Documentation Language And Style

- [x] Decide whether `docs/` must be entirely English.
- [x] If English remains mandatory, translate the French documentation in a
      controlled pass.
- [x] If French is acceptable for product/business docs, update
      `CLAUDE.md`, `AGENTS.md`, and `technical-writer` accordingly.
      Not applicable: English-only remains the accepted rule.
- [x] Standardize accent usage in French files if they remain French.
      Not applicable: French prose was translated. Remaining French terms are
      technical examples, filenames, or domain keywords.
- [x] Avoid mixing English and French headings inside the same document unless
      quoting source material.

### Indexes And Cross-Links

- [x] Add this review document to `docs/README.md`.
- [x] Add cross-links from product docs to ADRs and Galaxion docs.
- [x] Add cross-links from ADRs to the product docs they affect.
- [ ] Add cross-links from `architecture.md` to ADR-0002, ADR-0008, ADR-0009,
      ADR-0010, and any new ADRs created from this cleanup.
- [x] Ensure every new or moved document is reachable from an index.

## Complete Findings

### 1. Product Documentation Findings

Status after cleanup: the product hierarchy is now explicit. The functional
specification describes the broad support assistant foundation and target vision,
while `docs/product/v1-scope.md` defines the V1 billing/BSS invoice explanation
value slice. This decision is captured in ADR-0017 and linked from both product
documents and `docs/README.md`.

#### 1.1 Two incompatible V1 product definitions

The corpus currently contains two V1 product lines without a clear hierarchy.

`docs/product/v1-scope.md` defines V1 as an invoice-explanation assistant:

- BSS read-only data is the source of truth.
- Invoice or period comparison is deterministic.
- The LLM must not infer billing causes.
- The KB explains tariff/business rules but must not compensate for missing BSS
  data.

`docs/product/cahier-des-charges-fonctionnel.md` defines a broader general
Telecom/FAI support assistant:

- web voice;
- text fallback;
- telephony;
- WhatsApp later;
- multi-agent support, billing, and commercial routing;
- RAG answers from the KB;
- admin dashboard;
- future Genesys Cloud CX readiness.

`README.md` is closer to the general RAG support assistant and does not explain
the billing/BSS V1 focus. `docs/README.md` links only `product/v1-scope.md` as
the product scope and does not link the functional specification.

The missing hierarchy makes it unclear whether:

- invoice explanation is the V1 product;
- general support RAG is the MVP and invoice explanation is a later expansion;
- the functional spec is the broad target and `v1-scope.md` is the narrow first
  implementation cut.

#### 1.2 BSS and billing rules are not reflected everywhere

The ADRs and `v1-scope.md` are clear:

- BSS is read-only and authoritative.
- The system compares invoices deterministically.
- The LLM only formulates the explanation after evidence exists.
- PDF extraction is required when no validated structured invoice-line endpoint
  exists.

The functional spec and README do not fully reflect this. They describe generic
RAG over a KB and progressively connecting to business systems, which can be read
as pushing BSS integration later than V1.

#### 1.3 Escalation criteria diverge

`v1-scope.md` escalates when:

- the user explicitly asks for a human;
- the bot lacks enough certainty due to missing, inconsistent, or unprovable BSS
  data.

The functional specification escalates on:

- cancellation/resiliation;
- complaints;
- refund or dispute;
- GDPR/personal data;
- hacking or compromise;
- technician request;
- frustration.

`architecture.md` mostly follows the generic support keyword list and does not
explicitly include BSS confidence failures as an escalation trigger.

#### 1.4 WhatsApp and Genesys timing is ambiguous

The functional specification lists WhatsApp in project scope and includes a
journey, but ADR-0009 and ADR-0010 position WhatsApp as a future async channel
adapter gated by contracts, SLOs, and observability.

Genesys is more consistent: it is positioned as a future contact-center layer,
not the conversation engine. The missing piece is making that positioning visible
from the architecture spine and infra docs.

#### 1.5 Product docs lack cross-links

`docs/product/v1-scope.md` does not link to:

- the functional specification;
- ADR-0003, ADR-0004, ADR-0005;
- the Galaxion/BSS integration plan;
- invoice extraction JSON.

`docs/product/cahier-des-charges-fonctionnel.md` does not link to:

- `v1-scope.md`;
- ADRs;
- Galaxion/BSS integration docs.

### 2. Architecture Documentation Findings

#### 2.1 Two ADR registries exist

The formal ADR registry lives under:

```text
docs/architecture/adrs/
```

It defines ADR-0001 through ADR-0010.

`docs/architecture/architecture.md` still contains inline ADR-001 through
ADR-011. These are not the same decisions and do not share the same numbering.
This creates concrete conflicts:

- formal ADR-0004 is BSS typed ports;
- inline ADR-004 is in-memory event store;
- formal ADR-0010 is industrialization gates;
- inline ADR-010 is Pipecat target V1.

The inline ADR block should either be removed, archived, or converted into formal
ADRs.

#### 2.2 `TokenStream` vs Reactor `Flux<String>`

The code now uses a domain-level `TokenStream` abstraction for streaming tokens.
The docs still contain stale Reactor references:

- `architecture.md` says `LlmStreamingPort` uses `Flux<String>`;
- `README.md` class diagram shows `Flux~String~`;
- `development-guide.md` provider example returns `Flux<String>`;
- the adversarial review explicitly flags this as a known drift.

The architecture docs should not describe Reactor as part of the domain contract
if the accepted code direction is `TokenStream`.

#### 2.3 Redis/Postgres persistence drift

Remediation status: fixed. ADR-0008 and the operations backlog say:

- Redis stores active conversation/session state;
- PostgreSQL/JPA stores durable conversation events;
- Docker Compose wires `CONVERSATION_STORE=redis` and
  `CONVERSATION_EVENT_STORE=jpa`.

`architecture.md` now reflects this split in the port table and conversation
memory section. It keeps `InMemoryConversationStore` and
`InMemoryConversationEventStore` only as local/dev/test adapters. The hexagonal
Draw.io diagram now shows `RedisConversationStore` for active sessions and
`JpaConversationEventStore` for durable events.

#### 2.4 Pipecat target path is aligned after cleanup

Remediation status: fixed in the topology cleanup batch. The following sources
now describe `voice-agent/agent/bot.py` and `streaming_rag_processor.py` as the
target V1 path, and mark `bridge_server.py` as legacy/fallback/comparison:

- ADR-0002;
- ADR-0016;
- top-level `voice-support-bot/CLAUDE.md`;
- top-level `voice-support-bot/AGENTS.md`;
- root workspace `CLAUDE.md` and `AGENTS.md`;
- root Cursor rule `.cursor/rules/voice-support-bot.mdc`;
- `architecture.md`;
- `infra-v1.md`;
- `README.md`;
- `development-guide.md`;
- legacy `architecture-overview.drawio` labels.

#### 2.5 Channel/backend contract is defined in ADRs but absent from the
architecture spine

ADR-0009, ADR-0010, and the adversarial review define the expected channel
contract fields:

- `channel`;
- `external_session_id`;
- `message_id`;
- `idempotency_key`;
- `reply_mode`;
- escalation context.

`architecture.md` documents only the current `ask` and `ask-stream` flows with
`question` and `conversation_id`. It does not explain whether those APIs are the
final omnichannel contract or whether a future channel-oriented API is required.

#### 2.6 Genesys and WhatsApp are absent from the architecture spine

The product spec and ADRs position them correctly:

- Genesys = contact-center and human escalation layer;
- WhatsApp = future async channel adapter;
- Java backend keeps RAG, billing reasoning, guardrails, routing, and memory.

`architecture.md` and `infra-v1.md` do not yet make this visible.

#### 2.7 SLO/NFR language is unresolved

The corpus uses several targets:

- `first audio < 700 ms` as an obligatory Voice2Voice criterion;
- first audible response under one second;
- `time_to_first_audio p95 < 800 ms`;
- adversarial review says the official SLO is not settled.

`architecture.md` presents `~700ms` as a production-like budget, while backlog
items say the prerequisites are still to do. This needs a formal decision.

### 3. Galaxion/BSS Integration Findings

#### 3.1 `billing-api` vs `billing-service` is mostly consistent but noisy

The decision is consistent:

- use `billing-api`;
- do not use `billing-service`;
- retrieve invoice documents through `bill-run-documents`;
- extract structured invoice JSON before comparison.

The residual problem is archive noise. `billing-service` details remain long and
prominent in integration docs. This is useful as history, but easy to misread as
a still-open option.

#### 3.2 PDF extraction vs structured invoice lines remains muddy

ADR-0005 and `invoice-extraction-json.md` settle the current path:

- no validated structured line endpoint is available;
- PDF extraction is the V1 mechanism before comparison;
- the LLM must not read PDFs to calculate amounts.

`galaxion-billing-contracts.md` still suggests that:

- `GET /invoices/selected` may provide invoice lines and sections;
- `ComposedItemResponse` has useful V1 fields;
- PDF should not become the primary calculation source if structured data exists.

That last sentence is defensible as a future migration note, but it undermines
the current PDF-first decision unless clearly labeled as a future replacement
condition.

#### 3.3 Integer-cents contract is not propagated everywhere

The internal contract says:

- amounts use integer cents;
- fields should use `*_cents`;
- decimals from external systems must be normalized before domain comparison.

Gaps remain:

- product examples use decimal EUR values without linking to internal cents
  normalization;
- Galaxion fields mix unknown `number` units, possible cents, and decimal-like
  fields;
- the domain mapping section does not state cents types explicitly for
  `Invoice.totalAmount` or `InvoiceLine.amount`.

#### 3.4 BSS port naming drift

The canonical naming appears to be:

- `BssBillingPort`;
- `BssCustomerContextPort`.

`bss-integration-plan.md` uses `BillingContextPort`, which is not defined in the
ADRs or guidance files. This should be corrected or explicitly justified.

#### 3.5 Runtime BSS ports vs MCP is aligned but weakly linked

ADR-0004 and repo guidance clearly say:

- typed business ports are for runtime customer flows;
- MCP/ad hoc tools are for exploration and internal tooling.

The integration plan has the right port/adapter diagram but does not link to
ADR-0004 or explicitly exclude runtime MCP.

### 4. Knowledge Base Documentation Findings

#### 4.1 KB sync is internally coherent

`knowledge-base-guide.md`, `knowledge-base-technical.md`, ADR-0007, and repo
guidance agree on:

- `SourceDocument` pivot model;
- `contentHash`-based idempotent sync;
- Markdown reference connector;
- hourly cron;
- `POST /api/knowledge/sync`;
- one PostgreSQL vector store plus sync ledger.

#### 4.2 ADR numbering is wrong in KB docs

`knowledge-base-technical.md` references inline ADR-011, while the formal ADR is
ADR-0007. This must be corrected.

#### 4.3 KB connector priority is inconsistent

`v1-scope.md` says PDF/Confluence/DB connectors are V1 structural requirements.
The functional spec says advanced connectors beyond Markdown are out of initial
scope or medium-term roadmap.

The technical foundation is coherent, but the product priority is not.

### 5. Engineering And Developer Guidance Findings

#### 5.1 Developer examples still use stale streaming types

The OpenAI example in `development-guide.md` uses `Flux<String>`. It should be
updated to the current streaming abstraction if the code uses `TokenStream`.

#### 5.2 STT/TTS provider replacement references stale files

`development-guide.md` mentions `voice-agent/agent/ws_server.py` for provider
replacement. The target V1 path is `agent/bot.py` through Pipecat. The guide
should explain provider changes in the Pipecat target first, then legacy bridge
changes separately.

#### 5.3 Docker and dev startup docs do not fully reflect the V1 path

Remediation status: partially fixed. `README.md` and `development-guide.md` now
document `pipecat-agent` as the Docker Compose V1 path and label the
`voice-agent` WebSocket service as legacy/fallback/comparison. `README.md` also
states that host Ollama must be running when local embeddings or local LLM
inference are used.

Remaining open item: only add or document a `bss-mock` service if it exists;
otherwise mark it as planned in the BSS integration cleanup batch.

#### 5.4 Ollama embedding dependency is underdocumented

Remediation status: fixed in `README.md`. KB sync/query embeddings require
Ollama `nomic-embed-text`; Docker Compose does not provide Ollama by default, so
the README now states that host Ollama must be running when local embeddings or
local LLM inference are used.

#### 5.5 `bss-mock` is recommended but not present

The BSS integration plan recommends a `bss-mock/` service in Docker Compose.
The docs should either add it, mark it as planned, or avoid implying it exists.

#### 5.6 `conversation_id` vs `conversationId` examples conflict

Some examples use `conversation_id`; others use `conversationId`. The Python
bridge bug history makes this important: the wrong field can silently split
conversation history.

### 6. Documentation Language And Style Findings

Status after cleanup: English-only remains the documentation rule. The French
and mixed-language documentation was translated in a controlled pass across
product, architecture, engineering, operations, integration, README, `CLAUDE.md`,
and `AGENTS.md`. Remaining French strings are limited to technical examples,
filenames, or domain keywords intentionally kept as data.

#### 6.1 Current rule says English-only docs

Remediation status: fixed. `CLAUDE.md`, `AGENTS.md`, and related documentation
guidance require English-only docs, and the previously French product,
architecture, infrastructure, Galaxion, development, operations, adversarial
review, and README content has been translated.

#### 6.2 French docs are not even stylistically consistent

Remediation status: fixed by the English translation pass. Remaining French
phrases should be treated as domain examples, test data, or proper nouns unless
a later scan proves otherwise.

### 7. Root Workspace Guidance Findings

The nested `voice-support-bot/CLAUDE.md` and `voice-support-bot/AGENTS.md` are
mostly current.

Remediation status: fixed in the topology cleanup batch. The root workspace
`CLAUDE.md`, root `AGENTS.md`, and `.cursor/rules/voice-support-bot.mdc` now
point to `voice-support-bot/voice-agent/`, mark Pipecat as the V1 target, and
label the custom WebSocket bridge as legacy/fallback.

## Consolidated Recommendation

Treat this as a documentation stabilization mini-epic.

Recommended order:

1. Establish the product hierarchy and capture it in an ADR.
2. Remove duplicate inline ADRs from `architecture.md`.
3. Align architecture docs to current code: `TokenStream`, Redis/JPA, Pipecat V1,
   bridge legacy.
4. Decide the language policy and apply it consistently.
5. Normalize contract details: `conversation_id`, `BssBillingPort`, PDF-first,
   integer cents.
6. Add missing ADRs for SLO, `TokenStream`, bridge retirement, and product pivot.
7. Update cross-links and indexes.
8. Run another coherence review after the cleanup.
