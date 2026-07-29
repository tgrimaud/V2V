# Observability Technical Tasks

Cross-cutting observability tasks spanning the Java backend and the Python voice
runtime. Every runtime story must expose correlation id, per-slice latency, outcome
and sanitized error context (project OpenTelemetry rule); these tasks address the
export/tracing layer on top of the per-slice instrumentation already built.

| Task | Title | Classification | Status |
|---|---|---|---|
| TASK-OBS-001 | OpenTelemetry export (OTLP) for backend + voice runtime, or accept the residual risk in ADR-0028 | V1 hardening (observability) | ✅ Review 93/100 + QA GO (2026-07-29) on `task/TASK-OBS-001-otel-export` — hybrid, merge-ready (awaiting user validation) |

---

## TASK-OBS-001 — OpenTelemetry Export (OTLP) Or Accepted Residual Risk

**Parent:** EPIC-010 (Observability, latency and pilot validation)
**Classification:** V1 hardening (observability)
**Status:** ✅ Review + QA passed — **hybrid** (2026-07-29) on `task/TASK-OBS-001-otel-export` —
option (b) residual-risk acceptance in ADR-0028 **and** env-gated OTLP wiring (default off)
on both services + opt-in collector recipe. Adversarial code review **93/100 (Pass)**; QA GO
(backend `mvn test` green, voice unittest 396 + behave 11/31/146 green, OTLP-specific tests 5
green, default-off gate verified inert, live backend→collector smoke exported real traces +
metrics, telemetry attributes confirmed technical-only → no PII egress). **Merge-ready** —
awaiting explicit user validation/merge. Full cross-service correlated-trace validation
(traceparent propagation) remains deferred behind the mandatory-export trigger.
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

### Implementation notes (2026-07-29, hybrid)

Delivered on `task/TASK-OBS-001-otel-export` (from `feat/restart-from-scratch`):

- **Governance (option b) — ADR-0028 addendum.** Records the Micrometer + structured-logs +
  stderr-spans stack as the **accepted pilot residual risk**, with an explicit
  **mandatory-export trigger** (multi-service/non-localhost deployment, real channels per
  ADR-0010, or an externally-claimed SLO). Status line amended 2026-07-29.
- **Backend OTLP wiring (option a, env-gated, default OFF).** Added `micrometer-registry-otlp`
  (metrics) + `micrometer-tracing-bridge-otel` + `opentelemetry-exporter-otlp` (spans); **no
  instrumented call site changed**. Gated inert by config:
  `management.otlp.metrics.export.enabled=${OTEL_METRICS_EXPORT_ENABLED:false}` and
  `management.tracing.sampling.probability=${OTEL_TRACES_SAMPLER_ARG:0.0}`. Endpoints default
  to `http://localhost:4318` (`OTEL_EXPORTER_OTLP_*` overridable).
- **Voice runtime OTLP wiring (env-gated, default OFF).** `voice_common/otel_export.py`
  translates a `TelemetryRecorder`'s spans/events/metrics into OTel spans (identity attrs
  `correlation_id`/`conversation_id`/`turn_index` hoisted to the root span) and exports over
  OTLP/HTTP. Called best-effort next to the existing stderr dump (`_log_telemetry`,
  `_log_turn`); no-op unless `OTEL_EXPORTER_OTLP_ENDPOINT`/`VOICE_OTEL_EXPORT` is set; SDK
  imported lazily; failures swallowed. `opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-http`
  added to `requirements.txt` (only used when enabled).
- **Opt-in collector recipe.** `deploy/observability/` (`docker-compose.otel.yml`,
  `otel-collector-config.yaml`, `README.md`) — not wired into any default run.
- **Tests / evidence.**
  - Backend `mvn test` **312** green (no `@SpringBootTest`, so the new deps don't touch it);
    export **OFF** startup smoke on :8082 → clean start, `/actuator/health` 200, **zero** OTLP
    connection noise (inert by default).
  - Voice `unittest` **396** (+5, `tests/test_otel_export.py`: gate off-by-default, enable via
    env, `TelemetryRecorder → OTel spans` translation via in-memory exporter, never-raises) +
    `behave` 11 features/31 scenarios/146 steps green.
  - **Live backend → collector smoke** (opt-in collector up, export ON): collector received
    real **traces** (`/api/conversation/converse`, `/actuator/health` server spans) and
    **metrics** (`jvm.*`, `hikaricp.*`, `gen_ai.client.token.usage` from the embedding call,
    `http.server.requests`).
- **Deferred (still option-a remainder):** a single voice turn producing **one correlated
  trace** across runtime → backend (W3C `traceparent` propagation on the HTTP hop) exported to
  a collector — needs the collector running and is gated behind the mandatory-export trigger.
  The shared `correlation_id` remains the cross-service join key today.
