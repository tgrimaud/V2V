# Backend Answer-Engine — Hardening Tasks

Cross-cutting hardening for the Java answer-engine backend (`voice-support-bot/backend`,
contexts `knowledge` + `conversation`). These are **out of the Sprint 7 core theme**
(answer-engine happy path BE-004…BE-006) and scheduled opportunistically before the
pilot, unless pulled in earlier.

| Task | Title | Classification | Depends on | Status |
|---|---|---|---|---|
| TASK-BE-012 | Backend REST error contract (`GlobalExceptionHandler` + `ErrorResponse`) | V1 hardening | TASK-BE-002 | Planned (out of Sprint 7 core theme) |

---

## TASK-BE-012 — Backend REST error contract

**Parent:** EPIC-005 (Answer engine) — cross-cutting API hardening
**Classification:** V1 hardening
**Status:** ✅ Implemented + 137 tests green + adversarial review 92/100 + QA GO
(2026-07-20) on `task/TASK-BE-012-backend-error-contract` (cut from
`task/TASK-BE-009-observability`); merge-ready (awaiting the user's explicit merge).
Review fixed one acceptance gap: a provider `RestClientException` (e.g. embedding
endpoint down) now maps to 503 `ERR_UPSTREAM` instead of falling to 500.
**Medium finding fixed pre-merge (2026-07-20):** the LLM timeout executor is now
**bounded** (`ThreadPoolExecutor`, max 16 in-flight, `SynchronousQueue` +
`AbortPolicy`; rejection → sanitized 503) instead of an unbounded cached pool, and the
chat provider now carries a **HTTP read + connect timeout** (`RestClient` request
factory) so a stalled socket is actually closed rather than left hanging on an
abandoned thread. Live-verified with `LLM_TIMEOUT_MS=1`: `SocketTimeoutException: Read
timed out` on the Mistral socket → `UpstreamUnavailableException` → sanitized 503
(`llm_wording` slice `outcome=error`, ~79 ms, well below the 2 s executor backstop).
**Priority:** Medium
**Branch:** `task/TASK-BE-012-backend-error-contract`
**Surfaced by:** TASK-BE-004 adversarial review (2026-07-18) — degraded-mode / privacy
finding.
**Relates to:** TASK-BE-009 (observability / correlation id), ADR-0010
(industrialization: contracts + observability), TASK-WEB-006 (the voice-runtime
equivalent — generic error responses, closes RF-013).

### Context

The backend currently has **no `@RestControllerAdvice`**. When a dependency is down
(Ollama embedding endpoint, Postgres/pgvector) or a request is malformed, the REST
endpoints (`/api/knowledge/sync`, `/api/knowledge/ingest`,
`/api/conversation/retrieve`) fall through to Spring's **default error handling** and
can return a 500 whose body may echo raw exception text (upstream URLs, driver
messages, stack hints).

This mirrors two problems already fixed elsewhere in the workspace:
- voice runtime **RF-013 / TASK-WEB-006** — stop echoing raw provider error text in
  `/stt` `/tty` `/turn` 502 bodies;
- dashboard `GlobalExceptionHandler` — return a generic `ERR_UPSTREAM` + correlation
  id, keep full detail server-side only.

### Objective

Introduce a shared, sanitized REST error contract in the backend:

- `@RestControllerAdvice GlobalExceptionHandler` returning a structured
  `ErrorResponse` (snake_case) with a stable `error_code`, a `correlation_id`, and a
  **generic** client message — never `ex.getMessage()` verbatim.
- Map the common cases:
  - bean-validation / malformed body → **400** (`ERR_400`);
  - upstream dependency failure (embedding / vector store unavailable or timing out)
    → **502/503** (`ERR_UPSTREAM`);
  - not found where relevant → **404**.
- Add request validation: `@NotBlank` on `RetrievalRequest.question`
  (`spring-boot-starter-validation` is already on the classpath) so a blank question
  returns a 400 instead of a silent `LOW_CONFIDENCE`.
- Log the full exception detail server-side with the correlation id (structured),
  nothing sensitive in the client body.

### Acceptance

- A malformed request (blank/missing `question`) returns `400` with an `ErrorResponse`
  (`error_code` + `correlation_id`), not a `LOW_CONFIDENCE` 200 and not a 500.
- A dependency-down request (embedding/vector store unavailable) returns a documented
  `502/503` `ErrorResponse` with a stable `error_code` + `correlation_id` and **no**
  internal detail (no upstream URL, no driver/stack text) in the body.
- The full error detail is available server-side in structured logs with the same
  `correlation_id`.
- Covered by `@WebMvcTest` (contract) + a focused test proving no raw exception text
  leaks into the response body.

### Notes

- Keep the domain/application layers free of transport concerns — the advice lives in
  `shared/web` (or `shared/web/rest`) so both contexts reuse it.
- Correlation-id propagation should align with TASK-BE-009 (OTel); if BE-009 lands
  first, reuse its correlation-id source instead of inventing a second one.

### Implementation notes (2026-07-19)

Delivered on `task/TASK-BE-012-backend-error-contract` (branched from BE-009 so it
reuses the `CorrelationId` source, per the note above):

- `shared/web/rest/GlobalExceptionHandler` (`@RestControllerAdvice`) + `ErrorResponse`
  (`{error_code, message, correlation_id}`, snake_case). Maps bean-validation /
  malformed body → **400 `ERR_400`**, `UpstreamUnavailableException` + `DataAccessException`
  → **503 `ERR_UPSTREAM`**, and a generic fallback → **500 `ERR_INTERNAL`**. Client
  bodies carry only a stable code + generic message + `correlation_id`; the full
  exception (cause/stack) is logged server-side under the same id, never echoed.
- `@NotBlank` on `RetrievalRequest.question` + `@Valid` on `/retrieve` → a blank/missing
  question is a 400, not a silent `LOW_CONFIDENCE` 200.
- Hard LLM timeout in `AbstractChatClientAnswerAdapter` (`voice-support.llm.timeout-ms`,
  default 8000, 0 disables): the chat call runs on a **bounded** daemon executor
  (`ThreadPoolExecutor`, max 16 in-flight, `SynchronousQueue` + `AbortPolicy` — overflow
  is rejected and degrades to 503, never piling up) with
  `future.get(timeout + 2 s backstop)`; a timeout/failure/rejection throws
  `UpstreamUnavailableException` → sanitized 503 (the voice runtime then speaks the safe
  degraded turn). The provider chat API (`LlmConfig`) also sets a **HTTP read timeout =
  `timeout-ms`** and **connect timeout = `voice-support.llm.connect-timeout-ms`
  (default 3000)** on its `RestClient`, so the read timeout normally fires first and
  closes the socket cleanly (the executor timeout is only a backstop for pre-read hangs).
  The timed-out LLM slice is recorded with `outcome=error` (BE-009 telemetry), keeping
  the `tts/llm` success p95 clean.
- Tests (`mvn test` 134 green): `GlobalExceptionHandlerTest` (400 validation, malformed
  JSON, 503 upstream **no-leak**), `ConverseDegradedTest` (upstream → sanitized 503 with
  the runtime correlation id in body + header, no leak).
- Live-verified (pgvector 5433 + Ollama + Mistral, `LLM_TIMEOUT_MS=1`): blank/malformed
  → 400 `ERR_400`; valid non-LLM retrieve still 200; converse LLM timeout → 503
  `ERR_UPSTREAM` (generic message, `correlation_id=cid-degraded-live` in body + header);
  server log kept the full `LLM provider timed out after 1 ms` stack under the id.
