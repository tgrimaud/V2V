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
| Sample size (turns) | _to be filled by the warm live run_ |
| p50 / p95 / p99 (ms) | _to be filled by the warm live run_ |
| min / max / mean (ms) | _to be filled by the warm live run_ |
| Pilot gate (`p95 < 800 ms`) | _to be filled by the warm live run_ |

Per-slice p50/p95/p99 (`stt`, `backend_first_token`, `tts_first_audio`; the
`channel_ingress` / `channel_egress` gaps) are published alongside the composite in
the QA report. The measured baseline above is the honest gate outcome (pass, or the
stated gap) once the warm live sample is collected; until then it is an explicit
pending measurement, not an assumed pass.

## Related Documents

- `docs/architecture/adrs/ADR-0010-industrialization-requires-contracts-slos-and-observability.md`
- `docs/architecture/adversarial-architecture-review-2026-07-08.md`
- `docs/architecture/architecture.md`
- `docs/engineering/development-guide.md`
- `docs/operations/backlog.md`
- `docs/product/v1-scope.md`
