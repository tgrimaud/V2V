# Adversarial Code Review — TASK-OPS-010 (bridge `POST /drain` + deploy wiring)

Reviewed: 2026-09-29 (in-session) · Branch: `task/TASK-OPS-010-bridge-drain-endpoint` · Base: `feat/restart-from-scratch`

## Verdict

**Proceed.** Adds a token-gated `POST /drain` to the voice bridge that stops accepting new
sessions and waits (bounded) for in-flight calls to wind down, wired into the Ansible deploy so a
container recreate no longer cuts a live call. Third and last leg of BUG-018 (with TASK-WEB-045 +
TASK-WEB-046). One blocking finding was raised and **fixed during the review** (see below).

## Satisfaction Score

Score: **93/100**
QA gate: **Pass** (after the review-time fix)

## Blocking Findings

| Severity | Finding | Evidence | Required fix | Status |
|---|---|---|---|---|
| Medium | Drain token compared with a plain `==`, and `handle_drain` exceeded the 20-line method budget. A non-constant-time compare is a (minor) timing-oracle on the drain token. | `web_voice/drain.py` / endpoint handler before the fix. | Constant-time compare + method extraction. | **Fixed in-branch** — switched to `hmac.compare_digest`; extracted `_drain_and_report` / `_drain_body` / `_drain_token_matches` helpers to keep `handle_drain` ≤ 20 lines. |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | WebRTC sessions are not counted by the drain (only WS + Genesys handlers register with the controller). | WebRTC is a dev/lab transport (ADR-0042); not on the pilot live path. | Accepted — captured in the ticket's Out Of Scope. Revisit only if WebRTC becomes a served transport. |
| Low | On a drain **timeout** (in-flight calls exceed the wait window), the residual socket teardown falls back to the container recreate + the browser watchdog (TASK-WEB-046), not an active socket-close. | Bounded wait then returns `remaining`; recreate proceeds. | Accepted — documented in Out Of Scope; the deploy still degrades gracefully (a stuck UI is caught by the WEB-046 watchdog). |
| Info | When `VOICE_DRAIN_TOKEN` is unset the endpoint is disabled and the deploy degrades cleanly to LB-drain + a grace window. | `drain.yml` grace fallback. | Set `vault_voice_drain_token` in the vault to enable the exact drain. |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| `POST /drain` stops accepting new sessions and waits (bounded) for in-flight calls | ✅ | `DrainController` (draining flag, session-count providers, bounded wait, token+timeout config); unit tests for idle/one-in-flight/timeout |
| Token-gated (reject without/with wrong token) | ✅ | Constant-time `hmac.compare_digest`; 403/503 paths tested |
| Wired into the deploy so recreate drains first | ✅ | Ansible `roles/compose_tier` drain task (`Drain in-flight calls on the bridge …`) + `Report the bridge drain outcome` + grace fallback (`Grace window for in-flight calls to wind down (fallback)`) |
| Disabled/degrade-safe when no token configured | ✅ | Grace-window fallback path; endpoint not mounted / 503 when disabled |
| Full voice-agent suite green | ✅ | **703** tests OK; behave **15 / 43 / 194** OK; OpenAPI anti-drift guard OK; `git diff --check` clean; Ansible YAML/Jinja validated |

## Test Evidence

- Developer tests: `DrainController` unit tests (idle drain, one in-flight → wait then drained, timeout → `remaining ≥ 1`), endpoint token-gate (403/503/200), WS/Genesys handler registration; `test_not_mounted_without_controller`.
- Full suite: voice-agent **703** OK; behave **15 / 43 / 194** OK.
- Pilot QA: runbook `docs/qa/task-ops-010-bridge-drain-qa.md` (S0–S6). Baseline S0/S1/S5 run 2026-09-29 — the deployed image `0.9.3` **predates** OPS-010, so `POST /drain` is not mounted (405, matching `test_not_mounted_without_controller`). S2–S6 are **blocked until** an OPS-010 image is built + `vault_voice_drain_token` set + the tier redeployed.

## Observability And Latency

- Drain outcome reported by the Ansible task (`remaining` count) and logged.
- Bounded wait window is configurable (env), so the deploy step has a hard upper bound.
- Off the real-time audio path (deploy-time only).

## Security And Privacy

- Token gate uses constant-time compare (`hmac.compare_digest`); token sourced from the vault, never hand-written into `.env`.
- No PII; the endpoint only reports a session count.
- Endpoint disabled when no token is configured (fail-closed on control, fail-safe on deploy via the grace fallback).

## Required Developer Actions

1. None blocking (the timing-oracle + method-length findings were fixed in-branch).
2. Ops, before pilot QA S2–S6: build an OPS-010 image, set `vault_voice_drain_token`, redeploy the voice tier.

## Residual Risk If Accepted

- WebRTC (dev/lab) sessions are not drained.
- On a drain timeout, residual sockets are torn down by the recreate + browser watchdog, not an active close.
- Full pilot QA (S2–S6) is pending a build + token + redeploy.
