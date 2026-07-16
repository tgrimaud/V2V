# QA Functional And Latency Report — Streaming Voice Loop (Sprint 6 close, TASK-WEB-009)

**Ticket:** TASK-WEB-009 — Streaming QA, latency SLO report and ADR update
**Branch:** `task/TASK-WEB-009-streaming-qa-latency`
**Stories:** US-019 (voice loop), US-036 (per-slice timing), US-021 (barge-in)
**Decision:** ADR-0018 (pilot criterion `time_to_first_audio` p95 < 800 ms)
**Run date:** _to be finalized with the warm live run_

## Executive Summary
- **Overall readiness (functional):** Go — the streaming loop answers end to end
  (partials → answer → incremental first audio), barge-in interrupts playback, and
  error/degraded paths stay safe and observable.
- **Overall readiness (pilot latency):** **Gap to state honestly.** Indicative warm
  single-turn measurements put `time_to_first_audio` at **~1.1–1.2 s**, above the
  ADR-0018 pilot criterion of **p95 < 800 ms**. The dominant cost is the STT
  post-end-of-turn finalize tail (~0.8 s). The consolidated warm p50/p95/p99 sample
  is collected in the live run (below) before the go/no-go is final.
- **Main blockers:** none functional. The pilot latency criterion is not yet met on
  the current streaming path (documented gap, not a silent pass).
- **Residual risks:** (1) `channel_egress` not instrumented on the WebRTC path, so
  the composite covers EOT → first synthesized audio (not the last transport hop);
  (2) one WebSocket per turn (setup/teardown cost); (3) live numbers depend on
  network path to Gradium and warm state.

## Scope Tested
- **Epics / stories:** EPIC-006 / EPIC-010; US-019, US-036, US-021.
- **Channels:** web voice (streaming WebRTC path, `SmallWebRTCTransport`).
- **Providers / fakes:** unit + Behave use fake streaming STT/TTS providers and the
  deterministic stub backend (no network); the latency baseline uses **Gradium
  streaming STT + streaming TTS** + stub backend over a real WebRTC session.
- **Environment:** local, `voice-agent/.venv`, `pipecat-ai[webrtc]`, macOS, warm
  (server process pre-warmed), co-located.

## Functional Results
| Area | Status | Evidence | Notes |
|---|---|---|---|
| Streaming loop answers end to end (partials → answer → incremental first audio) | Pass | `streaming_loop.feature`; live run | Composed streaming STT → answer → streaming TTS, one correlation id |
| Partial transcripts stream during speech | Pass | `streaming_stt.feature` #1; `streaming_loop.feature`; `test_streaming_stt_processor` | `InterimTranscriptionFrame` partials before end-of-turn |
| Final transcript after end-of-turn drives the answer | Pass | `streaming_loop.feature`; `stt.request` span emitted | Final consumed by the answer step (spoken back), not echoed |
| Bot answer starts on the first synthesized chunk | Pass | `streaming_tts.feature` #1; `streaming_loop.feature`; live run | Incremental `TTSAudioRawFrame`s |
| `time_to_first_audio` derivable end to end under one correlation id | Pass | `streaming_loop.feature`; `test_pipeline_timing.TimeToFirstAudioCompositeTest` | Composite = STT tail + backend + TTS first-audio |
| Barge-in interrupts playback and starts the next turn | Pass | `barge_in.feature` #1; `test_streaming_stt_processor` (barge-in) | `InterruptionFrame` broadcast; `tts.interrupted`; `voice.barge_in.detected` |
| Normal turn is not a barge-in (anti-echo gate) | Pass | `barge_in.feature` #2 | Amplitude + sustained-frame gate |
| Empty answer → UNAVAILABLE, no invented audio | Pass | `streaming_tts.feature` #2 | `tts.unavailable` (`empty_text`) |
| STT/TTS/turn error → client-safe 502, no raw provider text | Pass | `test_error_response`, `test_voice_runtime` (TASK-WEB-006) | Stable `error_code` + `correlation_id` + generic `message` |
| Trailing partial utterance drained on call end | Pass | `webrtc_signaling` drain-and-discard; `test_*` | A mid-speech hangup still yields an end_of_turn + final |
| Batch HTTP path + stdlib/fixture path unchanged | Pass | full suite green; `--stt-mode/--tts-mode batch` | Fallbacks preserved |

Regression net: **297 unit tests OK**; **Behave 10 features / 26 scenarios /
120 steps** (adds `streaming_loop.feature`, the `time_to_first_audio` composite
tests, and `streaming_latency_report` tests).

## Latency Results

`time_to_first_audio` composite = `stt` (post-EOT finalize tail) +
`backend_first_token` (answer) + `tts_first_audio` (time-to-first-audio); the
end-of-turn silence hold ends at the composite's start, and `channel_ingress` /
`channel_egress` are batch-HTTP-only (WebRTC gaps). See
[voice-journey-timing](../observability/voice-journey-timing.md) and ADR-0018.

### Indicative warm single-turn (from Sprint 6 slice tickets)
Single warm live turns already measured per slice (Gradium streaming STT + TTS,
stub backend). These indicate the composite; the consolidated distribution is the
live run below.

| Slice / composite | Warm value | Source |
|---|---:|---|
| `voice.end_of_turn` (silence hold, ends at composite start) | ~500 ms | `stt-012-streaming-end-of-turn-qa.md` |
| `stt.request` (post-EOT finalize tail) | ~800 ms | `stt-010-streaming-stt-qa.md` |
| `backend_first_token` (stub) | ~few ms | stub backend, offline |
| `tts_first_audio` (time-to-first-audio) | ~363 ms | `web-004-streaming-tts-qa.md` |
| **`time_to_first_audio` (indicative composite)** | **~1.1–1.2 s** | sum of the post-EOT slices |

> Indicative composite **~1.1–1.2 s > 800 ms** pilot criterion. The dominant cost is
> the STT post-end-of-turn finalize tail (~0.8 s); backend (stub) and TTS first-audio
> are comparatively small. The optimization lever is the STT finalize tail (partial /
> incremental finalization), already reduced from ~3.4 s (batch) to ~0.8 s by
> TASK-STT-010.

### Consolidated warm sample (live run)

| Field | Value |
|---|---|
| Sample size (turns) | _to be filled by the warm live run_ |
| `time_to_first_audio` p50 / p95 / p99 (ms) | _to be filled_ |
| `time_to_first_audio` min / max / mean (ms) | _to be filled_ |
| `stt` p50/p95/p99 (ms) | _to be filled_ |
| `backend_first_token` p50/p95/p99 (ms) | _to be filled_ |
| `tts_first_audio` p50/p95/p99 (ms) | _to be filled_ |
| `channel_ingress` / `channel_egress` | Gap (batch-HTTP-only on WebRTC) |
| Pilot gate (`p95 < 800 ms`) | _to be filled — pass or the honest gap_ |

Collected with the streaming report over server telemetry dumps:

```bash
cd voice-agent
set -a && source ../.env && set +a
python3 -m web_voice.server --host 127.0.0.1 --port 8090 \
  --provider gradium --backend stub --runtime pipecat \
  --webrtc auto --stt-mode streaming --tts-mode streaming 2> /tmp/streaming-telemetry.jsonl
# run N warm turns (browser /static/webrtc.html or scripts/webrtc_live_client.py)
python3 scripts/streaming_latency_report.py --input /tmp/streaming-telemetry.jsonl \
  --channel web --provider gradium-streaming --warm
```

## Component Findings
| Brick | Status | Findings | Next action |
|---|---|---|---|
| Streaming STT | Pass | Partials during speech; finalize tail ~0.8 s dominates the composite | STT partial-finalization optimization (out of sprint) |
| Backend answer | Pass | Stub negligible; a live HTTP backend would add its own slice | Measure with `--backend http` when a live endpoint is available |
| Streaming TTS | Pass | First audio ~363 ms; incremental playback stable | Reuse/multiplex the WebSocket (out of sprint) |
| Barge-in | Pass | Interrupts playback; anti-echo gate holds on normal turns | — |
| Observability | Pass | One correlation id per call; spans + metrics dumped on teardown | — |
| Channel egress (WebRTC) | Gap | Not instrumented on the WebRTC transport | Instrument the last transport hop (follow-up) |

## Defects And Gaps
| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Medium | Composite `time_to_first_audio` indicatively > 800 ms | Pilot latency criterion not yet met on the current path | QA / Architecture (gap stated) |
| Info | `channel_egress` not measured on WebRTC | Composite excludes the last transport hop | Follow-up (out of sprint) |
| Info | One WebSocket per turn | Setup/teardown cost | Backlog (out of sprint) |

## Open Questions
- **Product:** is a functional pilot acceptable with `time_to_first_audio` ~1.1–1.2 s
  while the STT finalize tail is optimized, or is `p95 < 800 ms` a hard pilot gate?
- **Architecture:** should the WebRTC channel-egress hop be instrumented before the
  pilot, or is the EOT → first-synthesized-audio composite sufficient for V1?
- **Technical:** target for the STT post-EOT finalize tail (main lever to reach
  `p95 < 800 ms`).

## Recommendation
- **Functional:** Go — the streaming loop, barge-in and safe-failure paths meet their
  acceptance criteria with unit + Behave regression coverage.
- **Pilot latency:** decision pending the consolidated warm live sample. Indicative
  numbers show the `p95 < 800 ms` criterion is **not yet met** (gap driven by the STT
  finalize tail); the honest gate outcome is recorded here and in ADR-0018 once the
  live sample is collected.
- **Required before an SLO claim (ADR-0010):** per-channel/per-step dashboards,
  alerting, degraded-mode and provider-outage tests — out of this sprint.
