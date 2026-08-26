# ADR-0022: WebRTC Transport For The Streaming Voice Loop

## Status

Accepted (Sprint 6, TASK-WEB-007). **Refined by
[ADR-0046](ADR-0046-websocket-primary-live-voice-transport.md)** (2026-08-26): the WebRTC
transport described here remains valid *mechanically*, but is **demoted to an optional
same-subnet/dev live transport**. WebSocket (ADR-0043 → ADR-0040 Genesys Audio Connector) is
now the **primary V1 live transport** for external/pilot/Genesys audio. The TURN/STUN note in
this ADR's Consequences is the follow-up that ADR-0042 declined for the pilot.
**Further refined by [ADR-0047](ADR-0047-single-async-http-websocket-server-one-port.md)**
(2026-08-26): the "keep the stdlib `http.server`, no FastAPI" and "one asyncio loop *alongside*
a threaded HTTP server" constraints below are **reversed** in the ADR-0046 world — the runtime
unifies onto a single async HTTP+WebSocket server on one port (the stdlib server is now the
blocker, not the saver).

## Context

The Sprint 4/5 voice loop runs over HTTP: each turn uploads a whole audio buffer to
`POST /api/voice/turn`, and the Pipecat runtime spins a fresh event loop +
`PipelineTask`/`PipelineRunner` and `asyncio.run(...)` **per request** (finding
RF-012). This is fine for batch parity but blocks true streaming: there is no
persistent, bidirectional media channel, and no awaited pipeline for partial STT,
incremental TTS, VAD end-of-turn or barge-in to ride on.

ADR-0002 / DEC-005 already set **Pipecat + WebRTC** as the target voice path, with
the batch HTTP path kept as the fallback/comparison runtime (ADR-0016). TASK-WEB-007
opened with a spike (`docs/qa/webrtc-transport-spike.md`) to lock the transport API,
its dependency footprint and the single-loop model before building.

Key constraints discovered:

- Pipecat 1.5.0 ships `SmallWebRTCTransport`, but it **hard-imports** the optional
  WebRTC stack (`aiortc`, `av`, `cv2`) at class-import time — even an audio-only loop
  pulls the full `pipecat-ai[webrtc]` extra, including `opencv-python` (~90 MB) used
  only for `RawVideoTrack`.
- The bundled `SmallWebRTCRequestHandler` imports **FastAPI**; our runtime is a
  stdlib `http.server`.
- The runtime is a **threaded** stdlib server, but the media session needs a
  **single, persistent** asyncio loop that outlives individual HTTP requests.
- The Sprint 4/5 STT stage is **batch** (one whole-utterance frame per turn); WebRTC
  delivers continuous small audio frames.

## Decision

Add a WebRTC full-duplex runtime **alongside** the batch HTTP path (not replacing it).

1. **Transport:** use Pipecat `SmallWebRTCTransport` behind an **import guard**
   (`web_voice/webrtc_support.py`) so the base test suite runs without the heavy
   wheels. Depend on `pipecat-ai[webrtc]` (pinned `aiortc>=1.14,<2`,
   `opencv-python>=4.11,<5`; `av` transitively) — **accept `opencv-python` for now**
   rather than forking the transport; revisit `opencv-python-headless` for the
   deployment image (footprint only, no code change).
2. **Signaling without FastAPI:** reimplement the offer→answer handshake directly on
   `SmallWebRTCConnection` (`initialize` → `get_answer`) in
   `web_voice/webrtc_signaling.py`, exposed as `POST /api/voice/webrtc/offer` on the
   existing stdlib server. Non-trickle ICE (wait for gathering) for the first cut.
3. **Single long-lived loop:** run one persistent asyncio loop on a daemon thread
   (`web_voice/async_loop.py`); threaded HTTP handlers submit coroutines to it. The
   `PipelineRunner` is awaited **once** per call — closes RF-012.
4. **Reuse, don't fork:** the WebRTC session reuses the Sprint 4/5 STT/answer/TTS
   `FrameProcessor`s and the Sprint 5 `BackendAnswerPort` unchanged, on one
   `ChannelEnvelope` + `TelemetryRecorder` per call → the US-036 slices for every turn
   in a call share one correlation id.
5. **Interim utterance segmentation:** `web_voice/utterance_aggregator.py` turns
   continuous frames into whole-utterance frames using the existing energy-based
   end-of-turn thresholds (TASK-STT-009), explicitly a drop-in until streaming STT
   (TASK-STT-010) and Silero VAD (TASK-STT-012) land.

## Consequences

**Positive**

- True full-duplex media on one awaited loop; the foundation streaming STT/TTS/VAD
  and barge-in (TASK-WEB-008) build on.
- Batch endpoints keep their exact contract (ADR-0016 fallback preserved).
- No FastAPI/uvicorn added; signaling stays on the stdlib server.
- Base suite stays light — WebRTC deps are guarded and optional for non-WebRTC runs.

**Negative / risks**

- Dependency footprint grows (`aiortc`, `av`, `opencv-python`). `av` + `opencv` ship
  duplicate `libavdevice` dylibs → a benign macOS `objc[...]` warning; track
  `opencv-python-headless` for the image.
- Installs require the corporate VPN/mirror (the index is internal). Python 3.14
  wheels are confirmed present today (aiortc 1.15.0, av 17.1.0, opencv 4.13.0.92).
- **TURN/STUN:** non-trickle host candidates suffice for localhost/LAN; symmetric or
  corporate NAT needs STUN + a **TURN** relay (e.g. coturn), passed via `--stun`.
  Not provisioned yet — infra follow-up before any non-local pilot.
- The energy aggregator is coarse (no echo cancellation → use headphones); replaced
  by the VAD ticket.

**Neutral**

- Provider agnosticism is unchanged: STT/TTS stay behind their ports; only the
  transport is new.

## Alternatives considered

- **Bundled `SmallWebRTCRequestHandler` (+ FastAPI):** rejected — drags a second web
  framework into a stdlib server for a two-endpoint handshake.
- **`asyncio.run` per turn over WebRTC:** rejected — reintroduces RF-012 and cannot
  support streaming/barge-in.
- **Realtime provider API (single vendor):** rejected by ADR-0012 (modular pipeline
  over a monolithic realtime API keeps STT/LLM/TTS independently replaceable).
- **`opencv-python-headless` now:** deferred — needs verification that it satisfies
  the transport's `import cv2`; a footprint optimization, not a blocker.
