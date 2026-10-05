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

## Amendment (2026-10-05, TASK-BE-067) — service added/removed is a named cause

The deterministic comparison attributes each line delta to a `BillingCauseType`. A
`SUBSCRIPTION` line was previously left unmapped and always fell into the fail-closed
`UNEXPLAINED` bucket. Real multi-service invoices showed this is too coarse: when a customer
**adds or removes a whole service**, that service's base line is a `SUBSCRIPTION` that
**appeared** or **disappeared** — a perfectly explainable change, not an opaque one.

Decision: the cause of a `SUBSCRIPTION` delta now depends on its `ChangeKind` —
`APPEARED → SERVICE_ADDED`, `DISAPPEARED → SERVICE_REMOVED` (both named, voiceable causes that
reduce the residual) — while an in-place `CHANGED` subscription (recurring amount moved with no
finer line to say why) **stays `UNEXPLAINED`** and keeps gating confidence/escalation (BR-003).
Still deterministic, no LLM. Non-subscription categories are unchanged (mapped by category).
Verified end to end on the real eir B2C PDFs (`EirB2cBillingComparisonE2eTest`): accounts
adding eir TV / eir Mobile 5G are now fully explained (residual €0.00) instead of carrying the
new service's base amount as an unexplained residual.

## Related Documents

- `docs/product/v1-scope.md`
- `docs/integrations/galaxion/bss-integration-plan.md`
