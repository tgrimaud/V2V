# TASK-OPS-016 — Adversarial code review (sanitize_error key=value redaction)

**Date:** 2026-10-06
**Branch:** `task/TASK-OPS-016-sanitize-error-key-value` (off `feat/restart-from-scratch`)
**Reviewer skill:** `.cursor/skills/adversarial-code-review/SKILL.md`
**Scope:** `voice-agent/voice_common/sanitization.py` (shared redaction) + `tests/test_sanitization.py`.
Privacy hardening — unifies `key=value` redaction across the log path and the error-reason path.

## Verdict

**Proceed.** Small, behavior-preserving-plus-hardening change: the `key=value` value-side redaction
now lives in the shared `_redact_token`, so `sanitize_error` redacts `key=secret` like the log
scrubber already did. No reason-code / cap / safe-token change. Voice-agent 732 OK + behave 15/43/194.

## Satisfaction Score

Score: 96/100
QA gate: Pass

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Info | Nested `a=b=c` only redacts after the first `=` (value `b=c` kept unless itself id-shaped). | `partition("=")` splits on the first `=`; `_redact_core("b=c")` is not id-shaped. | Accept — identical to the prior `_scrub_log_token` behavior (no regression); real fault messages don't use nested `=`. |
| Info | The log path (`scrub_message`) now routes through `_redact_token` instead of the removed `_scrub_log_token`. | both were byte-identical logic (`key=value` split → `_redact_core`); `_scrub_log_token` had no other refs. | No action — strictly a de-duplication; log-path behavior unchanged (covered by `test_logging_config.py`). |

## Story Coverage

| Acceptance criterion (TASK-OPS-016) | Covered? | Evidence |
|---|---|---|
| `sanitize_error` redacts `key=secret` value | Yes | `test_key_value_secret_is_redacted_on_error_reason_path` (`key=<redacted-id>`, secret absent) |
| `scrub_message` unchanged | Yes | `test_logging_config.py::test_text_mode_scrubs_secret_and_path` (log path still redacts `key=…`) |
| Safe token as `key=value` value preserved | Yes | `test_key_value_with_safe_token_value_is_preserved` (`format=pcm_16000` kept) |
| New unit tests on the error-reason path | Yes | 2 added to `test_sanitization.py` |
| Suite + behave green | Yes | 732 OK; behave 15/43/194 |

## Test Evidence

- Developer tests: +2 unit tests (`test_sanitization.py`); full voice-agent suite **732 OK**; behave green.
  All prior redaction tests (paths, filenames, UUID, secret-prefix, digit-run, alnum id, safe tokens,
  dates, length cap) still pass, confirming the `_redact_token`→`_redact_core` extraction preserved them.
- Missing tests: none material.
- QA scenarios to run: none new — redaction-only hardening.

## Observability And Latency

- Relevant slices: none (pure sanitization helper). Error-reason strings become safer; `error_code`
  contract unchanged, so metrics/traces keyed on codes are unaffected.
- Missing: none. Not latency-affecting (same per-token pass).
- Risk: none.

## Security And Privacy

- Sensitive data risk: **reduced** — closes the `key=secret` leak on the error-reason path (used by
  STT/TTS/backend adapters + the streaming runner since TASK-OPS-015 V3).
- Identity/access risk: none.
- Logging risk: none introduced; the log path is unchanged (same helper, de-duplicated).

## Required Developer Actions

1. None (no blocking finding).

## Residual Risk If Accepted

- Nested `key=a=b` redacts only after the first `=` (unchanged from prior behavior); not a regression.
  No runtime, latency or architecture exposure.
