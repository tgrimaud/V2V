# ADR-0043: Interim WebSocket Audio Transport For External Browser Voice (Genesys-Ready)

## Status

Accepted (2026-08-15)

> Refines **ADR-0033** (WebRTC as the single live web voice transport) and implements
> Decision point 4 of **ADR-0042** (no TURN for the pilot; a WebSocket audio path is the
> chosen external-reach lever). Deliberately designed as the reusable foundation for
> **ADR-0040** (Genesys Audio Connector, Sprint 13). Delivered by **Sprint 12**
> (`sprint-12-external-voice-websocket.md`, TASK-WEB-026…031).

## Context

ADR-0042 established that the pilot provisions **no STUN/TURN**: external-browser WebRTC
**media** (SRTP over UDP, peer-to-peer) has no path off the `192.168.0.0/24` subnet, so
signalling succeeds while audio stays silent. Its Decision point 4 selected a **WebSocket
audio transport** (client→server TCP/TLS through the existing HAProxy edge) as the
external-reach path, preferred over standing up a throwaway TURN relay.

This appears to contradict **ADR-0033**, which *rejected* a browser-facing WebSocket
voice transport. That rejection was made for a **different problem**: on the same subnet,
WebRTC already works, and a WebSocket duplicate there only drops native
echo-cancellation / noise-suppression / jitter / Opus with **no latency or quality gain**
(and would reintroduce the ADR-0025 barge-in self-interruption). For **external reach**
the trade-off inverts: the choice is not "WebRTC vs WebSocket on an equal path" but
"a lower-quality-but-working TCP audio path" vs **no audio at all** until Genesys.

Two facts make the WebSocket path high-value beyond the pilot:

1. **Same transport shape as Genesys.** ADR-0040 shows Genesys **Audio Connector /
   AudioHook** is *"WebSocket over TLS, JSON control frames + binary audio"* — exactly the
   transport we need for the browser interim path. A well-factored WebSocket transport is
   therefore reusable capital for the Sprint 13 Genesys work, not throwaway code.
2. **The conversation core is already transport-agnostic.** `StreamingVoiceSession`
   (STT → backend RAG/LLM/guardrails → TTS) is driven today by a `SmallWebRTCTransport`;
   the session logic does not depend on WebRTC. The seam already exists — it is currently
   buried inside `WebRtcSignalingService`.

## Decision

1. **Add a browser WebSocket audio transport as the external-reach interim live path.**
   WebRTC (ADR-0033) **remains the same-subnet / dev live transport**. This ADR *refines*
   (does not supersede) ADR-0033: a browser WebSocket voice transport is no longer
   categorically rejected — it is rejected **as a same-subnet duplicate** and **accepted
   as the external-reach path** where WebRTC media cannot reach without TURN.

2. **Frame contract modelled on AudioHook.** One long-lived `wss://` connection carrying
   **JSON control frames + binary PCM16/16 kHz audio frames**, so the socket-handling and
   frame-demultiplexing layer is directly reusable by the Genesys Audio Connector adapter.
   We adopt the *shape* (JSON control + binary audio), **not** the exact AudioHook schema.

3. **Transport-agnostic session factory (the capitalisation move).** Extract the
   session-building logic out of `WebRtcSignalingService` into a shared factory. WebRTC,
   the WebSocket browser path, and the future Genesys Audio Connector become **thin
   transport adapters** over one `StreamingVoiceSession` core. The internal audio boundary
   stays **PCM16 / 16 kHz**; codec and sample-rate conversion live **inside each transport
   adapter** (Genesys PCMU/L16-8 kHz transcoding is deferred to Sprint 13 and must never
   leak a sample-rate assumption into the shared core).

4. **Pluggable control-signal seam.** Barge-in, end-of-turn, playback-started/completed
   and call-end become an internal event vocabulary with a **pluggable source**: the
   energy/amplitude detectors (ADR-0025) feed it on the WebSocket and WebRTC paths; the
   Genesys **protocol events** (`barge-in`, `playback-started`/`playback-completed`,
   `BotTurnResponse`) feed it on the Genesys path (ADR-0040). Internal event names mirror
   the Genesys semantics for a 1:1 mapping later.

5. **Reuse the existing cross-cutting machinery unchanged**: one correlation id per call,
   per-slice OpenTelemetry spans (mandatory), and the session-capacity ceiling +
   backpressure (as WebRTC, TASK-WEB-024).

6. **Interim, not a third permanent transport.** The WebSocket path is superseded by
   Genesys Audio Connector (ADR-0040) for the target contact-centre path. ADR-0042 stands:
   **no TURN** is provisioned.

## Spike Outcome (2026-08-24, TASK-WEB-026)

The socle spike **confirms this decision without changing it**. Concrete findings:

- pipecat 1.5.0 ships `SingleClientWebsocketServerTransport`
  (`pipecat.transports.websocket.server`) built on `websockets.asyncio.server.serve`,
  which pulls **no FastAPI** — FastAPI is isolated in the sibling `websocket.fastapi`
  module we never import. `websockets` is already a runtime dependency (Gradium TTS
  client), so **no new dependency** is added. The hand-rolled `wss`-on-stdlib option is
  therefore unnecessary; the pipecat transport is the lower-risk, higher-reuse socle.
- The frame contract is carried by the pipecat **serializer seam**
  (`WebSocketAudioSerializer`, `web_voice/websocket_framing.py`): binary → PCM16/16 kHz
  `InputAudioRawFrame`, text → JSON control. The control vocabulary mirrors the Genesys
  AudioHook semantics (the reference `pipecat.serializers.genesys.GenesysAudioHookSerializer`
  has the same JSON-control + binary-audio shape), so Sprint 13 reuses the demux layer.
- The transport is driven on the shared persistent asyncio loop
  (`web_voice/async_loop.py`), like the WebRTC signaling path. HAProxy `wss` upgrade
  routing to its listener is TASK-INFRA-010; wiring it into `StreamingVoiceSession` via
  the transport-agnostic session factory is TASK-WEB-027 (where the canonical per-slice
  OpenTelemetry spans — channel ingress → … → egress — are emitted by the existing
  session/ingress/egress probes). This socle ticket adds the library layer only and runs
  no live turn, so it introduces no new runtime span in isolation.

## Consequences

- **Weaker echo control than WebRTC.** The WebSocket path loses WebRTC's
  transport-integrated AEC reference; browser `getUserMedia` echo cancellation is less
  effective without a WebRTC render sink, so barge-in on this path inherits the ADR-0025
  point-7 mitigation (raised amplitude threshold + N-frame sustained-onset confirmation,
  env-tunable) and may be tuned more conservatively. Headphones remain the reliable setup.
- **TCP for real-time media.** Head-of-line blocking and no native jitter/loss handling:
  acceptable on the clean pilot network, worse on lossy/mobile links — a core reason it
  stays interim rather than replacing WebRTC.
- **Genesys reuse is the payoff.** Sprint 13's Audio Connector server becomes a **transport
  adapter** (AudioHook JSON schema + PCMU/L16 transcoding + protocol-event mapping) over
  the same session factory and control-signal seam; the socket/demux, session core,
  telemetry, correlation and capacity layers are reused, not rebuilt.
- **Do not pre-build the AudioHook protocol.** ADR-0040 is an unbuilt spike (TASK-WEB-025,
  gated by OQ-006); generalising the framing to an unseen schema now risks the wrong
  abstraction (YAGNI). Sprint 12 builds only the browser protocol behind reusable seams.
- **Refactor blast radius.** Extracting the session factory touches `WebRtcSignalingService`;
  it must keep WebRTC behaviour byte-for-byte, covered by the existing WebRTC tests.
- **Observability mandate met.** The WebSocket path emits the same canonical per-slice
  spans (channel ingress → end-of-turn → STT → backend → TTS first audio → channel egress)
  under the call correlation id.

## Alternatives Considered

- **Provision STUN/TURN (coturn) for public WebRTC audio:** rejected (ADR-0042) — real,
  security-heavy infra (public IP/DNS, UDP relay range, credential rotation) for a path
  the target Genesys Audio Connector replaces; the browser client would also need
  server-provided `iceServers` wiring it does not have today.
- **Keep ADR-0033's blanket WebSocket rejection and offer no external path before
  Genesys:** rejected — leaves every external user with no voice until Sprint 13, and a
  concrete pre-Genesys external-demo need was confirmed (2026-08-15).
- **Build the Genesys AudioHook protocol directly now (skip the browser interim):**
  rejected — ADR-0040 is a gated spike; committing to an unseen schema/auth/codec now is
  premature. Capitalise on the transport-agnostic seams, not on a guessed protocol.
- **Keep WebSocket as a third *permanent* transport alongside WebRTC and Genesys:**
  rejected — three live transports is a lasting maintenance/QA burden; WebSocket is scoped
  as interim and retired once Genesys Audio Connector is live.

## Related Documents

- `docs/architecture/adrs/ADR-0033-webrtc-single-live-voice-transport.md`
- `docs/architecture/adrs/ADR-0042-no-turn-for-pilot-genesys-audio-connector-external-media.md`
- `docs/architecture/adrs/ADR-0040-genesys-audio-connector-v2v-media-plane.md`
- `docs/architecture/adrs/ADR-0025-barge-in-native-interruption.md`
- `docs/architecture/adrs/ADR-0022-webrtc-transport-for-streaming-voice-loop.md`
- `docs/architecture/adrs/ADR-0024-streaming-tts-incremental-playback.md`
- `docs/architecture/adrs/ADR-0001-java-backend-owns-conversation-domain.md`
- `product-backlog/sprints/sprint-12-external-voice-websocket.md`
- `product-backlog/tasks/web-voice-tasks.md` (TASK-WEB-026…031)
