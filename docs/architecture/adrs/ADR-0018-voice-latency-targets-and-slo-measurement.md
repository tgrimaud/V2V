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

## Related Documents

- `docs/architecture/adrs/ADR-0010-industrialization-requires-contracts-slos-and-observability.md`
- `docs/architecture/adversarial-architecture-review-2026-07-08.md`
- `docs/architecture/architecture.md`
- `docs/engineering/development-guide.md`
- `docs/operations/backlog.md`
- `docs/product/v1-scope.md`
