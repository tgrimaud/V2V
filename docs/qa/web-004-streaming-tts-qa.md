# QA Functional And Latency Report — TASK-WEB-004 (Streaming TTS)

## Executive Summary
- **Overall readiness:** Go for pilot use on the streaming web voice path.
- **Main blockers:** none.
- **Residual risks:** (1) a WebSocket is opened per turn (setup/teardown cost) —
  future reuse optimization; (2) `web.voice.egress` slice still not measured on the
  WebRTC path (TASK-WEB-009); (3) barge-in cancellation of an in-flight stream is
  TASK-WEB-008.

## Scope Tested
- **Epics / stories:** EPIC-006 / EPIC-010, US-036 (`tts_first_audio` slice), US-019
  (voice-out).
- **Ticket:** TASK-WEB-004 — streaming/incremental TTS over Gradium WebSocket TTS.
- **Channels:** web voice (WebRTC streaming path).
- **Providers / fakes:** unit + Behave use a fake WebSocket / fake streaming provider
  (no network); the live gate uses **Gradium streaming TTS** + streaming STT + stub
  backend over a real `SmallWebRTCTransport`.
- **Environment:** local, `voice-agent/.venv`, `pipecat-ai[webrtc]`, macOS, warm.

## Functional Results
| Area | Status | Evidence | Notes |
|---|---|---|---|
| Playback starts on the first synthesized chunk (incremental `TTSAudioRawFrame`) | Pass | `test_streaming_tts_processor.test_streams_text_as_incremental_audio_frames`; `streaming_tts.feature` #1; live run | Chunks pushed in order as they arrive |
| `time_to_first_audio` observable via OTel | Pass | `..._emits_first_audio_span_and_latency_metrics`; `streaming_tts.feature` #1; live metrics | `voice.tts.first_audio` span + `tts.time_to_first_audio_ms` / `tts.time_to_last_audio_ms` |
| `TranscriptionFrame` forwarded untouched (only answer text synthesized) | Pass | `..._forwards_transcription_frame_untouched` | STT output never re-synthesized |
| `InterimTranscriptionFrame` (streaming partials) never synthesized | Pass | `..._does_not_synthesize_interim_transcription`; live run (1 synthesis/turn) | Regression for the "bot repeats the question" bug (partials inherit from `TextFrame`) |
| Empty answer → UNAVAILABLE, no invented audio | Pass | `..._empty_text_reports_unavailable_without_audio`; `streaming_tts.feature` #2 | `tts.unavailable` (`empty_text`) event, no frames |
| Provider error → FAILED, safe degrade (no audio) | Pass | `..._provider_error_degrades_without_audio` | sanitized `tts.failure`, session closed, no crash |
| Connect/handshake failure at `open()` → FAILED (no silent turn) | Pass | `..._connect_failure_degrades_without_audio` | `provider.open()` wrapped; auth/credit/drop maps to sanitized `tts.failure`, no audio |
| Text present but zero chunks → UNAVAILABLE (`no_audio`) | Pass | `..._zero_chunks_reports_unavailable_without_audio` | never invents audio when the stream is empty |
| API key never in a frame/log/telemetry | Pass | `test_streaming_tts_provider.test_setup_sent_first_without_key`, `..._api_key_travels_only_in_connect_header` | Key only in the connect header |
| Safe error mapping (credits / auth / voice id / drop / unparsable) | Pass | `test_streaming_tts_provider` (5 mapped cases) | Raw payload never surfaced |
| Batch TTS path + stdlib/fixture path unchanged | Pass | batch provider untouched; `--tts-mode batch` keeps `TtsFrameProcessor`; full suite green | Fallback preserved |

Synthesis is an exact-type **allowlist** (`type(frame) is TextFrame`): only a plain
answer frame is spoken; every `TextFrame` subclass is forwarded untouched, so a future
subclass cannot regress into "the bot speaks the question". Per-chunk stall budget
lowered 30 s → **8 s** so a stalled socket degrades within a turn.

Regression net: **261 unit tests OK**; **Behave 8 features / 23 scenarios / 103 steps**.

## Latency Results
Live WebRTC round trip, **Gradium streaming TTS** (+ streaming STT), stub backend,
correlation id `72ab6dfd…`, warm. Padded mic clip = `fixtures/long/billing-question.pcm`
+ low-amplitude noise tail (peak ≪ 1000, avoids Opus DTX). Re-run **after** the
interim-frame fix: exactly **one synthesis per turn** (the answer only), confirming
the "bot repeats the question" defect is gone (previously 9 syntheses/turn because
streaming STT partials were being spoken).

| Slice | Value | Warm/Cold | Notes |
|---|---:|---|---|
| **tts_first_audio (`voice.tts.first_audio`)** = time-to-first-audio | **363 ms** | Warm | vs ~1.59 s whole-clip batch synthesis (ST-1 spike) → ~**4.4× cut** |
| tts time-to-last-audio (`tts.time_to_last_audio_ms`) | 3975 ms | Warm | **not a lag figure** — time to fully stream the whole answer's audio (132 chunks = **10.4 s of speech**, 332,800 B PCM16). Delivery ≈ **2.6× faster than real-time**, so the playback buffer never starves after the first chunk. |
| stt (`stt.request`) = post-end-of-turn tail | 801 ms | Warm | streaming STT (TASK-STT-010), unchanged |
| stt time-to-first-partial (`stt.time_to_first_partial_ms`) | 1240 ms | Warm | first partial during speech |
| voice end-of-turn (`voice.end_of_turn`) | 500 ms | Warm | silence hang time (TASK-STT-012) |

> The headline result is **time-to-first-audio 363 ms** live: the customer hears the
> answer ~1.2 s sooner than waiting for the whole clip (~1.59 s batch), while the full
> 132-chunk answer keeps streaming behind it. `time_to_last_audio` (~3.98 s) is **not**
> a latency regression: the answer is **10.4 s of spoken audio**, so streaming all of
> it in ~4 s means chunks arrive ~2.6× faster than they are played — the buffer stays
> ahead and playback never stalls. (Delivery slower than real-time, ratio < 1×, would
> be the failure mode; here it is ~2×.) A warm single run is sufficient to prove the
> mechanism and the fix; full p50/p95/p99 by slice and the end-to-end
> `time_to_first_audio` (end-of-turn → first playable frame) close are TASK-WEB-009 scope.

## Observability
- `voice.tts.first_audio` span (duration = time-to-first-audio), `tts.audio.final` /
  `tts.unavailable` / `tts.failure` events, and `tts.time_to_first_audio_ms` +
  `tts.time_to_last_audio_ms` metrics — all carry the per-call correlation id and
  `provider=gradium-tts-streaming`. The WebRTC telemetry log includes metrics
  alongside spans/events.

## Findings
| Severity | Finding | Rationale | Owner |
|---|---|---|---|
| Info | One WebSocket per turn (setup/teardown) | Meets the first-audio target already; reuse/multiplex is a future optimization | Backlog (out of sprint) |
| Info | `web.voice.egress` not measured on the WebRTC path | Transport sends frames itself; end-to-end close is TASK-WEB-009 | QA (sprint close) |
| Info | Barge-in cannot yet cancel an in-flight stream | Async-iterator + `aclose()` supports it; interrupt wiring is TASK-WEB-008 | Backlog (Sprint 6) |

## Gate Decision
- **Go.** Functional ACs met (playback on the first chunk, time-to-first-audio
  observable), safe-failure paths covered (no invented audio), key hygiene preserved,
  batch fallback intact, and the live first-audio (~463 ms) confirms the ~3.4×
  latency win over batch synthesis.
