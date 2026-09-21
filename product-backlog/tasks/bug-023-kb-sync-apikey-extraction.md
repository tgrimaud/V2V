# BUG-023 — KB post-deploy sync extracts an empty api-key → 401 (auto-sync blocked)

**Type:** Bug · **Severity:** High (blocks post-deploy KB auto-sync / deploy gate) · **Status:** 🟢 Fixed (2026-09-21, pending merge)
**Found:** 2026-09-21 while deploying backend `0.9.2` (BUG-022 fix) + triggering the pilot re-sync
**Area:** deploy tooling (Ansible `compose_tier/kb_sync.yml`) · **Related:** TASK-OPS-009, ADR-0048, BUG-022

## Symptom

During the backend rollout the stack comes up healthy, then the post-deploy KB sync fails
immediately:

```
TASK [compose_tier : Trigger the KB sync (POST /api/knowledge/sync, async)] — changed
TASK [compose_tier : Wait for the KB sync to finish] — FAILED
  status: 401  error_code: ERR_401
  message: "A valid x-api-key header is required for this endpoint."
  url: http://127.0.0.1:8080/api/knowledge/sync
```

The async job reports `changed` (launching an async task always does), but the actual HTTP POST
executed with an **empty `x-api-key` header** and the backend rejects it (401). With
`serial:1` / `max_fail_percentage:0` this aborts the rollout before the second backend node.

## Root cause (confirmed)

`kb_sync.yml` extracted the api-key from the rendered `.env` with:

```yaml
kb_sync_api_key: >-
  {{ (kb_sync_env_slurp.content | b64decode).split('\n') | select('match', '^CONVERSATION_API_KEY=') | ... }}
```

Inside a YAML **folded scalar** (`>-`) the literal `\n` is preserved as a **two-character
backslash-n sequence**, not a newline. So `.split('\n')` never split the file — it returned the
whole `.env` as a single element, `select('match', '^CONVERSATION_API_KEY=')` matched nothing
(the file does not *start* with that line), and `first | default('')` yielded an **empty string**.

Reproduced on the pilot (`t03`) with a mini-playbook using the exact expression:
`extracted_len=0` → `warmup_http=401`. The `.env` key itself is correct (64 chars, no CR) and
authenticates: a host-side `curl` with the `.env` key returns `warm-up` **200**.

**Why it was latent:** the endpoint api-key gate is *open* when `CONVERSATION_API_KEY` is empty.
Earlier deploys ran with an empty key, so the empty header was accepted (200) and the sync ran
(this is the very sync that surfaced BUG-022's store-phase hang). Once a real
`CONVERSATION_API_KEY` was configured (64-char secret), the broken extraction started failing
auth — exposing the bug.

## Fix (implemented)

`deploy/ansible/roles/compose_tier/tasks/kb_sync.yml`: replace `.split('\n')` with
`.splitlines()`, which splits on real line breaks regardless of the folded-scalar escaping
ambiguity. Verified on `t03`: `splitlines_len=64` → `warmup_http=200`.

Ansible-only change (not baked into the container image) → takes effect on the next
`ansible-playbook` run; no image rebuild / re-tag required.

## Verification

- Reproduction playbook on `t03`: `.split('\n')` → `extracted_len=0`, warm-up 401.
- Fixed expression on `t03`: `.splitlines()` → `extracted_len=64`, warm-up **200**.
- Host-side control: `.env` key (64 chars) → warm-up 200; no key → 401 (gate closed, key required).
- Full re-deploy of backend `0.9.2` re-runs the sync with a valid header (see done-tasks).

## Follow-up

- Consider asserting a non-empty `kb_sync_api_key` before the trigger (fail fast with a clear
  message instead of a downstream 401) — tracked as a hardening note, not blocking.
