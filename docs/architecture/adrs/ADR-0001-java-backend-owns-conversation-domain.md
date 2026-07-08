# ADR-0001: Java Backend Owns The Conversation Domain

## Status

Accepted

## Context

Voice Support Bot combines voice orchestration, RAG, multi-agent routing,
guardrails, escalation, persistence, and administration. Several external entry
points are expected over time: WebRTC, telephony, web chat, WhatsApp, and
possibly Genesys Cloud CX.

If each channel owns its own business rules, the product will fragment quickly:
different answers, different escalation behavior, duplicated guardrails, and
inconsistent persistence.

## Decision

The Java backend is the conversation engine. It owns:

- RAG and knowledge-base lookup;
- business rules;
- guardrails;
- multi-agent routing;
- escalation decisions;
- conversation memory;
- durable conversation events;
- admin-facing conversation metrics.

Channel adapters call the backend through stable conversation APIs. They do not
own business decisions.

## Consequences

- All channels share one source of truth for conversation behavior.
- The backend becomes a critical shared dependency and must be protected with
  timeouts, observability, rate limiting, and channel-aware contracts.
- Channel adapters remain replaceable as long as they do not duplicate backend
  logic.

## Alternatives Considered

- **Put business logic in each channel adapter**: rejected because it duplicates
  rules and makes omnichannel behavior inconsistent.
- **Let a contact-center platform own the conversation logic**: rejected for the
  current product because the RAG, billing reasoning, guardrails, and
  persistence must stay under project control.

## Related Documents

- `docs/product/cahier-des-charges-fonctionnel.md`
- `docs/architecture/architecture.md`
- `docs/architecture/adversarial-architecture-review-2026-07-08.md`
