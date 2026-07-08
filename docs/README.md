# Voice Support Bot Documentation

## Structure

| Folder | Audience | Contents |
|--------|----------|----------|
| [`product/`](product/) | Product / delivery | Broad functional specification and V1 billing/BSS scope |
| [`architecture/`](architecture/) | Architecture / engineering | System architecture, ADRs, infra target and architecture diagrams |
| [`integrations/`](integrations/) | Architecture / backend / BSS | External system integration plans and contracts |
| [`knowledge-base/`](knowledge-base/) | Content contributors / engineering | RAG knowledge base authoring and technical docs |
| [`engineering/`](engineering/) | Developers | Development guide and implementation conventions |
| [`operations/`](operations/) | Delivery / ops | Operational backlog and run-oriented follow-ups |

## Main Entry Points

- Product hierarchy: [`product/cahier-des-charges-fonctionnel.md`](product/cahier-des-charges-fonctionnel.md)
  describes the broad support assistant target, while
  [`product/v1-scope.md`](product/v1-scope.md) defines the billing/BSS invoice
  explanation V1 value slice.
- Architecture: [`architecture/architecture.md`](architecture/architecture.md)
- Architecture decisions: [`architecture/adrs/`](architecture/adrs/)
- Documentation coherence review: [`architecture/documentation-coherence-review-2026-07-08.md`](architecture/documentation-coherence-review-2026-07-08.md)
- Infrastructure V1: [`architecture/infra-v1.md`](architecture/infra-v1.md)
- Galaxion BSS integration: [`integrations/galaxion/bss-integration-plan.md`](integrations/galaxion/bss-integration-plan.md)
- Missing Galaxion inputs: [`integrations/galaxion/missing-inputs.md`](integrations/galaxion/missing-inputs.md)
- Invoice PDF extraction JSON: [`integrations/galaxion/invoice-extraction-json.md`](integrations/galaxion/invoice-extraction-json.md)
- Knowledge base guide: [`knowledge-base/knowledge-base-guide.md`](knowledge-base/knowledge-base-guide.md)
- Development guide: [`engineering/development-guide.md`](engineering/development-guide.md)
- Operational backlog: [`operations/backlog.md`](operations/backlog.md)
