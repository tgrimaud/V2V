# Sprint 4 — Pipecat Runtime Migration (Batch Parity)

## Sprint Objective

Run the existing web voice **batch** loop (STT → echo → TTS) through a **Pipecat
pipeline**, aligning the runtime with the ADR-0002 target and **de-risking the
framework migration before streaming (Sprint 5)**. The user-visible behaviour is
unchanged: the browser keeps its current two-call echo loop and the same pipeline
slices stay observable.

This is a **migration / de-risking** sprint, **not** a latency sprint. Batch-on-Pipecat
is not expected to beat batch-on-stdlib; the value is isolating the runtime swap from
the streaming work and stopping the target-vs-real drift (the code has zero Pipecat
today). Streaming STT/TTS/VAD and the WebRTC transport are **Sprint 5**.

## Status

**Status:** Planned
**Created:** 2026-07-14
**Predecessor:** [`sprint-3-tts-voice-out.md`](sprint-3-tts-voice-out.md) (Sprint 3 — Done, 2026-07-13)
**Working branch:** `feat/sprint-4-pipecat-batch` (from `feat/restart-from-scratch`)
**Final validator:** User
**Merge rule:** no branch is merged unless the user explicitly asks.

## Roadmap Context

| Sprint | Theme | State |
|---|---|---|
| Sprint 1 | STT validation (fixtures → Gradium transcript, timing, QA) | ✅ Done |
| Sprint 2 | STT hardening (quality gate, sanitization, UNAVAILABLE, end-of-turn) | ✅ Done |
| Sprint 3 | TTS / voice-out (batch, non-streaming) → first end-to-end voice loop | ✅ Done (merged → `feat/restart-from-scratch`) |
| **Sprint 4** | **Pipecat runtime migration (batch parity, pipeline-only) — this sprint** | Planned |
| Sprint 5 | Latency optimization: streaming STT (TASK-STT-010) + streaming TTS (TASK-WEB-004) + streaming VAD (TASK-STT-012) + WebRTC transport | Planned |

## Included Tickets

| Ticket | Title | Type | Priority | Story | Sprint role |
|---|---|---|---|---|---|
| TASK-WEB-005 | Introduce the Pipecat batch runtime (pipeline parity) | Technical task | High | US-019 (runtime), US-036 | Wrap Gradium STT/TTS as Pipecat services, run the batch loop through a Pipecat pipeline, keep the stdlib path as a selectable fallback |

## Design Decisions (locked with the user)

- **Migration, not latency.** Deliver behaviour parity with the current stdlib echo
  loop; do not claim or chase a latency improvement this sprint.
- **Transport scope: pipeline-only.** Keep the current `http.server` boundary
  (`POST /api/voice/stt` PCM in, `POST /api/voice/tts` WAV out) and the browser
  (`web_voice/static/*`) **unchanged**. The Pipecat pipeline is driven server-side by
  an **in-memory frame source/sink**. WebRTC transport + Pipecat JS client are coupled
  with streaming → **Sprint 5**.
- **Dual runtime, selectable at startup.** Both implementations coexist and are
  switchable via `--runtime {stdlib,pipecat}` (env fallback `VOICE_RUNTIME`). The
  sprint ships with the default flipped to **`pipecat`**; `stdlib` stays selectable as
  the **fallback / comparison path** (ADR-0016). Because both runtimes delegate to the
  same runners, they produce identical WAV output for the same input.
- **New endpoint `POST /api/voice/turn`** runs the full pipeline (audio → STT → echo →
  TTS → WAV) in one server-side call, alongside the two legacy endpoints. The browser
  stays on the two legacy endpoints this sprint.
- **Delegate to existing runners.** The Pipecat services wrap the untouched
  `SttValidationRunner` / `TtsSynthesisRunner` (no provider fork, old runners not
  deleted) so behaviour, sanitization and telemetry are unchanged.
- **STT/TTS separation stays hard.** `voice_pipeline/stt_service.py` must not import
  `tts_synthesis`; `voice_pipeline/tts_service.py` must not import `stt_validation`.
  Shared code lives only in `voice_common/`. Enforced by the architecture test.
- **~80% reusable foundation.** Wrapping Gradium STT/TTS as Pipecat services + the
  frame/telemetry model carries forward to streaming; only the batch aggregation is
  transitional. Design the services so Sprint 5 = "emit partials" (additive), not a
  rewrite.

## Target Batch Pipeline (server-side, in-memory transport)

```
InMemoryFrameSource → GradiumSttService → EchoProcessor → GradiumTtsService → InMemoryFrameSink
     (audio/text)       (wraps STT runner)  (transcript→text)  (wraps TTS runner)   (collect WAV)
```

Slices emitted into `voice_common/pipeline_timing.py` unchanged: `web.voice.ingress`,
`voice.stt.*`, `voice.tts.first_audio`, `web.voice.egress`.

## Runtime Selection Seam

```
WebVoiceHTTPServer (--runtime)
        │
        ▼
  VoiceTurnProcessor (protocol: transcribe_turn / synthesize_turn / record_egress)
        ├── stdlib  → StdlibTurnProcessor  → WebVoiceIngress + WebVoiceEgress ─┐
        └── pipecat → PipecatTurnProcessor → Pipecat pipeline ─────────────────┤
                                                                                ▼
                                        SttValidationRunner + TtsSynthesisRunner (shared, identical output)
```

## Delivery Order (ST breakdown)

Each ST is one commit (`implement → test → commit`), independently testable, with an
adversarial review, mirroring the Sprint 3 discipline.

- [ ] **ST-1 — Pipecat spike + dependency pin.** Add `pipecat-ai` to
  `voice-agent/requirements.txt` (pin an upper bound, like the `websockets` pin). A
  throwaway script under `voice-agent/scripts/` runs a minimal `Pipeline` +
  `PipelineRunner`/`PipelineTask` with an in-memory source → passthrough → sink; lock
  the exact frame/runner API we depend on (frame types for audio/transcript/text/
  tts-audio, `EndFrame`, how to drive a pipeline to completion off a transport).
  Findings note in `docs/`.
- [ ] **ST-2 — Gradium STT as a Pipecat service (batch).** `voice_pipeline/stt_service.py`:
  a `FrameProcessor` consuming a whole-utterance audio frame, delegating to
  `SttValidationRunner` (no fork), emitting a transcription frame. Imports
  `stt_validation` + `voice_common` only. Fake-provider tests.
- [ ] **ST-3 — Gradium TTS as a Pipecat service (batch).** `voice_pipeline/tts_service.py`:
  a `FrameProcessor` consuming a text frame, delegating to `TtsSynthesisRunner`,
  emitting audio frame(s). Imports `tts_synthesis` + `voice_common` only.
  Fake-transport tests.
- [ ] **ST-4 — Echo processor + pipeline assembly + in-memory runner.**
  `voice_pipeline/echo.py` (transcript → text, reproduces the current echo stub) and
  `voice_pipeline/pipeline.py` composing `source → stt → echo → tts → sink` plus a
  `run_batch_turn(audio_bytes, correlation_id) → wav_bytes` helper. Unit test asserts
  parity of the echo WAV vs the current path.
- [ ] **ST-5 — Telemetry bridge (pipeline slices).** Ensure the services surface
  `voice.stt.*` / `web.voice.ingress` / `voice.tts.first_audio` / `web.voice.egress`
  into `voice_common/pipeline_timing.py` so US-036 measures the same slices unchanged.
  Extend `tests/test_pipeline_timing.py`.
- [ ] **ST-6 — Runtime seam + `--runtime` switch + `/api/voice/turn`.** Extract a
  `VoiceTurnProcessor` protocol in `web_voice/server.py`; add `StdlibTurnProcessor`
  (wraps the untouched ingress/egress) and `PipecatTurnProcessor` (drives the
  pipeline); `main()` adds `--runtime {stdlib,pipecat}` (env fallback `VOICE_RUNTIME`).
  Both legacy endpoints keep the exact contract on either runtime. Add
  `POST /api/voice/turn` (full pipeline in one call). No frontend edits. Intermediate
  default stays `stdlib`; the shipped default is flipped in ST-9.
- [ ] **ST-7 — Architecture separation test extended.** Extend
  `tests/test_architecture_separation.py`: `voice_pipeline/stt_service.py` must not
  import `tts_synthesis`, `voice_pipeline/tts_service.py` must not import
  `stt_validation`; the composing `pipeline.py` may import both.
- [ ] **ST-8 — A/B parity harness (stdlib vs pipecat).** A comparison script/test
  runs the same input through both runtimes, asserts identical WAV output and reports
  both runtimes' slice latencies (repeatable comparison artifact; supports the
  ADR-0016 comparison-path role).
- [ ] **ST-9 — Flip default to `pipecat` + QA + behave + docs.** Flip the shipped
  default runtime to `pipecat` (stdlib stays selectable). Behave features green through
  **both** runtimes (parameterized or a dedicated parity scenario). Chrome DevTools MCP
  re-validate the echo loop on the default (`pipecat`) runtime + record latency (expect
  parity, not improvement). Update `voice-agent/README.md` (document `--runtime`,
  default `pipecat`), `docs/observability/voice-journey-timing.md`, the ADR-0002 branch
  note (Pipecat now the default batch runtime, pipeline-only, no WebRTC, stdlib kept as
  fallback), and `docs/architecture/architecture.md` if it states "no Pipecat".

## Branch Plan

The sprint branch `feat/sprint-4-pipecat-batch` is cut from `feat/restart-from-scratch`.
Ticket work is developed on its own branch cut from the sprint branch and merged back
once validated (per the repository branching strategy).

| Ticket | Branch | Status |
|---|---|---|
| TASK-WEB-005 | `task/TASK-WEB-005-pipecat-batch` | Planned |

## Out Of Sprint

| Ticket / Item | Reason |
|---|---|
| TASK-STT-010 (streaming STT) | Latency optimization — **Sprint 5**, built with the WebRTC transport. |
| TASK-WEB-004 (streaming TTS) | Incremental playback (time-to-first-audio) — **Sprint 5**. |
| TASK-STT-012 (streaming VAD end-of-turn) | Real-time turn detection — **Sprint 5**, prerequisite of the streaming path. |
| SmallWebRTCTransport + Pipecat JS client | The real-time transport is coupled with streaming — **Sprint 5**; this sprint keeps the HTTP boundary and browser unchanged. |
| TASK-WEB-003 (backend bridge) | Real LLM/RAG answer — needs a backend; this sprint keeps the echo/stub text. |
| US-020 (quick acknowledgement), US-021 (barge-in) | Depend on streaming and/or backend orchestration. |

## Sprint Acceptance Criteria

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

## Open Questions (to resolve during the sprint)

- **Exact `pipecat-ai` frame/runner API** for driving a pipeline to completion off a
  transport (in-memory source/sink) — locked in ST-1.
- **`pipecat-ai` version** to pin (latest stable + upper bound) — decided at ST-1.
