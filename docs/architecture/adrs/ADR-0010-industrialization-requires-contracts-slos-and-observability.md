# ADR-0010: Industrialization Requires Contracts, SLOs, And Observability

## Status

Accepted

## Context

The adversarial architecture review concluded that the current architecture is a
solid MVP foundation with a coherent industrialization direction, but not yet an
industrial omnichannel platform.

The main gaps are measurable SLOs, failure modes, channel/backend contracts,
human escalation contracts, observability, and resilience controls.

## Decision

Before adding real production-grade omnichannel integrations such as WhatsApp or
Genesys Cloud CX, the project must formalize:

- a stable channel/backend contract including `channel`,
  `external_session_id`, `message_id`, `idempotency_key`, `reply_mode`, and
  escalation context;
- a human escalation handoff contract usable by Genesys or an equivalent contact
  center;
- measurable SLOs and latency budgets for STT, backend, vector search, LLM,
  TTS, first token, first audio, and escalation;
- observability by channel and pipeline step;
- timeout, retry, circuit-breaker, rate-limiting, and degraded-mode strategies;
- tests for provider outages, Redis failure, duplicate messages, backend
  slowness, and escalation unavailability.

## Consequences

- The architecture remains honest about its current maturity.
- New channel work is gated by contracts and operational readiness, not just
  diagrams.
- Genesys and WhatsApp can be integrated without pulling business logic out of
  the Java backend.
- The team gets a concrete readiness checklist for pilot and production.

## Alternatives Considered

- **Add WhatsApp and Genesys connectors immediately**: rejected for production
  readiness because missing contracts would duplicate logic and hide failure
  modes.
- **Document only the target diagram**: rejected because diagrams do not define
  SLOs, failure behavior, or operational contracts.

## Related Documents

- `docs/architecture/adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md`
- `docs/architecture/adrs/ADR-0019-escalation-rules-and-handoff-contract.md`
- `docs/architecture/adversarial-architecture-review-2026-07-08.md`
- `docs/operations/backlog.md`
- `docs/product/cahier-des-charges-fonctionnel.md`
