# Adversarial Code Review — TASK-OBS-002 (Structured JSON logs, both tiers)

**Branch:** `task/TASK-OBS-002-structured-json-logs` (off `feat/restart-from-scratch`)
**Scope reviewed:** voice-runtime JSON log formatter + per-turn `correlation_id` contextvar +
`scrub_message` sanitization (`VOICE_LOG_FORMAT=json`); backend Spring Boot 3.4 native
structured logging enablement (`LOGGING_STRUCTURED_FORMAT_CONSOLE`, config-only); deploy
passthrough (compose + Ansible `*.env.j2` + `group_vars`, default OFF).
**Reviewer skill:** `.cursor/skills/adversarial-code-review`
**Date:** 2026-09-30 (updated same day — correlation binding extended to all four ingress paths)

## Verdict

Proceed.

## Satisfaction Score

Score: 96/100
QA gate: Pass

> **Update (2026-09-30):** the initial residual (correlation id bound only on the browser WS
> path) has been closed. The `correlation_id` contextvar is now bound on **all four** voice
> ingress paths — browser WS (`_serve_connection`), **Genesys** (`_serve_genesys_connection`,
> set/reset), **WebRTC** (`WebRtcSignalingService._start_session_task`, isolated copied
> context so concurrent calls on the shared loop don't leak ids) and **batch REST**
> (`handle_turn` scope + `_run_blocking` copying the context into the thread executor). +4
> tests (698 unittest total, behave 15/43/194). Score raised 93 → 96.

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | No backend-side automated assertion that a line is JSON with the MDC keys. | Backend change is config-only; no Java touched. | Native Spring Boot structured logging is a framework feature (asserting it tests the framework). `mvn test` is unaffected. A one-line manual smoke on the pilot when enabled is enough. |
| Low | Batch REST logs emitted **inside pipecat/aiortc-owned tasks** (not created under `handle_turn`'s scope) would not inherit the id. | Contextvar is copied at task-creation time. | The batch path runs the processor synchronously in the executor (covered by the context copy); no long-lived child tasks are spawned outside the scope. Not a concern for the current batch processor. |
| Low | `configure_logging` replaces **all** root handlers (`root.handlers[:] = [handler]`) when JSON is on. | `voice_common/logging_config.py`. | Intended (single JSON sink) and it runs first in `main()` before anything logs. Loggers with `propagate=False` + own handlers would bypass it — none in-repo today. |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| Voice: each line valid JSON with `timestamp/level/logger/message` | Yes | `test_emits_fixed_json_shape`; `test_json_format_installs_json_handler` parses the emitted line. |
| Voice: carries `correlation_id` when a turn is in scope, omits it otherwise | Yes | `test_stamps_correlation_id_from_context` + `test_emits_fixed_json_shape` (absent case). Bound on all four ingress paths: WS (`_serve_connection`), Genesys (`test_correlation_id_is_bound_in_context_during_the_call`), WebRTC (`test_session_task_runs_under_the_call_correlation_id`), batch REST (`test_run_blocking_propagates_correlation_context_into_executor`, `test_turn_binds_the_correlation_id_for_the_processor_call`). |
| Voice: secrets / paths / UUIDs redacted in `message`/`error` | Yes | `test_sanitizes_secret_and_path_tokens_in_message`, `test_includes_sanitized_exception`; `scrub_message` reuses the shared redactor + `key=value` value redaction. |
| Voice: var unset → plain text, handlers untouched | Yes | `test_default_is_text_and_leaves_handlers_untouched` (default path is a pure no-op). |
| Backend: `LOGGING_STRUCTURED_FORMAT_CONSOLE=ecs` → JSON with MDC `correlation_id`/`channel` | Yes (config) | Spring Boot 3.4.1 native structured logging; `CorrelationIdFilter`/`CorrelationId` already set `correlation_id` + `channel` MDC keys. |
| Backend: unset → current text layout; `mvn test` unchanged | Yes | Config-only; no call site changed. |
| Enabling is one env var per tier; independent of the SRE collector | Yes | `VOICE_LOG_FORMAT` / `LOGGING_STRUCTURED_FORMAT_CONSOLE` in compose + `*.env.j2` + `group_vars` (default empty = OFF). |

## Test Evidence

- Developer tests: `tests/test_logging_config.py` (6 new: JSON shape, correlation present/absent,
  secret+path scrub, exception scrub, install-on-json, default no-op) + 4 correlation-binding
  tests across Genesys / WebRTC / batch REST. Full voice suite `unittest` **698** green +
  `behave` **15/43/194** green. Existing `test_sanitization` (21) green after the
  `scrub_message` addition.
- Missing tests: backend JSON assertion (framework feature — not required; config-only).
- QA scenarios to run: pilot smoke with `VOICE_LOG_FORMAT=json` / `LOGGING_STRUCTURED_FORMAT_CONSOLE=ecs`
  on one node each; confirm `docker logs` emits JSON and carries `correlation_id` on a WS turn.

## Observability And Latency

- Relevant slices: cross-cutting (logging), not a latency slice; no mouth-to-ear impact.
- OpenTelemetry traces: unchanged (OTLP export path untouched; this is the log leg of the
  three-pillar rule, complementary to TASK-OBS-001 traces/metrics).
- Metrics: unchanged.
- Structured logs: **this is the deliverable** — one sanitized JSON object per line, stamped
  with `correlation_id` on all four voice ingress paths (WS, Genesys, WebRTC, batch REST) and
  via the backend MDC (`correlation_id` + `channel`).
- Missing: none blocking.
- Risk: low — additive, env-gated, default text.

## Security And Privacy

- Sensitive data risk: reduced. Every JSON `message`/`error` passes `scrub_message`
  (paths/filenames/UUIDs/secret-prefixed + `key=value` value + long opaque/numeric ids
  redacted; safe tokens + dates kept). Formatter emits only fixed keys — an accidental
  `logger.info(..., extra=...)` cannot leak unsanitized attributes.
- Identity/access risk: none — no auth path changed.
- Logging risk: length-capped at 2048 chars; backend already returns generic codes + correlation
  id (no upstream echo — ADR-0028 / GlobalExceptionHandler).

## Required Developer Actions

None.

## Residual Risk If Accepted

- None material. Correlation binding now covers all four voice ingress paths; the backend
  side is a framework-native config toggle. Enabling JSON on the pilot is a deploy decision
  (needs a rolling redeploy), left default-OFF as intended.
