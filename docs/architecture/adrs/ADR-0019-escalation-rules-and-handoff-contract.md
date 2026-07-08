# ADR-0019: Escalation Rules And Handoff Contract

## Status

Accepted

## Context

The bot must escalate consistently across voice, text, telephony, and future
messaging/contact-center channels. Current documentation lists generic support
triggers, while billing V1 also needs escalation when BSS evidence, invoice
extraction, or deterministic comparison is insufficient.

Without one shared escalation decision and handoff payload, each channel could
invent its own behavior and Genesys or another contact-center platform would
receive incomplete context.

## Decision

The Java backend owns escalation decisions.

Channel adapters must display or speak the backend escalation result and must not
replace it with channel-specific policy. Genesys Cloud CX or an equivalent
platform is a future recipient of escalation context, not the owner of
escalation logic.

Escalation triggers include:

- explicit request for a human advisor;
- cancellation, complaint, refund, dispute, or legal/privacy request;
- suspected account compromise or safety/security concern;
- field intervention or technician request;
- strong dissatisfaction or repeated automation failure;
- off-topic or unsafe request that cannot be handled by the bot;
- low RAG confidence or insufficient knowledge-base evidence;
- billing/BSS uncertainty: unavailable account data, inconsistent invoice
  evidence, unusable invoice extraction, low-confidence monetary lines, or a
  deterministic comparison that cannot explain the requested delta.

The future `EscalationHandoff` payload must include:

- `conversation_id`;
- `channel`;
- `external_session_id`;
- `message_id` or last inbound event id;
- `customer_reference` when available and safe to transmit;
- `current_agent_id`;
- `reason_code`;
- `reason_label`;
- `priority`;
- `summary`;
- `last_user_message`;
- `evidence_status`;
- `citations` or evidence references;
- `recommended_next_action`;
- `created_at`.

## Consequences

- Escalation behavior remains consistent across all channels.
- Billing V1 can fail safely when evidence is insufficient instead of inventing
  an explanation.
- Contact-center integration can be added later without moving guardrails,
  billing reasoning, RAG, or memory out of the Java backend.
- Current synchronous and SSE routes may keep returning an escalation response,
  but production channel adapters need a stable handoff envelope before real
  Genesys or equivalent integration.

## Alternatives Considered

- **Let each channel decide escalation**: rejected because it fragments support
  policy and makes omnichannel behavior inconsistent.
- **Let Genesys own escalation logic**: rejected because Genesys is a
  contact-center layer, while product policy, evidence confidence, and billing
  reasoning live in the backend.
- **Escalate only explicit advisor requests**: rejected because billing
  uncertainty and low evidence confidence must fail safely.

## Related Documents

- `docs/architecture/adrs/ADR-0001-java-backend-owns-conversation-domain.md`
- `docs/architecture/adrs/ADR-0009-independent-channel-adapters-shared-java-backend.md`
- `docs/architecture/adrs/ADR-0010-industrialization-requires-contracts-slos-and-observability.md`
- `docs/architecture/adrs/ADR-0014-domain-guardrails-before-and-after-rag.md`
- `docs/product/cahier-des-charges-fonctionnel.md`
