# Bug Ticket

## Header

- **Bug ID:** BUG-021
- **Title:** Post-deploy KB sync 401 on a freshly-recreated backend aborts the whole rollout
- **Status:** New
- **Severity:** Medium
- **Priority:** P2
- **Detected by:** User validation (v0.9.0 pilot release)
- **Detected date:** 2026-09-17
- **Related user story:** TASK-OPS-009 (post-deploy KB sync)
- **Related epic:** EPIC-OPS (pilot deployment)
- **Branch:** `fix/BUG-021-kb-sync-cold-start-401`
- **Owner:** Cross-functional (deploy / backend)

## Problem Statement

During the `v0.9.0` (image `0.9.0`) deploy, the post-deploy KB sync step
(`roles/compose_tier/tasks/kb_sync.yml`) received an HTTP `401`
("A valid x-api-key header is required for this endpoint.") on the first backend node
immediately after the container was recreated. With `serial: 1` + `max_fail_percentage: 0`
this failed the play (`NO MORE HOSTS LEFT`), so the second backend node and both voice
nodes were never rolled to `0.9.0` on that run.

## Environment

- **Environment:** pilot (eir-ai4cc-tst)
- **Channel:** backend-only (deploy automation)
- **Provider configuration:** LLM pinned `mistral-api`; api-key gate enforced (non-empty `CONVERSATION_API_KEY`)
- **Build or commit:** image tag `0.9.0` (git `v0.9.0` → `ad89479`); `ansible-core 2.21.3`
- **Correlation ID:** `b465efe0-6235-4a96-8770-e5af0f2a06d3`

## Reproduction Steps

1. Given the backend api-key gate is enforced (`CONVERSATION_API_KEY` non-empty in the rendered `.env`).
2. When `deploy.yml` recreates a backend node and, right after `/actuator/health` first returns 200, fires the async `POST /api/knowledge/sync` with the extracted `x-api-key`.
3. Then the sync POST returns `401` on the just-recreated (cold-start) node and the play aborts.

## Expected Result

The post-deploy KB sync succeeds on a freshly recreated node, or transiently retries
across the cold-start window, so the rollout completes on every tier.

## Actual Result

`kb_sync.yml` "Wait for the KB sync to finish" failed with HTTP `401`; the rollout
aborted after only the first backend node was upgraded.

## Evidence

- API response: `{"error_code":"ERR_401","message":"A valid x-api-key header is required for this endpoint.","correlation_id":"b465efe0-..."}`
- Diagnostics (post-settle, same node/key):
  - `.env` `CONVERSATION_API_KEY` length = 64; `POST /api/conversation/retrieve` with the key → `200`, without → `401` (key is valid).
  - Playbook key extraction reproduced against the real `.env`: `split_len=64 splitlines_len=64` (extraction is correct).
  - Exact async+`run_once`+`no_log`+templated-header pattern reproduced against `retrieve` → `A_async_status=200` (pattern is not broken).
  - Conclusion: cold-start race — the api-key gate was not yet fully effective at the instant the sync fired, even though `/actuator/health` was 200.

## Impact

- operational impact: a routine deploy aborts mid-rollout, leaving a mixed-version backend
  (one node new, one old) until re-run; requires a manual workaround.
- customer impact: none directly (existing shared pgvector index keeps serving RAG).
- security/privacy impact: none (no secret exposure; `.env` mode 0600, `no_log` preserved).

### Workaround used for v0.9.0 (already applied)

1. Re-ran `deploy.yml -e image_tag=0.9.0 -e kb_sync_after_deploy=false` → completed t04 + voice (all tiers `0.9.0`, healthy).
2. Triggered the KB sync out-of-band on the first backend node as a detached `systemd-run` unit (`kbsync-090.service`) with the real key.

## Acceptance Criteria For Fix

- [ ] Add a readiness pre-check before the async sync: poll a cheap gated endpoint
      (e.g. `POST /api/conversation/warm-up` or `/retrieve`) with the api-key until `200`
      (bounded retries) so the gate is proven effective before the long sync fires.
- [ ] A deploy against a freshly recreated backend no longer 401s / aborts.
- [ ] Consider making the KB-sync failure non-fatal to the *other* tiers (KB is shared
      Postgres, so voice/second-backend rollout need not depend on it) — or document why it stays a hard gate.
- [ ] Relevant deploy logs/telemetry present.
- [ ] Adversarial review ≥ 90%.
- [ ] QA retest: a clean end-to-end deploy from cold containers completes with the sync green.

## Developer Notes

- root cause (hypothesis): cold-start race — `/actuator/health` UP precedes the api-key
  security filter being fully effective for `/api/knowledge/**` on the just-recreated node.
- files to change: `deploy/ansible/roles/compose_tier/tasks/kb_sync.yml` (add gated readiness poll before the async trigger).
- tests added/updated: —
- OpenTelemetry added/updated: —
- residual risk: —

## QA Retest

- **Retested by:**
- **Retest date:**
- **Scenarios rerun:**
- **Result:**
- **Retest evidence:**

## Closure

- **Closed by:**
- **Closed date:**
- **Closure reason:**
