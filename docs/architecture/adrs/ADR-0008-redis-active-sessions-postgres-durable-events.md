# ADR-0008: Redis Stores Active Sessions, PostgreSQL Stores Durable Events

## Status

Accepted

## Context

The product needs conversational memory for multi-turn flows, channel handoff,
and human escalation. It also needs durable events for audit, troubleshooting,
analytics, and future operational dashboards.

Active session state and durable history have different lifecycle and scaling
needs.

## Decision

Use Redis for active conversation/session state and PostgreSQL for durable
conversation events and vector data.

Redis is used for fast shared state across scaled backend instances and channel
adapters. PostgreSQL remains the durable store for persisted conversation events,
knowledge sync state, and pgvector data.

## Consequences

- Backend instances can scale horizontally without losing active conversation
  state.
- Conversation events remain queryable and durable outside Redis TTLs.
- Redis failure modes must be documented and tested because active session
  continuity depends on it.
- Session TTLs must be chosen from business expectations, not only technical
  cache defaults.

## Alternatives Considered

- **Store all conversation state only in memory**: rejected because it prevents
  scale-out and breaks omnichannel continuity.
- **Store all active state only in PostgreSQL**: rejected because active,
  frequently updated session state has different latency and lifecycle needs.
- **Use Hazelcast instead of Redis**: not retained for now because Redis is a
  simpler shared-state dependency for the current stack and Docker Compose
  target.

## Related Documents

- `docker-compose.yml`
- `docs/architecture/architecture.md`
- `docs/operations/backlog.md`
