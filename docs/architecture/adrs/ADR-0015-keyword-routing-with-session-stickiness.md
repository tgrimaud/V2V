# ADR-0015: Multi-Agent Routing Uses Keywords With Session Stickiness

## Status

Accepted

> **Implementation status (2026-08-05): NOT IMPLEMENTED on the current stack.** No
> `IntentClassifier` / `AgentProfile` exists in `backend/src/main` on
> `feat/restart-from-scratch` / the Sprint 11 branch (grep-verified); the rebuilt
> backend answers through a single RAG pipeline with domain filtering, not runtime
> multi-agent routing. An earlier implementation existed on `main`; this remains a
> target decision to re-introduce when multiple agent profiles are needed.

## Context

Voice Support Bot answers several support domains: technical support, billing,
and commercial questions. One generic prompt is less precise than domain-specific
agent profiles, but using an LLM classifier for every turn would add latency and
cost to the hot path.

The assistant also needs follow-up questions to stay with the current agent when
the topic remains implicit.

## Decision

Use deterministic keyword-based intent classification for the current agent
registry.

Each `AgentProfile` defines:

- an id and display name;
- a system prompt;
- a knowledge-base domain;
- intent keywords.

`IntentClassifier` scores profiles by whole-word keyword matches. When scores
tie, the current session agent is preferred. When no keyword matches and the
session already has an agent, the conversation stays with that agent. Otherwise
the backend falls back to the default support agent.

## Consequences

- Routing adds negligible latency compared with LLM-based classification.
- Agent behavior remains explainable and easy to test.
- The current agent is part of conversation state and must be preserved by the
  shared backend conversation store.
- Adding an agent requires updating the registry, prompt, keyword set, and
  knowledge-base domain.

## Alternatives Considered

- **Use one generic agent**: rejected because answers lose domain-specific
  prompting and retrieval filtering.
- **Use an LLM router for every turn**: deferred because it adds latency and cost
  before the deterministic approach is proven insufficient.
- **Ignore current-session stickiness**: rejected because follow-up questions can
  become ambiguous without the previous agent context.

## Related Documents

- `docs/architecture/adrs/ADR-0001-java-backend-owns-conversation-domain.md`
- `docs/architecture/adrs/ADR-0008-redis-active-sessions-postgres-durable-events.md`
- `docs/architecture/architecture.md`
