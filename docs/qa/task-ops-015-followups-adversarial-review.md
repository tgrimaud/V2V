# TASK-OPS-015 (V1b/V2/V3 follow-ups) — Adversarial code review

**Date:** 2026-10-06
**Branch:** `task/TASK-OPS-015-followups-v1b-v2-v3` (off `feat/restart-from-scratch`)
**Reviewer skill:** `.cursor/skills/adversarial-code-review/SKILL.md`
**Scope:** voice runtime log/trace hardening — 6 source + 4 test files. V1b (text-mode log
scrubbing), V2 (warm-up `traceparent` parity), V3 (streaming fault sanitization). No backend
(Java) change.

## Verdict

**Proceed.** All three follow-ups improve sanitization / trace continuity, are covered by
new unit tests, and preserve behavior except where a change is the explicit intent (V1b now
sanitizes the text default). Voice-agent suite 730 OK + behave 15/43/194. No blocking finding.

## Satisfaction Score

Score: 95/100
QA gate: Pass

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | **V1b changes the text default from "leave handlers untouched" to "install a root handler + set level INFO".** This is the point of V1b (text mode must scrub), but it now replaces any pre-existing root handler and pins the level in text mode too. | `configure_logging` always builds a `StreamHandler` + `root.handlers[:] = [handler]`; previously the non-JSON path returned early. | Accept — symmetric with the JSON path (which already replaced handlers), called once at startup (`web_voice/server.py:425`); tests save/restore root handlers. Documented in the module docstring + ticket. |
| Info | **Formatter mutates `record.message` (and caches `record.exc_text`) during `format`.** | `SanitizingTextFormatter.formatMessage` sets `record.message = scrub_message(...)`; base `Formatter.format` caches `exc_text`. | Safe in the single-root-handler runtime: base `format` recomputes `record.message = record.getMessage()` on every call, so no cross-handler leak; a cached scrubbed `exc_text` is strictly safer, not a leak. No action. |
| Info | **V2 warm-up trace parity is advisory / best-effort.** The hop joins the trace only when the connection envelope already carries a `correlation_id`; `None` → no trace headers (unchanged pre-V2 behavior). | `_warm_backend` reads `getattr(self._envelope, "correlation_id", None)`; `warm_up(None)` adds nothing. | Intended (warm-up is off the critical path). The warm-up telemetry already tags this same id, so the hop and its event now correlate. No action. |

## Story Coverage

| Acceptance criterion (TASK-OPS-015 follow-ups) | Covered? | Evidence |
|---|---|---|
| (V1b) text-mode logs scrubbed + unit test | Yes | `SanitizingTextFormatter` scrubs message (`formatMessage`) + exception/stack **line by line** (`formatException`/`formatStack`, tracebacks stay multi-line); `test_logging_config.py`: `test_text_mode_scrubs_secret_and_path`, `test_multiline_exception_stays_multiline_and_scrubbed`, `test_default_text_installs_sanitizing_handler` |
| (V2) warm-up hop carries `traceparent` | Yes | `HttpBackendAdapter.warm_up(correlation_id)` → shared `_inject_trace` adds `X-Correlation-Id` + `derive_traceparent`; `test_http_backend.py`: `test_warm_up_carries_correlation_id_and_traceparent_when_provided` / `..._without_correlation_id_sends_no_traceparent`; `test_answer_processor.py` asserts the processor passes `corr-1` |
| (V3) `streaming_answer` uses `sanitize_error` | Yes | raising-adapter branch → `sanitize_error(exc, domain="backend")` (code + redacted reason), prior ERROR/DONE code still wins; `test_streaming_answer.py`: `test_raising_adapter_degrades_safely` (code `backend_error`) + `test_raising_adapter_redacts_secret_in_reason` |
| No behavior change beyond the intended hardening | Yes (reasoned) | `_headers` refactor is pure extraction (same headers); warm-up signature backward-compatible (default `None`); removed `"stream_error"` literal has no consumer (only an unrelated behave step name matches) |

## Test Evidence

- Developer tests: +7 unit tests across `test_logging_config.py` (4), `test_http_backend.py` (2),
  `test_answer_processor.py` (1 assertion added), `test_streaming_answer.py` (2). Full voice-agent
  suite **730 OK**; behave **15 features / 43 scenarios / 194 steps** green.
- Missing tests: none material. The `_headers`/`_inject_trace` extraction is covered transitively by
  the existing turn-hop header tests (correlation id + traceparent already asserted there) plus the new
  warm-up ones.
- QA scenarios to run: a pilot/dev run confirming (a) text-mode startup logs still readable + scrubbed,
  (b) the warm-up span shares the turn trace id in the collector when a correlation id is present.

## Observability And Latency

- Relevant slices: logging (both tiers' shape), warm-up hop (`backend` trace continuity), streaming
  backend fault path.
- OpenTelemetry traces: V2 makes the warm-up hop carry the deterministic `traceparent` (same scheme as
  the turn hop), so it stitches into the turn trace instead of starting an orphan trace.
- Metrics: unchanged (`voice.backend.warmup` event/metric still tag the same correlation id).
- Structured logs: **improved** — text mode now redacts secrets/paths/ids like JSON mode; correlation id
  is now also stamped on text lines (`[%(correlation_id)s]`).
- Missing: none for this scope.
- Risk: none — all three strictly add redaction / trace continuity.

## Security And Privacy

- Sensitive data risk: **reduced**. V1b closes the text-mode leak (raw tracebacks on `exc_info=True`
  paths); V3 redacts a raising adapter's fault message instead of surfacing the raw string/type.
- Identity/access risk: none. The API key is still header-only; `_inject_trace` adds only the correlation
  id (not a secret) + a derived traceparent.
- Logging risk: none introduced. Note the known `sanitize_error._redact` limitation (it does not split
  `key=value` tokens — only the log-path `scrub_message` does); unchanged by this ticket and acceptable
  (bare secret-prefixed tokens, paths, UUIDs, long ids are still redacted).

## Required Developer Actions

1. None (no blocking finding). Optional: a short pilot smoke to eyeball text-mode startup logs and the
   warm-up trace join in the collector before merge.

## Residual Risk If Accepted

- V1b installs a root handler on the text path (vs the prior no-op). De-risked: symmetric with the JSON
  path, single startup call, tests save/restore handlers. No behavioral, latency, identity or privacy
  risk; the net effect is more sanitization and better trace continuity.
