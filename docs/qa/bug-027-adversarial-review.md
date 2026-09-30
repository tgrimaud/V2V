# Adversarial Code Review — BUG-027 (`/converse-stream` billing routing)

**Reviewed:** 2026-09-29 · **Related:** TASK-BE-061 / ADR-0055 · **Branch:** `task/TASK-BE-059-eir-b2c-period-model-and-mock`

## Verdict

**Proceed.**

## Satisfaction Score

Score: **92/100**
QA gate: **Pass**

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None. | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | On a billing turn the grounded text is emitted as a **single** SSE `chunk`, so time-to-first-audio equals the full billing compute (deterministic + one LLM rephrase) rather than a token trickle. | `ConverseStreamSession.answerFromBilling` | Acceptable — the billing chain is blocking by design (ADR-0052 D1a); token-level streaming is not applicable. If latency matters, sentence-split the billing text into multiple chunks (follow-up). |
| Low | The billing-routing predicate is duplicated conceptually between the blocking and streaming callers, but the **decision + mapping** are centralized in `BillingRoutingService` + `RoutableTurn`. | `BillingRoutingService`, `RoutableTurn.toBillingExplanationRequest()` | No action — single source of truth achieved; callers only choose their fallback (RAG blocking vs RAG stream). |
| Low | No dedicated route-split metric (same as BE-061). | — | Optional counter `conversation.route{route,stream}` (follow-up). |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| `/converse-stream` routes like `/converse` (account + billing intent → billing) | ✅ | `ConverseStreamSession.processTurn` → `billingRoutingService.billingAnswer`; `ConverseStreamControllerBillingRoutingTest.billingRouteStreamsBillingText` |
| Billing turn streams grounded text (chunk + done), RAG bypassed | ✅ | `answerFromBilling` (onChunk + finalizeTurn); test asserts `BILLING_TEXT` present, `RAG_TEXT` absent |
| No account / non-billing → RAG stream unchanged | ✅ | `noAccountKeepsRag` test; existing 7 stream tests still green |
| Escalation hand-off preserved on billing fail-closed | ✅ | `finalizeTurn` → `prepareHandoffIfEscalated` (shared with RAG path) |
| Single source of truth (no duplicated business rule) | ✅ | `BillingRoutingService` reused by blocking + streaming; `BillingRoutingServiceTest` |
| Reference never logged in clear | ✅ | `[ROUTE] route=… account_ref_present=… stream=true` (boolean only) |

## Test Evidence

- Developer tests: `ConverseStreamControllerBillingRoutingTest` (2), `BillingRoutingServiceTest` (3), `ConversationRoutingServiceTest` unchanged, 7 streaming `@WebMvcTest` configs updated with a disabled router bean. Backend **661** tests, 0 failures; ArchUnit (Hexagonal + ContextBoundary + Naming) green.
- Missing tests: none blocking.
- QA scenarios to run: live voice — select `99224964`, ask a billing question → grounded amounts spoken; "Sans compte" → generic RAG.

## Observability And Latency

- Slices: routing sits inside the streaming `backend_request`/`backend_first_token` slices; billing slice recorded by the chain (`slice=billing`).
- Logs: `[ROUTE] route={billing|rag} account_ref_present={} stream=true` on the streaming path; `[CONVERSE-STREAM]` unchanged.
- Missing: route-split metric (non-blocking).

## Security And Privacy

- Reference (personal data) never logged in clear (only presence). No new exposure — the reference was already carried on the request. Fail-safe: no account → never billing.

## Required Developer Actions

1. None blocking. (Optional: multi-chunk billing text; route-split counter.)

## Residual Risk If Accepted

- Single-chunk billing latency (blocking chain) — acceptable.
- Pilot low-bar identity trust (OQ-001) and session-locked identity — unchanged from ADR-0055/BE-061.
