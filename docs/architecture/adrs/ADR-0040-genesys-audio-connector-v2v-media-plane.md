# ADR-0040: Genesys Audio Connector As The V2V Media Plane

## Status

Accepted (target)

> **Implementation status (2026-08-07): NOT IMPLEMENTED — target decision.** No
> Genesys Audio Connector server, Architect flow, or adapter exists in the runtime
> yet. Full Genesys voice routing stays deferred (Sprint 13, gated by OQ-006). This
> ADR fixes the target integration shape and terminology so the future spike and
> backlog stay precise. It refines ADR-0020 and does not change any runtime code.

## Context

The target contact-center environment uses Genesys Cloud CX in front of our voice
platform. The team initially assumed a single "AudioHook" protocol would carry the
call to our application and also carry the call back on escalation. Reading the
Genesys [AudioHook introduction](https://developer.genesys.cloud/devapps/audiohook/introduction),
[Protocol Reference](https://developer.genesys.cloud/devapps/audiohook/protocol-reference)
and [Audio Connector overview](https://help.genesys.cloud/articles/audio-connector-overview/)
shows this is not accurate and would under-scope the integration.

Two facts drive this ADR:

1. **AudioHook is the transport protocol** (WebSocket over TLS, JSON control frames +
   binary audio), and it exposes **two different features**:
   - **Bot Transcription Connector** — a **listen-only** tap for monitoring,
     transcription, analytics, biometrics and recording. It cannot play audio back to
     the caller. This is what the AudioHook *introduction* page describes.
   - **Audio Connector** — a **bidirectional** feature: the service receives customer
     audio and **sends bot audio back**, with `playback-started`/`playback-completed`,
     barge-in and `BotTurnResponse` events. This is the "bring-your-own voicebot"
     integration (same slot as Dialogflow / Lex).
   A Voice2Voice bot that must **speak** to the caller therefore requires the **Audio
   Connector** feature, not bare AudioHook transcription.

2. **Routing a call is not part of the AudioHook socket.** Audio Connector is a media
   fork driven by the Architect **Call Audio Connector** action, which streams audio
   to our endpoint and **pauses the flow** until the streaming session ends. Escalation
   (transfer to a queue/advisor) is a Genesys control-plane operation performed by the
   Architect flow and the Platform API after our server ends the streaming session, not
   something our media socket performs.

## Decision

Adopt the **Genesys Audio Connector** feature (bidirectional AudioHook) as the target
media plane for Genesys-fronted voice, and model the integration as **three distinct
planes** that must not be conflated:

1. **Media plane** — audio in/out between Genesys and the voice runtime, over the
   **Audio Connector** feature of AudioHook (`wss://`). The Architect **Call Audio
   Connector** action forks the call to our endpoint and pauses the flow; our runtime
   does STT -> backend -> TTS and streams bot audio back; barge-in and playback are
   protocol events.
2. **Control / routing plane** — call steering, transfer, queue and advisor routing are
   owned by **Genesys Architect + Platform API**. On escalation, our server ends the
   streaming session (with a disconnect reason / output variables); the Architect flow
   resumes and Genesys routes to the advisor queue. Our runtime never "transfers" the
   call itself.
3. **Context / handoff plane** — the escalation payload (ADR-0019/0020: reason, summary,
   compared periods, evidence, unresolved points, recommended next action) is returned
   through **Architect input/output variables** and/or **conversation/participant
   attributes** via the Platform API, and stays **owned by the Java backend**.

The Java backend remains the source of truth for conversation decisions, RAG, billing
reasoning, guardrails, escalation policy and memory (ADR-0001). Genesys stays the
contact-center system of record (ADR-0020). Genesys is one channel/contact-center
adapter behind the normalized channel envelope (ADR-0009); adopting it must not force a
rewrite of the backend conversation model.

### Audio Connector constraints to design against

These platform constraints (from the Audio Connector documentation) shape the spike and
the NFR budget and must be tracked, not discovered late:

- **Premium application**, and **at most 5 Audio Connector integrations per org**.
- **One bidirectional stream per session**, within the **IVR channel**.
- **Default maximum call duration is 15 minutes** (longer requires Genesys Customer
  Care) — the billing-explanation journey must fit or checkpoint within that window.
- Audio codecs are **PCMU (µ-law) / L16**: L16 maps to our PCM16 pipeline; PCMU
  requires transcoding to/from the Gradium raw-PCM16 expectation.
- **Barge-in, end-of-turn and playback are protocol-native events**
  (`barge-in`, `playback-started`/`playback-completed`, `BotTurnResponse`). Behind Audio
  Connector, the runtime's bespoke energy-based end-of-turn and amplitude-gated barge-in
  (ADR-0025, TASK-WEB-008) are partly **superseded by Genesys events** and must not be
  duplicated or fought; the runtime should consume the Genesys signals on that path.

## Consequences

- Backlog and ADRs use precise terms: "Audio Connector feature" for the V2V media path,
  "Bot Transcription Connector" only for listen-only analytics. "Bare AudioHook" is
  never presented as a bidirectional bot path.
- The future Genesys voice spike is scoped as an **Audio Connector server**
  (WebSocket handling JSON control frames + PCMU/L16 audio, playback + barge-in events)
  plus an **Architect flow** with the Call Audio Connector action, not a generic tap.
- Escalation design separates the decision + context (backend) from routing (Genesys
  Architect/API); the handoff payload contract (ADR-0019) is transported on Architect
  variables / conversation attributes, not on the media socket.
- Latency measurement for this path keeps the ADR-0020 full round trip
  (Genesys -> runtime -> STT -> backend -> TTS -> Genesys) and adds the 15-minute cap
  and codec transcoding as explicit budget items.
- The energy/amplitude barge-in and end-of-turn detectors remain the target only for the
  **direct WebRTC/web** path (ADR-0033); on the Genesys path they defer to protocol
  events. This split must be documented where those detectors live.

## Alternatives Considered

- **Use bare AudioHook (Bot Transcription Connector) for V2V**: rejected — it is
  listen-only and cannot play the bot's TTS back to the caller.
- **Let our runtime perform the transfer/routing over the media socket**: rejected —
  AudioHook has no call-control; routing belongs to Architect + Platform API.
- **Genesys-native voicebot (Dialogflow/Lex/Nuance) instead of our engine**: rejected —
  it would move conversation intelligence, RAG, billing reasoning and guardrails out of
  the Java backend, contradicting ADR-0001.
- **Keep "Audio Connector or AudioHook" as interchangeable (status quo wording)**:
  rejected — it hides the listen-only vs bidirectional distinction and under-scopes the
  integration.

## Related Documents

- `docs/architecture/adrs/ADR-0020-genesys-handoff-v1-full-audio-connector-optional.md`
- `docs/architecture/adrs/ADR-0019-escalation-rules-and-handoff-contract.md`
- `docs/architecture/adrs/ADR-0009-independent-channel-adapters-shared-java-backend.md`
- `docs/architecture/adrs/ADR-0001-java-backend-owns-conversation-domain.md`
- `docs/architecture/adrs/ADR-0025-barge-in-native-interruption.md`
- `docs/architecture/adrs/ADR-0033-webrtc-single-live-voice-transport.md`
- `docs/architecture/diagrams/target-v1-solution.drawio`
- `docs/architecture/reviews/genesys-audio-connector-adversarial-review-2026-08-07.md`
- Genesys: AudioHook introduction, AudioHook Protocol Reference, Audio Connector overview
