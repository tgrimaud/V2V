# ADR-0050: Pilot Customer Identity Resolution For Billing Access

## Status

Accepted (2026-09-10)

> Records how the pilot resolves a **customer identity** to a billing `AccountId`
> before any billing access, and the **fail-closed** posture around it. Complements
> **ADR-0003 / ADR-0004** (read-only BSS billing through a typed port), **BR-002-1**
> (customer access scoped by `AccountId`), and is gated by **OQ-001** (identity /
> authentication policy). Implementation: **TASK-BE-044** (Sprint 14).

## Context

Billing is the most sensitive V1 domain: an invoice must only ever be reachable by
the customer it belongs to (**BR-002-1**, fail-closed). Every `BssBillingPort` call is
already scoped by an `AccountId`, but nothing yet turns *who is on the call/chat* into
that `AccountId`.

For the pilot:

- there is **no strong customer authentication** (no IVR PIN, no verified ANI, no SSO)
  — the authentication policy is an open question (**OQ-001**);
- billing runs on **synthetic accounts** (`customer-eir-001..006`, TASK-BE-040), not a
  real customer directory;
- the channel provides, at best, a **claimed** identifier (a web-entered account
  reference, or a Genesys-provided ANI/attribute), which is **not proof of identity**.

We still need a deterministic seam so the billing chain (TASK-BE-045) can obtain an
`AccountId` — or refuse — without guessing, and so the real verification policy can
drop in later behind the same boundary.

## Decision

1. **Introduce an identity seam** in the billing context: an inbound
   `ResolveCustomerIdentityUseCase` and an outbound `CustomerDirectoryPort`. The use
   case turns an `IdentityClaim` (channel + reference) into an `IdentityResolution`.

2. **Directory lookup returns matches; the domain decides the verdict.**
   `CustomerDirectoryPort.lookup` returns the `AccountId`s matching the claim; the
   `CustomerIdentityService` maps **0 → UNRESOLVED, 1 → RESOLVED, ≥2 → AMBIGUOUS**.

3. **Fail-closed.** Only a `RESOLVED` identity grants billing access
   (`IdentityResolution.canAccessBilling()`); `UNRESOLVED` and `AMBIGUOUS` **never**
   yield an `AccountId`. Downstream (TASK-BE-045) must then clarify or escalate — it
   must never fall back to an unscoped or guessed account.

4. **Pilot trust model.** A channel-provided reference is accepted at a **low bar**
   (existence in the directory), because the pilot uses synthetic accounts and the
   real authentication/verification strength is governed by **OQ-001**. The directory
   is a **mock adapter** now (`InMemoryCustomerDirectoryAdapter`, aligned with the
   `customer-eir-*` fixtures); a real CRM/BSS directory adapter registers later behind
   the same port.

5. **Placement.** Identity lives in the **billing bounded context** for the pilot,
   because it resolves the billing `AccountId`. If identity later spans domains
   (technical support, sales…), it may be extracted to its own context behind the same
   port — no caller change.

6. **Privacy.** The claimed reference is potentially personal data: it is **never
   logged in clear**. Observability records the channel, the resolution status/outcome
   and the resolved `AccountId` (already an internal id), not the raw claim.

## Consequences

- The billing chain has a single, testable, **fail-closed** entry point for identity;
  ambiguity is an explicit, safe outcome rather than a silent first-match.
- The pilot can run end-to-end on synthetic accounts without real authentication.
- **Residual risk (accepted for the pilot):** a claimed reference is trusted without
  strong verification — acceptable on synthetic data, **must not** ship to real
  customers until OQ-001 defines the verification strength (step-up auth, verified ANI,
  etc.). Tracked by OQ-001; the seam is designed so the policy drops in behind the port.
- No PII in logs by construction.

## Alternatives Considered

- **Trust the ANI/reference blindly and always resolve** — rejected: spoofable, and it
  provides no safe handling of "no match" or "multiple matches" (breaks BR-002-1).
- **Implement strong authentication now** — premature: there is no real directory and
  OQ-001 is unresolved; it would block the pilot for a policy we cannot yet finalize.
- **Put identity in the conversation context** — deferred: for V1 identity only serves
  billing's `AccountId`; extraction to a shared context is a later move behind the same
  port if other domains need it.
