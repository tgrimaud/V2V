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
| Backend/LLM orchestration | TASK-WEB-003 (A…G) | middle | TASK-WEB-001, TASK-WEB-002 — no external backend required (contract-first stub, Sprint 5) |

---

## TASK-WEB-001 - Capture Web Voice And Transcribe Through Gradium STT

**Parent:** EPIC-006
**Related story:** US-019 (STT half)
**Related finding:** RF-002 (TASK-STT-003) - replaces the `path.exists()` channel
ingress analog with a real web ingress
**Related decision:** DEC-005 / DEC-007 (voice runtime owns media orchestration)
**Classification:** V1 core
**Status:** Done (merged) — STT half delivered: live web mic → Gradium → transcript, QA GO in `docs/qa/web-voice-qa-report.md` (see `sprints/sprint-stt-validation.md`).
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
**Status:** Done (Sprint 3, 2026-07-13) — ST-1..ST-8 complete, 130 unit tests + 4 behave features green, echo loop MCP-validated + live Gradium demo validated by the user. **Merged (fast-forward) into `feat/restart-from-scratch`.**
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
- Register the emitted span name(s) in `voice_common/pipeline_timing.py`
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

- [x] **ST-8 — QA harness + fixtures + behave + docs.** Done 2026-07-13 — `features/tts_synthesis.feature` (synthesize→audio→slice observable, empty→unavailable no audio, failure sanitized with no secret leak) + extended `pipeline_timing.feature` (full-turn sample: TTS_FIRST_AUDIO + CHANNEL_EGRESS measured, only backend gap remains); `fixtures/tts/reference-texts.txt` consumed by the steps. Behave 4 features/12 scenarios green, 128 unit tests green. Docs updated. Adversarial review 93/100. (Offline fixture path is synthetic — no committed clips; live round-trip WER QA left as optional/future using the reference texts.)
  - Files: `voice-agent/fixtures/tts/reference-texts.txt`, `voice-agent/features/tts_synthesis.feature` + `features/steps/tts_steps.py`, extended `features/pipeline_timing.feature` + steps; docs `docs/observability/voice-journey-timing.md`, `voice-agent/README.md`.
  - AC: behave green (synthesize -> audio -> slice observable; empty text -> unavailable, no audio); both new slices shown measured; docs updated.

---

## TASK-WEB-003 - Orchestrate Transcript To Backend Answer (STT <-> TTS Bridge)

**Parent:** EPIC-006
**Related story:** US-019 (middle orchestration), US-036 (feeds the `backend_first_token` slice)
**Related decision:** DEC-007 (backend owns conversation intelligence), DEC-005
(providers/answer engine replaceable behind adapters), DEC-002 (LLM must not guess amounts)
**Classification:** V1 core
**Status:** Planned — Sprint 5 (`sprints/sprint-5-backend-bridge.md`)
**Priority:** High
**Sprint branch:** `feat/sprint-5-backend-bridge`

### Objective

Close the US-019 loop: route the STT transcript to a backend conversation surface,
get a response text, and hand it to the TTS slice so the web page **answers by
voice** (instead of echoing). This is the middle of the Voice2Voice journey.

### Backend Shape (decided — Option A)

The Java billing/RAG backend does not exist yet on this branch. This task uses a
**contract-first port + adapters** approach (locked with the user, Sprint 5):
a `BackendAnswerPort` seam in the voice runtime with a deterministic **stub**
adapter (default, offline/dev + tests) and an **HTTP** adapter (calls a real
conversation endpoint), selectable via `--backend {stub,http}` (env `VOICE_BACKEND`).
The real Java backend later implements the same contract without touching the runtime.

### Dependencies

- Requires the STT ingress (TASK-WEB-001) and TTS playback (TASK-WEB-002) — both Done.
- The `US-003` boundary stays intact: the backend owns the answer, the runtime owns
  the media.

### Business Rules

- The stub **never invents an amount or invoice content** (DEC-002); it returns a
  neutral, generic response. Real billing answers are gated by identity (OQ-001) and
  BSS availability (OQ-003) and stay out of Sprint 5.
- Backend unavailable / low confidence → a **safe spoken fallback**, no invented
  content, sanitized error, degraded outcome attribute. No Genesys handoff (EPIC-007
  out of scope); the real confidence threshold is gated by OQ-002.
- Ingress stays unauthenticated (RF-006 / RF-014 remain gated by OQ-001).

### Sub-Tickets (Sprint 5 execution)

Each sub-ticket is one branch and one `implement → test → commit` slice with an
adversarial review, mirroring the Sprint 3/4 discipline.

| Ticket | Title | Role | Status |
|---|---|---|---|
| TASK-WEB-003-A | Conversation contract + `BackendAnswerPort` (seam, no provider) | Contract | Implemented — review 96/100, merge-ready (pending user validation) |
| TASK-WEB-003-B | Deterministic stub backend adapter (default, offline/dev + tests) | Provider | Validated by user (2026-07-15) — review 96/100, merge-ready (merge on request) |
| TASK-WEB-003-C | HTTP backend adapter + `--backend {stub,http}` selection (env `VOICE_BACKEND`) | Provider | Planned |
| TASK-WEB-003-D | Wire the bridge into the runtime: transcript → backend answer → TTS text, on both runtimes | Integration | Planned |
| TASK-WEB-003-E | End-to-end telemetry: `backend.request`/`backend.first_token` span + `BACKEND_FIRST_TOKEN` slice (closes US-036 gap) | Observability | Planned |
| TASK-WEB-003-F | Degraded mode: backend unavailable / low confidence → safe spoken fallback | Robustness | Planned |
| TASK-WEB-003-G | QA + behave (e2e loop + degraded) + per-slice latency table + docs + conversation-contract ADR | QA / Docs | Planned |

Delivery order: A → B → D → E → F → C → G (C may precede D if the HTTP path is needed
earlier; D-before-C makes the answering loop visible ASAP on the stub).

### TASK-WEB-003-A — Conversation Contract + `BackendAnswerPort`

**Objective:** Define the runtime-side conversation contract and the port protocol,
with no provider implementation yet.

**Scope:**
- Request shape: transcript, channel envelope (`channel=web_voice`,
  `conversation_id`, `external_session_id`, `correlation_id`).
- Response shape: response text, outcome (success / degraded / unavailable),
  confidence or degraded reason.
- `BackendAnswerPort` protocol (`name`, `answer(request) -> AnswerResult`) mirroring
  the `SttProvider` / `TtsProvider` pattern; shared cross-cutting code stays in
  `voice_common/`.

**Acceptance Criteria:**
```gherkin
Scenario: The conversation contract is defined without a provider
  Given the backend answer seam
  When the contract types are constructed for a transcript and envelope
  Then a request carries the transcript, envelope and correlation id
  And a response can express success, degraded or unavailable outcomes
```
**Required Evidence:** developer tests for the contract types (no network); no leak
of secrets in `to_dict`/serialization.

**Delivery evidence:** new neutral package `voice-agent/conversation_backend/`
(`models.py` = `AnswerOutcome` {success,degraded,unavailable}, `AnswerRequest`
+ `from_envelope`/`to_dict`, `AnswerResult` + `is_success`/`to_dict`,
`ConversationEnvelope` structural Protocol; `port.py` = `BackendAnswerPort` Protocol
+ `EmptyTranscriptError`). Tests: `tests/test_conversation_backend_contract.py`
(8 tests, GIVEN/WHEN/THEN, incl. transcript/text never serialized) + architecture
neutrality added to `tests/test_architecture_separation.py`
(`conversation_backend` imports neither `stt_validation`, `tts_synthesis` nor
`web_voice`). 9 new tests green; full non-pipecat suite green (the 8 pre-existing
suite errors are `pipecat` not installed in this env, unrelated to this ticket).
OpenTelemetry: **not applicable** (contract types only, no runtime behaviour).
Adversarial review 96/100, QA gate Pass; non-blocking RF-015 (confidence not
range-validated → E) and RF-016 (`error_reason` free text → sanitize in C/F) logged.

### TASK-WEB-003-B — Stub Backend Adapter

**Objective:** A deterministic, offline answer adapter honoring DEC-002 (neutral
text, no fabricated amounts). Default backend for dev and tests.

**Acceptance Criteria:**
```gherkin
Scenario: The stub answers without inventing billing content
  Given the stub backend adapter
  When it answers a transcript
  Then it returns a neutral response text
  And it never fabricates an amount or invoice detail
```
**Required Evidence:** developer tests (deterministic output, no invented amounts,
success + degraded paths).

**Status:** Validated by user 2026-07-15 (checks re-run green: 171 unit tests + 14
behave). Merge-ready; merge only on explicit request. Implemented on
`task/TASK-WEB-003-B-stub-backend` (branched from
`feat/sprint-5-backend-bridge`). `StubBackendAdapter` in
`conversation_backend/stub_backend.py`: constant `STUB_ANSWER_TEXT` (digit- and
currency-free, DEC-002), `SUCCESS` + correlation-id passthrough, empty/whitespace
transcript → `EmptyTranscriptError`. 6 unit tests in
`tests/test_stub_backend_adapter.py` (neutral text, no digit/`€`, deterministic,
correlation id, empty→error, port compliance). Full suite 171 tests + 14 behave
scenarios green. Adversarial review 96/100 (QA gate Pass); non-blocking RF-017
(digit-free invariant guarded by test only) and RF-018 (`confidence=None` must be
read as "not provided" by the F degraded rule). OTel/QA-latency N/A — pure adapter,
not wired into a runtime path (instrumentation is TASK-WEB-003-E's scope).

### TASK-WEB-003-C — HTTP Backend Adapter + Selection

**Objective:** An HTTP adapter calling a real conversation endpoint, plus runtime
selection `--backend {stub,http}` (env `VOICE_BACKEND`).

**Acceptance Criteria:**
```gherkin
Scenario: The runtime can target a real conversation endpoint
  Given the http backend adapter with a fake transport
  When it answers a transcript
  Then it maps the endpoint response to the conversation contract
  And transport/timeout errors map to a sanitized degraded outcome
  And no secret appears in any error, log or telemetry
```
**Required Evidence:** fake-transport tests (success + error mapping + no key leak),
no live backend required.

### TASK-WEB-003-D — Wire The Bridge Into The Runtime

**Objective:** Insert the backend answer step between STT and TTS so the loop
**answers** instead of echoing, on **both** runtimes (stdlib + pipecat). The echo
processor is retired or repurposed as the answer step.

**Acceptance Criteria:**
```gherkin
Scenario: The web voice loop answers instead of echoing
  Given the runtime is started with the stub backend
  When the customer records a phrase on the web page
  Then the phrase is transcribed, answered by the backend and spoken back
  And the behaviour is equivalent on the stdlib and pipecat runtimes
```
**Required Evidence:** developer tests for the wired loop on both runtimes; behave
coverage; confirmation the TTS input is the backend answer, not the transcript.

### TASK-WEB-003-E — End-To-End Telemetry (closes US-036 gap)

**Objective:** Emit a backend span and register the missing US-036 slice.

**Scope:**
- Emit `backend.request` / `backend.first_token` with correlation id, outcome and
  duration.
- Register the span name in `voice_common/pipeline_timing.py`
  (`_SLICE_SPAN_NAMES[BACKEND_FIRST_TOKEN]`) so US-036 measures the slice.
- One correlation id across ingress → STT → backend → TTS → egress.

**Acceptance Criteria:**
```gherkin
Scenario: The backend slice becomes measured
  Given a full web voice turn through the backend bridge
  When the pipeline timing report is produced
  Then backend_first_token is reported measured (no longer a gap)
  And every slice shares one correlation id
```
**Required Evidence:** telemetry tests; a full-turn pipeline-timing sample showing
`backend_first_token` measured; no remaining implemented-slice gap in US-036.

### TASK-WEB-003-F — Degraded Mode

**Objective:** Safe behaviour when the backend is unavailable or not confident.

**Acceptance Criteria:**
```gherkin
Scenario: Safe fallback when the backend cannot answer
  Given the backend is unavailable or not confident
  When the turn is processed
  Then no billing content is invented
  And a safe spoken fallback is rendered to the customer
  And the degraded outcome is observable without leaking secrets
```
**Required Evidence:** developer tests for unavailable + low-confidence paths;
sanitized error contract; degraded outcome attribute in telemetry.

### TASK-WEB-003-G — QA, Behave, Latency, Docs, ADR

**Objective:** Close the sprint with QA evidence and documentation.

**Scope:**
- Behave scenarios: end-to-end answer loop + degraded fallback.
- Per-slice latency table for the full turn (feeds US-036).
- Docs: `voice-agent/README.md` (`--backend` flag), `docs/observability/voice-journey-timing.md`,
  and a new **ADR for the conversation contract** under `docs/architecture/adrs/`.
- **API contract documentation** (single source of truth for the sprint's contracts),
  because both are currently code-only:
  - **Voice runtime HTTP API** — `POST /api/voice/stt`, `/tts`, `/turn`: request/response
    JSON, status codes, the sanitized error shape (`error_code` + correlation id, RF-013)
    and the `--backend {stub,http}` selection. New page under `docs/` (e.g.
    `docs/architecture/voice-runtime-http-contract.md`), linked from `docs/README.md`.
  - **Conversation contract surface** — `BackendAnswerPort` + `AnswerRequest` /
    `AnswerResult` / `AnswerOutcome` / `EmptyTranscriptError` (fields, privacy rule:
    only lengths in `to_dict`, `confidence`/`degraded_reason`/`error_reason` semantics).
    Captured in the conversation-contract ADR above.
- Chrome DevTools MCP note re-validating the live answering loop (manual QA step,
  needs a live mic + Gradium key).

**Acceptance Criteria:** behave green (answer + degraded); `backend_first_token`
shown measured; docs + ADR updated; the voice runtime HTTP API contract and the
conversation-contract surface are both documented under `docs/` and linked from
`docs/README.md` (no code-only contract remains for this sprint).

### Notes

- When all sub-tickets pass QA and the user validates the loop, **US-019 moves to
  Done** and RF-002 can be closed (real ingress span replaced the scaffold analog).
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
  span name in `voice_common/pipeline_timing.py` so US-036 measures it.
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

---

## TASK-WEB-005 - Introduce The Pipecat Batch Runtime (Pipeline Parity)

**Parent:** EPIC-006 (+ EPIC-010 for observability)
**Related story:** US-019 (voice runtime), US-036 (per-slice timing preserved)
**Related decision:** DEC-005 / ADR-0002 (Pipecat is the target voice path), ADR-0012
(modular pipeline), ADR-0016 (legacy path kept as fallback/comparison)
**Depends on:** TASK-WEB-001 (STT ingress), TASK-WEB-002 (TTS voice-out)
**Classification:** V1 enabler
**Status:** Done — Sprint 4 (`sprints/sprint-4-pipecat-batch.md`); adversarial review 94/100 Pass (RF-012/013/014 logged)
**Priority:** High
**Branch:** `task/TASK-WEB-005-pipecat-batch` (from `feat/sprint-4-pipecat-batch`)

### Objective

Run the existing web voice **batch** loop (STT → echo → TTS) through a **Pipecat
pipeline** with **no user-visible change**, aligning the runtime with the ADR-0002
target and de-risking the framework migration **before** streaming (Sprint 6). This
is a migration / de-risking task, **not** a latency task: batch-on-Pipecat is not
expected to beat batch-on-stdlib; the value is isolating the runtime swap from the
streaming changes and stopping the target-vs-real drift (the code has zero Pipecat
today).

### Scope

- Wrap the existing Gradium STT and TTS paths as **Pipecat frame processors**,
  delegating to the current `SttValidationRunner` / `TtsSynthesisRunner` (no fork,
  no behaviour change).
- Assemble an in-memory Pipecat pipeline (`source → stt → echo → tts → sink`) driven
  server-side (no WebRTC transport, no browser change).
- **Dual runtime:** introduce a `VoiceTurnProcessor` seam in the web server so the
  legacy stdlib path and the new Pipecat path both exist and are selectable via
  `--runtime {stdlib,pipecat}` (env fallback `VOICE_RUNTIME`). Ship the sprint with
  the default flipped to `pipecat`; keep `stdlib` as the fallback/comparison path.
- Preserve the exact contract of the two legacy endpoints (`POST /api/voice/stt`
  PCM in, `POST /api/voice/tts` WAV out, sanitized JSON errors, correlation id) on
  both runtimes.
- Add `POST /api/voice/turn` (full audio → STT → echo → TTS → WAV in one server-side
  call) exercising the whole pipeline; the browser stays on the two legacy endpoints.
- Preserve the US-036 pipeline slices (`web.voice.ingress`, `voice.stt.*`,
  `voice.tts.first_audio`, `web.voice.egress`) via the shared `voice_common`
  telemetry so timing reporting is unchanged.
- Keep the hard STT/TTS separation: the STT service must not import `tts_synthesis`
  and the TTS service must not import `stt_validation` (shared code stays in
  `voice_common/`); enforced by the architecture test.

### Out Of Scope

- Streaming STT (TASK-STT-010), streaming TTS (TASK-WEB-004), streaming VAD
  (TASK-STT-012), WebRTC transport + Pipecat JS client — all **Sprint 6**.
- Barge-in (US-021), backend/LLM answer (TASK-WEB-003).
- Any frontend change (the browser keeps its current two-call echo loop).

### Acceptance Criteria

```gherkin
Scenario: The web voice batch loop runs through the Pipecat pipeline
  Given the voice runtime is started with --runtime pipecat
  When the customer records a phrase on the web page
  Then the phrase is transcribed, echoed and spoken back exactly as before
  And the same pipeline slices are observable via OpenTelemetry
```

```gherkin
Scenario: Both runtimes are selectable and behaviour-equivalent
  Given the same input audio
  When it is processed with --runtime stdlib and with --runtime pipecat
  Then both produce identical WAV output
  And switching runtime requires no code change, only the startup flag
```

```gherkin
Scenario: STT and TTS stay independent in the pipeline
  Given the Pipecat STT service and TTS service
  When the architecture separation test runs
  Then the STT service does not import tts_synthesis and vice versa
  And shared code lives only in voice_common
```

### Required Evidence

- Developer tests for the Pipecat STT/TTS frame processors (fake provider/transport,
  no live call) and for the in-memory batch pipeline runner.
- A/B parity harness comparing `stdlib` vs `pipecat` output on the same input
  (identical WAV) plus a per-slice latency report.
- Behave scenarios green through **both** runtimes (or a dedicated parity scenario).
- Architecture separation test extended to the new `voice_pipeline/` services.
- Chrome DevTools MCP note re-validating the echo loop on the default (`pipecat`)
  runtime (unchanged UX + timing).
- Confirmation no API key, raw audio or filesystem path is logged.

## TASK-WEB-006 - Genericize Voice Error Responses (Do Not Echo Raw Provider Error Text)

**Parent:** EPIC-006 (+ EPIC-010 for observability)
**Related story:** US-019 (voice runtime)
**Related decision:** ADR-0016 (fallback/comparison path); mirrors the Java backend
`GlobalExceptionHandler` `ERR_UPSTREAM` pattern
**Depends on:** TASK-WEB-005 (voice endpoints + `VoiceTurnProcessor` seam)
**Classification:** V1 hardening
**Status:** Planned
**Priority:** Low
**Branch:** `task/TASK-WEB-006-generic-voice-errors` (from the active sprint branch)
**Source finding:** RF-013 (`product-backlog/review-findings.md`)

### Objective

On a non-success turn, the STT/TTS `error_reason` currently echoes the raw provider
exception text verbatim into the `502` JSON body of `POST /api/voice/stt`,
`/api/voice/tts` and `/api/voice/turn`. Sanitization already redacts paths, UUIDs,
secret prefixes, filenames and long digit runs (RF-001 / RF-009), but generic free
text from a real provider exception can still reach the client. Return a generic,
client-safe `error_reason` (plus the correlation id) at the HTTP boundary while
keeping the full reason server-side in the structured logs — the same trade-off the
Java backend already makes with `ERR_UPSTREAM` + correlation id.

### Scope

- Introduce a client-facing error shape for the voice endpoints that carries a
  stable `error_code` + a generic message + the `correlation_id`, and omits the raw
  provider `error_reason` from the HTTP body.
- Keep the full `error_reason` in the server-side structured log line (already
  emitted via `_log_turn`) so operators can still diagnose via the correlation id.
- Apply uniformly to all three routes (`/stt`, `/tts`, `/turn`) and to both runtimes
  (the seam already routes both through the same handler).
- Keep the existing sanitization (paths/ids/secrets) as defense in depth.

### Out Of Scope

- Changing outcome semantics (FAILED / UNAVAILABLE stay as-is).
- Frontend changes beyond reading the new field name if it is renamed (the browser
  only surfaces a generic failure today).
- Authentication / identity gating (RF-006 / RF-014, gated by OQ-001 + TASK-WEB-003).

### Acceptance Criteria

```gherkin
Scenario: A failing provider does not leak its raw error text to the client
  Given a voice endpoint whose STT or TTS provider raises an exception
  When a client posts a turn and receives a 502
  Then the JSON body carries a stable error_code and the correlation id
  And it does not contain the raw provider exception message
  And the full reason is still present in the server-side structured log
```

```gherkin
Scenario: Both runtimes return the same client-safe error contract
  Given the stdlib and pipecat runtimes
  When the same failing input is posted to /api/voice/turn on each
  Then both return the identical generic error body (modulo correlation id)
```

### Required Evidence

- Developer test asserting the 502 body for `/stt`, `/tts`, `/turn` contains the
  `error_code` + correlation id and NOT the raw provider message, on both runtimes
  (extends `test_voice_runtime.py::test_turn_endpoint_fails_closed_with_json_when_stt_fails`).
- Confirmation the raw reason still appears in the server-side log line.
- Closes RF-013.
