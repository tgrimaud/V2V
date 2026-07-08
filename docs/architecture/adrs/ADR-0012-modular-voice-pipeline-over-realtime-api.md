# ADR-0012: Use A Modular Voice Pipeline Instead Of A Realtime All-In-One API

## Status

Accepted

## Context

Realtime voice APIs can combine STT, LLM, and TTS behind one provider contract.
They are attractive for prototypes, but Voice Support Bot needs tight control
over RAG, billing evidence, guardrails, escalation, conversation memory, and
provider replacement.

The product also needs to support several runtime channels over time. Coupling
the full voice-to-voice loop to one realtime provider would make channel
adapters and business behavior harder to test independently.

## Decision

Use a modular pipeline:

- voice runtime and audio orchestration in Pipecat;
- STT and TTS behind Pipecat services;
- RAG, billing reasoning, guardrails, routing, escalation, and memory in the
  Java backend;
- LLM generation behind backend LLM ports.

Do not make an all-in-one realtime API the owner of the conversation loop.

## Consequences

- The backend keeps full control over business decisions and explainability.
- Providers can be changed independently for STT, TTS, chat generation, and
  embeddings.
- The system has more integration points to observe and tune.
- Latency improvements must be achieved through streaming and pipeline
  orchestration rather than delegating the whole loop to one provider.

## Alternatives Considered

- **Use a realtime all-in-one provider for the full loop**: rejected because it
  would put business-critical behavior behind a provider-specific runtime.
- **Put STT/TTS directly in the Java backend**: rejected because real-time audio
  orchestration is better handled by Pipecat and Python voice tooling.

## Related Documents

- `docs/architecture/adrs/ADR-0001-java-backend-owns-conversation-domain.md`
- `docs/architecture/adrs/ADR-0002-pipecat-gradium-target-voice-path.md`
- `docs/architecture/architecture.md`
