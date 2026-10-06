# TASK-OPS-015 — Harden pilot log sanitization (JSON logs + follow-up polish)

**Type:** Technical task (operations / observability hardening)
**Status:** ✅ **V1(a) merged into `feat/restart-from-scratch`** (2026-10-06, `--no-ff`; branch deleted) — pilot voice tier pinned to `VOICE_LOG_FORMAT=json`. V1(b)/V2/V3 remain scoped follow-ups below (not started).
**Priority:** Medium
**Epic:** EPIC-012 (pilot operations)
**Surfaced by:** `docs/qa/2026-10-05-full-codebase-adversarial-review.md` (findings V1/V2/V3).

## Context

The voice runtime shares one log sanitization path (`voice_common/logging_config.py`):
the **JSON** formatter runs every `message` AND the formatted `exc_info` through
`scrub_message` before emitting. The **text** formatter (Python stdlib default) prints
tracebacks verbatim. The pilot ran with `voice_log_format: ""` (text), so the nine
`exc_info=True` sites on error/drain paths (`websocket_app.py:578`, `genesys_app.py:222`,
`control_signal_processor.py:93`, …) could log un-scrubbed exception text.

## Scope & decisions

- **V1(a) — DONE (this ticket):** pin the pilot voice tier to `VOICE_LOG_FORMAT=json`
  (`deploy/ansible/group_vars/voice.yml` `voice_log_format: "json"`). Zero code change;
  the leak path is closed because the JSON formatter scrubs message + exception. Renders
  `VOICE_LOG_FORMAT=json` via `voice.env.j2`.
- **V1(b) — follow-up (optional):** make the **text** formatter also scrub (so text mode
  is safe by default, not just json). Small code + unit test in `logging_config.py`.
- **V2 — follow-up:** inject the deterministic `traceparent` on the **warm-up** backend hop
  (`http_backend.py:142-156`) for trace parity (warm-up is best-effort → low impact).
- **V3 — follow-up:** use `sanitize_error(...)` instead of the raw exception **type name**
  in `streaming_answer.py` for consistency with the shared sanitizer.

## Verified NOT to change (audit false positives — kept for the record)

- **V4** `_stop_filler` `except Exception` (not `CancelledError`): **by design** — the
  filler must never break the turn, and `_cancel_filler` deliberately avoids awaiting so an
  outer barge-in cancellation is **not masked**. Catching `CancelledError` would mask barge-in.
- **V5** `hmac.compare_digest` unequal-length → 500: **already hardened** —
  `genesys_auth.py:151` compares **bytes** (encodes first, inline "never a 500 (Minor 2)");
  bytes-vs-bytes `compare_digest` returns `False` on unequal length, never raises.

## Acceptance

- [x] Pilot voice `.env` renders `VOICE_LOG_FORMAT=json`; YAML valid.
- [ ] (V1b) text-mode logs also scrubbed + unit test — *follow-up*.
- [ ] (V2) warm-up hop carries `traceparent` — *follow-up*.
- [ ] (V3) `streaming_answer` uses `sanitize_error` — *follow-up*.

## Observability / runtime impact

Config-only (deploy variable). No code path changes; the voice runtime already supports
`VOICE_LOG_FORMAT=json`. The backend tier (`backend_log_format`) stays text for now
(separate decision; backend logs go through logback MDC, no raw `exc_info` leak in the
same shape).

## Notes

Deploy applies on the next voice-tier roll (`ansible-playbook deploy.yml -e image_tag=<tag>`);
no new image required for the config to take effect, but it rides the normal deploy.
