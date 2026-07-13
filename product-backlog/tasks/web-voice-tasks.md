# Web Voice Journey Technical Tasks

Delivery slices for **US-019 - Ask From A Web Voice Chat**. US-019 is a full
Voice2Voice journey (voice in, voice out) and is too large for a single slice, so
it is decomposed into three tasks. US-019 stays `In progress` until all three are
delivered and the user validates the end-to-end web voice loop.

The slices follow the `US-003` channel/identity boundary
(`docs/architecture/channel-identity-boundary.md`): the web channel + voice
runtime own audio capture, transport and STT/TTS provider calls; the Java backend
owns conversation intelligence.

| Slice | Task | Half | Depends on |
|---|---|---|---|
| STT ingress (voice in) | TASK-WEB-001 | STT | GradiumSttProvider (TASK-STT-008) |
| Voice response (voice out) | TASK-WEB-002 | TTS | TASK-WEB-001 |
| Backend/LLM orchestration | TASK-WEB-003 | middle | TASK-WEB-001, backend availability |

---

## TASK-WEB-001 - Capture Web Voice And Transcribe Through Gradium STT

**Parent:** EPIC-006
**Related story:** US-019 (STT half)
**Related finding:** RF-002 (TASK-STT-003) - replaces the `path.exists()` channel
ingress analog with a real web ingress
**Related decision:** DEC-005 / DEC-007 (voice runtime owns media orchestration)
**Classification:** V1 core
**Status:** In progress
**Priority:** High
**Branch:** `us/US-019-web-voice-chat`

### Objective

Deliver the first real web voice input boundary: a browser page captures customer
microphone audio, sends it to the voice runtime, the runtime transcribes it with
the existing `GradiumSttProvider`, and the page displays the transcript. No
backend reasoning, LLM or TTS in this slice.

This is the STT half of US-019 and turns the STT validation scaffold into a live
web ingress path.

### Scope

- Minimal web page (mic capture + record/stop + transcript display).
- Browser audio capture converted to the Gradium input contract
  (mono 16 kHz PCM16) via the Web Audio API / AudioWorklet, not a container
  format the provider cannot read.
- A thin voice-runtime ingress endpoint that accepts the captured audio, builds a
  minimal channel envelope (`channel=web_voice`, `conversation_id`,
  `external_session_id`, `correlation_id`), and calls the STT provider through the
  existing `SttProvider` protocol (`--provider gradium`, fixture fallback for
  offline dev).
- Reuse `GradiumSttProvider`, `sanitization.py` error codes and the STT
  telemetry spans. Do not fork the provider.
- Real channel-ingress OpenTelemetry span (received audio -> STT -> transcript)
  replacing the scaffold `path.exists()` analog; correlation id follows the turn.
- Safe failure surfaces (auth, credits, timeout, unreachable, no-speech) render a
  user-visible non-invented message; never fabricate a transcript.

### Out Of Scope

- Voice response / TTS (TASK-WEB-002).
- Backend RAG/LLM answer generation (TASK-WEB-003).
- Identity confidence model (governed by OQ-001).
- Barge-in / interruption (US-021).

### Acceptance Criteria

```gherkin
Scenario: Web voice input is transcribed and shown
  Given the customer opens the web voice page
  When the customer records a spoken question and stops
  Then the captured audio is transcribed by the Gradium STT provider
  And the transcript is displayed on the page
  And the STT slice latency and outcome are observable via OpenTelemetry
```

```gherkin
Scenario: Web voice STT failure stays safe and observable
  Given the STT provider fails or the audio has no usable speech
  When the ingress processes the turn
  Then no transcript is invented
  And a sanitized failure message is shown to the customer
  And a stable error_code and correlation id are recorded without leaking secrets
```

### Required Evidence

- Developer tests for the ingress endpoint (fake STT transport, no live call) and
  for the browser->PCM16 conversion boundary.
- Chrome DevTools MCP notes for the web UI (record, transcript render, failure
  render) plus time-to-transcript measurement.
- Behave scenario(s) for the web voice ingress outcome.
- OpenTelemetry evidence: real ingress span + STT span with correlation id.
- Confirmation no API key, raw audio or filesystem path is logged.

### Delivery Evidence (implementation slice)

- `voice-agent/web_voice/`: `envelope.py` (minimal `ChannelEnvelope`,
  `channel=web_voice` + correlation id), `ingress.py` (`WebVoiceIngress` adds the
  real `web.voice.ingress` span with received audio byte count, then delegates to
  the existing `SttValidationRunner` so STT telemetry/sanitization/outcome are
  unchanged; temp audio file is always cleaned up), `server.py` (stdlib
  `http.server`, serves the mic page + `POST /api/voice/stt`, runtime provider
  selection, no new dependency).
- `voice-agent/web_voice/static/`: `index.html`, `app.js` (Web Audio API +
  AudioWorklet capture, downsample to 16 kHz, Float32->PCM16, POST raw bytes,
  render transcript / sanitized failure / latency), `pcm-worklet.js`.
- Reuses `GradiumSttProvider`, `sanitization.py` and STT spans; provider not
  forked.
- Tests: `tests/test_web_voice_ingress.py` (11 tests — ingress success/failure,
  real-byte ingress span, correlation-id propagation, path never leaked, temp
  cleanup, envelope parsing, live-socket server routing 200/502/404 + index).
  Full suite green (39 tests). `features/web_voice.feature` (2 scenarios) passes
  via the same code path. Behave total: 2 features / 7 scenarios / 32 steps.
- **Perf bug fixed:** `HTTPServer.server_bind()` calls `socket.getfqdn()`, which
  hung ~35 s on slow reverse DNS (affecting real server startup, not just tests).
  `WebVoiceHTTPServer` skips the FQDN lookup; the suite dropped from ~37 s to ~2 s.
- **Smoke test:** `python3 -m web_voice.server --provider fixture` serves `GET /`
  (200) and `POST /api/voice/stt?correlation_id=smoke-1` returns sanitized JSON
  (`error_reason` shows `<redacted-path>`, no path leak) with a `web.voice.ingress`
  span logged.

### QA Evidence (Chrome DevTools MCP, 2026-07-10)

- `docs/qa/web-voice-qa-report.md` (+ `docs/qa/assets/web-voice-*.png`). Live
  Gradium engine, real browser at `http://localhost:8090/`.
- **Success end to end:** a pre-recorded 16 kHz PCM utterance driven through the
  page's real `sendAudio()` → `POST /api/voice/stt` (200, `audio/pcm`, 107 956 B) →
  Gradium → transcript *"Bonjour, pourquoi ma facture augmentée ce mois-ci?"*
  rendered; time-to-transcript **2307 ms** (STT slice 2296 ms).
- **Safe failure:** silence → *"no speech"*, error styling, no invented transcript.
- **Observability:** real `web.voice.ingress` span (`audio_bytes: 107956`,
  `channel: web_voice`) + correlation id; server log has zero `gsk_` (no key leak).
- **Console:** clean after fixing a cosmetic `favicon.ico` 404 (server now 204,
  locked by a test). Suite: 13 web-voice unittests + 2 Behave scenarios green.
- **Human mic session (2026-07-10):** real microphone → `app.js` capture +
  48 kHz→16 kHz downsampling → 137 898 B of 16 kHz PCM → `POST /api/voice/stt`
  (200) → Gradium → transcript *"Bonjour. J'ai un problème avec ma facture."*
  rendered (success). Console clean, `web.voice.ingress` span `audio_bytes=137898`,
  no key leak. Closes the mic/downsampling gap; `web-voice-mic-session.png`.

### Remaining Before Done

- User validation of the branch before any merge.

---

## TASK-WEB-002 - Speak The Bot Response On The Web Page (TTS Half)

**Parent:** EPIC-006
**Related story:** US-019 (TTS half), US-036 (feeds the `tts_first_audio` and `channel_egress` slices)
**Related decision:** DEC-005 / DEC-007
**Classification:** V1 core
**Status:** In progress (Sprint 3, started 2026-07-13)
**Priority:** High
**Branch:** `task/TASK-WEB-002-tts-voice-out` (from `feat/sprint-3-tts-voice-out`)

### Objective

Complete the voice-out half of US-019: turn a response text into speech through a
Gradium TTS provider and play it back in the web page, symmetric to the STT
provider path.

### Scope

- New TTS provider behind a provider protocol (mirrors `SttProvider`), Gradium as
  the first implementation, replaceable and configurable.
- Web page plays the synthesized audio for the returned response.
- TTS-slice OpenTelemetry span (text -> audio -> playback start) with correlation
  id, plus safe failure handling (no silent failure, no secret leak).
- Register the emitted span name(s) in `stt_validation/pipeline_timing.py`
  (`_SLICE_SPAN_NAMES[TTS_FIRST_AUDIO]` and `[CHANNEL_EGRESS]`) so US-036 measures
  these slices instead of reporting them as gaps.
- Fixture/offline mode so QA can validate without live credentials.

### Out Of Scope

- Answer generation (TASK-WEB-003); this slice may speak a stubbed/echo text
  until the backend loop exists.
- Barge-in (US-021), quick acknowledgement (US-020).

### Acceptance Criteria

```gherkin
Scenario: The bot response is spoken on the web page
  Given a response text is available for the customer turn
  When the web voice page receives the response
  Then the text is synthesized by the TTS provider
  And the audio is played back to the customer
  And the TTS slice latency and outcome are observable via OpenTelemetry
```

### Required Evidence

- Developer tests for the TTS provider with a fake transport.
- Chrome DevTools MCP notes (playback, failure render) + time-to-first-audio.
- Behave scenario(s) for the TTS outcome.
- OpenTelemetry evidence for the TTS slice.

### Subtasks (Sprint 3 execution)

Each subtask is one commit (`implement -> test -> commit`), independently testable.
STT/TTS separation is a hard contract: `tts_synthesis/` must not import
`stt_validation/` and vice versa. Shared cross-cutting utilities now live in the
neutral `voice_common/` package (`telemetry`, `sanitization`) which both halves
import; `ChannelEnvelope` and the read-only `pipeline_timing` slice registry
remain the only other shared surfaces.

- [x] **ST-1 — Gradium TTS spike (lock the contract).** Done 2026-07-13 — contract verified live; see `docs/qa/gradium-tts-contract.md`. Finding: `voice_id=default` invalid, real catalog id required.
  - Files: `voice-agent/scripts/gradium_tts_spike.py` (disposable), findings note in `docs/qa/` or `docs/observability/`.
  - Do: load `.env`, open `wss://api.gradium.ai/api/speech/tts`, send `setup` (`voice_id` from `GRADIUM_VOICE_ID`, `output_format: pcm_16000`), send `text` + `end_of_stream`, collect `audio` chunks, save a `.wav` to listen.
  - AC: documented message shapes, base64 chunk format, `ready`/`end_of_stream` handshake, first-chunk latency, and whether `GRADIUM_VOICE_ID=default` is valid.
  - Evidence: live run note (real key). Add `websockets` to `voice-agent/requirements.txt`.

- [x] **ST-2 — TTS models + provider protocol + fixture provider.** Done 2026-07-13 — `tts_synthesis/` created (no import of `stt_validation`); 6 tests green; adversarial review 93/100 (added `to_dict` no-leak test).
  - Files: `voice-agent/tts_synthesis/__init__.py`, `models.py`, `providers.py`.
  - Content: `TtsOutcome{SUCCESS,FAILED,UNAVAILABLE}`, `SynthesisResult(audio, provider, outcome, duration_ms, tts_request_ms, correlation_id, audio_format, error_code, error_reason)`; `TtsProvider` Protocol (`name`, `synthesize(text)->bytes`); `EmptyTextError` (-> UNAVAILABLE); `FixtureTtsProvider` returning a committed reference clip keyed by text.
  - AC: fixture returns non-empty PCM for a known text; empty/whitespace text raises `EmptyTextError`.
  - Test: `tests/test_tts_providers.py` (no network).

- [x] **ST-3 — Gradium TTS provider + factory.** Done 2026-07-13 — WebSocket provider (injectable transport, key only in `x-api-key` header, safe error mapping incl. handshake-level rejection) + `build_provider` factory normalizing `voice_id=default` → Elise FR (`b35yykvVppLXyw_l`). 16 tests green; adversarial review 95/100.
  - Files: `voice-agent/tts_synthesis/gradium_tts_provider.py`, `provider_factory.py`.
  - Content: `GradiumTtsProvider(api_key, *, voice_id, output_format, url, timeout_s, transport=None)` with an injectable WS transport (default = thin `websockets` async wrapper called synchronously); `build_tts_provider(name)` reads `GRADIUM_API_KEY` + `GRADIUM_VOICE_ID` (+ output format).
  - AC: with a fake transport, returns concatenated PCM bytes; HTTP/WS/credit errors map to a sanitized failure; API key never appears in any exception message.
  - Test: `tests/test_gradium_tts_provider.py` (fake transport, success + error + key-never-leaks).

- [x] **ST-4 — Synthesis runner + telemetry + pipeline slices.** Done 2026-07-13 — extracted shared `telemetry`/`sanitization` into neutral `voice_common/` (STT keeps its public API via re-export shims + its fixture reason codes); `TtsSynthesisRunner` mirrors the STT runner (3 outcomes, `voice.tts.first_audio` span, `tts.request.duration_ms` metric, `sanitize_error(domain="tts")`). Registered TTS_FIRST_AUDIO/CHANNEL_EGRESS slice spans. 118 tests green; adversarial review 94/100.
  - Files: `voice-agent/voice_common/{telemetry,sanitization}.py` (new), `voice-agent/tts_synthesis/runner.py`; edited `voice-agent/stt_validation/{telemetry,sanitization,pipeline_timing}.py`.
  - Content: `TtsSynthesisRunner(provider, telemetry)` mirroring `SttValidationRunner` — events `tts.synthesis.started/…/completed`, metric `tts.request.duration_ms`, span `voice.tts.first_audio`; outcome mapping (`EmptyTextError`->UNAVAILABLE, else FAILED); reuse `voice_common/sanitization.py`. Registered `_SLICE_SPAN_NAMES[TTS_FIRST_AUDIO]=("voice.tts.first_audio",)` and `[CHANNEL_EGRESS]=("web.voice.egress",)`; notes updated (no longer deferred).
  - AC: three outcomes covered; `tts_first_audio` (and `channel_egress` once egress emits) reported measured.
  - Test: `tests/test_tts_runner.py`, extend `tests/test_pipeline_timing.py`.

- [x] **ST-5 — Web egress + `POST /api/voice/tts` (WAV out).** Done 2026-07-13 — `WebVoiceEgress` (synthesize → WAV via `pcm_to_wav`) + `web.voice.egress` span measured on the real send window; `POST /api/voice/tts?text=…` returns `audio/wav` on success, sanitized JSON on failure (`MAX_TTS_TEXT_CHARS` guard). HTTP round-trip test proves WAV out + both TTS spans with propagated correlation id. 124 tests green; adversarial review 93/100.
  - Files: `voice-agent/web_voice/egress.py`, edit `voice-agent/web_voice/server.py`; `pcm_to_wav` helper.
  - Content: `WebVoiceEgress(provider)` mirroring `WebVoiceIngress` — emits `web.voice.egress` span (real bytes-out) + delegates to `TtsSynthesisRunner`. Endpoint accepts text + envelope query params, returns WAV bytes (PCM16 + 44-byte header), stable JSON error contract on failure.
  - AC: endpoint returns playable WAV for a text; failure returns sanitized JSON error; egress span emitted.
  - Test: `tests/test_web_voice_egress.py`.

- [x] **ST-6 — Web playback + echo loop (frontend).** Done 2026-07-13 — after STT success, `app.js` POSTs the transcript to `/api/voice/tts`, `decodeAudioData`s the WAV and plays it via a single `AudioBufferSourceNode` (dedicated playback context; `stopPlayback()` guards the "stop source on clear" pitfall). Chrome DevTools MCP validation (fixture provider): decode 2.04 s mono, playing, TTFA ~109 ms, correlation id propagated (3× POST 200), empty-text failure renders a sanitized error with no fabricated audio, console clean. Adversarial review 92/100.
  - Files: edited `voice-agent/web_voice/static/app.js` + `index.html`.
  - Content: after STT returns, call `/api/voice/tts?text=<transcript>`, `decodeAudioData` the WAV, play via a single `AudioBufferSourceNode`; guard the "stop source on clear" pitfall.
  - AC: speaking a phrase plays back its echo; time-to-first-audio measurable.
  - Evidence: Chrome DevTools MCP note (playback + failure render + timing).

- [x] **ST-7 — Architecture separation test.** Done 2026-07-13 — AST-based import scan fails if `tts_synthesis/` imports `stt_validation.*` or vice versa (relative + `voice_common` imports allowed); includes a self-test proving the detector flags a synthetic cross-import. 4 tests green; both directions currently clean. Adversarial review 95/100.
  - Files: `voice-agent/tests/test_architecture_separation.py`.
  - AC: fails if any `tts_synthesis/` module imports `stt_validation.*` or any `stt_validation/` module imports `tts_synthesis.*` (shared code lives in the neutral `voice_common/`, which both may import).

- [ ] **ST-8 — QA harness + fixtures + behave + docs.**
  - Files: `voice-agent/fixtures/tts/` (reference texts + committed clips), `voice-agent/features/tts_synthesis.feature`, extend `voice-agent/features/pipeline_timing.feature`; optional live round-trip QA (`synthesize -> existing Gradium STT -> WER vs input text`); docs `docs/observability/voice-journey-timing.md`, `voice-agent/README.md`.
  - AC: behave green (synthesize -> audio -> slice observable; empty text -> unavailable, no audio); both new slices shown measured; docs updated.

---

## TASK-WEB-003 - Orchestrate Transcript To Backend Answer (STT <-> TTS Bridge)

**Parent:** EPIC-006
**Related story:** US-019 (middle orchestration), US-036 (feeds the `backend_first_token` slice)
**Related decision:** DEC-007 (backend owns conversation intelligence)
**Classification:** V1 core
**Status:** Draft
**Priority:** High
**Branch:** `us/US-019-web-voice-chat`

### Objective

Close the US-019 loop: route the STT transcript to the Java backend (conversation
intelligence / RAG), get a response text, and hand it to the TTS slice so the web
page answers by voice. This is the middle of the Voice2Voice journey.

### Dependencies

- Requires the STT ingress (TASK-WEB-001) and TTS playback (TASK-WEB-002).
- Requires a backend answer surface. Until the billing/RAG backend exists, this
  slice may target a minimal backend conversation endpoint or a documented stub,
  keeping the boundary from `US-003` intact (backend owns the answer, runtime
  owns media).

### Scope

- Transcript -> backend conversation call (channel envelope, correlation id
  propagated end-to-end).
- Backend response text -> TTS slice.
- End-to-end OpenTelemetry trace across ingress -> STT -> backend -> TTS with a
  single correlation id, enabling per-slice latency (feeds US-036). Register the
  backend span name in `stt_validation/pipeline_timing.py`
  (`_SLICE_SPAN_NAMES[BACKEND_FIRST_TOKEN]`) so US-036 measures that slice.
- Degraded-mode handling when the backend is unavailable or not confident.

### Out Of Scope

- Full billing reasoning quality (owned by the billing epics).
- Genesys handoff (EPIC-007).

### Acceptance Criteria

```gherkin
Scenario: End-to-end web Voice2Voice loop
  Given the customer asks a question by voice on the web page
  When the transcript is sent to the backend and a response is produced
  Then the response is spoken back to the customer
  And the page can display the relevant synthesis when available
  And the full turn is traceable per pipeline slice via one correlation id
```

### Required Evidence

- Developer/integration tests for the transcript->backend->response wiring.
- Chrome DevTools MCP notes for the full loop + per-slice latency table.
- Behave scenario(s) for the end-to-end outcome.
- OpenTelemetry evidence: one correlation id across all slices.

### Notes

- When all three tasks pass QA and the user validates the loop, US-019 moves to
  Done and RF-002 can be closed (real ingress span replaced the scaffold analog).
- Per-slice timing produced here is the input US-036 reports on.

---

## TASK-WEB-004 - Stream The Bot Voice Response (Incremental TTS Playback)

**Parent:** EPIC-006, EPIC-010
**Related stories:** US-019 (voice-out), US-036 (the `tts_first_audio` slice), US-020 (quick spoken acknowledgement)
**Depends on:** TASK-WEB-002 (base TTS provider)
**Pairs with:** TASK-STT-010 (streaming STT) — the two form the low-latency voice loop
**Related decision:** DEC-005 (Pipecat streaming voice path; ADR-0002), DEC-010 (per-step latency before any SLO claim)
**Classification:** V1 core
**Status:** Draft
**Priority:** High (latency-driven)
**Branch:** `task/TASK-WEB-004-streaming-tts`

### Objective

Stream synthesized speech so playback starts on the **first audio chunk**
(time-to-first-audio) instead of waiting for the full clip to be synthesized. This
minimizes the perceived response latency of the voice-out half and, paired with
streaming STT (TASK-STT-010), keeps the full voice loop conversational despite the
~2.3 s batch STT baseline measured in `docs/qa/web-voice-qa-report.md`.

### Context

TASK-WEB-002 introduces a batch TTS provider (synthesize whole text -> play). Given
the measured STT latency, waiting for full synthesis on top would push the loop well
past a conversational target. Streaming TTS emits audio incrementally so the
customer hears the first words quickly.

### Scope

- A streaming TTS provider variant emitting audio chunks; the web page plays them
  incrementally (e.g. `MediaSource` / audio worklet queue).
- Telemetry: the `tts_first_audio` span = time-to-first-audio chunk; register the
  span name in `stt_validation/pipeline_timing.py` so US-036 measures it.
- Safe failure handling (no silent failure, no secret leak); offline/fixture mode.

### Out Of Scope

- Streaming STT (TASK-STT-010).
- Barge-in during playback (US-021), though streaming playback is a prerequisite for it.

### Acceptance Criteria

```gherkin
Scenario: The bot response audio starts before full synthesis
  Given a response text is available for the customer turn
  When the TTS provider streams synthesized audio
  Then playback begins on the first audio chunk
  And time-to-first-audio is observable via OpenTelemetry
```

### Required Evidence

- Developer tests for the streaming TTS provider with a fake chunked transport.
- Chrome DevTools MCP notes + time-to-first-audio vs full-clip comparison.
- Behave scenario for the streaming playback outcome.
- OpenTelemetry evidence for the `tts_first_audio` slice.
