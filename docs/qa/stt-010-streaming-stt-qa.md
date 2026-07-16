# QA Functional And Latency Report — TASK-STT-010 (Streaming STT)

## Executive Summary
- **Overall readiness:** Go for pilot use on the streaming web voice path.
- **Main blockers:** none.
- **Residual risks:** (1) first-word warmup clipping from Gradium `delay_in_frames`
  (~800 ms) — a transcription-quality follow-up, not a latency blocker; (2) a
  WebSocket is opened per turn (setup/teardown cost) — future reuse optimization.

## Scope Tested
- **Epics / stories:** EPIC-006 / EPIC-010, US-036 (`stt` slice: time-to-first-partial
  + time-to-final), US-019 (web voice).
- **Ticket:** TASK-STT-010 — streaming/incremental STT over Gradium WebSocket ASR.
- **Finding:** RF-007 (chunked/streaming ingress transport) — **Closed** by this ticket.
- **Channels:** web voice (WebRTC streaming path).
- **Providers / fakes:** unit + Behave use a fake WebSocket / fake streaming provider
  (no network); the live gate uses **Gradium streaming STT** + stub backend over a real
  `SmallWebRTCTransport`.
- **Environment:** local, `voice-agent/.venv`, `pipecat-ai[webrtc]`, macOS, warm.

## Functional Results
| Area | Status | Evidence | Notes |
|---|---|---|---|
| Partials stream during speech (`InterimTranscriptionFrame`) | Pass | `test_streaming_stt_processor.test_streams_partials_then_final_on_silence_window`; `streaming_stt.feature` #1; live run | First partial ~1.25 s into the utterance |
| Final transcript produced after end-of-turn | Pass | same as above; live `stt.transcript.final` | One final `TranscriptionFrame` per turn |
| `time_to_first_partial` + `time_to_final` observable via OTel | Pass | `..._emits_end_of_turn_and_stt_spans`; `streaming_stt.feature` #1; live events | metrics `stt.time_to_first_partial_ms`, `stt.time_to_final_ms` |
| `voice.end_of_turn` span owned by the streaming processor | Pass | live: one span, `signal=silence_window`, `provider=gradium-stt-streaming` | Same contract as the aggregator it replaces |
| WS opened only once speech starts (no inter-turn silence stream) | Pass | `..._silence_only_never_opens_a_session` (`open_count == 0`) | `detector.has_speech` gate |
| Sub-minimum click discarded (no turn) | Pass | `..._sub_minimum_click_is_discarded` | Session opened then closed, no final |
| Safe failure on server error / transport drop | Pass | `test_streaming_stt_provider` (error + drop → `StreamingSttError`); `..._provider_error_degrades_without_final` | `stt.failure` recorded, no final frame, no crash |
| API key never in a frame/log/telemetry | Pass | `..._setup_sent_first_without_key`, `..._api_key_travels_only_in_connect_header` | Key only in the connect header |
| Batch REST path + stdlib/fixture path unchanged | Pass | batch provider untouched; `--stt-mode batch` keeps the aggregator; full suite green | Fallback preserved |

Regression net: **241 unit tests OK**; **Behave 7 features / 21 scenarios / 95 steps**.

## Latency Results
Live WebRTC round trip, **Gradium streaming STT**, stub backend, one correlation id
`4cad4bbf…`, warm, single sample. Padded clip = `fixtures/long/invoice-breakdown.pcm`
(5.45 s speech) + 1.6 s low-amplitude noise tail (peak ≪ 1000, avoids Opus DTX).

| Slice | Value | Sample | Warm/Cold | Notes |
|---|---:|---:|---|---|
| **stt (`stt.request`)** = post-end-of-turn tail = `time_to_final` | **818 ms** | 1 | Warm | vs ~3.4 s batch (extrapolated from 2.7 s @ 4.3 s) → ~**4× cut** |
| time_to_first_partial | **1249 ms** | 1 | Warm | first partial arrives *during* speech (utterance is 5.45 s) |
| end_of_turn (`voice.end_of_turn`) | 500 ms | 1 | Warm | deterministic silence-window confirmation hold (TASK-STT-012) |
| backend (`backend.request`, stub) | ~0 ms | 1 | Warm | stub backend; real backend measured elsewhere |
| tts_first_audio (`voice.tts.first_audio`, Gradium) | ~0.9 s | 1 | Warm | provider latency, unchanged |

> The headline result is the **`stt` slice tail: 818 ms** live, matching the spike's
> 0.78 s and confirming the ~4× perceived-latency cut over batch. `time_to_first_partial`
> is not a post-speech cost — it is when live captions/partials begin, mid-utterance.
> A single warm sample is sufficient here to prove the mechanism; full p50/p95/p99 by
> slice is TASK-WEB-009 scope.

## Observability
- `stt.request` span (duration = `time_to_final`), `stt.transcript.final` /
  `stt.unavailable` / `stt.failure` events, `stt.time_to_first_partial_ms` +
  `stt.time_to_final_ms` metrics, and the `voice.end_of_turn` span — all carry the
  per-call correlation id and `provider=gradium-stt-streaming`. The WebRTC telemetry
  log now includes metrics alongside spans/events.

## Findings
| Severity | Finding | Rationale | Owner |
|---|---|---|---|
| Info | First-word warmup clipping (`delay_in_frames` ~800 ms; spike dropped `Pouvez`) | Transcription-quality tuning (lead-in buffer / `delay_in_frames` / `padding_bonus`), independent of the latency objective | QA follow-up |
| Info | One WebSocket per turn (setup/teardown) | Meets the tail target already; reuse/multiplex is a future optimization | Backlog (out of sprint) |
| Info | Live latency is a single warm sample | Proves the mechanism; percentiles are TASK-WEB-009 | QA (sprint close) |

## Gate Decision
- **Go.** Functional ACs met (partials during speech, final after end-of-turn, both
  latency metrics observable), safe-failure paths covered, key hygiene preserved, batch
  fallback intact, and the live tail (818 ms) confirms the ~4× latency win. RF-007 closed.
