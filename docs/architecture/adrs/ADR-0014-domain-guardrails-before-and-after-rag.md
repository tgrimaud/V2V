# ADR-0014: Guardrails Run Before And After Retrieval

## Status

Accepted

## Context

The assistant must avoid answering outside its support scope and must not invent
answers when the knowledge base or billing evidence is insufficient. Greetings
also need to be handled naturally without consuming RAG and LLM resources.

Without a shared backend guardrail layer, each channel could implement different
fallback behavior and escalation triggers.

## Decision

Keep guardrails in the Java backend domain pipeline.

The backend applies guardrails in three stages:

- direct handling for greetings and simple conversational openings;
- pre-retrieval checks for off-topic or unsafe requests;
- post-retrieval confidence checks when retrieved evidence is too weak.

When guardrails block automation, the backend returns a controlled fallback or
escalation response. Channel adapters must display or speak that backend result
instead of replacing the decision locally.

## Consequences

- Guardrail behavior is consistent across voice, text, telephony, and future
  channels.
- Channels remain thin adapters and do not own support policy.
- Low-confidence and off-topic behavior is testable in the domain layer.
- Billing-specific uncertainty can be added to the same shared escalation model
  instead of being implemented per channel.

## Alternatives Considered

- **Implement guardrails in each channel adapter**: rejected because it fragments
  behavior and makes omnichannel escalation inconsistent.
- **Let the LLM decide when not to answer**: rejected because safety and support
  policy need deterministic checks before and after retrieval.

## Related Documents

- `docs/architecture/adrs/ADR-0001-java-backend-owns-conversation-domain.md`
- `docs/architecture/adrs/ADR-0010-industrialization-requires-contracts-slos-and-observability.md`
- `docs/architecture/architecture.md`
