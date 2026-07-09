# Guidance for AI agents — Voice Support Bot

## Repo & git

- `voice-support-bot` is a **separate git repository** (default branch `main`) nested in the `BMad` workspace (which is another repository). Commit/push bot work **in this repository**, not in `BMad`.
- **One branch per sprint/epic** (`feat/<name>`). Do not commit directly on `main`. Merge after validation.
- **Commit after each task**; do not leave code uncommitted.
- On `feat/restart-from-scratch`, the previous implementation directories
  (`backend/`, `frontend/`, `voice-agent/`) and `docker-compose.yml` are
  intentionally removed. `main` is the backup/reference for the old code.

## Before you edit

1. On the restart branch, create new implementation scaffolds only when the
   corresponding backlog story is selected.
2. Java backend: follow the `java-backend-developer` skill + `code-guidelines`
   (methods <= 20 lines, classes <= 200 lines, no Javadoc on ports).
3. Pure domain (no Spring annotations); wire services through `@Bean` in
   infrastructure configuration.
4. Tests: manual fakes, GIVEN/WHEN/THEN, **no Mockito**.
5. Voice runtime: preserve the target architecture direction (Pipecat + provider
   adapters), but rebuild the runtime from scratch on this branch.
6. Documentation files under `docs/` must be written in English.
7. Documentation work : use `.cursor/skills/technical-writer/SKILL.md` before creating, editing, translating or reviewing technical docs.
8. Diagram work : use `.cursor/skills/diagram-drawer/SKILL.md` before creating, editing or reviewing Mermaid/Draw.io diagrams.
9. Presentation work : use `.cursor/skills/presentation-maker/SKILL.md` to create high-level technical/strategy decks from `~/Downloads/Presentation.odp`.
10. Architecture decisions : use `.cursor/skills/software-architect/SKILL.md` and create or update an ADR under `docs/architecture/adrs/`.

## Common mistakes to avoid

- Confusing **LLM** and **embedding**: they are 2 distinct models. Chat uses Mistral (API), embedding uses Ollama (`nomic-embed-text`, 768 dim). "Switching to Mistral" does NOT change embeddings (Mistral embedding auto-config is excluded).
- Running `ALTER TABLE vector_store` to add metadata: unnecessary, metadata is stored as **JSONB**. However, **changing the embedding model** (and therefore the dimension) requires recreating the table + re-syncing.
- Forgetting that rows seeded through the old `curl /ingest` have no `source_id` -> `deleteBySource` does not clean them up. Empty `vector_store` once before the first sync.
- Adding a method to an outbound port (`VectorStorePort`, etc.) without updating **all** implementers, including **test fakes**.
- Returning a `mistral-embed` vector type (1024) without aligning `pgvector.dimensions` — silent mismatch on insert/search.
- Adding a dependency to parse YAML front-matter: SnakeYAML is already present (Spring Boot transitive dependency).
- Putting Spring annotations in the domain, or injecting a connector while forgetting the `@Bean` (it will not be in `List<KnowledgeSourceConnector>`).
- Believing `mvn test` needs a DB/Ollama: there is no `@SpringBootTest`; tests are domain units with fakes.
- Putting bot learnings in the root `BMad` `CLAUDE.md`: it belongs to another project (`cursor-usage-dashboard`). Bot knowledge files live in `voice-support-bot/`.
- Starting Billing V1 from scratch: keep the POC voice/RAG/orchestrator foundation, but rebuild the business core around the BSS and invoice comparison.
- Using a generic MCP as the main BSS access path in customer runtime: prefer a typed read-only business port (`BssBillingPort`) with BSS adapters; reserve MCP for exploration and internal tools.
- Coupling the product core to a specific LLM/STT/TTS SDK: expose these capabilities through configurable ports/adapters so providers can be benchmarked and swapped easily.
- Presenting `bridge_server.py` as the V1 voice target: false. The V1 target starts on Gradium + Pipecat (`agent/bot.py`); the custom bridge remains a historical POC / fallback.
- Writing new `docs/` content in French: documentation must be in English, even when the working conversation is in French.
- Closing the product around billing only: V1 = invoice explanation, but the architecture must remain extensible to other operator support domains.
- Creating a separate repository for the product backlog when the user mainly wants to keep it with the project: by default, store artifacts in `product-backlog/` in the `voice-support-bot` repo unless an external git repository is explicitly requested.
- Writing product EPICs/user stories without the `product-business` skill: this skill keeps stories at the level of need, value, business rules, and observable acceptance, without API or implementation details.
- Taking `billing-service` as the Galaxion source for invoices: it is no longer used. For V1, target only `billing-api`.
- Looking for a structured Galaxion invoice-line endpoint without proof: none has been identified. Retrieve the PDF through `bill-run-documents` and use a deterministic `InvoicePdfExtractor`.
- Letting the LLM read the invoice PDF directly to calculate amounts: forbidden. First extract structured JSON, verify reconciliation, then formulate the explanation.
- Placing Mermaid `retrieval` / `generation` labels on ambiguous internal handoffs: labels must live on the edge representing the real interaction, typically adapter -> PgVector or adapter -> external LLM.
- Creating/editing Draw.io XML with important unanchored connections: use explicit `exitX/exitY` and `entryX/entryY` anchors, especially with swimlanes and labeled edges.
- Generating a presentation by patching `Presentation.odp` without visual validation: the XML can contain text while still opening blank. If LibreOffice/soffice is unavailable, generate a `.pptx` with standard text shapes.
- Overfilling presentation template frames: use a large layout, one idea per slide, and two short bullets maximum to keep presentations readable.
- Presenting the omnichannel vision as industrialized because the diagram is clean: false. Until channel/backend contracts, an escalation contract, SLOs, observability, per-channel rate limiting, and degraded modes are defined/tested, this is a solid MVP with a healthy vision, not a production platform.
- Adding WhatsApp, Genesys, or a new channel before formalizing the shared contract (`channel`, `external_session_id`, `message_id`, `idempotency_key`, `reply_mode`, `escalation_context`) — that duplicates logic and couples channels.
- Making an architecture decision without an ADR: every structural decision must be documented under `docs/architecture/adrs/` with context, decision, consequences, and alternatives.
- Letting Genesys own RAG, billing reasoning, guardrails, escalation policy, or
  conversation memory: wrong boundary. Genesys owns contact-center operations;
  the backend owns conversation intelligence and handoff content.
- Claiming a voice SLO from a single end-to-end timing: first decompose latency
  into channel ingress, end-of-turn, STT, backend, BSS/PDF, comparison, RAG, LLM,
  TTS, channel egress and Genesys handoff.
- Adding Genesys voice routing without testing barge-in and interruption across
  the media layer and voice runtime: cancellation behavior is a cross-component
  integration concern, not a backend-only feature.
- Treating missing implementation directories on `feat/restart-from-scratch` as
  an accident: they were removed intentionally so the project can restart from
  the backlog and architecture baseline.

## Checklist After Substantive Changes

- [ ] If implementation scaffolds exist, run their relevant tests.
- [ ] On documentation-only changes, run `git diff --check`.
- [ ] If a REST contract changed: update `docs/` (architecture.md, README, API).
- [ ] If there is a new bean/port: wire it in `DomainServiceConfig`.
- [ ] Update `docs/` together with code (not as a separate batch).
