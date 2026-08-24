# ADR-0004: BSS Integration Goes Through Typed Domain Ports

## Status

Accepted

> **Implementation status (2026-08-05): NOT IMPLEMENTED — target decision.** No
> `BssBillingPort` or BSS adapter exists in `backend/src/main` yet (grep-verified).
> This governs the future billing V1 work (Sprint 12+, gated by OQ-003).

## Context

The operator BSS is composed of multiple services. V1 cannot block on full
production access to every BSS dependency, but the billing domain must not be
coupled to local fixtures or exploratory tools.

The project may use MCP or ad-hoc tools for exploration, but runtime customer
flows need stable, typed contracts.

## Decision

BSS access goes through typed domain ports such as `BssBillingPort` or
`BssCustomerContextPort`.

Adapters can target:

- a local contract-compatible mock;
- a BSS sandbox;
- the real BSS;
- snapshots for tests or demos.

The billing domain must not change when switching from mock to real BSS. The
adapter configuration changes; the domain contract stays stable.

## Consequences

- Early development can proceed with realistic fixtures without blocking on all
  real BSS environments.
- The mock must be contract-compatible, not an internal shortcut.
- BSS provider details stay outside the billing domain.
- The team must keep mock payloads aligned with the useful BSS contract.

## Alternatives Considered

- **Use MCP as the runtime BSS access path**: rejected for customer-facing flows
  because MCP is better suited to exploration and internal tools.
- **Hard-code fixtures inside the bot**: rejected because it would make the real
  BSS migration a rewrite.

## Related Documents

- `docs/integrations/galaxion/bss-integration-plan.md`
- `docs/integrations/galaxion/galaxion-billing-contracts.md`
- `docs/product/v1-scope.md`
