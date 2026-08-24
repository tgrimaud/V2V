# ADR-0044: Pilot Data-Tier Resilience — SPOF Acceptance And Graceful Redis Degradation

## Status

Accepted (2026-08-15)

> Records the resilience posture for the **pilot** (eir-ai4cc-tst) data tier and the
> decision to reduce its blast radius. Complements **ADR-0038** (pilot deployment
> architecture), **ADR-0008 / TASK-BE-021** (Redis-backed conversation memory),
> **ADR-0039** (embeddings placement) and the `backup-restore.md` runbook (durability).
> Global-review decision #4 (2026-08-15). Implementation: **TASK-BE-030**.

## Context

The **target production** infrastructure (`infra-v1.md`) specifies **managed HA
PostgreSQL + pgvector** and **managed HA Redis** (2 instances each, ≥2 replicas). The
**pilot** deliberately does not run that yet:

- **PostgreSQL 18 + pgvector** runs on a **single** VM `vlb-ai4cc-t01` (`.102`), podman
  pod, **no replica / no PITR**.
- **Redis** runs on a **single** VM `vlb-ai4cc-t02` (`.107`), podman, AOF, **no
  replica / no Sentinel**.
- The backend and voice tiers *are* redundant (2 nodes each behind Keepalived VIPs), and
  the `backup-restore.md` runbook provides **durability** (off-host backup + restore) but
  explicitly puts **HA (replica / Sentinel / PITR) out of scope**.

So the two remaining single points of failure are precisely **Postgres** and **Redis**.
Their impact is **outage**, not merely lost durability:

- With `CONVERSATION_STORE=redis` and `REDIS_HEALTH_ENABLED=true`, a Redis outage makes
  the Actuator Redis indicator flip `/actuator/health` to **DOWN**, so HAProxy pulls
  **every** backend node out of rotation → a **full conversation outage**, even though the
  backend process is otherwise healthy and could still answer.
- A Postgres outage takes the vector store down → RAG retrieval fails → the voice journey
  degrades to the safe fallback.

For a **pilot / tst** environment, standing up full managed HA is disproportionate. But
the Redis failure mode above turns a **memory-only dependency** into a **total-availability
dependency**, which is an unnecessarily large blast radius.

## Decision

1. **Accept the pilot data-tier SPOF (formal risk acceptance).** For the pilot, a
   **single** Postgres and a **single** Redis instance are accepted, with `backup-restore.md`
   (off-host backup + restore) as the durability net. Managed HA (Postgres replica/PITR,
   Redis Sentinel/replica) **remains the documented production target** (`infra-v1.md`),
   not a pilot deliverable. Recovery from a data-VM loss is **restore-from-backup**, with an
   accepted RTO/RPO bounded by backup cadence (see the runbook), not automatic failover.

2. **Reduce the Redis blast radius with graceful degradation (TASK-BE-030).** A Redis
   outage must **degrade, not outage**: when Redis is unreachable the backend falls back to
   **in-process conversation memory** and **stays in rotation** instead of flipping
   `/actuator/health` DOWN and being pulled by HAProxy. Redis health becomes a **non-fatal /
   degraded** signal (observable, alertable) rather than a hard readiness failure in
   `redis`-store mode.

3. **Accept the multi-turn caveat during a Redis outage.** With in-process fallback across
   two backend nodes and no session affinity, a conversation's turns may land on different
   nodes, so **multi-turn context can be partially lost** while Redis is down. This is
   explicitly preferred over a full outage: single-turn billing/support answers keep working,
   and context recovers when Redis returns. (If this proves too visible, per-call affinity or
   sticky routing is a later lever — out of scope here.)

4. **Postgres stays fail-safe, not degraded-silent.** No graceful "RAG-less" mode is added
   in this ADR: a Postgres outage keeps producing the existing safe fallback + `ERR_UPSTREAM`
   observability. Postgres durability relies on backup/restore; its blast radius is not
   widened by a health-flip surprise the way Redis's was.

## Consequences

- **Cheap, high-value resilience win.** The most damaging pilot failure mode (Redis down →
  whole backend out of rotation → total outage) becomes a **graceful degradation** with no
  new infrastructure — only a health-gating + fallback change in the backend.
- **Risk is explicit, not implicit.** The pilot's lack of data-tier HA is now a recorded,
  accepted decision with a defined recovery path (restore-from-backup), instead of an
  undocumented gap that surfaces during an incident.
- **Observability preserved.** Redis-unreachable and Postgres-unreachable remain **distinct,
  alertable** signals (degraded vs fail-safe); a degraded Redis must be visible even though it
  no longer pulls the node.
- **Not production HA.** This ADR does **not** claim production availability. Any pilot→prod
  promotion must revisit `infra-v1.md` managed-HA before an SLO is claimed.
- **Test surface.** TASK-BE-030 must cover: Redis-down → node stays UP + in-process fallback
  path exercised; Redis-restored → shared memory resumes; the Redis health indicator reports
  degraded without failing readiness. Manual fakes, no Mockito.

## Alternatives Considered

- **Add managed HA now (Postgres replica/PITR + Redis Sentinel/replica):** rejected for the
  pilot — disproportionate infra/operational cost for a tst environment; already the
  documented production target.
- **Accept the SPOF unchanged (backup/restore only, no code change):** rejected — leaves the
  Redis-down → total-outage blast radius in place, which is avoidable at low cost.
- **Also add a Postgres "degraded, RAG-less" answer mode:** deferred — larger design question
  (what a billing answer means without retrieval), and the current fail-safe fallback already
  behaves acceptably; revisit only if a Postgres outage proves a frequent pilot failure mode.
- **Keep `REDIS_HEALTH_ENABLED=true` as a hard readiness gate:** rejected — it is exactly what
  converts a memory dependency into an availability dependency.

## Related Documents

- `docs/architecture/adrs/ADR-0038-pilot-deployment-architecture-eir-ai4cc-tst.md`
- `docs/architecture/adrs/ADR-0008-redis-active-sessions-postgres-durable-events.md`
- `docs/architecture/adrs/ADR-0039-embeddings-placement-and-provider-egress-tst.md`
- `docs/architecture/infra-v1.md`
- `docs/operations/backup-restore.md`
- `docs/operations/deployment-eir-ai4cc-tst.md`
- `product-backlog/tasks/backend-hardening-tasks.md` (TASK-BE-030)
