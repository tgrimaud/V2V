# Bug Ticket

## Header

- **Bug ID:** BUG-027
- **Title:** The streaming conversation path (`/converse-stream`) does not route to the billing chain → the voice UI never uses invoice data even with a channel-provided account
- **Status:** ✅ Fixed (2026-09-29) — routing extended to `/converse-stream` (shared `BillingRoutingService`); backend 661 tests + ArchUnit green; adversarial review 92/100 (Pass). Pending: live voice retest by the user.
- **Severity:** High
- **Priority:** P2
- **Detected by:** User validation (local run) + developer log analysis
- **Detected date:** 2026-09-29
- **Related ticket:** TASK-BE-061 / ADR-0055 (channel-provided identity + RAG↔billing routing)
- **Related epic:** EPIC-005 (answer engine) / EPIC-006 (voice runtime) / billing journey
- **Branch:** `task/TASK-BE-059-eir-b2c-period-model-and-mock` (same line as TASK-BE-061)
- **Owner:** Backend developer

## Problem Statement

TASK-BE-061 added RAG↔billing routing on `POST /api/conversation/converse` only. The voice UI
uses the **streaming** endpoint `POST /api/conversation/converse-stream` (SSE,
`VOICE_BACKEND_STREAM` on by default), which stayed **pure RAG with no routing**. So a customer
who selected account `99224964` in the UI and asked "pourquoi je paye plus ce mois-ci que le mois
dernier" got a **generic RAG answer** — the deterministic billing chain (and the invoice data)
was never reached on the real voice path.

## Environment

- **Environment:** local full-stack (backend `mvn spring-boot:run` on :8080, voice runtime on :8090, Postgres pgvector :5433, Ollama :11434)
- **Channel:** web voice (WebSocket streaming, `channel=web_voice`)
- **Provider configuration:** STT/TTS Gradium streaming; LLM overridden to `ollama` locally (Azure Foundry OpenAI endpoint unreachable from the dev host); embedding Ollama
- **Build or commit:** `task/TASK-BE-059…` at TASK-BE-061 (`ccc4fb7`)

## Reproduction Steps

1. Launch the full stack; open `http://127.0.0.1:8090/` (or `ws.html`).
2. Select account `99224964` in the account listbox.
3. Ask a billing question ("ma facture est plus élevée que le mois dernier").
4. The bot answers with a generic RAG reply; no invoice comparison / amounts.

## Expected Result

- On the streaming voice path, a channel-provided account + a billing question runs the
  deterministic billing chain and speaks the grounded explanation (amounts) — identical routing
  to `/converse`.
- "No account" or a non-billing turn keeps the RAG stream unchanged.

## Actual Result

Backend logs for the voice turns show `[CONVERSE-STREAM] … grounded=true confidence≈0.73` with
**no `[ROUTE]` line** — the streaming controller never evaluated the routing decision. The
`/converse` (non-streaming) `curl` test on the same account correctly logged
`[ROUTE] route=billing account_ref_present=true` + `slice=billing outcome=explained`.

## Evidence

- Backend `[CONVERSE-STREAM]` telemetry (local, session `613a06e7…`): several turns, all RAG
  (`confidence` ~0.71–0.74), **zero** `[ROUTE]` lines.
- `ConverseStreamController` bound the same `ConverseRequest` DTO (so `account_id` **was**
  deserialized and reached the backend), but `ConverseStreamSession` ignored it and called
  `ConverseStreamUseCase` (RAG) directly.
- Python side was already correct: `HttpBackendAdapter._payload` sends `account_id` on **both**
  the `/converse` and `/converse-stream` bodies.

## Root Cause (confirmed in code)

TASK-BE-061 wired routing only into `ConverseController` (blocking `/converse`). The streaming
counterpart `ConverseStreamController` → `ConverseStreamSession` was left on the pure-RAG path.
Since `VOICE_BACKEND_STREAM` is on by default, the voice runtime always hits `/converse-stream`,
so the billing routing shipped in BE-061 was never exercised by the real voice path.

## Impact

- customer impact: the flagship "explain my invoice" voice journey silently degrades to generic
  RAG; invoice data is never used even when identity is provided. High functional impact.
- operational/pilot-readiness impact: BE-061's own acceptance ("facture expliquée à la voix") was
  not actually met on the streaming path.
- security/privacy impact: none (the reference was already carried; no new exposure).

## Acceptance Criteria For Fix

- [x] `/converse-stream` routes exactly like `/converse`: account present + billing question →
      billing chain; else RAG stream. Shared decision (`BillingRoutingService`) — single source of
      truth for the predicate + billing-request mapping (no duplicated business rule).
- [x] On a billing turn the streaming session emits the pre-computed grounded billing text as a
      `chunk` + terminal `done` (the billing chain returns a full vetted answer, not a token
      stream — ADR-0052 D1a); escalation hand-off (by-reference) preserved.
- [x] "No account" / non-billing turns keep the RAG token stream unchanged (regression).
- [x] Tests: `ConverseStreamControllerBillingRoutingTest` (billing route streams grounded text +
      RAG bypassed; no-account keeps RAG), `BillingRoutingServiceTest` (decision unit),
      `ConversationRoutingServiceTest` unchanged (blocking path still green).
- [x] OpenTelemetry: `[ROUTE] route={billing|rag} account_ref_present={} stream=true` on the
      streaming path; billing slice recorded by the chain; reference never logged in clear.
- [x] Adversarial code review ≥ 90% (92/100, Pass — 2026-09-29).
- [x] Backend 661 tests + ArchUnit green; docs/backlog updated (ADR-0055 amended, this ticket).
- [ ] Live voice retest by the user (local).

## Developer Notes

- fix: extracted the routing decision into `BillingRoutingService`
  (`Optional<GeneratedAnswer> billingAnswer(RoutableTurn)`), reused by `ConversationRoutingService`
  (blocking) and `ConverseStreamSession` (streaming). Added `RoutableTurn.toBillingExplanationRequest()`
  so both build an identical billing request. `ConverseStreamController` injects the shared bean.
- `ConverseStreamController`/`ConverseStreamSession` unchanged otherwise; the RAG branch, idempotency,
  escalation hand-off and telemetry are preserved.
- naming: the decision service ends with `Service` to satisfy the `..application.service..` ArchUnit
  naming rule.
- **secondary recall fix (same session):** the live retest showed `[ROUTE] route=rag
  account_ref_present=true` for "pourquoi je **paye** plus ce mois-ci…" — the routing fired but
  `BillingIntentDetector` missed the phrasing (default keywords had `facture/montant/augmente/tarif`
  but no FR payment/price verbs). Extended the default keyword set in `BillingConfig`
  (`voice-support.billing.intent.keywords`) with `paye,paie,payer,paiement,prix,coute,cher` +
  regression test (`BillingIntentDetectorTest.detects_a_payment_phrasing_without_the_word_facture`).
  Keywords stay env-tunable.
- residual: on a billing turn the streamed answer arrives as a single chunk (the billing chain is
  blocking), so time-to-first-audio equals the full billing compute — acceptable (deterministic +
  one LLM rephrase); token-level streaming of billing text is not applicable.

## QA Retest

- **Retested by:** automated (2026-09-29)
- **Retest date:** 2026-09-29
- **Scenarios rerun:** `ConverseStreamControllerBillingRoutingTest`, `BillingRoutingServiceTest`, full backend suite
- **Result:** GO — 662 tests, 0 failures, ArchUnit green. **Live retest PASSED** (local, 2026-09-29):
  `POST /converse-stream` with `account_id=99224964` + "pourquoi je paye plus…" →
  `[ROUTE] route=billing … stream=true` + `slice=billing outcome=explained`, streamed grounded billing
  text ("55,47 € = 16,98 + 8,50 + 29,99", confidence 0.9); same question **without** `account_id` →
  `route=rag` generic answer (confidence 0.72). User to confirm from the voice UI.

## Closure

- **Closed by:**
- **Closed date:**
- **Closure reason:**
