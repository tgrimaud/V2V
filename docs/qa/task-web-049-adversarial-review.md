# Adversarial Code Review — TASK-WEB-049 (server-side `turn_error` terminal signal)

Reviewed: 2026-09-29 (in-session) · Branch: `task/TASK-WEB-049-turn-error-terminal-signal` · Base: `feat/restart-from-scratch`

## Verdict

**Proceed.** On a WS turn/session crash the runtime force-emits a `turn_error` control frame on
the raw aiohttp socket so the UI leaves "Thinking" immediately instead of waiting for the client
watchdog. Targeted, best-effort/fail-safe, WS-scoped. Closes the deferred third leg of BUG-018
(server terminal signal). The client already honours `turn_error` (shipped by TASK-WEB-046). No
blocking findings.

## Satisfaction Score

Score: **94/100**
QA gate: **Pass**

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | Ordering: after `turn_error`, if `_safe_stop` still emits an `EndFrame` → `call_end`, the client message goes from "please try again" to "Call ended". Both are terminal (the UI is never stuck), but the wording can flip. | `_serve_connection` `except` branch → `_send_turn_error` then `_safe_stop`. | Documented as an accepted minor delta (ticket + `docs/architecture/voice-runtime-http-contract.md`). |
| Low | WS-scoped only. WebRTC (dev/lab, ADR-0042) and the Genesys AudioHook error protocol are not re-signalled here. | `TURN_ERROR` is emitted only from the aiohttp `/ws` handler. | A cross-transport `ControlSignalType` unification stays a follow-up, tracked in TASK-WEB-046's deferred block. |
| Info | The `except` branch fires only on a pipeline/session-level crash. Normal backend errors degrade to a spoken fallback in `StreamedAnswerRunner` (DEC-002), so this is a targeted defensive signal — not dead code and not double-signalling (one event per failed turn). | `_serve_connection` wraps `session.run()`; the runner owns graceful degradation. | — |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| On a WS turn/session crash the server emits a terminal signal so the UI leaves "Thinking" | ✅ | `test_failed_session_run_emits_turn_error_terminal_signal` (real aiohttp socket → TEXT frame contains `"turn_error"`, event recorded, session stopped) |
| A normal turn emits **no** spurious `turn_error` | ✅ | `test_normal_turn_does_not_emit_turn_error` |
| Client leaves "Thinking" on receipt (no fabricated answer, DEC-002) | ✅ | `ws.js` already handles `turn_error` (shipped by TASK-WEB-046) → leaves "Thinking", invites retry |
| Best-effort / fail-safe (a send failure never masks the original crash) | ✅ | `_send_turn_error` guards `websocket.closed` and swallows send errors (debug log only) |

## Test Evidence

- Developer tests: 2 new (`test_failed_session_run_emits_turn_error_terminal_signal`, `test_normal_turn_does_not_emit_turn_error`) with `_FailingSession`/`_FailingFactory` fixtures driving `session.run()` to raise.
- Full suite: voice-agent unittest **685** OK; behave **15 features / 43 scenarios / 194 steps** OK; OpenAPI anti-drift guard OK; `git diff --check` clean.
- QA scenarios to run: force a WS turn crash → assert the browser leaves "Thinking" immediately (not after the ~20 s watchdog).

## Observability And Latency

- New OTel event `voice.ws.turn_error_signal` (outcome=`error`), correlation-id carried.
- On the critical path only on the failure branch; adds no latency to the normal turn.
- Structured log on send failure (debug, sanitized — no payload).

## Security And Privacy

- Sensitive data risk: none — the frame is a constant `{"type":"turn_error"}`, no payload.
- The signal is emitted on the already-authenticated WS session; no new surface.
- Logging risk: none (debug-only, no PII).

## Required Developer Actions

1. None blocking. (Follow-up already tracked: unify a cross-transport terminal signal for WebRTC/Genesys under TASK-WEB-046's deferred block.)

## Residual Risk If Accepted

- Wording flip (`turn_error` then possible `call_end`) — both terminal, never stuck.
- WebRTC (dev/lab) and Genesys AudioHook are not covered by this signal.
