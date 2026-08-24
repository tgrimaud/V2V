# BUG-013 — `VOICE_BACKEND_URL` should be the server base; the bridge must build the converse path

## Header

- **Bug ID:** BUG-013
- **Title:** The voice bridge uses `VOICE_BACKEND_URL` verbatim as the converse endpoint, so a natural "server base" value (e.g. the backend VIP) silently degrades every turn to `backend_unavailable`
- **Status:** Ready for adversarial review
- **Severity:** High
- **Priority:** P1
- **Detected by:** User validation (pilot voice-journey validation)
- **Detected date:** 2026-08-14
- **Related user story:** TASK-WEB-003-C (HTTP conversation backend adapter)
- **Related epic:** EPIC-012 (V1 pilot deployment)
- **Branch:** fixed inline on `feat/sprint-11-remote-deployment` (found during pilot validation)
- **Owner:** Voice runtime developer

## Problem Statement

`VOICE_BACKEND_URL` was consumed verbatim by `HttpBackendAdapter` as the full converse
endpoint. The pilot config set it to the backend server/VIP (`http://192.168.0.11:8080`,
a base host), so the bridge POSTed to the server root instead of
`/api/conversation/converse`. Every voice turn came back **`degraded / backend_unavailable`**
even though STT, TTS and the backend RAG pipeline were healthy.

## Environment

- **Environment:** pilot (eir-ai4cc-tst); bridges `vla-ai4cc-t01/t02`; backend VIP `.11`
- **Channel:** web voice (`/api/voice/turn`) and WebRTC turn path
- **Build or commit:** voice image `0.5.x`; `conversation_backend/backend_factory.py` / `http_backend.py`
- **Correlation ID:** captured during validation (bridge `X-Answer-Outcome: degraded`)

## Reproduction Steps

1. Given `VOICE_BACKEND_URL=http://<backend host or VIP>` (a server base, no REST path).
2. When a voice turn runs (`POST /api/voice/turn`) with valid STT + backend.
3. Then the bridge POSTs to the server root, the backend returns a non-2xx/HTML body,
   and the adapter maps it to `X-Answer-Outcome: degraded`, `X-Answer-Degraded-Reason:
   backend_unavailable` — no grounded answer is ever produced.

## Expected Result

Operators configure only the backend **server base** URL; the bridge builds the
conversation path (`/api/conversation/converse`) and its `converse-stream` / `warm-up`
siblings. A voice turn against a healthy backend returns `X-Answer-Outcome: success`
with a grounded answer.

## Actual Result

With a base URL the turn always degraded; the journey only worked when the operator
manually set the **full** converse URL — a brittle, undocumented coupling of the ops
config to the backend's internal REST layout.

## Evidence

- Bridge `/api/voice/turn` reply headers: `X-Answer-Provider: http-backend`,
  `X-Answer-Outcome: degraded`, `X-Answer-Degraded-Reason: backend_unavailable`.
- Direct `POST http://192.168.0.11/api/conversation/converse` (full path) → HTTP 200
  with a grounded `{text, confidence}` answer, proving the backend itself was healthy.

## Impact

- **Customer / pilot-readiness:** the whole voice journey silently degrades — the bot
  speaks a safe fallback instead of the real billing explanation.
- **Operational:** the failure hid behind the safe-degrade path, so it looked like a
  backend/LLM outage rather than a URL-shape mismatch; costly to diagnose.
- No security/privacy impact (the API key was never in the URL).

## Acceptance Criteria For Fix

- [x] `VOICE_BACKEND_URL` is treated as the server base; the bridge appends
      `/api/conversation/converse` (`backend_factory._converse_endpoint`).
- [x] Idempotent/back-compat: a legacy full converse URL is kept as-is, never doubled.
- [x] Unit tests cover base-URL append, trailing-slash trim and the idempotent full URL.
- [x] OpenTelemetry: not applicable (no telemetry contract change; outcome now `success`).
- [ ] Adversarial code review ≥ 90%.
- [ ] QA retest passes (live voice turn returns `success` after image rebuild + redeploy).
- [x] Documentation/backlog updated (this ticket; CLAUDE.md/AGENTS.md, READMEs,
      development-guide, deployment-eir-ai4cc-tst, `group_vars/voice.yml`).

## Developer Notes

- **root cause:** the env value was used verbatim as the endpoint, coupling the ops
  contract to the backend's REST path.
- **files changed:** `voice-agent/conversation_backend/backend_factory.py`
  (`CONVERSE_PATH` + `_converse_endpoint`, idempotent); `deploy/ansible/group_vars/voice.yml`
  (`voice_backend_url: http://192.168.0.11`); docs.
- **tests added/updated:** `voice-agent/tests/test_backend_factory.py`
  (base-URL append, trailing slash, idempotent full URL).
- **residual risk:** low. Requires a voice image rebuild + redeploy to activate the
  base-URL semantics on the pilot; the idempotent guard means the full URL currently
  live on `0.5.1` bridges keeps working with the new code, so there is no flip-day gap.

## QA Retest

- **Retested by:** (pending — needs image rebuild + voice tier redeploy)
- **Retest date:** —
- **Scenarios rerun:** `python -m unittest tests.test_backend_factory tests.test_http_backend` green; live `/api/voice/turn` returns `success` after redeploy.
- **Result:** Local passed (30 tests); live retest pending redeploy.
- **Retest evidence:** —

## Closure

- **Closed by:** —
- **Closed date:** —
- **Closure reason:** —
