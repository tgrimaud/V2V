# TASK-OPS-016 — Redact `key=value` tokens in `sanitize_error` (match the log scrubber)

**Type:** Technical task (privacy / sanitization hardening — voice runtime)
**Status:** ✅ **Merged into `feat/restart-from-scratch`** (2026-10-06, `--no-ff`; branch deleted) — `key=value` redaction factored into `_redact_token` (shared by both entry points); voice-agent suite 732 OK + behave 15/43/194.
**Adversarial review 96/100 (Pass, 2026-10-06)** — no blocking finding; privacy hardening, de-duplicates the `key=value` split, prior redaction tests all still green. Residual (accepted, Info): nested `a=b=c` redacts only after the first `=` (unchanged from prior behavior). Full review: `docs/qa/task-ops-016-adversarial-review.md`.
**Priority:** Low
**Epic:** EPIC-012 (pilot operations / observability hardening)
**Surfaced by:** `docs/qa/task-ops-015-followups-adversarial-review.md` (Security & Privacy note) and
the BUG-029 independent review context.

## Context

The voice runtime has two redaction entry points in `voice-agent/voice_common/sanitization.py`:

- `scrub_message(...)` (log path) splits a token on `=` and redacts the **value** side of a
  `key=value` pair via `_scrub_log_token` (keeps the key readable).
- `sanitize_error(...)` (error-reason path, used by STT/TTS/backend adapters + the streaming
  runner since TASK-OPS-015 V3) uses `_redact`, which splits on **whitespace only**. A token
  like `key=sk-abc123def456` is therefore **not** redacted by `sanitize_error`, because the
  whole token doesn't match a path/filename/identifier pattern (the `=` breaks `_ALNUM_ID` and
  the `sk-` prefix is behind `key=`).

Bare secret-prefixed tokens, paths, filenames, UUIDs and long numeric/opaque ids ARE already
redacted by `sanitize_error`; only the `key=value` form slips through on the error-reason path.
This is a known, documented limitation (TASK-OPS-015 review), low-likelihood (upstream fault
messages rarely embed `key=secret`), hence Low priority — but it is an inconsistency worth closing.

## Scope & decision

- Make `_redact` (the `sanitize_error` tokenizer) reuse the same `key=value` value-side redaction
  that `_scrub_log_token` already applies, so both entry points treat `key=secret` identically.
  Preferred shape: factor the `key=value` split into a shared helper used by both
  `_scrub_log_token` and `_redact_token`'s caller, keeping `_SAFE_TOKENS` and the existing
  per-token heuristics unchanged.
- Keep the `_MAX_REASON_LEN` (160) cap on `sanitize_error` and the `_MAX_LOG_LEN` (2048) cap on
  `scrub_message` as-is (different budgets by design).
- No change to reason codes (`<domain>_timeout` / `<domain>_error` / `type_codes`).

## Acceptance

- [x] `sanitize_error(RuntimeError("upstream rejected key=sk-topsecret9999")).reason` redacts the
      value (`key=<redacted-id>`), not just bare `sk-...` tokens. (`test_sanitization.py::test_key_value_secret_is_redacted_on_error_reason_path`)
- [x] `scrub_message` behaviour unchanged (regression test still green — `test_logging_config.py::test_text_mode_scrubs_secret_and_path` exercises `key=…` on the log path).
- [x] Technical tokens in `_SAFE_TOKENS` (e.g. `pcm_16000`, `audio/pcm`) stay readable, including
      when they appear as a `key=value` value. (`test_key_value_with_safe_token_value_is_preserved`)
- [x] New unit tests in `tests/` cover the `key=value` redaction on the `sanitize_error` path.
- [x] Voice-agent suite + behave green (732 OK; 15/43/194).

## Implementation notes

- Moved the `key=value` value-side redaction from the log-only `_scrub_log_token` **into** `_redact_token`,
  and extracted the per-token heuristics into `_redact_core`. Both `scrub_message` (log path) and `_redact`
  (`sanitize_error` path) now call `_redact_token`, so they treat `key=secret` identically. `_scrub_log_token`
  removed (no external refs). `_SAFE_TOKENS` / `_MAX_*` caps / reason codes unchanged.

## Observability / runtime impact

Pure sanitization hardening (reduces potential leakage in error reasons). No new telemetry; the
`error_code` contract is unchanged. Not latency-affecting.

## Notes

Discovered while reviewing TASK-OPS-015 V3 (which routed the streaming raising-adapter fault
through `sanitize_error`). The gap predates V3; V3 only made the error-reason path more visible.
