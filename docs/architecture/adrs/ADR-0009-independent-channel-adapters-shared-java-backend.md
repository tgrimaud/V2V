# ADR-0009: Independent Channel Adapters Share The Java Backend

## Status

Accepted

## Context

The product vision includes multiple entry points:

- WebRTC voice;
- telephony;
- web chat;
- WhatsApp;
- future contact-center integration through Genesys Cloud CX or an equivalent
  platform.

These channels have different protocols, latency profiles, payload formats, and
failure modes. At the same time, they must share business behavior.

## Decision

Each channel is an independent adapter that calls the shared Java conversation
backend.

Genesys Cloud CX is positioned as a future contact-center and human-escalation
platform, not as the owner of RAG, billing reasoning, guardrails, or conversation
memory.

WhatsApp is positioned as a future asynchronous messaging channel adapter, not a
separate conversation engine.

## Consequences

- Channels can evolve, fail, and be deployed independently when their adapters
  are isolated correctly.
- Shared backend contracts must include channel identity and idempotency data.
- Real-time voice traffic must be protected from asynchronous channel bursts
  through quotas, prioritization, and observability.
- Genesys integration can be added later without replacing the backend
  conversation engine.

## Alternatives Considered

- **Route all channels through Genesys from the start**: deferred because it would
  make industrialization dependent on a contact-center platform before the core
  conversation engine is proven.
- **Implement one backend per channel**: rejected because it duplicates business
  logic and increases inconsistency risk.

## Related Documents

- `docs/product/cahier-des-charges-fonctionnel.md`
- `docs/architecture/adversarial-architecture-review-2026-07-08.md`
- `docs/architecture/architecture.md`
