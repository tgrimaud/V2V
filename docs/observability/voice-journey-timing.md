# Voice Journey Timing By Pipeline Slice (US-036)

**Story:** US-036 - Measure key voice journey timings by pipeline slice
**Parent:** EPIC-010
**Module:** `voice-agent/voice_common/pipeline_timing.py` (neutral, shared; re-exported by `stt_validation.pipeline_timing` for the STT CLI/tests)
**Status:** Delivered on branch `us/US-036-voice-timing-slices`

## Purpose

Let a reviewer assess the voice journey **slice by slice** instead of as one
opaque latency number, and expose p50/p95/p99 over a reviewed sample of turns.
Slices that are not yet instrumented are reported as explicit gaps
(`"measured": false` + a reason) so a missing measurement can never be mistaken
for a fast one.

## Canonical slices

The journey is reported in flow order (`PIPELINE_SLICES`):

| Slice | Span source | Status |
|---|---|---|
| `channel_ingress` | `web.voice.ingress` (web) or `stt.audio.accept` (fixture) | Instrumented |
| `end_of_turn` | `voice.end_of_turn` (batch ingress + streaming aggregator + streaming STT processor) | Instrumented (TASK-STT-009 batch, TASK-STT-012 streaming) |
| `stt` | `stt.request` (batch: transcription call; streaming: post-end-of-turn tail = `time_to_final`) | Instrumented (TASK-STT-010 streaming) |
| `backend_first_token` | `backend.first_token` (streaming) or `backend.request` (batch) | Instrumented (TASK-WEB-003-D/E) |
| `tts_first_audio` | `voice.tts.first_audio` (batch runner; streaming: time-to-first-audio) | Instrumented (TASK-WEB-002 batch, TASK-WEB-004 streaming) |
| `channel_egress` | `web.voice.egress` (web voice runtime) | Instrumented (TASK-WEB-002) |

For `channel_ingress` the first present span wins: a web turn uses
`web.voice.ingress`; a fixture-only run falls back to `stt.audio.accept`. The two
never mix into the same distribution.

### End-of-turn detection (TASK-STT-009)

The web voice runtime owns turn detection (`web_voice/end_of_turn.py`). For the
V1 batch web path the **authoritative signal is a trailing-silence window** over
the captured PCM16; if the buffer ends before a full window has elapsed the
detector falls back to an **explicit client stop**.

On the **streaming WebRTC path (TASK-STT-012)** the drop-in replacement has
landed: `StreamingEndOfTurnDetector` consumes audio **frame by frame** and fires
the same `EndOfTurnResult` / `voice.end_of_turn` span contract as soon as the
silence window follows speech — *before* the whole utterance buffer exists — with
a `client_stop` fallback on stream end (`finish()`). It is driven by the
`UtteranceAggregator`, which emits the span and flushes the utterance; the batch
`EndOfTurnDetector` inside `WebVoiceIngress` is then skipped
(`transcribe_turn(detect_end_of_turn=False)`) so the span is recorded exactly
once. The batch detector stays the default for the stdlib/fixture path.

The emitted `voice.end_of_turn` span duration is the end-of-turn **slice
latency**: the confirmation hold after speech ends (the silence window, or the
residual trailing silence on a client stop). Span attributes carry
`end_of_turn_signal` (`silence_window` / `client_stop`), `trailing_silence_ms`
and `speech_end_ms`. A buffer with **no usable speech** invents no turn boundary:
no span is emitted (a `voice.end_of_turn.absent` event is recorded instead), so
the slice is reported as a gap for that turn rather than a fabricated latency.

### Streaming STT (TASK-STT-010)

On the streaming WebRTC path a `StreamingSttProcessor`
(`web_voice/streaming_stt_processor.py`) replaces the `[UtteranceAggregator ->
batch SttFrameProcessor]` pair. It streams audio to the Gradium **WebSocket** ASR
(`GradiumStreamingSttProvider`) *while the customer speaks* — pushing
`InterimTranscriptionFrame` partials as they arrive — and finalizes on the
`StreamingEndOfTurnDetector` end-of-turn (which this processor now owns, emitting
the `voice.end_of_turn` span on this path). Because most audio is transcribed
during speech, the `stt.request` span measures only the **post-end-of-turn tail**
(`time_to_final`) — live ~0.8 s vs ~3.4 s for the batch REST call on a clip this
long. The processor also emits `time_to_first_partial` and `time_to_final` (as
records + `stt.time_to_first_partial_ms` / `stt.time_to_final_ms` metrics) so the
`stt` slice reports both. Selected with `server --stt-mode streaming` (Gradium
only, default); `--stt-mode batch` keeps the aggregator path. A server error or
mid-turn transport drop degrades safely (`stt.failure`, no final frame). See
ADR-0023 and `docs/qa/stt-010-streaming-stt-qa.md`.

### Streaming TTS (TASK-WEB-004)

On the streaming WebRTC path a `StreamingTtsProcessor`
(`web_voice/streaming_tts_processor.py`) replaces the batch `TtsFrameProcessor`. It
streams the answer text to the Gradium **WebSocket** TTS
(`GradiumStreamingTtsProvider`) and pushes each `TTSAudioRawFrame` *as it arrives*,
so playback starts on the first synthesized chunk instead of after the whole clip.
The `voice.tts.first_audio` span (same name the batch runner emits, so the
`tts_first_audio` slice needs no change) now measures **time-to-first-audio** — live
~0.46 s vs ~1.59 s for the batch whole-clip synthesis (~3.4x cut). The processor
also emits `tts.time_to_first_audio_ms` and `tts.time_to_last_audio_ms` metrics (+ a
`tts.audio.final` event with the chunk count). A non-success outcome never invents
audio: empty text → `tts.unavailable`, a provider error → sanitized `tts.failure`,
nothing flows downstream. Selected with `server --tts-mode streaming` (Gradium only,
default); `--tts-mode batch` keeps the batch processor. See ADR-0024 and
`docs/qa/web-004-streaming-tts-qa.md`.

### Streaming loop composite: `time_to_first_audio` (TASK-WEB-009)

ADR-0018 defines the pilot acceptance metric `time_to_first_audio` as the latency
from the moment the runtime **accepts the end of the user's turn** to the **first
playable audio frame** emitted back to the same channel. On the streaming WebRTC
path the `voice.end_of_turn` span *ends* at that acceptance point, so the composite
is the sum of the sequential post-end-of-turn slices that lead to the first audio
frame:

```
time_to_first_audio = stt (post-EOT finalize tail)
                    + backend_first_token (answer)
                    + tts_first_audio (time-to-first-audio)
```

`voice_common.pipeline_timing.time_to_first_audio_report(spans)` computes it
per-turn: spans are grouped by `(correlation_id, turn_index)` (TASK-WEB-017), so on
the streaming path each turn is its own bucket with one span per slice and a turn
missing a component (e.g. a barge-in turn with no final answer) is skipped **without
desyncing the other turns**. Legacy/batch spans that carry no `turn_index` fall back
to per-correlation grouping with positional zip (the k-th of each slice = turn k). It
reports p50/p95/p99 over the sample and the ADR-0018 gate (`p95 < 800 ms`).

**WebRTC-path egress (TASK-WEB-014):** `channel_egress` (`web.voice.egress`) is now
also emitted on the WebRTC streaming path by the `ChannelEgressProbe`
(`web_voice/channel_egress_probe.py`), placed between the TTS processor and the
transport output. It times the **runtime egress** of the *first* audio frame of each
spoken turn (frame → transport output), reusing the batch span name so
`PipelineTimingReport` measures the slice on both paths. It re-arms after each
`BotStoppedSpeakingFrame`, so a multi-turn call yields one egress sample per turn.
`channel_ingress` (`web.voice.ingress`) stays batch-HTTP-only for now.

**Honest residual gap:** the probe measures runtime egress (hand-off to the
transport), **not** the full browser-audible add-on (RTP encode/packetize + network
+ jitter buffer + playout), which is not server-observable. The
`scripts/webrtc_live_client.py` headless client logs a client-side **first-audible
proxy** (`mouth_to_ear_proxy_ms`) — the browser-received end-to-end number — to close
that residual gap during a live sample.

### Mouth-to-ear composite: `voice_to_first_audio` (TASK-WEB-014, ADR-0029)

`time_to_first_audio` starts at end-of-turn **acceptance**; the market measures
**mouth-to-ear** (ADR-0029) — from the instant the customer stops speaking to the
first agent audio they *hear*. `voice_to_first_audio` folds back the two slices
`time_to_first_audio` excludes:

```
voice_to_first_audio = end_of_turn (trailing-silence hold, pre-acceptance)
                     + stt + backend_first_token + tts_first_audio
                     + channel_egress (runtime egress, WebRTC; folded when present)
```

`voice_common.pipeline_timing.voice_to_first_audio_report(spans)` computes it per
turn (same `(correlation_id, turn_index)` bucketing, positional-zip fallback for
spans without a per-turn id). `end_of_turn` + the post-EOT path are
**required**; `channel_egress` is folded **per turn when present** and reported as an
explicit residual gap otherwise — a missing egress span is never silently treated as
zero. `scripts/streaming_latency_report.py` reports it alongside `time_to_first_audio`
and evaluates the **ADR-0029 gate**: mouth-to-ear p95 ≤ 1.5 s (primary) + a
`time_to_first_audio` p95 ≤ 1.2 s engineering sub-target (overall `not_measured` when
either composite has no complete turn — never a silent pass).

### Per-turn identity on the streaming path (TASK-WEB-017)

The WebRTC streaming path builds **one** `ChannelEnvelope` + **one** `TelemetryRecorder`
per call, so a single stable `correlation_id` spans the whole conversation (desirable —
it lets us follow the dialogue end to end). Before TASK-WEB-017 the streaming emitters
propagated only `correlation_id`, so `conversation_id`/`message_id` came out `None` and
every turn's spans shared the same key — turns could only be separated by a fragile
positional zip, which desyncs as soon as a turn is missing a slice (e.g. a barge-in).

The turn owner (`StreamingSttProcessor` on the live path, `UtteranceAggregator` on the
batch-bridge path) now calls `TelemetryRecorder.begin_turn(conversation_id, message_id,
turn_index)` at each detected end-of-turn. The recorder merges that per-turn baggage
into **every** subsequent span/event/metric/log of the turn (STT, backend, TTS, channel
egress), so the whole turn is individually traceable while `correlation_id` stays
per-conversation. An explicit attribute always wins over the baggage on a key clash.

Consequences for the report:

- slices are bucketed by `(correlation_id, turn_index)`, so a barge-in turn is skipped
  on its own without desyncing the others;
- `scripts/streaming_latency_report.py` adds a **`per_turn`** section
  (`voice_common.pipeline_timing.per_turn_timings`) — one row per `(correlation_id,
  turn_index)` with that turn's slice values, `message_id`, and both composites — so a
  multi-turn browser session is readable turn by turn and per-turn p50/p95/p99 can be
  derived from live sessions.

## How it works

`PipelineTimingReport.from_spans(spans)` groups recorded `Span` durations by
canonical slice and builds a `LatencyReport` (nearest-rank p50/p95/p99) per
instrumented slice. Spans accumulate on a single `TelemetryRecorder` across the
reviewed sample, so percentiles sharpen as the sample grows.

## Reproduce

```bash
cd voice-agent
# STT-only replay: runtime slices are reported as explicit gaps (fixture manifest)
python3 -m stt_validation.pipeline_timing_cli fixtures/manifest.json
# Full-turn sample: ALL SIX slices measured, incl. backend (TASK-WEB-003, US-036)
python3 scripts/turn_latency_sample.py --iterations 30            # success path
python3 scripts/turn_latency_sample.py --iterations 30 --degraded # safe-fallback path
```

### Streaming WebRTC path (TASK-WEB-009)

The streaming loop cannot be driven in-process like the batch turn (it needs a real
transport + live STT/TTS). Its telemetry is emitted **server-side**: on each call
teardown `WebRtcSignalingService` prints one JSON line
(`{"spans": [...], "events": [...], "metrics": [...]}`) to stderr. Capture a warm
sample of streaming calls, then aggregate with the streaming report:

```bash
cd voice-agent
# 1) start the streaming server (Gradium, streaming STT + TTS defaults), capturing stderr
set -a && source ../.env && set +a
python3 -m web_voice.server --host 127.0.0.1 --port 8090 \
  --provider gradium --backend stub --runtime pipecat \
  --webrtc auto --stt-mode streaming --tts-mode streaming 2> /tmp/streaming-telemetry.jsonl

# 2) run N warm streaming calls (browser at /static/webrtc.html, or the headless client)
python3 scripts/webrtc_live_client.py --url http://127.0.0.1:8090 --audio speech.wav --hold 12

# 3) aggregate per-slice + time_to_first_audio p50/p95/p99 + the ADR-0018 gate
python3 scripts/streaming_latency_report.py \
  --input /tmp/streaming-telemetry.jsonl \
  --channel web --provider gradium-streaming --warm
```

The report flags `channel_ingress`/`channel_egress` as gaps on the WebRTC path (see
the streaming composite section above) and prints the pilot-acceptance gate
(`p95 < 800 ms`). The published baseline lives in
[`docs/qa/streaming-voice-qa-report.md`](../qa/streaming-voice-qa-report.md) and the
ADR-0018 evidence section.

#### Pilot-latency live pass: end-of-turn hold before/after (TASK-WEB-015 lever 3)

The lever-3 mechanism (env-tunable hold, ADR-0037) is delivered and reviewed, but its
**behavioural acceptance** — does a shorter hold actually cut perceived latency without
raising the false-endpoint (premature-cut) rate — is a **live** gate. Capture it with
the same harness, against the **real backend** (`--backend http`, not the stub, per
TASK-WEB-014), by running the sample twice and comparing:

```bash
cd voice-agent
set -a && source ../.env && set +a
# A) baseline hold (500 ms default): start the real-backend streaming server, capture stderr
python3 -m web_voice.server --host 127.0.0.1 --port 8090 \
  --provider gradium --backend http --runtime pipecat \
  --webrtc auto --stt-mode streaming --tts-mode streaming 2> /tmp/eot-500.jsonl
python3 scripts/webrtc_live_client.py --url http://127.0.0.1:8090 --audio speech.wav --hold 12  # xN warm turns

# B) tuned hold (350 ms): same run with the override (a below-floor value clamps + warns once)
VOICE_END_OF_TURN_SILENCE_MS=350 python3 -m web_voice.server --host 127.0.0.1 --port 8090 \
  --provider gradium --backend http --runtime pipecat \
  --webrtc auto --stt-mode streaming --tts-mode streaming 2> /tmp/eot-350.jsonl
python3 scripts/webrtc_live_client.py --url http://127.0.0.1:8090 --audio speech.wav --hold 12  # xN warm turns

# C) report each against the ADR-0029 mouth-to-ear gate and compare end_of_turn + voice_to_first_audio
python3 scripts/streaming_latency_report.py --input /tmp/eot-500.jsonl --channel web --provider gradium-streaming --warm
python3 scripts/streaming_latency_report.py --input /tmp/eot-350.jsonl --channel web --provider gradium-streaming --warm
```

Read the win from the `end_of_turn` slice (p50/p95 should drop by ≈ the hold delta) and
the `voice_to_first_audio` composite (mouth-to-ear p95 vs ADR-0029 ≤ 1.5 s). Read the
**cost** — the false-cut rate — from the `voice.end_of_turn` telemetry: each turn's span
now carries the **configured** `silence_window_ms` (so the two runs are distinguishable)
plus `end_of_turn_signal`; a spike in mid-utterance `client_stop`/premature
`silence_window` cuts at 350 ms vs 500 ms is the premature-endpoint regression to gate
on. Keep 500 ms unless the shorter hold holds a comparable false-cut rate on real audio.

The `backend_first_token` slice is measured for both the `stub` and `http`
backends (the span comes from `voice_pipeline/answer.py`, not the adapter), and a
degraded turn still measures backend + TTS + egress because the safe fallback is
transcribed → answered → spoken. The HTTP surface that drives these turns is
documented in
[`voice-runtime-http-contract.md`](../architecture/voice-runtime-http-contract.md).

Example output (fixture sample, 5 turns). The fixture CLI is a pure STT replay
(it does not run the web voice runtime), so `end_of_turn`, `backend_first_token`,
`tts_first_audio` and `channel_egress` are gaps here; they are measured on the
**web voice path** — see the end-of-turn section above and the
`pipeline_timing.feature` scenarios, which drive full turns through the runtime
(`StdlibTurnProcessor.run_turn` → ingress, STT, backend answer, TTS, egress):

```json
{
  "slices": [
    { "slice": "channel_ingress", "measured": true,
      "latency": { "count": 5, "p50_ms": 0.004, "p95_ms": 0.005, "p99_ms": 0.005 } },
    { "slice": "end_of_turn", "measured": false,
      "note": "no end-of-turn span in this sample" },
    { "slice": "stt", "measured": true,
      "latency": { "count": 5, "p50_ms": 0.027, "p95_ms": 0.03, "p99_ms": 0.03 } },
    { "slice": "backend_first_token", "measured": false,
      "note": "no backend.first_token span in this sample" },
    { "slice": "tts_first_audio", "measured": false,
      "note": "no voice.tts.first_audio span in this sample" },
    { "slice": "channel_egress", "measured": false,
      "note": "no web.voice.egress span in this sample" }
  ]
}
```

## Acceptance criteria coverage

| Acceptance criterion | Evidence |
|---|---|
| Ingress, end-of-turn, STT, backend, TTS first audio, egress assessed separately | Six canonical slices always reported (`PIPELINE_SLICES`) |
| p50/p95/p99 for the reviewed sample | `LatencyReport` per instrumented slice over the sample's spans |
| End-of-turn detected and measured as its own slice (TASK-STT-009) | `voice.end_of_turn` span from `WebVoiceIngress`; `end_of_turn` slice reports p50/p95/p99 over the web sample |
| TTS first audio + channel egress measured (TASK-WEB-002) | `voice.tts.first_audio` span from `TtsSynthesisRunner`, `web.voice.egress` span from `WebVoiceEgress`; both slices report p50/p95/p99 over a full-turn sample |
| Backend slice measured (TASK-WEB-003-D/E) | `backend.first_token` + `backend.request` spans from `voice_pipeline/answer.py`; the `backend_first_token` slice reports p50/p95/p99 over a full-turn sample, with one correlation id shared across every slice |
| Latency gaps are visible, not hidden | Any slice with no span in a given sample is reported `"measured": false` with a reason (e.g. the fixture STT replay above) |
| `time_to_first_audio` composite measured, ADR-0018 pilot gate applied (TASK-WEB-009) | `time_to_first_audio_report` sums the post-EOT slices per turn; `scripts/streaming_latency_report.py` reports p50/p95/p99 + the `p95 < 800 ms` gate over a warm streaming sample |

## Pipecat runtime (Sprint 4, TASK-WEB-005)

The slices are runtime-agnostic. Under the `pipecat` runtime the Pipecat frame
processors (`voice-agent/voice_pipeline/`) delegate to the same
`WebVoiceIngress`/`WebVoiceEgress` and the `AnswerProcessor` shares the **same
`TelemetryRecorder`**, so the identical spans (`web.voice.ingress`, `stt.request`,
`backend.first_token` + `backend.request`, `voice.tts.first_audio`,
`web.voice.egress`) are emitted and the same slices are measured. A full turn
through `/api/voice/turn` emits them in a single request under one correlation id.
This is verified by `PipelineTelemetryBridgeTest` in `tests/test_pipeline_timing.py`
and the scenarios in `features/web_voice.feature` / `features/pipeline_timing.feature`.

## Tests

- `tests/test_pipeline_timing.py` (unit: slice order, percentiles, gap flags,
  ingress span precedence, end-of-turn measured when its span is present; plus the
  Pipecat pipeline telemetry-bridge integration test).
- `tests/test_end_of_turn.py` (unit: silence-window vs client-stop signal,
  no invented boundary on silence/empty audio, threshold/config).
- `tests/test_streaming_end_of_turn.py` (unit: frame-incremental fire, no-speech
  guarantee, client-stop `finish()`, sub-minimum click discard, per-turn reset).
- `tests/test_utterance_aggregator.py` (streaming aggregator: `voice.end_of_turn`
  span emission on flush, no span on a silent stream).
- `features/streaming_end_of_turn.feature` (streaming end-of-turn outcome + span).
- `tests/test_web_voice_ingress.py` (end-of-turn span emission + absent event).
- `tests/test_tts_runner.py` / `tests/test_web_voice_egress.py` (`voice.tts.first_audio`
  and `web.voice.egress` span emission for the voice-out slices).
- `tests/test_streaming_tts_provider.py` (streaming TTS seam: incremental chunks,
  key hygiene, safe error mapping) and `tests/test_streaming_tts_processor.py`
  (streaming TTS processor: incremental `TTSAudioRawFrame`s, `voice.tts.first_audio`
  span + time-to-first/last-audio metrics, UNAVAILABLE/FAILED safe degrade).
- `features/streaming_tts.feature` (streaming TTS incremental-playback outcome +
  time-to-first-audio observability).
- `features/pipeline_timing.feature` (US-036 acceptance scenarios over a reviewed
  sample of web voice turns — the STT-only sample, plus full-turn samples through
  the backend bridge where the `backend_first_token`, `tts_first_audio` and
  `channel_egress` slices become measured under one correlation id).
