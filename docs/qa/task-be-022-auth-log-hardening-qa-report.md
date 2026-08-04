# QA Functional And Latency Report — TASK-BE-022

**Ticket:** TASK-BE-022 — Constant-time API-key gate unification (`ApiKeyGuard`) + client-controlled
log/header sanitization (`correlation_id` / `channel`).
**Branch:** `task/TASK-BE-022-auth-log-hardening` (commit `84c8fee` + this QA regression test).
**Date:** 2026-08-04
**Source findings:** full backend adversarial review 2026-08-04 (91/100) — non-blocking findings
**#1** (timing side-channel / auth-gate inconsistency) and **#3** (log injection via client fields).
**Adversarial code review (pre-QA):** 95/100 — QA gate **Pass**, no blocking findings.

## Executive Summary

- **Overall readiness:** **GO.** The change removes the `String.equals` timing side-channel on the
  two converse endpoints (now delegating to the constant-time `ApiKeyGuard`) and neutralizes CR/LF
  log injection / HTTP response splitting through client-supplied `correlation_id` / `channel`.
  Behaviour is preserved for well-formed inputs; the localhost pilot's open-when-no-key semantics
  are unchanged.
- **Main blockers:** none.
- **Residual risks:** live end-to-end smoke deferred (deterministic transport hardening fully
  exercised through the real MVC filter+controller stack in automation — see Residual); the
  BE-019 `ApiKeyAuthInterceptor` still logs `request.getRequestURI()` unsanitized (percent-encoded
  → negligible, out of this ticket's scope, tracked as a low note).

## Scope Tested

- **Epics / stories:** EPIC-009 (Trust, security and auditability) — TASK-BE-022. Related: TASK-BE-019
  (`ApiKeyGuard` + interceptor), TASK-BE-009 (`CorrelationId` / MDC), ADR-0021 (`/converse` gate).
- **Channels:** backend HTTP surface (`/api/conversation/converse`, `/converse-stream`) — the voice
  runtime's server-to-server contract; no browser CORS on these routes.
- **Providers / fakes:** JUnit 5 manual fakes (`ConverseUseCase`, `ConverseStreamUseCase`,
  `SimpleMeterRegistry` telemetry, no-op executor). No Mockito. No DB/Ollama/Mistral needed.
- **Environment:** `mvn test` (unit + `@WebMvcTest` slices + ArchUnit + BDD), local JDK. No running
  backend required.

## Functional Results

| Area | Status | Evidence | Notes |
|---|---|---|---|
| API-key compare is constant-time on every endpoint | ✅ Pass | `ApiKeyGuard.authorized` = `MessageDigest.isEqual`; `ConverseController`/`ConverseStreamController` delegate to it; inline `String.equals` methods deleted | Single definition of "authorized" across `/converse`, `/converse-stream`, interceptor-gated KB/read endpoints |
| Auth accept/reject unchanged (empty key = open, configured key enforced) | ✅ Pass | `ConverseControllerApiKeyTest`, `ConverseStreamControllerAuthTest` green (401 without/with wrong key; 200 / async-started with matching key) | Pilot semantics preserved (ADR-0021) |
| CR/LF in body `correlation_id` cannot forge a log line nor split the response header | ✅ Pass | `ConverseControllerTest.sanitizesMaliciousCorrelationIdHeader` — end-to-end MVC: body `correlation_id="corr\r\nInjected: 1"` → echoed header = single clean value `corrInjected: 1` | The exact non-blocking test gap flagged by the code review, now closed |
| `CorrelationId.sanitize` strips ISO control chars, caps length, handles null/blank | ✅ Pass | `CorrelationIdTest` (5): CR/LF strip, 200-char cap, null→null / whitespace-trim, `set`/`setChannel`→MDC clean, blank channel→`n/a` | Choke-point covers MDC-derived logs `[TELEMETRY]/[PROMPT]/[GUARDRAIL]/[LANGUAGE]` for free |
| Inbound `X-Correlation-Id` header sanitized + correlation-id continuity preserved | ✅ Pass | `CorrelationIdFilterTest` green (well-formed id reused + echoed, generated when absent, MDC always cleared); `resolve` now routes through `sanitize` | No regression on the runtime→backend id continuity |
| No functional/answer regression | ✅ Pass | Full suite **336** green (unit + slices + ArchUnit + Cucumber BDD), ArchUnit boundaries OK | Behaviour-preserving change |

## Latency Results

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| Auth gate + field sanitization (transport) | n/a | n/a | n/a | — | — | **Not a measured ADR-0018 pipeline slice.** Header/x-api-key check + `MessageDigest.isEqual` + `sanitize` (single pass over a ≤200-char string) are sub-millisecond and off the STT→backend→LLM→TTS critical path. A rejected request short-circuits **before** the use case (faster-failing than the open path). No latency impact expected or claimed. |

All canonical voice slices (channel ingress, end-of-turn, STT, backend orchestration, BSS/PDF,
comparison, RAG, LLM, TTS, channel egress, Genesys handoff) are **unaffected** by this transport
hardening and were not re-measured.

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| `ApiKeyGuard` (shared/web/security) | ✅ | Now the single constant-time authorizer for all gated endpoints | — |
| `ConverseController` / `ConverseStreamController` | ✅ | Inline gates removed; delegate to `ApiKeyGuard`; log fields sanitized via `nullSafe`; stream echoes a sanitized correlation id | — |
| `CorrelationId` / `CorrelationIdFilter` (shared/observability) | ✅ | `sanitize` choke-point applied at every client-value entry (MDC, log, response header) | — |
| `ApiKeyAuthInterceptor` (BE-019) | ⚠️ Low | Logs `request.getRequestURI()` unsanitized | Negligible (URI is percent-encoded, Tomcat rejects raw control chars); optional defense-in-depth, out of BE-022 scope |
| Observability | ✅ | Correlation-id continuity preserved; structured-log integrity strengthened; no new slice/metric required | — |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Low | `ApiKeyAuthInterceptor` logs the request URI without `sanitize` | Quasi-nil (encoded URI, container-rejected control chars) | Backend (optional follow-up, not BE-022) |
| Info | Live end-to-end smoke against a running backend not executed | None — deterministic transport hardening, fully covered by the real MVC filter+controller automation | QA (deferred, see Residual) |

## Open Questions

- **Product:** none.
- **Architecture:** none (transport-layer hardening, no boundary change; `sanitize` lives in
  `shared/observability`, the gate in `shared/web/security` — both allowed shared dependencies).
- **Technical:** none.

## Recommendation

- **Go / No-go:** **GO** — merge-ready pending the user's explicit merge request.
- **Required fixes before pilot:** none. Optional follow-ups: (1) route the interceptor's logged
  request URI through `sanitize`; (2) a one-off live smoke (post a CR/LF `correlation_id` to a
  running backend, confirm single-line logs + single-value header) can be folded into the next
  live backend session, but is not required given the automated MVC coverage.

### Residual (deferred live smoke — rationale)

The BE-019 QA ran a live gate smoke on `:8081` because auth interacts with the full RAG/LLM path
(200 on a real retrieval). TASK-BE-022 is purely deterministic transport hardening: the
constant-time compare and `sanitize` do not depend on pgvector/Ollama/Mistral, and the header echo
is already exercised through the **real** `CorrelationIdFilter` + controller in
`ConverseControllerTest.sanitizesMaliciousCorrelationIdHeader` (MockMvc drives the actual servlet
filter chain + controller). A full backend boot would add no discriminating signal, so the live
smoke is deferred rather than blocking.
