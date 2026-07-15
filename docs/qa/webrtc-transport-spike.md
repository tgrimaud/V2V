# WebRTC Transport Contract (Sprint 6 / TASK-WEB-007, spike)

Findings from the opening spike for the streaming voice loop. Same discipline as
`pipecat-batch-contract.md` and `gradium-tts-contract.md`: verify the real API and
its dependency footprint **before** wiring the runtime. This note locks the
`SmallWebRTCTransport` API, the single long-lived event-loop model (closes RF-012),
the signaling handshake, the browser client, version pins, TURN/STUN needs and the
environment risks discovered while probing.

- **Framework:** `pipecat-ai 1.5.0` (already pinned `>=1.5,<2`), Python 3.14.2.
- **Transport module:** `pipecat.transports.smallwebrtc` (`transport.py`,
  `connection.py`, `request_handler.py`). Present in the base wheel; the classes
  import the WebRTC deps lazily and raise a clear `ImportError` if they are missing.

## Dependency footprint (governance decision — needs ADR)

`SmallWebRTCTransport` **hard-imports** the optional WebRTC stack at class-import
time (`transport.py` top-level `try: import cv2; from aiortc import ...; from av import ...`).
So even an **audio-only** loop pulls the full extra:

| Dep | Constraint (from `pipecat-ai[webrtc]`) | Purpose | Notes |
|---|---|---|---|
| `aiortc` | `>=1.14.0,<2` | WebRTC peer connection, SRTP, ICE, DTLS | core |
| `av` (PyAV) | (transitive of aiortc) | audio/video frame codecs, resampler | core |
| `opencv-python` | `>=4.11.0.86,<5` | `RawVideoTrack` / `cv2` | **video only, still required to import** |
| `onnxruntime` | `~=1.24.3` (already a base dep, **installed 1.24.4**) | Silero VAD inference | needed by TASK-STT-012 |

**Install command:** `pip install "pipecat-ai[webrtc]"` (adds `aiortc`, `opencv-python`;
`av` comes transitively). VAD: `pip install "pipecat-ai[silero]"`.

**Footprint concern to record in the ADR:** `opencv-python` (~90 MB) is dragged in
only for `cv2`/`RawVideoTrack` although V1 is audio-only. Two options for the ADR:
1. Accept `pipecat-ai[webrtc]` as-is (simplest, supported path).
2. Vendor a slimmer set (`aiortc` + `av` + `opencv-python-headless`) and confirm the
   headless build satisfies the `import cv2` at `transport.py:48`.
Recommendation: **option 1** for the spike/first cut; revisit headless in the ADR if
image size matters for the deployment target.

## ⚠️ Environment risk found during the spike (blocks a live handshake here)

The live in-process offer/answer smoke could **not** run in this session:

- The workstation's active pip index is the corporate Artifactory
  (`jfrog-artifactory.steelhome.internal`), which is **unresolvable offline / off-VPN**
  (`NameResolutionError`). `aiortc`/`av`/`opencv-python` are therefore not installable
  in the current shell.
- **Python 3.14 wheel availability** for `aiortc`, `av`, `opencv-python` must be
  verified on a networked machine before committing the pins — these are C-extension
  wheels and 3.14 is recent. If a wheel is missing, either fall back to Python 3.12
  for the voice-agent venv or wait for the wheel.

**Consequence for this ticket:** the offline-validatable parts (single-loop driver
seam, fake-transport tests, teardown) are delivered and green now; the **live WebRTC
round trip** (real ICE, browser mic/speaker) is gated on installing
`pipecat-ai[webrtc]` in a network-enabled env and is captured as the remaining
Chrome DevTools MCP evidence step in the ticket.

## Transport API (locked from source)

### `SmallWebRTCTransport`
`pipecat.transports.smallwebrtc.transport.SmallWebRTCTransport`

```python
transport = SmallWebRTCTransport(
    webrtc_connection,             # SmallWebRTCConnection
    params=TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_in_sample_rate=16000,   # match STT (Gradium pcm_16000)
        audio_out_sample_rate=16000,  # match TTS output
        # vad_analyzer=SileroVADAnalyzer(...)  # added in TASK-STT-012
    ),
)
input_processor  = transport.input()   # BaseInputTransport  -> emits InputAudioRawFrame
output_processor = transport.output()  # BaseOutputTransport -> consumes TTSAudioRawFrame
```

- `BaseInputTransport` emits `InputAudioRawFrame` (the same frame the batch STT stage
  already consumes → the STT/answer/TTS processors are reused unchanged).
- `BaseOutputTransport` consumes `TTSAudioRawFrame` and writes to the peer's audio
  track (the batch `_AudioCaptureSink` is replaced by `transport.output()`).
- `TransportParams` audio fields confirmed: `audio_in_enabled`, `audio_out_enabled`,
  `audio_in_sample_rate`, `audio_out_sample_rate`, `vad_analyzer` (default off).

### `SmallWebRTCConnection`
`pipecat.transports.smallwebrtc.connection.SmallWebRTCConnection`

```python
conn = SmallWebRTCConnection(ice_servers=[...], connection_timeout_secs=60)
await conn.initialize(sdp=offer_sdp, type="offer")   # new peer
# or, reuse:
await conn.renegotiate(sdp=offer_sdp, type="offer", restart_pc=False)
await conn.connect()
await conn.disconnect()
await conn.add_ice_candidate(candidate)              # trickle ICE
# events: "connecting","connected","disconnected","closed","failed","new",
#         "track-started","track-ended","app-message"
conn.event_handler("closed")(async_handler)
```

`ice_servers` accepts `list[str]` (URLs) or `list[IceServer]`.

## Signaling handshake (HTTP)

`pipecat.transports.smallwebrtc.request_handler.SmallWebRTCRequestHandler` wraps the
whole offer→answer + ICE lifecycle, so the stdlib HTTP server only needs two routes.

```python
handler = SmallWebRTCRequestHandler(ice_servers=[...])   # ConnectionMode single/multiple

# POST /api/voice/webrtc/offer   (browser sends SDP offer)
answer = await handler.handle_web_request(
    SmallWebRTCRequest.from_dict(body),  # {sdp, type, pc_id?, restart_pc?, requestData?}
    webrtc_connection_callback,          # builds transport+pipeline, starts the loop
)
# -> {"sdp": <answer>, "type": "answer", "pc_id": <id>}   (JSON)

# PATCH /api/voice/webrtc/ice     (trickle ICE candidates)
await handler.handle_patch_request(
    SmallWebRTCPatchRequest(pc_id=..., candidates=[IceCandidate(...)])
)
```

- `SmallWebRTCRequest.from_dict` accepts both `requestData` (camelCase) and
  `request_data` — the browser can send camelCase.
- `handle_web_request` reuses the connection when `pc_id` matches (renegotiate),
  otherwise creates one, invokes the callback (where we build the transport + pipeline
  and start the single-loop runner), and returns the answer dict.
- **Signaling stays plain HTTP** on the existing stdlib server; only the media plane
  is WebRTC. No new web framework needed.

### STUN / TURN

- **STUN** (`stun:stun.l.google.com:19302` or a self-hosted one) is enough for most
  NATs to discover the public reflexive candidate.
- **TURN** is required for symmetric/restrictive NATs and many corporate networks
  (media relayed through the TURN server). Pilot on a corporate LAN → **budget a TURN
  server** (e.g. coturn). ICE servers are passed once to
  `SmallWebRTCRequestHandler(ice_servers=...)`. Track as a Sprint 6 infra note.

## Single long-lived event loop (closes RF-012)

Batch today (`voice_pipeline/pipeline.py::_drive`) spins a fresh
`PipelineRunner`/`PipelineTask` and `asyncio.run(...)` **per turn** (RF-012). The
streaming path builds the pipeline **once** and awaits the runner **once** for the
whole session:

```python
pipeline = Pipeline([
    transport.input(),   # InputAudioRawFrame in
    stt,                 # SttFrameProcessor      (reused)
    answer,              # AnswerProcessor        (reused, BackendAnswerPort)
    tts,                 # TtsFrameProcessor      (reused)
    transport.output(),  # TTSAudioRawFrame out
])
task = PipelineTask(                # same kwargs as the batch path
    pipeline, params=PipelineParams(),
    enable_rtvi=False, enable_turn_tracking=False,
    cancel_on_idle_timeout=False, check_dangling_tasks=False,
)
runner = PipelineRunner(handle_sigint=False)   # off-main-thread safe
await runner.run(task)          # awaited ONCE, lives for the whole call
# teardown: await task.cancel() on transport drop / session end
```

- No `EndFrame` is queued up front (the session is open-ended); teardown is driven by
  the transport's `disconnected`/`closed` events → `task.cancel()`.
- **Interruptions/barge-in are frame-driven** in 1.5.0 (a VAD emits interruption
  frames), **not** a `PipelineParams` flag — that flag does not exist in 1.5.0
  (`PipelineParams` fields: `audio_in/out_sample_rate`, `enable_metrics`,
  `enable_heartbeats`, ...). Barge-in wiring is TASK-WEB-008 (needs the VAD from
  TASK-STT-012).
- The STT/answer/TTS `FrameProcessor`s from Sprint 4/5 are reused **unchanged**
  (~80% reuse, matching the Sprint 4 retro), so the conversation contract, degraded
  fallback and US-036 telemetry all carry over.

## Browser client

- Pipecat JS: `@pipecat-ai/client-js` + `@pipecat-ai/small-webrtc-transport`
  (mic capture + speaker playback, posts the SDP offer to `/api/voice/webrtc/offer`,
  PATCHes ICE to `/api/voice/webrtc/ice`).
- The existing batch page (whole-buffer `POST /api/voice/turn`) is **kept** as the
  fallback/comparison path (ADR-0016). The WebRTC page is additive.
- Minimum browser flow: `getUserMedia({audio})` → `RTCPeerConnection` → add mic track
  → `createOffer` → POST offer → `setRemoteDescription(answer)` → play remote track.

## Frame types over the streaming path (unchanged from batch)

| Stage | In | Out |
|---|---|---|
| `transport.input()` | (WebRTC audio) | `InputAudioRawFrame` |
| STT | `InputAudioRawFrame` | `TranscriptionFrame` |
| answer | `TranscriptionFrame` | `TextFrame` |
| TTS | `TextFrame` | `TTSAudioRawFrame` |
| `transport.output()` | `TTSAudioRawFrame` | (WebRTC audio) |

Whole-utterance frames until streaming STT/TTS/VAD land (TASK-STT-010 /
TASK-WEB-004 / TASK-STT-012) — this ticket is transport-only.

## Version pins to add (implementation step, in a networked env)

```
# voice-agent/requirements.txt — streaming voice loop (TASK-WEB-007), optional extra
aiortc>=1.14,<2          # WebRTC media plane (from pipecat-ai[webrtc])
opencv-python>=4.11,<5   # required by SmallWebRTCTransport import (cv2/RawVideoTrack)
# av (PyAV) comes transitively via aiortc
# onnxruntime already present (Silero VAD, TASK-STT-012)
```

Keep the transport behind an **import guard** so the base test suite (STT/TTS/backend
bridge) still runs without the heavy WebRTC wheels — see
`voice-agent/web_voice/webrtc_support.py` and `scripts/webrtc_spike.py`.

## What the spike delivered (offline) vs. what remains (networked)

**Delivered + green now (no aiortc):**
- Single-loop driver seam that awaits the runner **once** and reuses STT/answer/TTS.
- Fake in-memory transport + developer tests: one-loop drive and graceful teardown on
  transport drop (no real ICE).
- Import guard so the suite stays green without the WebRTC extra.
- `scripts/webrtc_spike.py`: prints the resolved API + missing-dep guidance; when
  `aiortc` is present it runs an in-process offer/answer smoke.

**Remaining (needs `pip install "pipecat-ai[webrtc]"` on a networked machine):**
- Signaling routes on the stdlib server (`/api/voice/webrtc/offer` + `/ice`).
- Pipecat JS browser page.
- Live WebRTC round trip + Chrome DevTools MCP evidence (audio in/out + correlation
  id) and US-036 slices over the WebRTC path.
- ADR for the WebRTC dependency footprint + TURN/STUN infra.
