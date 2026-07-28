# Web Voice Journey Technical Tasks

Delivery slices for **US-019 - Ask From A Web Voice Chat**. US-019 is a full
Voice2Voice journey (voice in, voice out) and is too large for a single slice, so
it is decomposed into tasks. **US-019 is Done** (Sprint 5, 2026-07-15): all slices
(STT ingress, TTS voice-out, and the backend answer bridge TASK-WEB-003 A–G) are
delivered and the end-to-end web voice loop was validated by the user.

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
| TASK-WEB-003-C | HTTP backend adapter + `--backend {stub,http}` selection (env `VOICE_BACKEND`) | Provider | Implemented — merge-ready (pending user validation) |
| TASK-WEB-003-D | Wire the bridge into the runtime: transcript → backend answer → TTS text, on both runtimes | Integration | Implemented — review 93/100, merge-ready (pending user validation) |
| TASK-WEB-003-E | End-to-end telemetry: `backend.request`/`backend.first_token` span + `BACKEND_FIRST_TOKEN` slice (closes US-036 gap) | Observability | Validated by user 2026-07-15 (checks re-run: 182 unit + 15 behave green) — merge-ready (merge on explicit request) |
| TASK-WEB-003-F | Degraded mode: backend unavailable / low confidence → safe spoken fallback | Robustness | Implemented — merge-ready (pending user validation); resolves RF-020 |
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

**Status:** Implemented on `task/TASK-WEB-003-C-http-backend` (from
`feat/sprint-5-backend-bridge`, which already carries E+F); adversarial review 93/100
(QA gate Pass), merge-ready, pending user validation. New `conversation_backend/http_backend.py` (`HttpBackendAdapter`,
`BackendAnswerPort`) with an **injectable transport** (default stdlib `urllib`, so
unit tests never hit the network). `answer` posts `{transcript, conversation_id,
correlation_id, channel}` as JSON and maps a 2xx response's `text` (alias `answer`) +
optional `confidence` onto `AnswerResult(SUCCESS)`. An empty transcript raises
`EmptyTranscriptError` before any call (stays UNAVAILABLE, never fabricates). Any
transport fault, timeout, non-2xx status, unparsable body or empty answer maps to a
**sanitized DEGRADED** result (safe fallback text + `sanitize_error(domain="backend")`
→ `backend_error` / `backend_timeout`), reusing the TASK-WEB-003-F `degraded_answer`.
The API key lives only in the `x-api-key` request header — never in an exception, log,
result or telemetry attribute. New `conversation_backend/backend_factory.py`
(`build_backend(name)`, `STUB` default / `HTTP`) builds the HTTP adapter from env
(`VOICE_BACKEND_URL`, `VOICE_BACKEND_API_KEY`, `VOICE_BACKEND_TIMEOUT_S`);
`server.py` adds `--backend {stub,http}` (env `VOICE_BACKEND`, default `stub`) and
logs the selected backend. Tests: `test_http_backend.py` (mapping success, `answer`
alias, request/header shape, empty-transcript, all degraded paths, no key leak, +
low-confidence degrade via `answer_with_telemetry`), `test_backend_factory.py`
(stub default / http from env / missing URL / unknown). Behave:
`conversation_backend.feature`. Full suite 208 unit + 17 behave green. The
request/response field names are provisional; **TASK-WEB-003-G**'s conversation-contract
ADR formalizes them.

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

**Status:** Implemented on `task/TASK-WEB-003-D-wire-bridge` (from
`feat/sprint-5-backend-bridge`). New `voice_pipeline/answer.py` (`AnswerProcessor`
+ `answer_with_telemetry`, span `backend.request`) replaces the echo step; `echo.py`
retired. `run_batch_turn` and both `StdlibTurnProcessor` / `PipecatTurnProcessor`
insert the `BackendAnswerPort` between STT and TTS (default `StubBackendAdapter`,
injectable — `--backend` selection is C). `BatchTurnResult` gains `answer_result`.
`server.py` wires the stub in `main()` and returns the transcript + spoken answer as
`X-Voice-Transcript` / `X-Voice-Answer` / `X-Answer-Provider` / `X-Correlation-Id`
headers on `/turn`; the web page (`app.js`) now calls `/turn` and speaks the answer
instead of echoing. Tests: `test_answer_processor.py` (new), rewritten
`test_pipeline.py`, extended `test_voice_runtime.py` (answer-not-echo on both
runtimes + `/turn` headers) and `test_architecture_separation.py` (answer step stays
out of the voice halves). Full suite 178 tests + 14 behave green. Adversarial review
93/100 (QA gate Pass); non-blocking RF-019 (frontend has no CI test → manual QA in G)
and RF-020 (no-answer path returns generic `no_audio` 502 → safe spoken fallback is
F). OTel: emits `backend.request` span + `voice.backend.answered` event (correlation
id, provider, outcome, duration, lengths only); registering the US-036
`backend_first_token` slice is TASK-WEB-003-E.

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

**Status:** Validated by user on 2026-07-15 (checks re-run green: 182 unit + 15
behave). Merge-ready; merge into `feat/sprint-5-backend-bridge` on explicit user
request. Implemented on `task/TASK-WEB-003-E-backend-telemetry` (from
`feat/sprint-5-backend-bridge`). `answer_with_telemetry` now emits **both**
`backend.first_token` and `backend.request` spans (batch: equal duration; a future
streaming backend diverges them) plus the `voice.backend.answered` event — lengths
only, no raw text. `voice_common/pipeline_timing.py` registers
`_SLICE_SPAN_NAMES[BACKEND_FIRST_TOKEN] = ("backend.first_token", "backend.request")`
and drops the "deferred" note, so US-036 measures the backend slice. Tests:
`test_pipeline_timing.py` (backend measured from first_token, request fallback,
first_token-precedence; bridge test asserts all six slices measured + a single
correlation id `corr-bridge`), `test_answer_processor.py` (both spans emitted).
Behave: `pipeline_timing.feature` full-loop scenarios drive `StdlibTurnProcessor.run_turn`
so backend/TTS/egress are all measured, with an explicit "one correlation id end to
end" scenario. Full suite 182 tests + 15 behave green. Docs
`docs/observability/voice-journey-timing.md` updated (backend slice now
instrumented). Adversarial review 95/100 (QA gate Pass); non-blocking RF-021 (batch
`backend.first_token` equals `backend.request` until a streaming backend exists).

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

**Status:** Implemented on `task/TASK-WEB-003-F-degraded-mode` (from
`task/TASK-WEB-003-E-backend-telemetry`); adversarial review 94/100 (QA gate Pass),
merge-ready, pending user validation.
The safe fallback lives in the neutral contract (`conversation_backend/degraded.py`):
`DEGRADED_FALLBACK_TEXT` (no digit / amount, DEC-002), `DEFAULT_CONFIDENCE_THRESHOLD`
(0.5) and the `degraded_answer(...)` builder. The **policy** lives in the shared
answer step (`voice_pipeline/answer.py`), so both runtimes behave identically:
`answer_with_telemetry` now (1) catches any backend fault (except
`EmptyTranscriptError`, which stays UNAVAILABLE / silent) and returns a DEGRADED
result carrying the safe fallback + a **sanitized** `error_code`/`error_reason`
(`sanitize_error(domain="backend")`), (2) replaces a below-threshold-confidence
SUCCESS answer with the safe fallback (`low_confidence`), and (3) replaces a
confident-but-empty answer (`empty_answer`). A DEGRADED result is spoken (has text,
not UNAVAILABLE), so the customer always hears something safe and the turn never
crashes or 502s. Telemetry: both `backend.first_token` / `backend.request` spans and
the `voice.backend.answered` event carry `outcome=degraded`, `degraded=true`,
`degraded_reason` and the sanitized error (lengths only for text); a `warning` log is
emitted on degrade. `/turn` returns the spoken WAV (200) with
`X-Answer-Outcome: degraded` + `X-Answer-Degraded-Reason`; the web page shows a
degraded badge. Tests: `test_answer_processor.py` (6 degraded cases: failure→fallback,
sanitized no-leak, degraded telemetry, low-confidence replacement, high-confidence
kept, fallback has no digit) + AnswerProcessor degraded frame; `test_voice_runtime.py`
(both runtimes speak the fallback; `/turn` degraded WAV + headers). Behave:
`web_voice.feature` "Safe fallback when the backend cannot answer". Full suite 191
unit + 16 behave green. **Resolves RF-020** (no more generic `no_audio` 502 when the
backend cannot answer).

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
**Status:** ✅ Done — Sprint 6 (`sprints/sprint-6-streaming.md`); validated by user + merged into `feat/sprint-6-streaming` (2026-07-16, no-ff). Live first-audio 363 ms vs ~1.59 s batch (~4.4x cut); ADR-0024 + `docs/qa/web-004-streaming-tts-qa.md`; adversarial review 96/100 (open()-failure sanitized, allowlist synthesis, 8s chunk budget); 261 unit + Behave 8/23/103 green
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
**Status:** ✅ Validated by user (2026-07-16) — adversarial review 94/100 (Pass), 281 unit + behave green, live full-stack validated. Merge-ready on `task/TASK-WEB-006-generic-voice-errors` (unmerged — merge on explicit request). Closes RF-013
**Priority:** Low
**Branch:** `task/TASK-WEB-006-generic-voice-errors` (from `feat/sprint-6-streaming`)
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

### Implementation (2026-07-16)

- New `web_voice/error_response.py::client_error_body(error_code, correlation_id,
  outcome)` builds the client-safe body `{outcome, error_code, correlation_id,
  message}`. Only author-controlled strings reach the body; the raw provider reason
  is never included. A small curated message map covers client-actionable codes
  (`no_speech`, `empty_text`, timeouts, `no_transcript`, `no_audio`) with a generic
  default.
- `server.py` `_handle_stt` / `_handle_tts` / `_handle_turn` now serialize this body
  on every 502 (both runtimes route through the same handler). `_turn_stt_error` /
  `_turn_tts_error` cover the `no_transcript` / `no_audio` fallbacks with the
  envelope correlation id.
- Full sanitized reason retained server-side: `_log_turn` still dumps the
  `stt.failure` / `tts.failure` telemetry events (which carry `error_reason`) to
  stderr under the correlation id — verified by
  `test_voice_runtime.py::test_turn_502_keeps_the_full_reason_in_the_server_log`.
- Frontend `static/app.js` reads the generic `message` (falls back to legacy
  `error_reason`).
- Tests: `tests/test_error_response.py` (mapper units) +
  client-safe/parity/server-log tests in `test_voice_runtime.py`, plus `/stt` and
  `/tts` HTTP client-safe assertions in `test_web_voice_ingress.py` /
  `test_web_voice_egress.py`. Full suite: 281 unit + 9 behave features green.
- Docs: `docs/architecture/voice-runtime-http-contract.md` updated to the new 502
  shape.

---

## TASK-WEB-007 - WebRTC Transport For The Streaming Voice Loop

**Parent:** EPIC-006 (+ EPIC-010 for observability)
**Related stories:** US-019 (voice runtime), US-036 (per-slice timing), US-021 (barge-in enabler)
**Related decision:** DEC-005 / ADR-0002 (Pipecat + WebRTC target voice path), ADR-0012
(modular pipeline over realtime API), ADR-0016 (batch path kept as fallback), ADR-0018 (latency)
**Depends on:** TASK-WEB-005 (Pipecat pipeline + `VoiceTurnProcessor` seam)
**Source finding:** RF-012 (`asyncio.run` per turn → single long-lived async loop)
**Classification:** V1 core (latency enabler)
**Status:** In progress — Sprint 6 (`sprints/sprint-6-streaming.md`). **Implemented**
(pending the spoken-answer QA gate). `pipecat-ai[webrtc]` installed (aiortc 1.15.0, av
17.1.0, opencv 4.13.0.92 on Py3.14). Delivered: `SmallWebRTCTransport` wired via a
persistent single loop (`web_voice/async_loop.py`, closes RF-012); signaling route
`POST /api/voice/webrtc/offer` on the stdlib server without FastAPI
(`web_voice/webrtc_signaling.py`); browser page `/webrtc.html`; interim utterance
aggregator (`web_voice/utterance_aggregator.py`, reuses TASK-STT-009 thresholds); tests
(aggregator + real in-process handshake reaching `connected`); ADR-0022; spike +
findings (`docs/qa/webrtc-transport-spike.md`). **QA gate PASSED:** live spoken-answer
round trip with `--provider gradium` captured the full US-036 slice decomposition over
WebRTC under one correlation id (ingress → end_of_turn 500ms → STT/Gradium 2775ms →
backend → TTS/Gradium 4112ms). Finding logged: Opus DTX suppresses pure-silence
packets, so end-of-turn relies on a real mic's ambient noise (test clips pad with
low-amplitude noise). **Remaining (infra, not code):** trickle ICE + TURN (coturn) for
corporate NAT.
**Priority:** High
**Branch:** `task/TASK-WEB-007-webrtc-transport`

### Objective

Add a **WebRTC full-duplex transport** (Pipecat `SmallWebRTCTransport` + a Pipecat
JS client in the browser) that drives the existing pipeline (`ingress → stt →
answer → tts → egress`) on **one long-lived asyncio event loop**, replacing the
per-turn `asyncio.run(...)` of the batch endpoints for the realtime path. This is
the foundation the streaming STT/TTS/VAD and barge-in tickets ride on.

### Context (why this is needed)

The Sprint 4/5 loop runs synchronously over HTTP: `PipecatTurnProcessor` spins a
fresh event loop + `PipelineTask`/`PipelineRunner` per request (RF-012), and audio
is exchanged as whole buffers. True streaming and barge-in need a persistent,
bidirectional media channel and an awaited pipeline. The Sprint 4 retro notes the
pipeline is ~80% reusable for this.

### Scope

- A `SmallWebRTCTransport`-based runtime driving the pipeline on a single
  long-lived loop; signaling endpoint(s) for the WebRTC handshake.
- A minimal Pipecat JS client in the browser (mic capture + speaker playback over
  WebRTC), alongside the existing batch page (kept as fallback/comparison, ADR-0016).
- Reuse the same STT/TTS runners and the Sprint 5 `BackendAnswerPort`; no fork.
- Preserve the US-036 slices under one correlation id over the streaming path.
- Safe failure (transport drop, ICE failure) — no secret leak, graceful teardown.
- **A spike opens the ticket** (lock the transport + JS client handshake, the
  single-loop drive, frame types and version pins) → findings in `docs/qa/`.

### Out Of Scope

- Streaming STT/TTS/VAD partial semantics (TASK-STT-010 / TASK-WEB-004 / TASK-STT-012);
  this ticket carries whole-utterance frames until those land.
- Barge-in behaviour (TASK-WEB-008).
- Identity/auth on the signaling path (OQ-001 / RF-006 / RF-014, gated).

### Acceptance Criteria

```gherkin
Scenario: The voice loop runs over a WebRTC transport on one async loop
  Given the streaming runtime with the WebRTC transport
  When the customer speaks a question in the browser
  Then audio flows in and out over WebRTC
  And the pipeline is awaited on a single long-lived event loop (no per-turn asyncio.run)
  And the US-036 slices are observable under one correlation id
```

```gherkin
Scenario: The batch endpoints remain as a fallback
  Given the WebRTC transport is added
  When the batch HTTP endpoints are used
  Then POST /api/voice/stt|tts|turn keep their exact contract
```

### Required Evidence

- Spike note in `docs/qa/` (transport + JS client handshake, single-loop drive,
  version pins, TURN/STUN needs).
- Developer tests for the single-loop pipeline drive with a fake transport (no real
  ICE), and for graceful teardown on transport drop.
- Chrome DevTools MCP note: live WebRTC round trip (audio in/out) + correlation id.
- OpenTelemetry evidence: US-036 slices measured over the WebRTC path.
- **Closes RF-012.** No API key / raw audio / path leak.

---

## TASK-WEB-008 - Barge-In During A Spoken Answer (US-021)

**Parent:** EPIC-006, EPIC-010
**Related story:** US-021 (interrupt the bot), US-019 (voice runtime)
**Related decision:** DEC-005 / ADR-0002 (streaming voice path), ADR-0018 (latency)
**Depends on:** TASK-WEB-007 (WebRTC full-duplex), TASK-WEB-004 (streaming/incremental
playback to cancel), TASK-STT-012 (streaming VAD to detect speech onset)
**Classification:** V1 core
**Status:** Planned — Sprint 6 (`sprints/sprint-6-streaming.md`)
**Priority:** Medium
**Branch:** `task/TASK-WEB-008-barge-in`

### Objective

Let the customer **interrupt the bot while it is speaking**: when the streaming VAD
detects customer speech onset during playback, stop the outgoing TTS playback
promptly and start a new turn, so the conversation feels natural (US-021).

### Context (why this is needed)

Barge-in is the user-visible payoff of the streaming sprint. It requires full-duplex
media (TASK-WEB-007), a detector that fires on speech onset during playback
(TASK-STT-012) and cancellable incremental playback (TASK-WEB-004) — none of which
exist in the batch loop. The frontend already learned the "stop the current
`AudioBufferSourceNode` on clear" pitfall (Sprint 3), which this reuses.

### Scope

- Detect customer speech onset during bot playback via the streaming VAD.
- Cancel in-flight TTS synthesis/playback and flush the audio queue promptly;
  begin capturing the new turn.
- Emit a barge-in OpenTelemetry event/span (correlation id, time-to-stop) for pilot
  review; register any new span name if it feeds a slice.
- Safe behaviour: no barge-in on the bot's own audio / echo; configurable onset
  threshold; no invented turn on spurious noise (reuse the TASK-STT-012 guarantee).
- **Graceful end-of-turn flush on call end/drop (carried from TASK-STT-012 QA).**
  Today the streaming `UtteranceAggregator.finish()` (client-stop flush) only runs
  on an `EndFrame`, but WebRTC teardown cancels the pipeline task (`session.stop()`
  → `CancelFrame`) and a single client `"closed"` event only logs telemetry, so a
  trailing partial utterance (customer still mid-speech at hangup) is never flushed.
  This ticket already touches the same frame-cancellation/teardown machinery, so
  fold in a graceful drain: add a `StreamingVoiceSession.drain()` that queues an
  `EndFrame` (or `stop_when_done`) and awaits completion, and call it on the
  `"closed"`/`"disconnected"` event in `webrtc_signaling` before discard. The
  aggregator's `EndFrame → finish()` path already exists.
  - Evidence: unit test (fake transport: speech then drop with no silence window →
    exactly one `client_stop` flush + `voice.end_of_turn` span); live re-run with a
    clip that ends mid-speech asserting `end_of_turn_signal=client_stop`.
  - Note: a genuinely abrupt network drop may remain best-effort. Cost estimate:
    ~2–4 h incl. tests (see `docs/qa/stt-012-streaming-end-of-turn-qa.md`).

### Out Of Scope

- Streaming STT/TTS/VAD themselves (their own tickets); this consumes them.
- Backend cancellation semantics beyond stopping playback (the answer engine is the
  stub/http backend).

### Acceptance Criteria

```gherkin
Scenario: Customer interrupts the assistant mid-answer
  Given the assistant is playing a spoken answer over the streaming loop
  When the customer starts speaking
  Then the assistant stops playback promptly
  And a new turn begins from the customer's speech
  And the barge-in outcome (and time-to-stop) is observable for pilot review
```

```gherkin
Scenario: The bot does not interrupt itself
  Given the assistant is playing its own audio
  When only the bot's audio is present (no customer speech)
  Then no barge-in is triggered
```

### Required Evidence

- Developer tests: VAD-onset-during-playback triggers cancellation; no self-barge-in;
  time-to-stop measured.
- Behave scenario for the barge-in outcome.
- Chrome DevTools MCP note: live interrupt stops playback; timing captured.
- OpenTelemetry evidence: barge-in event + time-to-stop under the turn correlation id.
- When validated live by the user, **US-021 → Done**.

---

## TASK-WEB-009 - Streaming QA, Latency SLO Report And ADR Update (Sprint 6 Close)

**Parent:** EPIC-010 (+ EPIC-006)
**Related stories:** US-036 (per-slice timing), US-019 (voice loop), US-021 (barge-in)
**Related decision:** ADR-0018 (latency taxonomy: pilot `p95 < 800 ms`), DEC-010
(per-step latency before any SLO claim), ADR-0010 (industrialization gates)
**Depends on:** TASK-WEB-007, TASK-STT-012, TASK-STT-010, TASK-WEB-004, TASK-WEB-008
**Classification:** V1 pilot gate
**Status:** In progress — Sprint 6 (`sprints/sprint-6-streaming.md`). Delivered:
`time_to_first_audio` composite + `scripts/streaming_latency_report.py` + E2E
`streaming_loop.feature` (297 unit tests, 10 Behave features green); docs
(voice-journey-timing, HTTP contract WebRTC surface, ADR-0018 evidence) + QA report
`docs/qa/streaming-voice-qa-report.md`. Pending: warm live latency sample (fills the
consolidated p50/p95/p99 + ADR-0018 gate outcome), adversarial review, user validation.
**Priority:** High
**Branch:** `task/TASK-WEB-009-streaming-qa-latency`

### Objective

Close the sprint with the consolidated QA + latency evidence: measure and publish
`time_to_first_audio` and every per-slice distribution over the streaming WebRTC
path (warm, web channel), confirm the ADR-0018 **pilot acceptance criterion
`p95 < 800 ms`**, and update the docs/ADR evidence.

### Scope

- Behave scenarios: end-to-end streaming loop (partials + first-audio) + barge-in.
- A repeatable latency sample over the streaming path (extends
  `scripts/turn_latency_sample.py`) reporting `time_to_first_partial`,
  `time_to_final`, streamed `tts_first_audio`, `time_to_first_audio` and the full
  per-slice p50/p95/p99 (sample size, min/max/mean, warm/cold, provider config).
- QA report `docs/qa/streaming-voice-qa-report.md` (functional + latency +
  go/no-go), comparing against the Sprint 1–5 batch baseline.
- Update `docs/observability/voice-journey-timing.md`,
  `docs/architecture/voice-runtime-http-contract.md` (WebRTC signaling surface) and
  the **ADR-0018 evidence** (measured `p95 < 800 ms` or the honest gap if not met).
- Live Chrome DevTools MCP re-validation of the streaming loop + barge-in (manual QA;
  closes the streaming half of RF-019).

### Acceptance Criteria

```gherkin
Scenario: The streaming loop meets the pilot latency acceptance criterion
  Given a warm streaming WebRTC session on the web channel
  When a reviewed sample of turns is measured
  Then time_to_first_audio p95 is reported below 800 ms (or the gap is stated honestly)
  And every pipeline slice is measured (p50/p95/p99) under one correlation id
```

### Required Evidence

- Behave green (streaming + barge-in); per-slice + `time_to_first_audio` report.
- QA report published; docs + ADR-0018 evidence updated; no code-only contract for
  the new WebRTC surface.
- Go/no-go recommendation for the streaming voice pilot.

---

## TASK-WEB-010 - End The Call On A Customer Closing Formula (US-041)

**Parent:** EPIC-006 (+ EPIC-010)
**Related story:** US-041 (end the call when the customer signals they are done),
US-019 (voice runtime)
**Related decision:** ADR-0002 (streaming voice path); a dedicated ADR is required
if intent-based detection or a confirmation step is chosen (see open questions)
**Depends on:** streaming STT (TASK-STT-010, merged), streaming TTS (TASK-WEB-004,
merged), graceful pipeline drain on call end (delivered with TASK-WEB-008)
**Classification:** V1 core
**Status:** ✅ Done (validated live by the user 2026-07-27) — adversarial review ≥90%,
QA acceptance and user live validation all passed; **US-041 → Done**.
Deterministic no-LLM `ClosingIntentDetector`
(`web_voice/closing_intent.py`, word-boundary token matching, negation + embedded-request
guards) + `CallEndFarewellProcessor` (`web_voice/call_end_farewell.py`) inserted on a new
`pre_answer` seam of `StreamingVoiceSession`. Confirmation turn + bounded confirmation-scoped
silence timer (`VOICE_FAREWELL_CONFIRM_TIMEOUT_S`); ending reuses the TASK-WEB-008 `drain()`
path via a signaling teardown callback; `voice.call_end` reason telemetry
(`customer_farewell` vs `client_stop`/`client_drop`) under the call correlation id. FR phrase
sets env-tunable (`VOICE_FAREWELL_ENABLED/PROMPT/CLOSING/PHRASES/DONE_PHRASES`). ADR-0035.
Tests: 384 voice-agent unit (+28: `test_closing_intent`, `test_call_end_farewell`, signaling
wiring) + Behave `call_end_farewell.feature` (2 scenarios) green.
**Priority:** Medium
**Branch:** `task/TASK-WEB-010-call-end-farewell`

### Objective

Let the bot **end the call cleanly when the customer signals they are done**
(closing formulas such as "au revoir", "merci c'est tout", "bonne journée"):
detect the closing intent on a final transcript, speak a short closing message,
then terminate the streaming session — instead of leaving the customer to hang up
manually (US-041).

### Context (why this is needed)

Today a call only ends when the customer closes the browser tab / drops the
WebRTC session (`session.stop()` → graceful drain added in TASK-WEB-008). There is
no conversational way to end a call, which feels unnatural and leaves the channel
open. This is the customer-facing counterpart to barge-in on the conversation
lifecycle. It reuses the existing streaming STT final transcript, TTS for the
closing message, and the drain/teardown machinery already in place.

### Decisions (2026-07-16, user)

- **Hybrid detection** (DEC-041-b): a config-tunable FR closing-phrase list + an
  anti-false-positive guard (standalone phrase, word-boundary match, reject
  negations like "non, pas au revoir"). No LLM intent classifier in V1.
- **Confirmation step** (DEC-041-a): on a detected closing, the bot asks
  "Souhaitez-vous autre chose ?" and ends only on a positive confirmation / silence.
- **Unscheduled**: kept in backlog, not attached to Sprint 6 (off the latency theme).

### Scope

- Detect a customer closing on a **final** transcript (not partials) via a
  config-tunable FR closing-phrase list.
- **False-positive protection (BR-041-1):** word-boundary match, reject closing
  words embedded in a longer request or negated ("non, pas au revoir"). Mirror the
  barge-in echo lesson: naive `contains()` matching is fragile.
- **Confirmation turn (BR-041-2):** speak "Souhaitez-vous autre chose ?", then end
  the call only on a positive confirmation of being done (or silence); otherwise
  continue the conversation.
- Speak a short closing message via TTS, then terminate the streaming session
  gracefully after the closing message drains (reuse the TASK-WEB-008 drain path).
- **Telemetry (BR-041-3):** record the end-of-call reason as a distinct value
  (e.g. `customer_farewell`) vs manual/`client_stop` vs error/drop, under the turn
  correlation id; emit an OpenTelemetry event/span for pilot review.
- FR closing formulas in V1 (BR-041-4); phrase set externalizable (env-tunable),
  consistent with the barge-in thresholds pattern.

### Out Of Scope

- Phone / Genesys hangup semantics (deferred to the contact-center integration).
- Silence-timeout-based end of call (candidate separate story — OQ-041-c).
- Backend conversation-summary generation on call end (separate concern).

### Acceptance Criteria

```gherkin
Scenario: Customer says a closing formula and the call ends cleanly
  Given the streaming voice loop is active and the customer has their answer
  When the customer clearly says a closing formula (for example "au revoir")
  Then the bot asks whether they need anything else
  And when the customer confirms they are done (or stays silent)
  Then the bot plays a short spoken closing
  And the streaming session ends gracefully
  And the end-of-call reason is recorded as customer_farewell for pilot review
```

```gherkin
Scenario: A closing word inside a longer request does not end the call
  Given the streaming voice loop is active
  When the customer uses a closing word as part of a longer sentence
  Then the call is not ended
  And the turn is answered normally
```

### Required Evidence

- Developer tests: closing-intent detection fires on standalone closing, not on
  embedded/negated closing; end-of-call reason set correctly; teardown path taken.
- Behave scenario for the end-of-call outcome (composed STT → intent → TTS →
  graceful drain), reusing the TASK-WEB-008 single-phase harness pattern.
- OpenTelemetry evidence: end-of-call event with reason under the turn correlation id.
- Live Chrome DevTools MCP validation: closing formula ends the call after the
  spoken closing; embedded closing word does not.
- When validated live by the user, **US-041 → Done**.

### Open Questions

- OQ-041-a / OQ-041-b: **resolved** (see Decisions above).
- OQ-041-c: silence-timeout end of call — kept as a separate future story.
- OQ-041-d: V1 channel boundary = web session close only (phone/Genesys deferred).

---

## TASK-WEB-011 - Pre-Warm / Reuse The TTS WebSocket To Cross The ADR-0018 Gate

**Parent:** EPIC-006, EPIC-010
**Related stories:** US-036 (the `tts_first_audio` slice + `time_to_first_audio`), US-019 (web voice)
**Related decisions:** ADR-0018 (pilot latency criterion), ADR-0023 (streaming transport)
**Builds on:** TASK-WEB-004 (streaming TTS), TASK-STT-013 (STT finalize tail solved; isolated the residual gap)
**Classification:** V1 pilot gate — **the expected-final lever to meet ADR-0018 `p95 < 800 ms`**
**Status:** Implemented (2026-07-17) — **ADR-0018 gate MET**. TTS WebSocket pre-warmed off the per-turn critical path: `tts_first_audio` p95 **484 → 381 ms**, `time_to_first_audio` p95 **853 → 761.5 ms → GO (+38.5 ms)** with a stub backend. Adversarial review **93/100 (Pass)** — no blocking findings (2026-07-17). QA acceptance **GO** (2026-07-17): 315 unit / 10 Behave features (26 scenarios) green + ADR-0018 gate re-confirmed (`streaming-voice-qa-report.md`). **Validated by user (2026-07-17)** — merged into `feat/sprint-6-streaming`.
**Priority:** High (latency-driven; sprint-blocking for the ADR-0018 gate)
**Branch:** `task/TASK-WEB-011-tts-prewarm`

### Objective

Remove the per-turn TTS WebSocket connect from the `time_to_first_audio` critical
path so the composite crosses the ADR-0018 pilot criterion of **p95 < 800 ms** warm
on the web channel.

### Context (why this is needed)

After TASK-STT-013 finalized streaming STT on the `flushed` ack, the STT tail is no
longer the bottleneck (p95 373 ms). The post-fix warm baseline
(`docs/qa/streaming-latency-warm-postfix.json`, 8 turns, stub backend) measures
`time_to_first_audio` **p50 827 ms / p95 853 ms** — a **−53 ms** miss on the gate.
The residual is now `tts_first_audio` (p95 484 ms), and the streaming TTS processor
(`web_voice/streaming_tts_processor.py`) starts its `voice.tts.first_audio` timer
**before** `await provider.open()`, so the span includes a **fresh TTS WebSocket
connect + setup every turn**. Measured directly (6 runs): TTS `open()` ~90 ms warm
(~188 ms cold); the first chunk after open is ~350 ms (inherent Gradium TTS
latency). Taking the ~90 ms connect off the per-turn path projects `tts_first_audio`
p95 ~484 → ~394 ms and **composite p95 ~853 → ~763 ms → PASS**.

### Scope

- Pre-warm and/or reuse the streaming TTS WebSocket so the connect + setup handshake
  is **not** on the per-turn critical path (e.g. open at session start / keep a warm
  connection across turns, re-warm after a drop).
- Keep the `voice.tts.first_audio` span semantics honest: still measure EOT → first
  playable chunk; the connect simply no longer happens per turn on that path.
- Handle connection lifecycle safely: drop/reconnect, barge-in cancellation
  (TASK-WEB-008), and the no-audio/empty/failure invariants stay intact (never invent
  audio; key never logged).
- Re-measure warm with `scripts/streaming_latency_report.py` (N large enough for a
  meaningful p95) and update the ADR-0018 evidence + streaming QA report go/no-go.

### Out Of Scope

- Reducing the inherent Gradium TTS first-chunk latency (~350 ms) — provider-side.
- Real backend answer time (`backend_first_token`) — still the Sprint 5 stub/http
  backend for this measurement.
- STT finalize tail (TASK-STT-013, done).

### Acceptance Criteria

```gherkin
Scenario: The streaming voice loop meets the ADR-0018 pilot latency criterion
  Given the streaming WebRTC voice runtime with a pre-warmed/reused TTS connection
  When a warm sample of turns is measured on the web channel
  Then time_to_first_audio p95 is below 800 ms
  And the per-slice p50/p95/p99 baseline is published
  And no audio is invented and no safety invariant is regressed
```

If pre-warming does **not** bring p95 below 800 ms, the alternative acceptance is an
explicit Product/Architecture revision of the ADR-0018 criterion recorded in the ADR
(not a silent weakening).

### Required Evidence

- Unit tests for the pre-warm/reuse lifecycle (open-at-start, reuse across turns,
  reconnect after drop, barge-in) with a fake WS.
- A re-measured warm sample + updated ADR-0018 evidence and streaming QA report.
- Adversarial review ≥ 90% + QA acceptance + user validation before merge.

### Delivery Evidence (2026-07-17)

- **Root cause confirmed live:** Gradium's TTS WebSocket is **single-use** — a 2nd
  `synthesize()` on one connection fails ("connection failed"), so it cannot be
  *reused*; but it can be *pre-warmed*. The `voice.tts.first_audio` timer started
  before `provider.open()`, baking a fresh ~90 ms connect (measured warm; ~188 ms
  cold) into every turn.
- **Implementation:** `voice-agent/web_voice/tts_session_warmer.py` — `TtsSessionWarmer`
  keeps one spare session opening/opened off the per-turn path: `start()` (idempotent)
  begins the open, `acquire()` hands out the ready spare (or opens on demand if
  none/failed), `aclose()` discards an unused spare (cancel pending / close opened —
  no leaked connection). `StreamingTtsProcessor` (`prewarm=True` default) warms on
  `StartFrame`, hands out the spare + pre-opens the next in `_acquire_session`, and
  releases the spare on `EndFrame`/`CancelFrame`. All safety invariants unchanged
  (never invents audio; key never logged; barge-in cancellation intact; a bad spare
  falls back to on-demand open, an on-demand failure still surfaces `tts.failure`).
- **Tests:** +8 `TtsSessionWarmer` unit (`tests/test_tts_session_warmer.py`:
  start→acquire uses the spare with one open; on-demand fallback; idempotent start;
  fallback when spare open failed; propagate on-demand failure; aclose closes an
  opened spare / cancels a pending open / no-op with no spare) and +2 processor
  prewarm tests (uses the pre-opened spare & releases the unused one; falls back on
  spare-open failure). Existing processor tests opt out (`prewarm=False`). Full suite
  **315 unit / 10 Behave features (26 scenarios)** green; no lint.
- **Live re-measurement (`docs/qa/streaming-latency-warm-prewarm.json`, 8 warm turns,
  WebRTC, stub backend):** `tts_first_audio` p50/p95 365/**381 ms** (was 457/484);
  `time_to_first_audio` p50/p95 739/**761.5 ms** (was 827/853). **ADR-0018 gate: GO
  (p95 761.5 ms < 800 ms, margin +38.5 ms).** Full arc: 1698 ms (−898) → 853 ms (−53)
  → 761.5 ms (+38.5). Stub-backend + `channel_egress` caveats still apply.
- ADR-0018 evidence + streaming QA report updated with the gate-met baseline.

### Adversarial Review (2026-07-17, covers TASK-STT-013 + TASK-WEB-011)

- **Verdict: Proceed. Score 93/100 — QA gate Pass.** No blocking findings.
- **Functional/architecture:** ADR-0018 gate met (p95 761.5 ms); `TtsSessionWarmer`
  stays in the `web_voice` composition layer, provider behind its adapter, STT
  finalize-on-`flushed` guarded by `_flush_id > 0` with `end_of_stream`/`error`
  fallbacks. No boundary violation; class/method sizes within budget.
- **Tests:** STT-013 +2 (finalize-on-`flushed` no word loss + `end_of_stream`
  fallback); WEB-011 +8 warmer + 2 processor prewarm. Suite 315 unit / 10 Behave
  green, 0 lint.
- **Security:** API key stays in the provider connect header only; warmer never
  handles text/keys; no new logging. Clean.
- **Non-blocking findings (accepted residual):**
  1. Pre-warm hit/miss is not surfaced as a distinct telemetry signal (silent
     fallback to on-demand open on a spare failure) → recommend a `tts.prewarm`
     warm/miss metric; the `voice.tts.first_audio` slice itself stays fully measured.
  2. `TtsSessionWarmer.aclose()` catches `BaseException` around `await task`
     (teardown best-effort) → could narrow to `Exception` + re-raise `CancelledError`.
  3. Narrow race: a cancel landing exactly during `acquire()`'s await of the warm
     task can orphan one spare (server reaps the idle WS) — very rare.
  4. Processor prewarm coverage is single-turn; add a 2-turn chain test + a
     barge-in-with-prewarm QA scenario.
- **Residual risk accepted:** gate measured with a **stub backend**, **N=8**, and
  `channel_egress` excluded — the pilot gate is met for the EOT→first-audio
  streaming path as specified, not an end-to-end production SLO.

---

## TASK-WEB-014 - Instrument True Mouth-To-Ear Latency (Fold Channel-Egress + End-Of-Turn Hold)

**Parent:** EPIC-010 (+ EPIC-006)
**Related stories:** US-036 (per-slice timing), US-019 (voice loop), US-021 (barge-in timing)
**Related decisions:** ADR-0029 (pilot criterion revised to mouth-to-ear p95 ≤ 1.5 s /
`time_to_first_audio` p95 ≤ 1.2 s — this ticket is its **measurement prerequisite**),
ADR-0018 (latency taxonomy + the `channel_egress` / end-of-turn known gap), DEC-010
(per-step latency before any SLO claim), ADR-0010 (industrialization gates)
**Depends on:** TASK-WEB-007 (WebRTC transport), TASK-WEB-009 (streaming composite
report — done), TASK-BE-010 (real-backend composite baseline)
**Classification:** V1 pilot gate
**Status:** ✅ Merged into `feat/restart-from-scratch` (2026-07-23) — instrumentation +
reporting + dev tests + docs done on `task/TASK-WEB-014-mouth-to-ear-latency`; unittest
**334** green, behave **10 features / 26 scenarios / 120 steps** green. `voice_to_first_audio`
mouth-to-ear composite (EOT hold + STT + backend + TTS + `channel_egress`), `ChannelEgressProbe`
emitting `web.voice.egress` on the WebRTC streaming path, ADR-0029 gate in
`streaming_latency_report`, and a client-side first-audible proxy. Closes the
ADR-0018 / TASK-WEB-009 `channel_egress` + end-of-turn known gap. **Remaining before
pilot sign-off:** capture a **warm live sample against the real backend** and record
measured `voice_to_first_audio` p50/p95/p99 vs the ADR-0029 gate — an out-of-sprint
pre-pilot measurement in the pilot-readiness latency theme (off the billing theme, now
Sprint 10); voice + backend are frozen so the sample stays valid whenever run. Adversarial
review + QA go/no-go pending.
**Priority:** High
**Branch:** `task/TASK-WEB-014-mouth-to-ear-latency`

### Objective

Measure and report the **true perceived (mouth-to-ear) latency** — from the instant
the customer stops speaking to the instant they **hear** the first agent audio — over
the streaming WebRTC path, by folding in the two slices currently **excluded** from
ADR-0018's `time_to_first_audio` composite: the **end-of-turn silence hold** and
**`channel_egress`** (WebRTC first frame → audible at the browser). This is the
ADR-0029 prerequisite: no pilot latency acceptance is recorded against a partial
composite.

### Context (why this is needed)

ADR-0018's `time_to_first_audio` starts at **end-of-turn acceptance** and ends at the
**first playable frame emitted by the runtime**. It therefore excludes:

- the ~500 ms trailing-silence **`end_of_turn` hold** before acceptance (measured as
  its own span, but not part of the composite); and
- **`channel_egress` on WebRTC** — the `web.voice.egress` span is emitted only on the
  **batch HTTP** path; the WebRTC transport egress → browser-audible add-on is not
  folded in (ADR-0018 "known gap").

The market measures **mouth-to-ear** (ADR-0029 baseline). Comparing our middle-of-chain
composite (~1.41 s p95, real backend, BE-011) to end-to-end market numbers understates
real perceived latency (~2 s today once the hold + egress are added). ADR-0029 revises
the pilot criterion to **mouth-to-ear p95 ≤ 1.5 s** (primary) plus a
**`time_to_first_audio` p95 ≤ 1.2 s** engineering sub-target, so the perceived metric
must actually be instrumented before any go/no-go.

### Scope

- Define and emit a **mouth-to-ear** composite (`voice_to_first_audio` =
  `end_of_turn` hold + `time_to_first_audio` + `channel_egress`) per turn under one
  correlation id, in `voice_common/pipeline_timing.py`, **alongside** the existing
  `time_to_first_audio` composite (do not overwrite it).
- Instrument **`channel_egress` on the WebRTC streaming path** (first synthesized
  frame handed to the transport → audible at the browser). Browser-audible timing may
  require a small client-side measurement (first-audio playback timestamp) posted back
  or logged; if true browser-audible is not reachable, measure **runtime egress**
  (first frame written to the transport) and state the residual gap honestly.
- Report **p50/p95/p99** for the mouth-to-ear metric and every slice (`end_of_turn`,
  `stt`, `backend_first_token`, `tts_first_audio`, `channel_egress`) with sample size,
  min/max/mean, warm/cold, channel and provider config — measured with the **real
  backend** (not the stub).
- Evaluate against **ADR-0029**: mouth-to-ear p95 ≤ 1.5 s (primary) and
  `time_to_first_audio` p95 ≤ 1.2 s (engineering). Publish a go/no-go.
- Fold in the remaining **OQ-005** sub-items: which journeys count toward the pilot
  metric, the fixture-vs-live provider mix, and which component is authoritative for
  barge-in cancellation timing.
- Update the ADR-0018 evidence + ADR-0029 + `docs/qa/streaming-voice-qa-report.md` +
  `docs/observability/voice-journey-timing.md`.

### Out Of Scope

- **Reducing** latency (answer-engine + provider work) — this ticket **measures**.
- Speech-to-speech evaluation (its own ADR per ADR-0029).
- Production SLO operational controls (ADR-0010).

### Acceptance Criteria

```gherkin
Scenario: Mouth-to-ear latency is measured end to end
  Given a warm streaming WebRTC session on the web channel with the real backend
  When a reviewed sample of turns is measured
  Then the mouth-to-ear latency (end-of-turn hold + composite + channel egress) is reported p50/p95/p99 under one correlation id
  And it is evaluated against the ADR-0029 criteria (mouth-to-ear p95 <= 1.5 s, time_to_first_audio p95 <= 1.2 s)
  And no slice is silently omitted (a missing slice is marked measured=false with a reason)
```

```gherkin
Scenario: Channel egress is folded into the perceived latency
  Given the WebRTC streaming path
  When a turn produces spoken audio
  Then channel_egress is measured on the WebRTC path (not only the batch HTTP path)
  And it is included in the mouth-to-ear metric, or the residual gap is stated honestly
```

### Required Evidence

- Developer tests for the mouth-to-ear composite computation (fake spans) and for
  `channel_egress` emission on the WebRTC path.
- A warm live sample with the **real backend**; per-slice + mouth-to-ear p50/p95/p99.
- Updated ADR-0018 / ADR-0029 evidence + streaming QA report go/no-go.
- **Closes the ADR-0018 / TASK-WEB-009 `channel_egress` + end-of-turn known gap.**
- No API key / raw audio / path leak.

---

## TASK-WEB-015 - Perceived-Latency Optimization Levers (Backend-Stream-To-TTS, Connect-Time Warm-Up, End-Of-Turn Hold)

**Parent:** EPIC-010 (+ EPIC-004, EPIC-005)
**Related stories:** US-036 (per-slice timing), US-019 (voice loop), US-040 (pilot readiness)
**Related decisions:** ADR-0029 (pilot criterion: mouth-to-ear p95 ≤ 1.5 s /
`time_to_first_audio` p95 ≤ 1.2 s — the target this ticket optimizes toward),
ADR-0012 (**modular cascade reaffirmed for V1** — so lever 1 below is a keeper, not
throwaway), OQ-005 ("OpenAI" in V1 = cascade chat provider, **not** Realtime
speech-to-speech), TASK-WEB-011 (TTS pre-warm — the precedent for lever 2)
**Depends on:** TASK-WEB-014 (mouth-to-ear measurement — **optimize against a real
instrumented baseline, not blind**)
**Classification:** V1 pilot gate (perceived latency)
**Status:** Proposed (2026-07-20, from the Sprint 7 demo) — **out-of-sprint
pilot-readiness follow-up**, kept **off the billing theme**
(identity/BSS/PDF/comparison, now Sprint 10); schedule in the pilot-readiness latency
pass, after TASK-WEB-014 has published the mouth-to-ear baseline.
**Priority:** High
**Branch:** `task/TASK-WEB-015-perceived-latency-levers` (to be created when scheduled)

### Objective

**Reduce** the perceived time-to-first-audio on the streaming WebRTC path (TASK-WEB-014
**measures** it; this ticket **lowers** it), targeting the ADR-0029 sub-target
`time_to_first_audio` p95 ≤ 1.2 s and contributing to the mouth-to-ear p95 ≤ 1.5 s
primary criterion.

### Context (measured baseline — Sprint 7 demo, 2026-07-20)

Live streaming WebRTC turns against the **real backend** (Gradium STT/TTS streaming +
Mistral chat + Ollama embeddings + pgvector), time-to-first-audio decomposed **from
the instant the customer stops speaking**:

| Slice | 1st turn (cold) | Warm turn | Note |
|---|---:|---:|---|
| End-of-turn hold (trailing silence) | 500 ms | 500 ms | fixed window, env-tunable |
| STT finalize (`time_to_final`) | 851 ms | 496 ms | STT streaming session cold on turn 1 |
| **Backend `/converse` (full answer)** | **1224 ms** | **1121 ms** | biggest slice; `backend.first_token == backend.request` → runtime waits the **whole** answer before TTS |
| TTS first audio (`time_to_first_audio`) | 375 ms | 379 ms | already pre-warmed (TASK-WEB-011) ✅ |
| **≈ time-to-first-audio** | **~2950 ms** | **~2496 ms** | excludes WebRTC client playback/jitter (see TASK-WEB-014) |

Cold-start penalty ≈ **+450 ms** on turn 1 (STT session open + first LLM call);
TTS is flat (~375 ms) thanks to TASK-WEB-011.

### Scope (the three levers, largest impact first)

1. **Backend answer streaming → TTS on the first sentence** (~ −700 to −900 ms,
   every turn). Today the runtime calls the blocking `POST /api/conversation/converse`
   and waits for the **complete** LLM answer (~1.1–1.2 s) before any TTS. The backend
   already exposes an **SSE streaming** endpoint (`GET /api/conversation/ask-stream`)
   that is unused by the voice path. Consume the stream and hand the **first
   sentence-sized, guardrail-passing chunk** to the streaming TTS as soon as it is
   ready, so first audio starts on the first sentence instead of the full answer.
   Valid for V1 because ADR-0012 reaffirms the modular cascade (not caduc under the
   OpenAI move — OQ-005: V1 OpenAI = cascade chat provider).
2. **Connect-time warm-up of the STT streaming session + first LLM/embedding call**
   (~ −450 ms on turn 1). Symmetric to TASK-WEB-011 (TTS pre-warm): when the WebRTC
   session connects, open a throwaway STT stream and fire a tiny LLM/embedding warm
   call so the **first real turn** is already warm. Provider-agnostic, low risk.
3. **End-of-turn hold tuning** (~ −150 ms). Make the ~500 ms trailing-silence window
   env-tunable down to ~350 ms and evaluate the premature-cut / false-endpoint
   trade-off with real audio. Lowest-risk-to-implement but **highest behavioural
   risk** (premature cuts) — gate on a measured false-cut rate.

### Out Of Scope

- **Measuring** mouth-to-ear (that is TASK-WEB-014, the prerequisite).
- Speech-to-speech / Realtime evaluation (its own ADR per ADR-0029; not V1).
- Provider swap to OpenAI chat (ADR-0006 / DEC-011 track).

### Acceptance Criteria

```gherkin
Scenario: Backend answer is streamed to TTS on the first sentence
  Given a warm streaming WebRTC session on the web channel with the real backend
  When the customer asks a KB-grounded question
  Then TTS starts on the first guardrail-passing sentence, not on the full answer
  And the measured time_to_first_audio p95 improves against the TASK-WEB-014 baseline
  And grounding + guardrail behaviour (DEC-002, no invented amounts) is unchanged
```

```gherkin
Scenario: The first turn no longer pays the full cold-start penalty
  Given a freshly connected WebRTC session
  When the very first turn is measured
  Then its time-to-first-audio is within a stated margin of a warm turn
  And no STT/LLM connection is leaked by the warm-up
```

### Required Evidence

- Developer tests for the streaming-to-TTS first-sentence seam (fake SSE + fake TTS)
  and the connect-time warm-up lifecycle (open-at-connect, reuse, no leak).
- A warm + cold live sample with the **real backend**, per-slice + composite
  p50/p95/p99, compared against the TASK-WEB-014 baseline (before/after per lever).
- Updated ADR-0029 evidence + `docs/qa/streaming-voice-qa-report.md` go/no-go.
- False-cut rate report for lever 3 if the hold is reduced.
- No API key / raw audio / path leak.

---

## TASK-WEB-016 - OpenAPI Spec For The Python Voice Runtime (`web_voice`)

**Parent:** EPIC-006 (Voice2Voice) — cross-cutting API hardening
**Related:** TASK-BE-016 (OpenAPI for the Java backend)
**Classification:** V1 hardening
**Status:** Implemented (2026-07-28, Sprint 9) — hand-written OpenAPI 3.0.3 spec
`voice-agent/web_voice/openapi.yaml` describing every `/api/voice/*` endpoint
(`stt`, `tts`, `turn`, `webrtc/offer`) plus the meta spec route: audio bodies
(`audio/pcm` in, `audio/wav` out), query-param envelope (`conversation_id`,
`session_id`, `correlation_id`, `language`), the full `/turn` `X-Voice-*`/`X-Answer-*`
response headers incl. degraded contract, the two error shapes (`VoiceErrorBody`
client-safe, `GuardError` for size/route/webrtc guards) and the 413/502/503 codes —
all verified 1:1 against `server.py` (25 MiB / 5000-char guards, port 8090, exact
`error_code`s). Served at `GET /api/voice/openapi.yaml` (`application/yaml`) via the
stdlib handler. Tests: `tests/test_voice_openapi.py` (5) — structural validity, schema
contract, a **drift guard** asserting documented paths == the server route constants,
and a live serve+parse round-trip. unittest **390** green (full `discover`, incl. the
5 new spec tests), behave unaffected (non-runtime doc/spec surface).
Adversarial review ~95/100 (no blocking findings; one test rename for accuracy). The
spec mirrors `docs/architecture/voice-runtime-http-contract.md` (source of truth).
**QA: Go** — `docs/qa/task-web-016-voice-openapi-qa.md`: both AC met; the committed
**and the live-served** bytes pass the industry-standard `openapi-spec-validator`
(added as a test-only dep); a Behave discovery scenario (`web_voice.feature`, +1) starts
the runtime, fetches `GET /api/voice/openapi.yaml` (`application/yaml`, 13 629 B), schema-
validates it and asserts documented paths == server routes; unittest **390** green, behave
**30 scenarios / 140 steps** green. Latency N/A (static meta route, not a journey slice).
**Merged** into `feat/restart-from-scratch` (2026-07-28, merge commit `a2be7a5`) as part of the
Sprint 9 closure; post-merge integration green (backend 305, unittest 390, behave 30/140).
**Priority:** Medium
**Branch:** `task/TASK-WEB-016-voice-openapi`

### Context

The Java backend can auto-generate OpenAPI via springdoc (TASK-BE-016), but the
Python voice runtime (`web_voice`) serves `/api/voice/*` on the **stdlib
`http.server`** with **no framework**, so there is no auto-generated spec.

### Objective

Publish an OpenAPI (Swagger) description for the voice runtime HTTP surface so all
project APIs are documented consistently.

### Scope

- Hand-write an OpenAPI YAML for `/api/voice/stt`, `/api/voice/tts`,
  `/api/voice/turn` and the WebRTC signaling route, derived from the single source of
  truth [docs/architecture/voice-runtime-http-contract.md](../../docs/architecture/voice-runtime-http-contract.md)
  (request/response shapes, headers, error contract, flags).
- Serve/version the spec (static path or committed file) and keep it in sync with the
  contract doc.

### Acceptance

- A valid OpenAPI document describes every `web_voice` endpoint (paths, params,
  request/response, error shape, correlation-id headers).
- The spec matches the HTTP contract doc; drift is caught in review.

---

## TASK-WEB-017 - Per-Turn Identity On WebRTC Streaming Telemetry (enable per-turn latency)

**Parent:** EPIC-006 (Voice2Voice) — observability hardening
**Related:** US-036 (per-slice latency), ADR-0028 (backend observability correlation),
TASK-WEB-013 (telemetry import unification), TASK-WEB-014 (mouth-to-ear latency),
`docs/architecture/channel-identity-boundary.md` (identity fields)
**Classification:** V1 hardening (observability)
**Status:** Implemented (2026-07-23, Sprint 9) — per-turn identity baggage on
`TelemetryRecorder.begin_turn(...)`, advanced by the turn owner (`StreamingSttProcessor`
on the live path, `UtteranceAggregator` on the batch-bridge path) at each end-of-turn; the
recorder stamps `conversation_id`/`message_id`/`turn_index` on **every** span/event/metric/log
of the turn (STT, backend, TTS, channel egress) while `correlation_id` stays per-conversation.
`pipeline_timing` buckets by `(correlation_id, turn_index)` (positional-zip fallback for
spans without a per-turn id) and adds `per_turn_timings`; `streaming_latency_report.py` gains
a `per_turn` section. unittest **346** green (+12), behave **27** green (+1 multi-turn
`streaming_loop.feature` scenario driving the real STT→backend→TTS processors and asserting
every slice span carries a per-turn id). Adversarial review **93/100**. QA passed —
`docs/qa/task-web-017-per-turn-telemetry-qa.md`: the `per_turn` report separates turns end to
end via `scripts/streaming_per_turn_sample.py` (2 calls × 3 paced turns → 6 distinct rows,
distinct `message_id` under one `correlation_id`, one `time_to_first_audio` per turn),
barge-in turn → null composite with no desync, no key/audio/path leak in telemetry. Warm **live**
sample captured (Gradium STT/TTS + Mistral over WebRTC, call `3bcf0fac…`): `turn_index` 1/2/3,
3 distinct `message_id` under one `conversation_id`, every slice span once per turn; real per-turn
`time_to_first_audio` 5154/5740/5350 ms. All Required Evidence satisfied — **done** (SLO latency is a
separate STT-finalize concern owned by TASK-STT-010/011, not WEB-017).
**Priority:** Medium
**Branch:** `task/TASK-WEB-017-streaming-per-turn-telemetry-id`

### Context

On the **WebRTC streaming** path a single `ChannelEnvelope` is created **per session**
(`web_voice/webrtc_signaling.py:164`, `ChannelEnvelope.for_web_turn(...)`), and the streaming
telemetry emitters propagate **only** `correlation_id` (+`channel`) —
`web_voice/streaming_stt_processor.py:240/256`, `web_voice/streaming_tts_processor.py:233`,
`web_voice/utterance_aggregator.py:126`. They drop `conversation_id` and `message_id` even
though the envelope already carries them. Consequently:

- the session-end telemetry flush **stacks all turns' spans keyed by span name**, so per-turn
  slices (`stt.request`, `voice.tts.first_audio`, …) overwrite each other within a call;
- `conversation_id` and `message_id` come out **`None`** on the streaming path;
- `scripts/streaming_latency_report.py` / `voice_common/pipeline_timing.py` (which group by
  span name) cannot separate turns, so **per-turn p50/p95/p99 cannot be derived from a
  multi-turn browser session** (verified live 2026-07-23, session `b4fa2735…`: 3 turns, one
  flush, all identity keys except `correlation_id` null).

The **batch** path (`web_voice/server.py:273`) already creates a fresh envelope per turn and
emits the full identity set, so it is unaffected.

### Objective

Make each turn on the streaming path **individually traceable** while keeping the
**conversation-level `correlation_id` stable** (that stability is desirable — it lets us follow
the whole dialogue end to end). Enable per-turn latency distributions from live/browser sessions.

### Scope

- Allocate a **per-turn id** (a fresh `message_id` and/or a monotonic turn index) at each
  detected end-of-turn on the streaming path, without minting a new `correlation_id`.
- Stamp that per-turn id (+ `conversation_id`, `channel`) on **all** streaming spans/events
  (STT processor, TTS processor, utterance aggregator, channel egress probe).
- Update `voice_common/pipeline_timing.py` / `scripts/streaming_latency_report.py` to bucket
  slices **by turn id**, then aggregate p50/p95/p99 across turns.
- Align with `docs/architecture/channel-identity-boundary.md` (correlation vs conversation vs
  message id) and update `docs/observability/voice-journey-timing.md`.

### Out Of Scope

- The batch `/api/voice/turn` path (already correct — one envelope per request).
- Backend `conversation_id` memory semantics (owned by the Java backend).
- Changing the meaning/stability of `correlation_id` (it stays per-conversation).

### Acceptance Criteria

- Each streaming turn's spans/events carry a **unique per-turn id** plus the **stable
  per-conversation `correlation_id`**; `conversation_id`/`message_id` are no longer `None` on
  the streaming path.
- `streaming_latency_report.py` produces **per-turn** slice distributions (p50/p95/p99) from a
  single multi-turn WebRTC session, without turns overwriting each other.
- The conversation trace remains followable end to end (correlation stability unchanged).
- Developer tests cover the per-turn id allocation and the by-turn aggregation.

### Required Evidence

- Developer tests (per-turn id lifecycle on the streaming path; by-turn bucketing in the report).
- A multi-turn live (or headless `scripts/webrtc_live_client.py`) sample showing **distinct
  per-turn slices** in the report from one session.
- Updated `docs/observability/voice-journey-timing.md`.
- No API key / raw audio / path leak in telemetry.

**Evidence status (2026-07-23):**
- ✅ Developer tests — `test_telemetry_turn_baggage.py`, `test_streaming_stt_processor.py`,
  `test_utterance_aggregator.py`, `test_pipeline_timing.py` (per-turn lifecycle + by-turn bucketing).
- ✅ Multi-turn sample showing distinct per-turn slices — Behave `streaming_loop.feature` #2
  (real processors) + `scripts/streaming_per_turn_sample.py` → `streaming_latency_report.py`
  `per_turn` section (offline, repeatable). See `docs/qa/task-web-017-per-turn-telemetry-qa.md`.
- ✅ Updated `docs/observability/voice-journey-timing.md`.
- ✅ No API key / raw audio / path leak — offline + live dump attribute scan (id/latency/provider/outcome only).
- ✅ **Warm live** multi-turn sample (Gradium STT/TTS + Mistral over WebRTC) — one call `3bcf0fac…`,
  `conversation_id 1e5b912d…`, `turn_index` 1/2/3, 3 distinct `message_id`, every slice span once per
  turn (no overwrite). Real per-turn `time_to_first_audio` 5154/5740/5350 ms (p50 5350 / p95 5740),
  mouth-to-ear p50 5850 / p95 6240 ms; `barge_in_count=2` yet all turns cleanly separated. Full numbers
  in `docs/qa/task-web-017-per-turn-telemetry-qa.md`. (Composite p95 exceeds ADR-0018/0029 gates due to
  ~4 s Gradium STT finalize — pre-existing, owned by TASK-STT-010/011, out of WEB-017 scope.)

---

## TASK-WEB-018 — Speak A Degraded Fallback On Streaming STT Failure

**Parent:** EPIC-006 (Voice2Voice journey foundation)
**Classification:** V1 hardening (degraded mode)
**Status:** ✅ QA validated (2026-07-28) on `task/TASK-WEB-018-streaming-stt-degraded-fallback`
— adversarial review and functional QA both passed; merge-ready (pending explicit merge request).
Live Gradium-voice confirmation of the spoken fallback is deferred to pilot (validated
deterministically with fakes here).
**Priority:** Medium
**Branch:** `task/TASK-WEB-018-streaming-stt-degraded-fallback`
**Surfaced by:** full adversarial code+doc review 2026-07-28
(`docs/architecture/reviews/full-adversarial-review-2026-07-28.md`, medium functional finding).
**Relates to:** TASK-WEB-006 (generic voice error responses / RF-013), ADR-0021 (degraded
answer contract), ADR-0023 (streaming STT finalization), ADR-0025 (barge-in / interruption).

### Context

There is a **behavioural asymmetry** between the two transports on STT failure:

- **Batch `/turn` (HTTP):** an STT failure returns a **502 JSON** (`server.py`), so the
  caller knows the turn failed.
- **Streaming WebRTC:** on STT finalize timeout/error, `_emit_stt_failure`
  (`voice-agent/web_voice/streaming_stt_processor.py:218-222, 303-315`) records telemetry
  but **does not push a `TranscriptionFrame`** — so the answer step never runs and no
  degraded fallback is spoken. The call can go **silent** on a real STT failure, which is
  worse than the batch path.

### Objective

Make streaming STT failure **audible and safe**: when finalize fails, the customer hears
the safe degraded fallback (or an explicit end-of-call), consistent with the degraded
policy already used everywhere else (no invented amount, no fabricated transcript).

### Scope

- On streaming STT finalize timeout/error, drive the existing degraded path: emit a
  degraded answer turn (reusing `conversation_backend/degraded.py`
  `DEGRADED_FALLBACK_TEXT`) through TTS, or a bounded, explicit end-of-call, instead of
  silently swallowing the failure.
- Keep the failure telemetry (`stt` slice `outcome=error`, correlation id / turn id) and
  add a `voice.stt.degraded_spoken` (or equivalent) outcome event so QA can observe that
  a fallback was actually spoken.
- Do not fabricate a transcript; the degraded text must remain digit/currency-free
  (DEC-002) and language-appropriate.
- Ensure barge-in/interruption interaction stays correct (a degraded utterance is still
  interruptible).

### Acceptance

- A simulated streaming STT finalize failure results in a **spoken** degraded fallback
  (or explicit end-of-call), never silence — proven by a unit test on
  `StreamingSttProcessor` and a Behave scenario.
- The `stt` slice still records `outcome=error` with the correlation id / `turn_index`,
  plus a new outcome event proving the fallback was spoken.
- No transcript fabrication; degraded text is digit/currency-free.
- `./.venv/bin/python -m unittest discover tests` + `./.venv/bin/behave` green.

### Notes

- This closes the batch-vs-streaming degraded-mode gap noted in the review; pair the QA
  wording with TASK-WEB-006 (generic error surfaces) so client-facing behaviour is
  consistent across transports.

### Implementation notes (2026-07-28)

Delivered on `task/TASK-WEB-018-streaming-stt-degraded-fallback` (branched from
`feat/restart-from-scratch`):

- **`StreamingSttProcessor._finalize` failure branch now speaks a fallback.** On a
  `StreamingSttError` **or** `asyncio.TimeoutError` from `session.finish()` /
  `wait_final()`, after `aclose()` + the existing `stt.failure` telemetry, the processor
  calls the new `_speak_degraded_fallback(direction)` which pushes a **plain `TextFrame`**
  carrying `conversation_backend.DEGRADED_FALLBACK_TEXT` downstream. Both TTS stages
  (`TtsFrameProcessor`, `StreamingTtsProcessor`) synthesise plain `TextFrame`s (exact-type
  allowlist), so the customer hears the safe fallback instead of silence. **No transcript
  is fabricated** — a `TranscriptionFrame` is never emitted on failure, so the answer/LLM
  step is not driven with invented text; the digit/currency-free text satisfies DEC-002.
- **Barge-in preserved:** the fallback is a normal bot answer, so the output transport
  emits `BotStartedSpeakingFrame` upstream and the existing anti-echo barge-in gate makes
  the degraded utterance interruptible with no extra code (TASK-WEB-008 path unchanged).
- **Observability:** kept the `stt` slice `outcome=error` (`stt.failure` event + `stt.request`
  span with the correlation id / turn id) and added a new **`voice.stt.degraded_spoken`**
  outcome event + **`voice.stt.degraded_spoken.count`** metric (attrs: correlation_id,
  channel, provider, `degraded_reason="stt_finalize_failed"`) so QA can distinguish "spoke a
  safe fallback" from a silent call.
- **Tests (`./.venv/bin/python -m unittest discover tests` = 391 green;
  `./.venv/bin/behave` = 11 features / 31 scenarios / 146 steps green):**
  - `test_streaming_stt_processor.py`: `test_provider_error_speaks_degraded_fallback`
    (StreamingSttError → no final, fallback spoken, digit-free, `voice.stt.degraded_spoken`
    event+metric with the correlation id) and `test_finalize_timeout_speaks_degraded_fallback`
    (`asyncio.TimeoutError` via a stalled `wait_final` + small `final_timeout_s`). The sink
    now captures plain `TextFrame`s (exact type) alongside interims/finals.
  - `streaming_stt.feature`: new scenario "A streaming STT finalize failure speaks the safe
    degraded fallback" (no final transcript, fallback spoken, no digit/amount, degraded-spoken
    event observable).
- **Architecture:** `web_voice` (composition layer) may import `conversation_backend`
  (`streaming_runtime` already does); `test_architecture_separation` stays green (the STT/TTS
  half-separation and `conversation_backend` neutrality rules are untouched).

### QA validation (2026-07-28)

QA (skill `qa-functional-latency`) — **GO** (deterministic; no live Gradium in this QA env):

- **Functional (failure → audible fallback):** `test_streaming_stt_processor.py` — 12 unittests
  green, including `test_provider_error_speaks_degraded_fallback` (StreamingSttError → **no** final
  transcript, plain `TextFrame` fallback spoken, **digit/currency-free** per DEC-002,
  `voice.stt.degraded_spoken` event + metric with correlation id) and
  `test_finalize_timeout_speaks_degraded_fallback` (`asyncio.TimeoutError`). No transcript is
  fabricated; barge-in remains intact.
- **BDD regression:** Behave `streaming_stt.feature` — 2 scenarios / 9 steps green, incl.
  "A streaming STT finalize failure speaks the safe degraded fallback".
- **Full suite re-run:** `./.venv/bin/python -m unittest discover tests` and `./.venv/bin/behave`
  green (see counts below).
- **Latency:** the fallback is on the **exceptional** STT-failure path, not an SLO journey — it
  replaces a silent call with a short fixed TTS phrase; no pipeline-slice latency claimed.
- **Residual (non-blocking / info):** live-voice (Gradium streaming) confirmation of the spoken
  fallback deferred to pilot; the failure→spoken-fallback contract is fully covered by fakes.
