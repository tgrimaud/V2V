# Adversarial Review — Deployment, Infrastructure & Observability

- **Date:** 2026-08-28
- **Branch:** `feat/sprint-12-external-voice-websocket` (read-only review, no changes made)
- **Reviewer role:** Adversarial code + architecture review (delivery gate)
- **Goal:** Confirm the deploy/observability assets are clean before the next sprint begins.
- **Skills applied:** `.cursor/skills/adversarial-code-review` (0–100 gate),
  `.cursor/skills/adversarial-architecture-review` (secrets, degraded modes, provider replaceability).

---

## Scope

Reviewed (tracked files only):

- `deploy/ansible/` — `group_vars/all/{vars,vault.example}.yml`, `group_vars/{backend,voice,redis}.yml`,
  `deploy.yml`, `prereqs.yml`, `rollback.yml`, `ansible.cfg`, `inventory/hosts.ini`,
  `roles/compose_tier/{tasks,templates}/*`, `roles/host_prereqs/*`, `.gitignore`.
- `deploy/observability/` — `docker-compose.otel.yml`, `otel-collector-config.yaml`, `prometheus.yml`.
- `deploy/compose/{backend,voice,redis}/docker-compose.yml` and their `.env.example`.
- `deploy/backup/*.sh` (pg + redis).
- Root `docker-compose.yml`, `scripts/dev-db-init/01-extensions.sql`, `.gitignore`, `.env.example`.
- `scripts/` (llm_benchmark reports, be018_ab.sh, translate_csv_kb.py, retrieval_eval).
- Cross-checked against `docs/operations/first-deploy-runbook.md`, ADR-0038, ADR-0041, ADR-0048, BUG-013/BUG-014.

Out of scope / not run: no real deploy, no remote host connection, no branch switch, no commits.

## Method

- **Secrets:** `git ls-files` on secret-bearing paths; regex grep for `api_key/secret/password/token/credential`
  and provider key shapes (`sk-…`, `ghp_…`, `AKIA…`, `-----BEGIN`, `xox…`) across the tracked tree; verified
  `.env`, `vault.yml`, `.vault_pass` are untracked and vault is encrypted.
- **KB sync (TASK-OPS-009):** verified ordering (post-health), async pattern, idempotency, the `processed`
  gate, and FR-corpus coherence with ADR-0048.
- **Health gate:** traced `health.yml` + `group_vars/voice.yml health_url` against the documented loopback
  false-negative and the `serial:1 / max_fail_percentage:0` play semantics.
- **Backend URL:** checked `voice_backend_url` / template against BUG-013 (server base, VIP on :80).
- **Liquibase split (TASK-INFRA-009 / ADR-0041):** confirmed no `CREATE EXTENSION/ROLE/DATABASE` at app
  startup; dev via `/docker-entrypoint-initdb.d`, pilot via superuser bootstrap changelog + psql pre-step.
- **OTel opt-in (TASK-OPS-007):** verified both tiers gate export off when `otel_collector_endpoint` is empty.
- **Idempotency, failure modes, image pinning:** read every task/template for re-run safety and floating tags.

---

## Overall score: 87 / 100

## Verdict: **CLEAN** for the next sprint (no blockers)

No committed secrets and no app-startup privileged DDL — the two hard gate conditions are met.
One **Major** (loopback health gate) should be ticketed and fixed, but it is a known,
worked-around operational risk and does not block starting the next sprint.

- **Blockers:** 0
- **Majors:** 1
- **Minors:** 6
- **Secrets committed:** none found.

---

## Blockers

None.

Positive confirmations for the two blocker classes:

- **Secrets:** `.env` (root + `backend/.env` + `*/.env`) and `articles*.csv` are git-ignored and untracked;
  `deploy/ansible/group_vars/all/vault.yml` is **not tracked** and, on disk, is `$ANSIBLE_VAULT;1.1;AES256`
  encrypted; `.vault_pass` is `0600` and git-ignored; only `vault.example.yml` (all `CHANGE_ME`) is tracked.
  Every rendered `.env` value comes from a `vault_*` variable (`*.env.j2`), rendered `mode: 0600`, `no_log: true`.
  Regex/key-shape grep across the tracked tree returned no plaintext secrets.
- **Privileged DDL:** the backend runs `ddl-auto: none` + `initialize-schema: false` and only executes the
  Liquibase **app** changelog at startup. `CREATE EXTENSION` is done by `scripts/dev-db-init/01-extensions.sql`
  (dev, `/docker-entrypoint-initdb.d`) and, on the pilot, by the one-shot **superuser bootstrap changelog**
  (runbook Step 4b) with separate tracking tables; `CREATE DATABASE/ROLE` + `ALTER … OWNER` are a psql
  superuser pre-step (Step 4a). Matches ADR-0041 exactly. The bootstrap Liquibase image is pinned
  (`liquibase/liquibase:4.29.2`) and its password passed via `LIQUIBASE_COMMAND_PASSWORD` (env, not argv).

---

## Majors

### M1 — Voice health gate still probes loopback; can abort a serial deploy after node recreation

- **Where:** `deploy/ansible/group_vars/voice.yml:8` (`health_url: "http://127.0.0.1:8090/"`) consumed by
  `deploy/ansible/roles/compose_tier/tasks/health.yml:5-13` (`uri` on the target host, `retries: 30 delay: 5`).
- **Risk:** documented recurring false-negative — on the pilot Podman hosts, host→`127.0.0.1:8090` returns
  `000` even when the bridge is `healthy` and answers `200` on the host LAN IP. `main.yml` recreates the stack
  (`compose pull` + `up -d`) **before** this gate, and the voice play runs `serial: 1` with
  `max_fail_percentage: 0` (`deploy.yml:53-58`). A false-negative therefore burns ~150 s, then **aborts the
  whole voice play after the node was already recreated at the new tag**, and the second bridge is never
  touched — leaving the fleet on mixed tags. This is captured in `CLAUDE.md` as a recurring issue but has
  **no tracked remediation ticket** and the asset is unchanged.
- **Remediation:** point `health_url` at the host LAN IP (e.g. derive `ansible_default_ipv4.address`) or
  replace the `uri` probe with a container-native check (`podman inspect --format '{{.State.Health.Status}}'`
  / `podman exec … healthcheck`), OR make the gate non-fatal (`failed_when: false`) with an explicit out-of-band
  confirmation task. Open a `TASK-OPS`/`TASK-INFRA` follow-up so the fix is tracked, not tribal knowledge.
- **Note:** the backend gate (`backend.yml:8`, `/actuator/health`) is also loopback but is documented as
  "ungated" and has not shown the same quirk; still worth the same treatment for consistency.

---

## Minors

### m1 — `image_tag` defaults to `latest`
- **Where:** `deploy/ansible/group_vars/all/vars.yml:12` and the compose `${IMAGE_TAG:-latest}` fallbacks.
- **Assessment:** mitigated — `deploy.yml:12-25` refuses `image_tag == 'latest'` and demands an immutable tag;
  the default only bites a manual `podman compose` run that bypasses Ansible. Keep, but consider defaulting to
  an obviously-invalid sentinel to fail even the manual path.

### m2 — A few floating image tags (not digest/patch-pinned)
- **Where:** `deploy/ansible/group_vars/redis.yml:12` (`redis:7-alpine`, pilot); root `docker-compose.yml:8,27`
  (`pgvector/pgvector:pg16`, `ollama/ollama:latest`, dev only).
- **Assessment:** reproducibility risk. Contrast with the correctly-pinned assets: OTel collector `0.115.1`,
  Prometheus `v2.55.1`, ollama sidecar `0.5.4`, Liquibase `4.29.2`, compose provider `v5.4.0` **+ sha256**.
  Pin redis to a patch tag (or digest) for the pilot; dev floats are acceptable.

### m3 — Local-dev Postgres password committed in plaintext
- **Where:** root `docker-compose.yml:12` (`POSTGRES_PASSWORD: voicesupport`).
- **Assessment:** well-known dev-only default, ports 5433, not a pilot credential — low risk, but it is a
  committed credential. Consider sourcing it from a dev `.env` for hygiene.

### m4 — Redis password reaches process argv on host/container
- **Where:** `deploy/compose/redis/docker-compose.yml:22` (`--requirepass ${REDIS_PASSWORD}` in the container
  command) and `:32` (`redis-cli -a "$$REDIS_PASSWORD"` healthcheck); `roles/compose_tier/tasks/health.yml:19-21`
  (`docker exec -e REDISCLI_AUTH={{ vault_redis_password }} …`).
- **Assessment:** partially contradicts the stated "never in argv" intent — the value is visible to `ps` /
  `podman inspect` on the host (the `-e KEY=VALUE` and `--requirepass VALUE` forms both land in an argv), even
  though `no_log`/`REDISCLI_AUTH` keep it out of Ansible logs and the redis-cli `-a` case. Minor hardening:
  pass `-e REDISCLI_AUTH` as a pass-through from an already-set env, and prefer a mounted `requirepass`/ACL
  file over the inline command.

### m5 — Backend compose KB_CSV_PATH fallback is the EN corpus
- **Where:** `deploy/compose/backend/docker-compose.yml:48` (`KB_CSV_PATH:-/app/kb-assets/articles.csv`).
- **Assessment:** harmless because Ansible always overrides to `articles-fr.csv` (`backend.env.j2:40`,
  `group_vars/backend.yml:69`), but the compose fallback diverges from the ADR-0048 pilot decision (FR). Align
  the fallback or drop it so a manual run can't silently load EN.

### m6 — Liquibase bootstrap is a manual runbook step, not automated/idempotently enforced
- **Where:** `docs/operations/first-deploy-runbook.md` Step 4a/4b; nothing in `deploy/ansible/`.
- **Assessment:** acceptable and correct per ADR-0041 (one-shot, superuser, out of the app path) and very well
  documented, but it is a residual operational dependency outside the idempotent playbooks. Consider a guarded,
  optional `prereqs`-style task (or a CI check) so a fresh environment cannot skip it.

---

## What was verified clean (evidence)

| Area | Result | Evidence |
|---|---|---|
| No committed secrets | Pass | `git ls-files` (vault.yml/.vault_pass/.env untracked), vault `AES256`, key-shape grep empty |
| Deploy guards | Pass | `deploy.yml:12-38` refuses `latest`, asserts vault ≠ `CHANGE_ME` |
| KB sync post-health + async + gate | Pass | `main.yml:82-89` (after health), `kb_sync.yml` (poll:0 + async_status, 2400/2700 s + 90×30 s, `processed ≥ 50`) |
| KB sync idempotent + FR corpus | Pass | content_hash skip; `kb_csv_filename: articles-fr.csv` / `kb_csv_language: fr` (ADR-0048) |
| KB api key handling | Pass | read from rendered `.env` via slurp, `no_log`; never argv |
| `VOICE_BACKEND_URL` = server base | Pass | `group_vars/voice.yml:28` `http://192.168.0.11` (VIP :80, not :8080, not full converse path) — BUG-013 |
| No privileged DDL at app startup | Pass | dev init script + pilot bootstrap changelog; `ddl-auto none`, `initialize-schema false` (ADR-0041) |
| OTel opt-in both tiers | Pass | `backend.env.j2:50-53`, `voice.env.j2:31-32` gate `OTEL_METRICS_EXPORT_ENABLED` + sampler off when endpoint empty; valid localhost fallback avoids Spring OTLP empty-endpoint crash |
| Backup secret handling | Pass | `backup.yml` renders `0600` env files sourced by cron; `pg-backup.sh:38` uses `-e PGPASSWORD` env, not argv |
| Least privilege / idempotency | Pass | source-scoped firewalld rich rules; registry login→logout drops cached creds; `:ro,Z` SELinux; serial:1 + fail-safe non-fatal LB drain/re-enable hooks; compose provider sha256-pinned |

---

## Concrete remediation per finding

| ID | File:line | Action |
|---|---|---|
| M1 | `group_vars/voice.yml:8` + `roles/compose_tier/tasks/health.yml:5-13` | Repoint `health_url` to host LAN IP or use a `podman inspect`/`podman exec` health probe; or make the gate non-fatal with out-of-band confirmation. Open a tracked TASK-OPS/INFRA ticket. |
| m1 | `group_vars/all/vars.yml:12` | Default `image_tag` to an invalid sentinel so even manual compose runs fail without an explicit tag. |
| m2 | `group_vars/redis.yml:12` | Pin redis to a patch tag or digest for the pilot. |
| m3 | `docker-compose.yml:12` | Source the dev Postgres password from a dev `.env`. |
| m4 | `deploy/compose/redis/docker-compose.yml:22,32`; `health.yml:19-21` | Pass `REDISCLI_AUTH` as env pass-through; prefer a mounted requirepass/ACL file over inline argv. |
| m5 | `deploy/compose/backend/docker-compose.yml:48` | Align the `KB_CSV_PATH` fallback with the FR pilot default or drop the fallback. |
| m6 | `first-deploy-runbook.md` Step 4 | Add a guarded optional bootstrap task or a CI/pre-deploy check for the superuser changelog. |

---

## Residual risk if accepted

- **M1 not fixed before next deploy:** a voice version promotion can abort mid-roll on a false-negative
  loopback probe, leaving the two bridges on **different image tags** until an operator manually finishes the
  blocked node (bump `IMAGE_TAG` in `/opt/voice-support/voice/.env` + `podman compose up -d`). Availability is
  preserved by the VIP peer, but the deploy is not self-completing and requires tribal knowledge.
- **m4:** a local shell user on a deploy VM can read the Redis password from process listings during a deploy
  window; mitigated by host access being restricted and by `requirepass` + source-scoped firewalling.
- **m6:** a fresh environment that skips the manual bootstrap fails closed at first backend start
  (`type "vector" does not exist`) — noisy but not silent; recovery is documented in the runbook troubleshooting.
- **m1/m2/m3/m5:** reproducibility / hygiene only; no runtime or security impact on the pilot path as
  currently driven by Ansible.
