# ADR-0017: Billing Explanation Is The V1 Value Focus On A General Support Foundation

## Status

Accepted

## Context

The documentation historically described two product scopes:

- a broad telecom support assistant with voice, text, RAG, multi-agent routing,
  escalation, admin monitoring, and future omnichannel integrations;
- a narrower V1 focused on explaining customer invoice discrepancies through
  read-only BSS data and deterministic billing comparison.

Both scopes are useful, but without an explicit hierarchy they look like
competing V1 definitions.

## Decision

The broad telecom support assistant is the product foundation and target vision.

The V1 value focus is billing/BSS invoice explanation:

- users ask why an invoice or billing period changed;
- the system retrieves evidence from read-only BSS-compatible sources;
- invoice or period deltas are computed deterministically;
- invoice PDFs are extracted into structured data when no validated structured
  invoice-line endpoint is available;
- the LLM formulates explanations only after evidence and deltas exist.

Generic support/RAG capabilities, voice interaction, multi-agent routing,
guardrails, escalation, persistence, and admin monitoring remain necessary
foundation capabilities. They do not replace the V1 billing evidence path.

## Consequences

- Product docs must describe the functional specification as the broad target
  vision and `v1-scope.md` as the first value slice.
- Billing correctness depends on BSS evidence and extraction quality, not only
  knowledge-base retrieval.
- The knowledge base explains telecom and pricing rules but must not invent
  customer-specific billing causes.
- Future support domains can reuse the same foundation after the billing V1
  slice is stabilized.

## Alternatives Considered

- **Treat the general support assistant as the only V1 scope**: rejected because
  it hides the accepted billing/BSS evidence requirements.
- **Treat billing explanation as a separate product unrelated to support/RAG**:
  rejected because the voice, RAG, guardrails, escalation, persistence, and
  admin foundation is shared.
- **Keep both product scopes without hierarchy**: rejected because it creates
  inconsistent acceptance criteria and roadmap priorities.

## Related Documents

- `docs/product/v1-scope.md`
- `docs/product/cahier-des-charges-fonctionnel.md`
- `docs/architecture/adrs/ADR-0003-billing-v1-uses-read-only-bss-and-deterministic-comparison.md`
- `docs/architecture/adrs/ADR-0004-bss-integration-through-typed-domain-ports.md`
- `docs/architecture/adrs/ADR-0005-invoice-pdf-extraction-before-llm-explanation.md`
