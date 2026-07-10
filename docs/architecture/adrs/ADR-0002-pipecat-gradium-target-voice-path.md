# ADR-0002: Pipecat + Gradium Is The Target V1 Voice Path

## Status

Accepted

> **Branch note (2026-07-10):** on `feat/restart-from-scratch` neither voice path
> is implemented — both `agent/bot.py` and `agent/bridge_server.py` were removed
> (preserved on `main`). Pipecat + Gradium remains the accepted **target**; the
> "the project has two voice paths" wording below describes the `main` reference.
> The only voice code on this branch is the STT-in web ingress (`voice-agent/web_voice/`),
> which posts PCM16 audio to a Python server and returns a Gradium transcript — no
> Pipecat, no TTS.

## Context

The project has two voice paths:

- a target Pipecat path through `voice-agent/agent/bot.py`;
- a custom WebSocket bridge through `voice-agent/agent/bridge_server.py`.

The custom bridge was useful for the initial POC and fallback testing, but it
duplicates voice orchestration responsibilities and increases the risk of drift.

## Decision

V1 starts with Pipecat + Gradium as the target voice path:

- Pipecat orchestrates WebRTC and Twilio Media Streams;
- Gradium provides STT/TTS;
- the Java backend remains responsible for RAG, business rules, guardrails,
  routing, escalation, and persistence;
- the custom bridge remains legacy/fallback/comparison until explicitly removed.

## Consequences

- WebRTC and telephony converge on the same voice orchestration model.
- Barge-in, server-side VAD, and streaming are handled by the target Pipecat path.
- The project must avoid treating `bridge_server.py` as the target architecture
  in new documentation or product decisions.
- Keeping both paths alive increases test and maintenance cost until the legacy
  path is retired.

## Alternatives Considered

- **Keep the custom bridge as the main path**: rejected because it recreates
  capabilities already provided by Pipecat and makes industrialization harder.
- **Move STT/TTS into the Java backend**: rejected because the backend should own
  conversation logic, not real-time audio orchestration.

## Related Documents

- `README.md`
- `docs/architecture/architecture.md`
- `docs/operations/backlog.md`
