# Adversarial Code Review — TASK-OBS-002 (Structured JSON logs, both tiers)

**Branch:** `task/TASK-OBS-002-structured-json-logs` (off `feat/restart-from-scratch`)
**Scope reviewed:** voice-runtime JSON log formatter + per-turn `correlation_id` contextvar +
`scrub_message` sanitization (`VOICE_LOG_FORMAT=json`); backend Spring Boot 3.4 native
structured logging enablement (`LOGGING_STRUCTURED_FORMAT_CONSOLE`, config-only); deploy
passthrough (compose + Ansible `*.env.j2` + `group_vars`, default OFF).
**Reviewer skill:** `.cursor/skills/adversarial-code-review`
**Date:** 2026-09-30

## Verdict

Proceed.

## Satisfaction Score

Score: 93/100
QA gate: Pass

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Medium | `correlation_id` is bound only on the **WS** path (`_serve_connection`). Batch REST (`/api/voice/turn`) runs backend I/O in a thread executor where `ContextVar` does not propagate, and the **WebRTC/Genesys** streaming entrypoints (`webrtc_signaling.py`) have no bind, so their JSON lines omit `correlation_id`. | `web_voice/websocket_app.py:539/567`; no bind in `webrtc_signaling.py`. | Documented as an explicit follow-up in the ticket. JSON structure + sanitization still apply to every line regardless of path; correlation binding on those paths is additive and can land next without changing the shape. Acceptable residual. |
| Low | No backend-side automated assertion that a line is JSON with the MDC keys. | Backend change is config-only; no Java touched. | Native Spring Boot structured logging is a framework feature (asserting it tests the framework). `mvn test` is unaffected. A one-line manual smoke on the pilot when enabled is enough. |
| Low | `configure_logging` replaces **all** root handlers (`root.handlers[:] = [handler]`) when JSON is on. | `voice_common/logging_config.py`. | Intended (single JSON sink) and it runs first in `main()` before anything logs. Loggers with `propagate=False` + own handlers would bypass it — none in-repo today. |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| Voice: each line valid JSON with `timestamp/level/logger/message` | Yes | `test_emits_fixed_json_shape`; `test_json_format_installs_json_handler` parses the emitted line. |
| Voice: carries `correlation_id` when a turn is in scope, omits it otherwise | Yes | `test_stamps_correlation_id_from_context` + `test_emits_fixed_json_shape` (absent case). WS binds it before `session.run()`. |
| Voice: secrets / paths / UUIDs redacted in `message`/`error` | Yes | `test_sanitizes_secret_and_path_tokens_in_message`, `test_includes_sanitized_exception`; `scrub_message` reuses the shared redactor + `key=value` value redaction. |
| Voice: var unset → plain text, handlers untouched | Yes | `test_default_is_text_and_leaves_handlers_untouched` (default path is a pure no-op). |
| Backend: `LOGGING_STRUCTURED_FORMAT_CONSOLE=ecs` → JSON with MDC `correlation_id`/`channel` | Yes (config) | Spring Boot 3.4.1 native structured logging; `CorrelationIdFilter`/`CorrelationId` already set `correlation_id` + `channel` MDC keys. |
| Backend: unset → current text layout; `mvn test` unchanged | Yes | Config-only; no call site changed. |
| Enabling is one env var per tier; independent of the SRE collector | Yes | `VOICE_LOG_FORMAT` / `LOGGING_STRUCTURED_FORMAT_CONSOLE` in compose + `*.env.j2` + `group_vars` (default empty = OFF). |

## Test Evidence

- Developer tests: `tests/test_logging_config.py` (6 new: JSON shape, correlation present/absent,
  secret+path scrub, exception scrub, install-on-json, default no-op). Full voice suite
  `unittest` **694** green + `behave` **15/43/194** green. Existing `test_sanitization` (21) green
  after the `scrub_message` addition.
- Missing tests: backend JSON assertion (framework feature — not required; config-only).
- QA scenarios to run: pilot smoke with `VOICE_LOG_FORMAT=json` / `LOGGING_STRUCTURED_FORMAT_CONSOLE=ecs`
  on one node each; confirm `docker logs` emits JSON and carries `correlation_id` on a WS turn.

## Observability And Latency

- Relevant slices: cross-cutting (logging), not a latency slice; no mouth-to-ear impact.
- OpenTelemetry traces: unchanged (OTLP export path untouched; this is the log leg of the
  three-pillar rule, complementary to TASK-OBS-001 traces/metrics).
- Metrics: unchanged.
- Structured logs: **this is the deliverable** — one sanitized JSON object per line, stamped
  with `correlation_id` (voice WS + backend MDC) and `channel` (backend).
- Missing: correlation binding on batch REST + WebRTC/Genesys (follow-up, non-blocking).
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

None blocking. Optional: land the batch-REST / WebRTC correlation bind as the tracked follow-up.

## Residual Risk If Accepted

- Batch-REST and WebRTC/Genesys JSON lines omit `correlation_id` until the follow-up bind lands
  (structure + sanitization already apply). Accepted for this ticket.
