# QA Functional And Latency Report — TASK-STT-012 (Streaming VAD end-of-turn)

## Executive Summary
- **Overall readiness:** Go for pilot use on the streaming web voice path.
- **Main blockers:** none.
- **Residual risks:** `client_stop` flush on abrupt call drop is not reached over
  WebRTC (teardown cancels the task rather than sending an `EndFrame`); low impact
  because the silence-window signal covers normal turn completion.

## Scope Tested
- **Epics / stories:** EPIC-006 / EPIC-010, US-036 (`end_of_turn` slice), US-019.
- **Ticket:** TASK-STT-012 — streaming/frame-incremental VAD end-of-turn detection.
- **Channels:** web voice (WebRTC streaming path).
- **Providers / fakes:** unit + Behave use fakes/fixtures; live gate uses **Gradium
  STT** + stub backend over a real `SmallWebRTCTransport`.
- **Environment:** local, `voice-agent/.venv`, `pipecat-ai[webrtc]`, macOS, warm.

## Functional Results
| Area | Status | Evidence | Notes |
|---|---|---|---|
| End-of-turn fires from streamed frames before full buffer | Pass | `test_streaming_end_of_turn.py`, `streaming_end_of_turn.feature` #1 | Fires on the frame completing the silence window |
| `voice.end_of_turn` span recorded with turn correlation id | Pass | `test_utterance_aggregator.test_records_end_of_turn_span_on_flush`; live run | One span, one correlation id |
| No boundary invented on a silent stream (TASK-STT-009 guarantee) | Pass | `test_streaming_end_of_turn.test_no_speech_never_invents_a_turn`; `..._no_span_when_stream_has_no_speech`; feature #2 | No span, no flush |
| No duplicate span (batch detector skipped on streaming path) | Pass | `test_web_voice_ingress.test_detect_end_of_turn_false_skips_the_span`; live run shows exactly one `voice.end_of_turn` span | Double-span guard |
| Same span/attribute contract as batch (TASK-STT-009) | Pass | Live attrs: `end_of_turn_signal=silence_window`, `trailing_silence_ms`, `speech_end_ms`, `provider=gradium-stt` | Contract preserved |
| Client-stop fallback (`finish()`) | Pass (unit) / Not reached (live WebRTC drop) | `test_..._finish_flushes_pending_speech_as_client_stop` | See residual risk |
| Batch/stdlib path unchanged | Pass | `test_web_voice_ingress` batch end-of-turn tests still green | Default `detect_end_of_turn=True` |

Regression net: **226 unit tests OK**; **Behave 6 features / 19 scenarios / 86 steps**.

## Latency Results
Live WebRTC round trip, Gradium STT, one correlation id `d33e416d…`, warm, single sample:

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| channel_ingress (`web.voice.ingress`) | 0.001 ms | — | — | 1 | Warm | transport-measured |
| **end_of_turn** (`voice.end_of_turn`) | **500 ms** | — | — | 1 | Warm | **This ticket.** Semantic confirmation hold = silence window (configurable); `signal=silence_window`, `trailing_silence_ms=500`, `speech_end_ms=2919` |
| stt (`stt.request`, Gradium) | 2700 ms | — | — | 1 | Warm | provider latency, unchanged |
| backend (`backend.request`, stub) | 0.022 ms | — | — | 1 | Warm | stub |
| tts_first_audio (`voice.tts.first_audio`, Gradium) | 3781 ms | — | — | 1 | Warm | provider latency, unchanged |

**Detector compute overhead (micro-benchmark, 360k frames):** ~**6 µs per 20 ms
frame** (0.03 % of real time), ~1.1 ms per turn — negligible; the `end_of_turn`
slice latency is the configurable silence-window confirmation hold, not compute.

> The `end_of_turn` slice is a semantic confirmation hold (deterministic = the
> silence window), not a provider round trip; a large percentile sample adds no
> information for this slice. The p95<800 ms `time_to_first_audio` pilot target is
> a **sprint-close (TASK-WEB-009)** measurement gated on streaming STT/TTS, not on
> this turn-detection ticket.

## Component Findings
| Brick | Status | Findings | Next action |
|---|---|---|---|
| `StreamingEndOfTurnDetector` | Pass | Frame-incremental; fires before full buffer; no-speech safe; click discard; per-turn reset | — |
| `UtteranceAggregator` | Pass | Delegates detection, emits span at real streaming moment, buffers + flushes utterance | — |
| Ingress double-span guard | Pass | `transcribe_turn(detect_end_of_turn=False)` skips batch span; verified live (1 span) | — |
| Observability | Pass | Same `voice.end_of_turn` span/event contract; correlation id continuity across all slices | — |

## Defects And Gaps
| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Low | `finish()` client-stop not reached on WebRTC call drop (cancel, not `EndFrame`) | Trailing partial utterance lost on mid-speech hangup; silence-window covers normal completion | Dev (future ticket / TASK-WEB-008) |
| Info | Live latency is a single warm sample | Percentiles not meaningful for a deterministic hold; full p50/p95/p99 is TASK-WEB-009 scope | QA (sprint close) |

## Open Questions
- Product: none.
- Architecture: none.
- Technical: whether to emit a graceful `EndFrame` on normal WebRTC call end so
  `finish()` can flush a trailing partial — deferred (out of AC).

## Recommendation
- **Go / No-go:** **Go** — functional acceptance and observability validated on the
  live WebRTC path; no blocking defects.
- **Required fixes before pilot:** none from this ticket. The `time_to_first_audio`
  p95 pilot gate and full per-slice percentile baseline are measured at sprint
  close (TASK-WEB-009) once streaming STT/TTS land.
