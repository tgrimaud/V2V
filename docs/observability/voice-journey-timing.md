# Voice Journey Timing By Pipeline Slice (US-036)

**Story:** US-036 - Measure key voice journey timings by pipeline slice
**Parent:** EPIC-010
**Module:** `voice-agent/stt_validation/pipeline_timing.py`
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
| `end_of_turn` | `voice.end_of_turn` (web voice runtime) | Instrumented (TASK-STT-009) |
| `stt` | `stt.request` | Instrumented |
| `backend_first_token` | — | Gap: backend orchestration deferred (TASK-WEB-003) |
| `tts_first_audio` | — | Gap: voice response / TTS deferred (TASK-WEB-002) |
| `channel_egress` | — | Gap: voice response egress deferred (TASK-WEB-002) |

For `channel_ingress` the first present span wins: a web turn uses
`web.voice.ingress`; a fixture-only run falls back to `stt.audio.accept`. The two
never mix into the same distribution.

### End-of-turn detection (TASK-STT-009)

The web voice runtime owns turn detection (`web_voice/end_of_turn.py`). For the
V1 batch web path the **authoritative signal is a trailing-silence window** over
the captured PCM16; if the buffer ends before a full window has elapsed the
detector falls back to an **explicit client stop**. A streaming VAD is a future
drop-in replacement — the `EndOfTurnDetector` is injected into `WebVoiceIngress`,
so swapping it changes nothing else.

The emitted `voice.end_of_turn` span duration is the end-of-turn **slice
latency**: the confirmation hold after speech ends (the silence window, or the
residual trailing silence on a client stop). Span attributes carry
`end_of_turn_signal` (`silence_window` / `client_stop`), `trailing_silence_ms`
and `speech_end_ms`. A buffer with **no usable speech** invents no turn boundary:
no span is emitted (a `voice.end_of_turn.absent` event is recorded instead), so
the slice is reported as a gap for that turn rather than a fabricated latency.

## How it works

`PipelineTimingReport.from_spans(spans)` groups recorded `Span` durations by
canonical slice and builds a `LatencyReport` (nearest-rank p50/p95/p99) per
instrumented slice. Spans accumulate on a single `TelemetryRecorder` across the
reviewed sample, so percentiles sharpen as the sample grows.

## Reproduce

```bash
cd voice-agent
# Per-slice report over a reviewed sample (fixture manifest)
python3 -m stt_validation.pipeline_timing_cli fixtures/manifest.json
```

Example output (fixture sample, 5 turns). The fixture CLI is a pure STT replay
(it does not run the web voice runtime), so `end_of_turn` is a gap here; it is
measured on the **web voice path** — see the end-of-turn section above and the
`pipeline_timing.feature` scenario, which drives turns through `WebVoiceIngress`:

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
      "note": "backend orchestration deferred (TASK-WEB-003)" },
    { "slice": "tts_first_audio", "measured": false,
      "note": "voice response / TTS deferred (TASK-WEB-002)" },
    { "slice": "channel_egress", "measured": false,
      "note": "voice response egress deferred (TASK-WEB-002)" }
  ]
}
```

## Acceptance criteria coverage

| Acceptance criterion | Evidence |
|---|---|
| Ingress, end-of-turn, STT, backend, TTS first audio, egress assessed separately | Six canonical slices always reported (`PIPELINE_SLICES`) |
| p50/p95/p99 for the reviewed sample | `LatencyReport` per instrumented slice over the sample's spans |
| End-of-turn detected and measured as its own slice (TASK-STT-009) | `voice.end_of_turn` span from `WebVoiceIngress`; `end_of_turn` slice reports p50/p95/p99 over the web sample |
| Latency gaps are visible, not hidden | Deferred slices reported `"measured": false` with a reason |

## Tests

- `tests/test_pipeline_timing.py` (unit: slice order, percentiles, gap flags,
  ingress span precedence, end-of-turn measured when its span is present).
- `tests/test_end_of_turn.py` (unit: silence-window vs client-stop signal,
  no invented boundary on silence/empty audio, threshold/config).
- `tests/test_web_voice_ingress.py` (end-of-turn span emission + absent event).
- `features/pipeline_timing.feature` (US-036 acceptance scenario over a
  reviewed sample of web voice turns — now including the `end_of_turn` slice).
