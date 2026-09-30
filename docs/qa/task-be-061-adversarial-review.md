# Adversarial Code Review — TASK-BE-061 (channel-provided identity + RAG↔billing routing on `/converse`)

**Reviewed:** 2026-09-29 · **ADR:** ADR-0055 · **Branch:** `task/TASK-BE-059-eir-b2c-period-model-and-mock`

## Verdict

**Proceed.**

## Satisfaction Score

Score: **93/100**
QA gate: **Pass**

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None. | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | The route decision is emitted as a structured log line (`[ROUTE] route=… account_ref_present=…`) but there is no dedicated OTel **metric** for the billing-vs-RAG split. | `ConversationRoutingService.answer` | Adding a counter `conversation.route{route=billing\|rag}` would let Ops report the billing-routing rate. The turn is already timed by the `BACKEND_REQUEST` slice, so latency is observable; a route-split metric is a nice-to-have (follow-up, not blocking). |
| Low | Session-locked identity: switching account mid-call requires a reconnect (envelope built once per connection). | `ChannelEnvelope.for_web_turn`, `_serve_connection` | Accepted for pilot and documented in ADR-0055; no action. |
| Low | Pilot trust model — a channel-provided reference is accepted at a low bar (existence in the mock directory), no strong auth. | ADR-0050 / ADR-0055 residual | Governed by OQ-001; must not ship to real customers until then. Documented. |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| Account selected + billing turn → grounded comparison (or fail-closed hand-off) via `/converse`, no separate endpoint | ✅ | `ConversationRoutingService.routesToBilling` + `toBillingRequest`; `ConversationRoutingServiceTest.routes_to_billing_when_account_reference_present_and_billing_intent` |
| "Sans compte" (no `account_id`) → RAG path unchanged | ✅ | `routes_to_rag_when_no_account_reference_even_if_billing_intent`; `test_omits_account_id_when_no_channel_reference` |
| Account present but non-billing turn → RAG | ✅ | `routes_to_rag_when_account_reference_present_but_not_a_billing_question` |
| Forced language still reaches RAG | ✅ | `forwards_the_forced_language_to_rag` |
| Channel supplies identity up front (UI listbox → `?account_id=` → envelope → `/converse` body) | ✅ | UI selects in `ws/webrtc/index.html`; `_resolve_account_reference`; `HttpBackendAdapter._payload`; `test_sends_account_id_when_a_channel_reference_is_present` |
| Reference never logged in clear | ✅ | `[ROUTE] … account_ref_present={}` (boolean); envelope telemetry `account_ref_present="true"` only |
| Routing ADR created | ✅ | ADR-0055 + README row |

## Test Evidence

- Developer tests: `ConversationRoutingServiceTest` (4 branches, manual fakes, no Mockito); 4 `@WebMvcTest` configs updated to wrap the RAG use case in `ConversationRoutingService`; Python `test_http_backend` (account_id present/absent) + `test_websocket_app` (`_resolve_account_reference`). Backend **656** green + ArchUnit green; Python **688** + behave **15/43/194** green.
- Missing tests: none blocking. (A WebRTC-offer `account_id` end-to-end test is covered indirectly by the signaling unit path; UI wiring is thin and mirrors the language selector.)
- QA scenarios to run: manual UI check — select each of the 3 accounts, ask "ma facture a augmenté", confirm a grounded/escalation answer; select "Sans compte", confirm generic RAG.

## Observability And Latency

- Relevant slices: backend request (routing sits inside the `BACKEND_REQUEST` timed slice → both routes are timed the same way).
- OpenTelemetry traces: unchanged; correlation id continuity preserved (`establishContext`), `traceparent` derived from correlation id on the Python hop still applies.
- Metrics: existing channel-delivery + backend-request timing. Route-split counter is a non-blocking follow-up.
- Structured logs: `[ROUTE] route=… account_ref_present=…` (no PII); `[CONVERSE]` unchanged.
- Missing: dedicated route-split metric (non-blocking).
- Risk: low.

## Security And Privacy

- Sensitive data risk: account reference is personal data — **never logged/exported in clear** on either tier (only presence). ✅
- Identity/access risk: fail-safe — "no account" never routes to billing; billing requires an explicit channel reference. Pilot low-bar trust accepted (OQ-001).
- Logging risk: client-controlled fields still CR/LF-sanitized (`nullSafe`); `account_id` not in `[CONVERSE]`/`[ROUTE]` value output.

## Required Developer Actions

1. None blocking. (Optional follow-up: add a `conversation.route` split counter.)

## Residual Risk If Accepted

- Pilot trust model: channel-provided reference accepted at a low bar (no strong auth) — OQ-001; do not ship to real customers until resolved.
- Session-locked identity (reconnect to switch account) — acceptable for pilot.
- Multi-service cause-attribution escalations remain — tracked by TASK-BE-060.
