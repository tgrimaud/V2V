# TASK-OPS-009 — Adversarial Code Review (deploy triggers/verifies KB sync + FR corpus default)

- **Ticket:** TASK-OPS-009 — Deploy must trigger/verify KB sync + FR corpus default
- **Branch reviewed:** `task/TASK-OPS-009-kb-sync-fr-default`
- **Commit reviewed:** `876619c` (code) — doc-evidence commit `9589b3e`
- **Reviewer skill:** `.cursor/skills/adversarial-code-review/SKILL.md`
- **Related:** ADR-0048 (bilingual KB corpus + retrieval language scope), ADR-0038 (pilot
  deploy), ADR-0030 (CSV domain classification), ADR-0031 (answer language), ADR-0034
  (audience fail-closed)
- **Date:** 2026-08-27

## Verdict

**Proceed.** The change is functionally correct against the *actual* backend contracts,
QA is green, the playbook syntax-checks clean, secrets are protected, and the deploy gate
is sound (it cannot silently leave the RAG markdown-only). Two non-blocking maintainability
findings were fixed during the review.

## Satisfaction Score

- **Initial: 92/100** (Pass) — two non-blocking maintainability findings.
- **After fixes: 96/100.**
- **QA gate: Pass.**

## Scope of the change

`deploy/ansible/`:

- `group_vars/backend.yml` — FR corpus default (`kb_csv_filename: articles-fr.csv`,
  `kb_csv_language: fr`) + async-sync tunables (`kb_sync_timeout/_async_seconds/_poll_retries/
  _poll_delay/_min_processed`, `kb_sync_after_deploy`).
- `roles/compose_tier/templates/backend.env.j2` — renders `KB_CSV_PATH` + `KB_CSV_LANGUAGE`
  from the vars.
- `deploy/compose/backend/.env.example` — mirrors the FR default.
- `roles/compose_tier/tasks/kb_assets.yml` — copies `{{ kb_csv_filename }}`.
- `roles/compose_tier/tasks/kb_sync.yml` (new) — backend-tier post-health KB sync.
- `roles/compose_tier/tasks/main.yml` — wires `kb_sync.yml` after `health.yml`, gated to the
  backend tier and `kb_sync_after_deploy`.
- `qa-validate-ansible.sh` — +7 structural checks (76/76).

## Contract verification (against the real backend code)

The strongest guarantee of this review: every backend contract the sync task depends on was
verified against source, not assumed.

| Assumption in `kb_sync.yml` | Backend source | Result |
|---|---|---|
| `POST /api/knowledge/sync` returns `{processed, ingested, skipped, deleted}` | `SyncReport` (record) + `KnowledgeController.syncAll()` returns `SyncReport` directly | ✅ fields match `json.processed/ingested/skipped/deleted` |
| Gate on `processed` passes on an idempotent re-deploy | `KnowledgeSyncService.syncConnector`: `new SyncReport(documents.size(), ingested, skipped, deleted)` | ✅ `processed = documents.size()` = all docs seen (ingested + skipped), so a re-sync with `ingested=0` still reports `processed ≈ 300 ≥ 50` |
| `x-api-key` header gates the endpoint; empty key ⇒ open | `ApiKeyAuthInterceptor.HEADER = "x-api-key"`; `WebSecurityMvcConfig` gates `/api/knowledge/**` + `/api/conversation/retrieve`; `ApiKeyGuard` open when unset | ✅ correct header + gated paths |
| `POST /api/conversation/retrieve` accepts `{question, top_k}` and returns `{verdict, evidence[]}` | `RetrievalRequest(question, domain, topK, alreadyGreeted)` + `RetrievalResponse(answerable, verdict, fallbackMessage, evidence[])`; global `JacksonConfig` = `SNAKE_CASE` | ✅ `top_k`→`topK`, `json.verdict`/`json.evidence` are snake_case — all map correctly |

Because Jackson is globally `SNAKE_CASE` (`shared/config/JacksonConfig.java`), the `top_k`
body field and all `json.*` reads resolve correctly (verified against
`RetrievalControllerTest`, which sends `top_k` and asserts `source_id`/`fallback_message`).

## Blocking Findings

_None._

## Non-Blocking Findings

| Severity | Finding | Evidence | Resolution |
|---|---|---|---|
| Low (maintainability) | `no_log: true` on the `async_status` wait suppressed the HTTP status/body of a *failed* sync, hurting diagnosability, even though that task carries no secret (it polls by job id only; the `uri` result never echoes request headers). | `kb_sync.yml` "Wait for the KB sync to finish" | **Fixed** — removed `no_log` from `async_status` (secret-bearing tasks — slurp, set_fact, sync-fire, retrieve — keep `no_log`). A failed sync now surfaces status/body for the gate + operator. |
| Low (maintainability) | The read-only retrieval smoke-check reported `changed` on every deploy. | `kb_sync.yml` retrieve task | **Fixed** — added `changed_when: false` (read-only grounding probe). |
| Info | `kb_sync_min_processed: 50` is a heuristic tuned to the current corpus (markdown 3 + FR ≈ 300). | `group_vars/backend.yml` | Accepted — it is env-tunable and documented; a smaller future corpus needs a lower gate. |

## Story Coverage

| Acceptance criterion (ticket Gherkin) | Covered? | Evidence |
|---|---|---|
| A redeploy leaves the RAG populated, not markdown-only (sync fired async, api key from rendered `.env`, waits via `async_status`, fails if `processed` below baseline) | ✅ | `kb_sync.yml` slurp+extract (no_log) → async `uri` (poll:0) → `async_status` wait → `assert processed >= kb_sync_min_processed` |
| An idempotent re-deploy is a fast no-op and still passes the processed gate | ✅ | `processed = documents.size()` includes skipped (verified in `KnowledgeSyncService`); content_hash skip in `isUnchanged` |
| The pilot CSV corpus is French (`KB_CSV_PATH` → `articles-fr.csv`, `KB_CSV_LANGUAGE=fr`) | ✅ | `group_vars/backend.yml` + `backend.env.j2` + `.env.example` |

## Test Evidence

- **QA:** `deploy/ansible/qa-validate-ansible.sh` → **76/76 passed, 0 failed** (re-run in this
  review). New checks assert FR default, env wiring, sync wired + verify, api-key `no_log`,
  async + `async_status`, and the `processed` gate.
- **Playbook syntax:** `ansible-playbook --syntax-check -i inventory/hosts.ini deploy.yml` → clean.
- **Backend contracts:** verified by reading `SyncReport`, `KnowledgeController`,
  `KnowledgeSyncService`, `RetrievalController/Request/Response`, `WebSecurityMvcConfig`,
  `ApiKeyAuthInterceptor`, `JacksonConfig` (see table above).
- **Not run (deliberate):** a live pilot redeploy — out of scope per the ticket and the user
  instruction ("do NOT run a prod redeploy"). The immediate pilot load was done out-of-band
  (done-tasks 2026-08-27) and is the runtime evidence for grounding.

## Observability And Latency

- This is a **deploy/config** change that *triggers* already-instrumented runtime endpoints; it
  adds no new runtime code path or latency slice.
- Runtime evidence exists backend-side: `KnowledgeController` emits `[KB-SYNC] op=… processed=…
  ingested=… skipped=… deleted=… duration_ms=…` and the observer records `syncCompleted` /
  `syncFailed`; `RetrievalController` emits `[GROUNDING] … verdict=… hits=… best_score=…
  duration_ms=…`.
- Deploy-side evidence: the play prints the aggregate sync counts and the retrieval
  evidence-count/verdict (counts only — no KB content, no key).
- **Missing:** nothing required for this change.

## Security And Privacy

- **API key:** read from the host-rendered `.env` (mode 0600) via `slurp` → `set_fact`, both
  `no_log`; passed only as the `x-api-key` header on `no_log` tasks; never on argv, never logged.
- **No content/PII leakage:** the visible `debug` tasks emit aggregate counts + verdict +
  evidence *count* only — never evidence text or the key.
- **No new write surface / no BSS writes.**

## Required Developer Actions

1. ~~Remove `no_log` from the `async_status` wait so a failed sync is diagnosable.~~ ✅ Done.
2. ~~Mark the read-only retrieval smoke-check `changed_when: false`.~~ ✅ Done.
3. Re-run `qa-validate-ansible.sh` after the fixes. ✅ 76/76.

## Residual Risk If Accepted

- **Live behaviour unproven by this branch** (async wait duration, gate on the real corpus) —
  a full prod redeploy is intentionally deferred (known voice health-gate false-negative,
  TASK-INFRA-011). The immediate pilot load already proved grounding out-of-band. Low risk:
  contracts + gate logic are verified against source and QA is green.
- **`kb_sync_min_processed` heuristic** — tunable; only a mis-set value on a much smaller corpus
  could false-fail a deploy (fails safe/loud, never silently markdown-only).
