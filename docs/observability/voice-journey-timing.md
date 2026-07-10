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
| `end_of_turn` | — | Gap: turn/end-of-speech detection not implemented (TASK-STT-009) |
| `stt` | `stt.request` | Instrumented |
| `backend_first_token` | — | Gap: backend orchestration deferred (TASK-WEB-003) |
| `tts_first_audio` | — | Gap: voice response / TTS deferred (TASK-WEB-002) |
| `channel_egress` | — | Gap: voice response egress deferred (TASK-WEB-002) |

For `channel_ingress` the first present span wins: a web turn uses
`web.voice.ingress`; a fixture-only run falls back to `stt.audio.accept`. The two
never mix into the same distribution.

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

Example output (fixture sample, 5 turns) — instrumented slices carry a
distribution, deferred slices are flagged as gaps:

```json
{
  "slices": [
    { "slice": "channel_ingress", "measured": true,
      "latency": { "count": 5, "p50_ms": 0.004, "p95_ms": 0.005, "p99_ms": 0.005 } },
    { "slice": "end_of_turn", "measured": false,
      "note": "turn/end-of-speech detection not implemented in the STT ingress slice" },
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
| Latency gaps are visible, not hidden | Deferred slices reported `"measured": false` with a reason |

## Tests

- `tests/test_pipeline_timing.py` (unit: slice order, percentiles, gap flags,
  ingress span precedence).
- `features/pipeline_timing.feature` (US-036 acceptance scenario over a
  reviewed sample of web voice turns).
