# Bug Ticket

## Header

- **Bug ID:** BUG-021
- **Title:** Post-deploy KB sync 401 on a freshly-recreated backend aborts the whole rollout
- **Status:** 🟢 Fixed — readiness gate landed to `feat/restart-from-scratch` (2026-09-23); QA = next cold-container deploy (no live re-deploy since landing yet). Deploy-automation change (no unit harness); lightweight review done at landing. Branch merged (fix landed) then deleted.
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

- [x] Add a readiness pre-check before the async sync: poll a cheap gated endpoint
      (`POST /api/conversation/warm-up`) with the api-key until `200` (bounded retries,
      401 = not-ready → retry) so the gate is proven effective before the long sync fires.
- [x] A deploy against a freshly recreated backend no longer 401s / aborts — validated in
      isolation (readiness gate returns 200 on t03); full cold-start reproduction is a QA
      retest deferred to the next real deploy (see QA Retest).
- [x] Decision on non-fatal-to-other-tiers: **keep the hard gate.** The `assert processed >= min`
      is a deliberate quality gate (never leave RAG markdown-only), and the readiness pre-check
      removes the cold-start race that made it abort spuriously. Decoupling the voice/second-backend
      rollout from the KB sync would require reordering the `deploy.yml` plays (out of scope for
      this hotfix); the shared-Postgres nuance is documented here instead.
- [x] Relevant deploy logs present (the async result surfaces HTTP status/body; readiness gate is `no_log` as it carries the key).
- [ ] Adversarial review ≥ 90%.
- [ ] QA retest: a clean end-to-end deploy from cold containers completes with the sync green.

## Developer Notes

- root cause: cold-start race — a just-recreated backend serves `/actuator/health`=200
  before the api-key gate consistently accepts the rendered key (and/or the prior container
  briefly still answers on the same port with an older/different key during `compose up -d`),
  so the immediately-fired async KB sync 401s. Confirmed the key itself is valid and the
  async+templated-header pattern is sound (reproduces 200 post-settle); the variable is timing.
- files changed: `deploy/ansible/roles/compose_tier/tasks/kb_sync.yml` — added a bounded
  readiness gate (`POST /api/conversation/warm-up` with the key, `until status==200`,
  `status_code: [200,401]`, `retries: 12`, `delay: 5`, tunables `kb_sync_gate_{timeout,retries,delay}`)
  before the async sync trigger. Warm-up is api-key-gated + side-effect-free and also primes
  embedding + LLM for the first turn.
- validation: `ansible-playbook deploy.yml --syntax-check` PASS; isolated run of the exact
  readiness-gate task against the live `vla-t03` → `warm_up_status=200 attempts=1`.
- OpenTelemetry added/updated: n/a (deploy automation; no runtime code changed).
- residual risk: the true cold-start reproduction (a fresh container recreate racing the gate)
  is not exercised by the isolated test; covered by the deferred QA retest on the next deploy.
  If a legitimate misconfiguration ever keeps the gate at 401, the readiness task now fails
  fast (retries exhausted) with a clear signal instead of the sync 401 mid-rollout.

## QA Retest

- **Retested by:** (deferred)
- **Retest date:**
- **Scenarios rerun:** on the next real deploy, run `deploy.yml -e image_tag=<next>` (with
  `kb_sync_after_deploy` default true) against freshly recreated backend containers and
  confirm the readiness gate absorbs any cold-start 401 and the KB sync completes green on the
  first rolling node (no `NO MORE HOSTS LEFT`).
- **Result:** pending
- **Retest evidence:** (isolated pre-validation already captured: readiness gate → 200 on `vla-t03`)

## Closure

- **Closed by:**
- **Closed date:**
- **Closure reason:**
