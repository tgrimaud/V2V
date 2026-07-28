# Observability Technical Tasks

Cross-cutting observability tasks spanning the Java backend and the Python voice
runtime. Every runtime story must expose correlation id, per-slice latency, outcome
and sanitized error context (project OpenTelemetry rule); these tasks address the
export/tracing layer on top of the per-slice instrumentation already built.

| Task | Title | Classification | Status |
|---|---|---|---|
| TASK-OBS-001 | OpenTelemetry export (OTLP) for backend + voice runtime, or accept the residual risk in ADR-0028 | V1 hardening (observability) | Proposed (2026-07-28) — partially doable now |

---

## TASK-OBS-001 — OpenTelemetry Export (OTLP) Or Accepted Residual Risk

**Parent:** EPIC-010 (Observability, latency and pilot validation)
**Classification:** V1 hardening (observability)
**Status:** Proposed (2026-07-28) — **partially doable now** (wiring/decision are doable;
full end-to-end validation needs an OTel collector).
**Priority:** Medium
**Branch:** `task/TASK-OBS-001-otel-export` (to create)
**Surfaced by:** full adversarial code+doc review 2026-07-28
(`docs/architecture/reviews/full-adversarial-review-2026-07-28.md`, observability gap vs
the project OTel rule).
**Relates to:** ADR-0010 (industrialization: observability), ADR-0028 (backend
correlation + slice metrics; names the Tracing→OTel bridge as the upgrade path),
`docs/observability/voice-journey-timing.md`, TASK-BE-009, TASK-WEB-017.

### Context

Per-slice instrumentation exists on both sides, but neither exports **distributed
OpenTelemetry traces/spans**:

- **Backend:** `BackendTelemetry` emits Micrometer timers/counters + structured logs;
  ADR-0028 explicitly defers a Tracing→OTel bridge as "the upgrade path to spans"
  (no collector today).
- **Voice runtime:** `voice_common/telemetry` emits spans/events/metrics to **stderr
  only** — there is no OTLP exporter.

The project rule mandates OpenTelemetry traces/metrics/logs for runtime behaviour.
Today the deviation is documented (ADR-0028) but not formally accepted as a pilot
residual risk, and cross-service trace correlation (single trace across voice runtime
→ backend) is not possible.

### Objective

Either (a) export real OpenTelemetry data over OTLP from both services with a shared
trace/correlation context, or (b) formally record the current Micrometer+stderr
approach as an **accepted residual risk for the pilot** in ADR-0028, with the
conditions under which OTLP export becomes mandatory.

### Scope (option a — export)

- **Backend:** add the Micrometer Tracing → OTel bridge (or OpenTelemetry Spring Boot
  starter) and an OTLP exporter; map the existing `voice_support.slice` timings and the
  `correlation_id` (MDC) onto spans/trace context. Keep instrumentation at the infra
  boundary (ADR-0028).
- **Voice runtime:** add an OTLP exporter behind the existing `TelemetryRecorder`
  (env-gated; default off = stderr, so offline/tests are unchanged), propagating
  `correlation_id` / `conversation_id` / `turn_index` as span attributes/baggage.
- **Cross-service:** propagate a shared trace/correlation context on the
  runtime→backend HTTP call (already sends `X-Correlation-Id`) so a turn can be followed
  end to end.
- Provide a local collector recipe (e.g. an OTel collector in `docker-compose.yml`) for
  validation; keep it opt-in.

### Scope (option b — accept residual risk)

- Add a decision note to **ADR-0028** (or a short new ADR) recording that V1/pilot uses
  Micrometer + structured logs + stderr spans, why that is sufficient for pilot QA, and
  the trigger that makes OTLP export mandatory (e.g. multi-service prod, real channels
  per ADR-0010).

### Acceptance

- **Option a:** a single voice turn produces a correlated trace across voice runtime and
  backend, exported over OTLP to a local collector; existing tests stay green; export is
  env-gated (off by default for offline/tests).
- **Option b:** ADR-0028 (or new ADR) records the accepted residual risk + the mandatory-
  export trigger; the review's observability finding is marked accepted with a reference.

### Notes

- This is the one review finding that is **partially** doable now: the ADR decision
  (option b) is immediate; full OTLP validation (option a) needs a collector, so land the
  wiring behind an env flag and validate with the local collector recipe.
- Do not remove the current Micrometer/stderr evidence — OTLP is additive.
