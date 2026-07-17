# ADR-0018: Voice Latency Targets And SLO Measurement

## Status

Accepted

## Context

The documentation used several latency statements for the voice path:

- first audible sentence around 700 ms;
- first audible answer under one second;
- `time_to_first_audio` p95 below 800 ms;
- production SLO still unsettled in the adversarial architecture review.

Using these phrases interchangeably makes the V1 scope look more industrialized
than it is. The project needs one vocabulary that separates product ambition,
pilot validation, measured baseline, and production SLO.

## Decision

Use the following latency taxonomy for the target V1 Pipecat voice path:

- **Aspirational user-experience target**: first audible sentence around 700 ms
  on the optimized streaming path.
- **Pilot acceptance criterion**: `time_to_first_audio` p95 below 800 ms in a
  pre-warmed and co-located environment, measured separately for each voice
  channel.
- **Measured baseline**: every validation report must publish sample size, p50,
  p95, p99, min, max, mean, channel, environment, provider configuration, and
  whether caches/connections were warm.
- **Production SLO**: not contractual yet. It can only be accepted after the
  ADR-0010 industrialization gates are satisfied: per-step/channel observability,
  dashboards, alerting, degraded modes, retries/timeouts, and provider outage
  tests.

`time_to_first_audio` is measured from the moment the voice runtime accepts the
end of the user's turn to the first playable audio frame emitted back to the
same channel. Step-level spans must also capture STT, backend request, vector
search, LLM first token, TTS first audio, and channel output.

For billing explanations, speed must not override correctness. If BSS evidence
or deterministic comparison requires more time, the bot may produce a fast oral
acknowledgement first, then deliver the reliable explanation once evidence is
available.

## Consequences

- `~700 ms` remains an experience target, not a claimed production SLO.
- `p95 < 800 ms` becomes the current measurable pilot acceptance criterion.
- Production readiness cannot be claimed from a clean diagram or a single local
  run; it requires measured baselines and ADR-0010 operational controls.
- Web voice, telephony, and future voice channels must report latency separately
  because channel transport and provider behavior differ.

## Alternatives Considered

- **Declare 700 ms as the production SLO now**: rejected because current
  observability, degraded-mode tests, and provider measurements are not mature
  enough.
- **Use only "under one second"**: rejected because it is readable for product
  docs but too vague for engineering validation.
- **Keep both 700 ms and 800 ms without distinction**: rejected because it caused
  the documentation drift this ADR resolves.

## Evidence (TASK-WEB-009, Sprint 6 close)

The streaming WebRTC voice path is now instrumented end to end, so the pilot
acceptance criterion is measurable. This section records how it is measured and the
measured baseline.

### How `time_to_first_audio` is measured

On the streaming path the `voice.end_of_turn` span ends at end-of-turn acceptance,
so the composite (acceptance → first playable frame) is the sum of the sequential
post-end-of-turn slices:

```
time_to_first_audio = stt (post-EOT finalize tail)
                    + backend_first_token (answer)
                    + tts_first_audio (time-to-first-audio)
```

`voice_common.pipeline_timing.time_to_first_audio_report` computes it per turn
(positional zip within a correlation group; turns missing a component are skipped),
and `scripts/streaming_latency_report.py` reports p50/p95/p99 and the
`p95 < 800 ms` gate over a warm streaming sample parsed from the server telemetry
dumps. **Known gap:** `channel_ingress` / `channel_egress` are emitted only on the
batch HTTP path, so the WebRTC channel-egress transport add-on (first frame emitted
→ playable at the browser) is not yet folded into the number — it is reported
separately, not silently included. Reproduction commands and the full breakdown are
in [`docs/qa/streaming-voice-qa-report.md`](../../qa/streaming-voice-qa-report.md)
and [`docs/observability/voice-journey-timing.md`](../../observability/voice-journey-timing.md).

### Measured baseline — web channel (streaming WebRTC)

| Field | Value |
|---|---|
| Metric | `time_to_first_audio` (end-of-turn → first playable frame) |
| Channel | web (streaming WebRTC) |
| Provider config | Gradium streaming STT + streaming TTS, stub backend, `pipecat` runtime |
| Environment | co-located dev host, warm (server process pre-warmed) |
| Date | 2026-07-16 |
| Sample size (turns) | 5 turns with first audio (from 7 warm calls; 2 calls produced no turn telemetry) |
| p50 / p95 / p99 (ms) | 1310.4 / 1697.9 / 1697.9 |
| min / max / mean (ms) | 961.6 / 1697.9 / 1317.5 |
| Pilot gate (`p95 < 800 ms`) | **FAIL** (measured p95 1697.9 ms, margin −897.9 ms) |

Per-slice p50/p95/p99 over the same warm sample:

| Slice | p50 (ms) | p95 (ms) | p99 (ms) | Notes |
|---|---|---|---|---|
| `end_of_turn` | 500.0 | 500.0 | 500.0 | trailing-silence window before acceptance — **not** part of the composite (starts at acceptance) |
| `stt` (post-EOT finalize tail) | 865.8 | 1388.6 | 1388.6 | dominant slice; Gradium WebSocket finalize after end-of-turn |
| `backend_first_token` | 0.01 | 0.01 | 0.01 | stub backend (no BSS/RAG/LLM) — real backend will add materially here |
| `tts_first_audio` | 309.3 | 478.9 | 478.9 | Gradium streaming TTS first playable chunk |
| `channel_ingress` | — | — | — | not measured on WebRTC path (batch-HTTP-only span) |
| `channel_egress` | — | — | — | not measured on WebRTC path (WebRTC transport egress not folded in) |

**Gate outcome: NO-GO on the pilot latency criterion.** The warm streaming path is
functionally complete and instrumented, but `time_to_first_audio` p95 (~1.70 s) is
~2.1× over the 800 ms pilot criterion, dominated by the STT post-EOT finalize tail
(p95 ~1.39 s). Two caveats keep this an honest, not a flattering, baseline: (1) the
backend is a stub, so the real BSS/PDF/comparison/RAG/LLM answer time is **not** in
this number and will only increase the composite; (2) `channel_egress` (WebRTC first
frame → playable at the browser) is still excluded. Reducing the STT finalize tail
(streaming-final / partial-commit tuning) is the primary lever and is tracked as a
Sprint 6 follow-up. The reproducible sample is committed at
[`docs/qa/streaming-latency-warm-sample.json`](../../qa/streaming-latency-warm-sample.json).

For the TTS slice specifically, the QA report also records a **provider baseline**
comparison against Gradium's published "time to first audio buffer" percentiles
(2026-07-16), so the transport/handling delta our path adds on top of the provider
is objectified rather than assumed — see
[Provider baseline — TTS time to first audio buffer](../../qa/streaming-voice-qa-report.md#provider-baseline--tts-time-to-first-audio-buffer-2026-07-16).
This is a supporting provider-side measurement; it does not replace the measured
baseline above (our end-to-end sample remains the source for the pilot gate).

### Post-fix baseline — web channel (TASK-STT-013, 2026-07-17)

TASK-STT-013 attacked the dominant slice above. The spike
([`docs/qa/stt-013-finalize-tail-spike.md`](../../qa/stt-013-finalize-tail-spike.md))
found the STT post-EOT tail was ~430 ms of pure waiting for the terminal
`end_of_stream` *after* the full transcript was already received; the streaming STT
now finalizes on Gradium's `flushed` ack (zero word loss). Re-measured warm, 8 turns
over WebRTC, stub backend ([`streaming-latency-warm-postfix.json`](../../qa/streaming-latency-warm-postfix.json)):

| Slice | p50 (ms) | p95 (ms) | Before p95 | Notes |
|---|---:|---:|---:|---|
| `stt` (post-EOT finalize tail) | 370.8 | **373.5** | 1388.6 | now the ~350 ms `flushed` round-trip, stable |
| `backend_first_token` | 0.0 | 0.0 | 0.01 | stub backend |
| `tts_first_audio` | 457.2 | 483.8 | 478.9 | now the dominant slice; includes a ~90 ms per-turn TTS WebSocket connect |
| **`time_to_first_audio`** | **826.5** | **852.9** | 1697.9 | p95 cut by 845 ms (~50 %) |

**Gate outcome: still NO-GO, but the margin closed from −897.9 ms to −52.9 ms.** The
STT lever is now exhausted (tail is the irreducible ~350 ms provider ack). The
remaining slice is `tts_first_audio`, of which ~90 ms is a fresh TTS WebSocket
connect + setup performed on the per-turn critical path (measured: `open()` ~90 ms
warm / ~188 ms cold; first chunk after open ~350 ms). Pre-warming/reusing the TTS
connection projects `tts_first_audio` p95 ~484 → ~394 ms and composite p95 ~853 →
~763 ms (**PASS**). This is tracked as **TASK-WEB-011** (TTS connection pre-warm),
the next and expected-final lever for the pilot gate. The stub-backend and
`channel_egress` caveats from the baseline above still apply.

### Post-fix baseline — web channel (TASK-WEB-011, 2026-07-17) — GATE MET

TASK-WEB-011 removed the per-turn TTS WebSocket connect from the critical path.
Gradium's TTS socket is single-use (a 2nd synthesis on one connection fails), so the
connection cannot be reused, but a spare is now **pre-opened** off the per-turn path
(`TtsSessionWarmer`: warm on pipeline start, hand out the spare, pre-open the next).
Re-measured warm, 8 turns over WebRTC, stub backend
([`streaming-latency-warm-prewarm.json`](../../qa/streaming-latency-warm-prewarm.json)):

| Slice | p50 (ms) | p95 (ms) | Before p95 (TASK-STT-013) | Notes |
|---|---:|---:|---:|---|
| `stt` (post-EOT finalize tail) | 370.4 | 380.8 | 373.5 | unchanged (STT lever from TASK-STT-013) |
| `backend_first_token` | 0.0 | 0.1 | 0.0 | stub backend |
| `tts_first_audio` | 365.1 | 380.7 | 483.8 | ~90 ms per-turn connect removed (pre-warm) |
| **`time_to_first_audio`** | **739.1** | **761.5** | 852.9 | **PASS** |

**Gate outcome: GO on the pilot latency criterion — `time_to_first_audio` p95
761.5 ms < 800 ms (margin +38.5 ms).** Full arc: baseline 1698 ms (−898) →
TASK-STT-013 finalize-on-`flushed` 853 ms (−53) → TASK-WEB-011 TTS pre-warm
**761.5 ms (+38.5, PASS)**.

**Caveats (the gate is met, but read them):** (1) still measured with a **stub
backend** — the real BSS/PDF/comparison/RAG/LLM answer time is not in this number and
will add to the composite; the 800 ms criterion is defined EOT → first audio and the
answer-engine latency is a separate budget line. (2) `channel_egress` (WebRTC first
frame → audible in the browser) is still excluded. (3) N = 8 warm turns (p95 = p99 =
max at this sample size). The pilot gate is met for the streaming voice path as
specified; a production SLO claim still needs the ADR-0010 operational controls
(dashboards, alerting, degraded-mode + provider-outage tests) and a real backend.

## Related Documents

- `docs/architecture/adrs/ADR-0010-industrialization-requires-contracts-slos-and-observability.md`
- `docs/architecture/adversarial-architecture-review-2026-07-08.md`
- `docs/architecture/architecture.md`
- `docs/engineering/development-guide.md`
- `docs/operations/backlog.md`
- `docs/product/v1-scope.md`
