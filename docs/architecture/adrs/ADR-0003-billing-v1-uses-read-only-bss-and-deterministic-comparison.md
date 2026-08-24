# ADR-0003: Billing V1 Uses Read-Only BSS And Deterministic Comparison

## Status

Accepted

> **Implementation status (2026-08-05): NOT IMPLEMENTED — target decision.** No
> `BssBillingPort`, invoice-PDF extractor, or deterministic comparison engine
> exists in `backend/src/main` yet (grep-verified). Billing V1 is deferred
> (Sprint 12+, gated by OQ-001/003/004). The runnable product answers billing
> questions from the static knowledge base via RAG only.

## Context

The V1 product value is invoice explanation for telecom customers. Users ask why
one invoice or billing period differs from another.

Invoice explanations must be reliable and traceable. A language model cannot be
allowed to infer billing causes or calculate amounts without evidence.

## Decision

Billing V1 uses the BSS as the read-only source of truth. The system must:

- retrieve invoices, contracts, offers, options, discounts, usage, adjustments,
  and billing events from BSS-compatible sources;
- compare invoices or periods deterministically;
- produce explicit causes and proof references;
- use the LLM only to formulate the explanation in clear language after the
  deterministic comparison has produced evidence.

The LLM must not calculate invoice amounts or invent billing causes.

## Consequences

- Billing correctness depends on BSS access and extraction quality, not LLM
  creativity.
- The domain model must represent billing evidence, deltas, and confidence.
- Missing or inconsistent BSS data must lead to a transparent limitation or
  escalation, not an invented answer.

## Alternatives Considered

- **Ask the LLM to read invoice data and infer the explanation**: rejected
  because it is not auditable enough for billing support.
- **Start with FAQ-only invoice explanations**: rejected because invoice deltas
  need customer-specific data and proof.

## Related Documents

- `docs/product/v1-scope.md`
- `docs/integrations/galaxion/bss-integration-plan.md`
