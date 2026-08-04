# QA Functional And Latency Report — TASK-INFRA-001 (per-tier docker-compose deploy stacks)

## Executive Summary

- **Overall readiness:** GO for merge-ready. The three per-tier compose stacks
  (`deploy/compose/{backend,voice,redis}`) render and satisfy every deployment
  invariant in the ticket acceptance criteria and the adversarial review
  (22/22 automated checks pass via `deploy/compose/qa-validate.sh`).
- **Main blockers:** none.
- **Residual risks:** the "stack up and reaches Postgres/Redis/backend-VIP" end of
  the acceptance criteria can only be fully proven on the **eir-ai4cc-tst**
  environment, which is gated by still-open inputs (container registry, internet
  egress, DB/Redis credentials, embeddings host). Live smoke is therefore
  **deferred to tst** and tracked, not run here. This mirrors the BE-022 pattern:
  deterministic parts fully automated, live-only parts explicitly deferred.

## Scope Tested

- **Epics / tasks:** EPIC-012 (Pilot deployment, release & operations) / TASK-INFRA-001.
- **Channels:** N/A (deployment configuration; no conversation behavior changed).
- **Providers / fakes:** none needed — validation renders the stacks with
  `docker compose config` using the committed `.env.example` templates.
- **Environment:** local, Docker 29.1.3 / Compose v2. No DB, Redis, Ollama or
  Mistral required.

## Acceptance Scenarios (Gherkin)

```gherkin
Feature: Per-tier docker-compose deploy stacks for eir-ai4cc-tst

  Scenario: Backend stack is deployable and self-describing
    Given the backend compose and its .env.example
    When an operator renders the stack with docker compose config
    Then the stack is valid
    And it exposes an /actuator/health healthcheck, a restart policy and a memory limit
    And it wires Postgres, Redis (CONVERSATION_STORE) and the KB read-only mount

  Scenario: Voice stack reaches the backend VIP
    Given the voice compose and its .env.example
    When an operator renders the stack
    Then the stack is valid
    And it publishes the bridge on 8090 with a GET / healthcheck
    And it wires VOICE_BACKEND_URL to the backend VIP

  Scenario: Redis stack protects shared session memory
    Given the redis compose and its .env.example
    When an operator renders the stack
    Then Redis requires a password, persists (appendonly) and never evicts active sessions
    And its healthcheck is an authenticated PING

  Scenario: Secrets are never committed
    Given the compose directory
    When the repository is inspected
    Then only .env.example templates are tracked
    And a real .env is git-ignored
    And templates carry only CHANGE_ME placeholders

  Scenario: Cross-tier key contract is expressed
    Given the backend and voice templates
    Then the backend CONVERSATION_API_KEY and the voice VOICE_BACKEND_API_KEY are both present
    And the docs state they must match (as must backend/redis REDIS_PASSWORD)
```

Automation: `deploy/compose/qa-validate.sh` (22 deterministic checks) is the
regression net for these scenarios.

## Functional Results

| Area | Status | Evidence | Notes |
|---|---|---|---|
| Backend stack renders + invariants | ✅ Pass | qa-validate 7/7 backend checks | health `/actuator/health`, `restart: unless-stopped`, memory limit, `CONVERSATION_STORE`, `REDIS_HOST`, KB `read_only: true` mount |
| Voice stack renders + reaches backend VIP | ✅ Pass | qa-validate 4/4 voice checks | `VOICE_BACKEND_URL`, port 8090, `GET /` healthcheck, restart policy |
| Redis stack protects session memory | ✅ Pass | qa-validate 4/4 redis checks | `requirepass`, `appendonly yes`, `noeviction`, authenticated PING |
| Secrets not committed | ✅ Pass | qa-validate secret-hygiene 3/3 | only `.env.example` tracked, `.env` git-ignored, placeholders only |
| Cross-tier key parity documented | ✅ Pass | qa-validate parity check + README | voice↔backend api key, backend↔redis password |
| KB provisioning (adversarial fix) | ✅ Pass | rendered `read_only: true` → `/app/kb-assets` | closes the review's blocking finding; sync into pgvector on first run |
| Live "reaches Postgres/Redis/VIP" | ⏳ Deferred | needs tst env (registry/egress/creds open) | run as first-deploy smoke on tst (TASK-DOC-003 runbook) |

## Latency Results

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| — | — | — | — | — | — | **N/A — not runtime-affecting.** INFRA-001 is deployment configuration; it adds no span, no code path and no measurable slice. It preserves the existing OTLP opt-in (`OTEL_*` OFF by default, ADR-0028) and propagates it to both services (backend `OTEL_EXPORTER_OTLP_*`, voice `OTEL_EXPORTER_OTLP_ENDPOINT`, names verified against code). |

Per the pipeline-slice rule, no slice is claimed rather than fabricated: this ticket
does not run the loop, so no p50/p95/p99 is produced. Latency for the deployed loop
is measured on tst once the stacks run (existing US-036 pipeline timing applies to
the backend/voice code, unchanged here).

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| backend compose | ✅ Pass | KB now mounted read-only (review fix); all invariants present | live smoke on tst |
| voice compose | ✅ Pass | reaches backend VIP; image entrypoint already binds 0.0.0.0:8090 | live smoke on tst |
| redis compose | ✅ Pass | auth + persistence + noeviction; authenticated healthcheck | confirm run mode vs native Redis (open input #8) |
| `.env.example` templates | ✅ Pass | complete per-tier contract; open inputs as documented placeholders | Ansible renders real `.env` (TASK-OPS-002) |
| `.gitignore` / secret hygiene | ✅ Pass | only templates tracked, `.env` ignored | — |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Info | Live "stack up reaches Postgres/Redis/VIP" not executed | Deterministic config fully validated; live connectivity proven only on tst | Ops (first-deploy smoke, TASK-DOC-003) |
| Low | Secrets injected via `environment:` (visible to `docker inspect`) | Acceptable for pilot; harden later | TASK-OPS-002 (secrets store) |
| Low | `REDIS_HEALTH_ENABLED=true` is stack-default (diverges from app default `false`) | Correct for the redis-backed tier; footgun only if reused in memory mode | documented in `.env.example` |

## Open Questions

- **Product:** none (no conversation behavior changed).
- **Architecture:** confirm Redis run mode on `.107` (container vs native) — open input #8.
- **Technical:** container registry path + credentials (open input #5) and egress
  (open input #2) to run the first live pull/deploy on tst.

## Recommendation

- **Go / No-go:** **GO** — merge-ready. Adversarial review 93/100 (Pass) + 22/22
  QA checks green.
- **Required fixes before pilot:** none from this ticket. Before the stacks run
  end-to-end on tst, the open infra inputs (registry, egress, DB/Redis creds,
  embeddings host) must be provided; the live first-deploy smoke belongs to
  TASK-INFRA-002/OPS-002/DOC-003.
