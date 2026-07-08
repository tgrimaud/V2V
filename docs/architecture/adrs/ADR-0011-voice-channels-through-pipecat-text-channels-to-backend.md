# ADR-0011: Voice Channels Go Through Pipecat, Text Channels Go To Backend

## Status

Accepted

## Context

The product is expected to support multiple entry channels over time:

- phone calls;
- web voice;
- WhatsApp calls or equivalent voice-over-messaging calls;
- web chat;
- WhatsApp text messages;
- other asynchronous messaging channels.

Voice and text channels have different runtime needs. Voice channels need
real-time audio orchestration, VAD, interruption handling, STT, TTS, and audio
streaming. Text channels do not need those capabilities and can call the
conversation backend directly.

## Decision

Any entry channel that contains real-time voice must go through a channel proxy
or adapter that communicates with Pipecat.

Examples:

- phone call -> telephony proxy -> Pipecat;
- web voice -> WebRTC proxy / frontend -> Pipecat;
- WhatsApp call -> WhatsApp voice proxy -> Pipecat.

Text-only or asynchronous channels call the Java backend directly through a
channel adapter.

Examples:

- web chat text -> Java backend;
- WhatsApp text message -> Java backend;
- contact-center text chat -> Java backend.

Pipecat owns the voice runtime concerns: audio transport, VAD, barge-in, STT,
TTS, and audio streaming. The Java backend remains the shared conversation and
business engine for both voice and text.

## Consequences

- Voice channels share one real-time orchestration path through Pipecat.
- Text channels avoid unnecessary audio infrastructure and keep lower latency and
  simpler failure modes.
- The Java backend remains the single owner of RAG, billing reasoning, guardrails,
  routing, escalation rules, and conversation memory.
- Channel proxies must normalize channel identity and session metadata before
  calling Pipecat or the backend.
- Future WhatsApp voice and WhatsApp text integrations may use different adapter
  paths even if they belong to the same commercial channel.

## Alternatives Considered

- **Send all channels through Pipecat**: rejected because text channels do not
  need audio orchestration and would inherit unnecessary dependencies.
- **Let each channel call the backend and manage voice independently**: rejected
  because it would duplicate STT/TTS, VAD, and barge-in behavior across voice
  channels.
- **Let Pipecat own conversation logic**: rejected because business rules, RAG,
  billing reasoning, guardrails, routing, escalation, and memory must stay in the
  Java backend.

## Related Documents

- `docs/architecture/adrs/ADR-0001-java-backend-owns-conversation-domain.md`
- `docs/architecture/adrs/ADR-0002-pipecat-gradium-target-voice-path.md`
- `docs/architecture/adrs/ADR-0009-independent-channel-adapters-shared-java-backend.md`
- `docs/architecture/diagrams/application-components.drawio`
