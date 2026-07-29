# ADR-0028: Backend Observability — Correlation Id Continuity And Per-Slice Latency Metrics

## Status

Accepted (2026-07-19). Records the observability approach implemented by
**TASK-BE-009** for the answer-engine backend (`voice-support-bot/backend`), on top
of the modular decomposition (ADR-0027) and the answer contract (ADR-0021).

**Amended 2026-07-29 (TASK-OBS-001):** adds an **env-gated OTLP export** path on both
the backend and the voice runtime (default **off** → unchanged offline/pilot behaviour)
and **formally accepts** the Micrometer + structured-logs + stderr-spans default as the
pilot residual risk, with an explicit trigger that makes OTLP export mandatory. See the
addendum at the end of this ADR.

## Context

Runtime work in this project is required to be observable per latency slice
(DEC-010 / ADR-0010), and the ADR-0018 voice-journey taxonomy expects the backend
to expose its **RAG** and **LLM** slices so p50/p95/p99 can be reported by
channel/provider before any SLO claim. Until now the backend only emitted
`[GROUNDING]` and `[CONVERSE]` structured logs carrying a `duration_ms`; there was:

- **no correlation-id continuity** — the voice runtime sends a `correlation_id`
  (ADR-0021 body field), but nothing tied it to the backend's log lines, so a turn
  could not be followed runtime → backend;
- **no metric** exposing retrieval / LLM latency distributions (percentiles were
  hand-derived from logs during QA, which does not scale and is not queryable);
- no single, reusable instrumentation seam — each controller timed its own request.

The backend runs locally for the pilot with **no metrics/tracing collector**, so the
solution must produce useful evidence offline and stay unit-testable without a
running backend, DB or Ollama (the suite has no `@SpringBootTest`).

## Decision

**1. Correlation id via a servlet filter + SLF4J MDC.**
`CorrelationIdFilter` (order 1) resolves an `X-Correlation-Id` request header (or
generates a UUID when absent), puts it in the MDC under `correlation_id`, echoes it
on the response header, and always clears the MDC in a `finally`. Every structured
log line therefore carries the id. Endpoints that receive an **authoritative** id in
the request body (the voice runtime's `correlation_id` on `/converse`) call
`CorrelationId.set(...)` to override the generated id and overwrite the response
header, so backend slices share the runtime's id end to end. The originating
`channel` is propagated the same way (MDC), used as a metric tag.

**2. Per-slice latency as a Micrometer timer.**
A single `BackendTelemetry` component times a unit of work and records the
`voice_support.slice` timer tagged `slice` / `channel` / `provider` / `outcome`,
with client-side percentiles (p50/p95/p99). It also emits a `[TELEMETRY]` structured
log (correlation id, slice, provider, channel, outcome, `duration_ms`). Instrumented
slices, mapped onto the ADR-0018 taxonomy:

| Slice (`slice` tag) | ADR-0018 mapping | Instrumented at |
|---|---|---|
| `retrieval` | RAG retrieval | `InProcKnowledgeRetrievalAdapter` (seam) |
| `llm_wording` | LLM full request | `AbstractChatClientAnswerAdapter` (provider adapter) |
| `backend_request` | backend composite | `ConverseController` (the runtime endpoint) |

The **input/output guardrail** decision is not a separate timer: it is deterministic
and effectively instantaneous (a keyword short-circuit voiced in ~0 ms), and its
verdict is already visible as the `[GROUNDING]`/`[CONVERSE]` outcome and the request
`grounded` flag. Promoting it to its own timer is deferred until it carries real
latency (e.g. an LLM/ML-based guardrail).

**3. Metrics exposed via actuator, no external exporter (pilot).**
`spring-boot-starter-actuator` provides the `MeterRegistry`; `/actuator/metrics/voice_support.slice`
exposes the tagged timer with percentiles for local reporting. No OTLP/collector is
wired for the pilot.

**4. Privacy.** Tags and logs carry only technical dimensions and durations — never
raw transcript, answer text, api-key or other secrets. Only text **length** is ever
logged (existing `[CONVERSE]` behavior, unchanged).

## Consequences

- A turn is followable runtime → backend under one correlation id; retrieval and LLM
  latency are queryable as distributions (p50/p95/p99) by channel/provider, meeting
  the TASK-BE-009 acceptance and the ADR-0018 reporting expectation.
- Instrumentation lives only at the **infrastructure boundary** (adapters,
  controllers, servlet filter) and in cross-cutting `shared/observability`; the pure
  domain and application layers stay free of transport/metrics concerns (hexagonal
  purity preserved). `ContextBoundaryTest` was extended to let the knowledge seam
  depend on the context-agnostic `com.voicesupport.shared..` package (like it already
  may on `org.springframework..`); `sharedMustNotDependOnAnyContext` still forbids the
  reverse, so no boundary is weakened.
- The same `BackendTelemetry` call sites can be promoted to **distributed spans**
  later by adding a Micrometer Tracing → OpenTelemetry bridge and an exporter, with
  no change to the instrumented code.
- A real time-to-first-token (`backend.first_token`, RF-021) is **not** produced yet:
  the LLM call is timed as a single full-request slice. That divergence is delivered
  by streaming (TASK-BE-007 / ADR-0013), which will add an `llm_first_token` slice.

## Alternatives considered

- **Micrometer Tracing + OTel bridge + collector now.** Rejected for the pilot: it
  needs a running collector, complicates offline unit testing, and adds heavy deps
  for evidence we can already expose via actuator metrics + structured logs. Kept as
  the documented upgrade path.
- **Keep deriving percentiles from `duration_ms` logs only.** Rejected: not
  queryable, not tagged, and does not scale beyond manual QA sampling.
- **Instrument inside domain/application services.** Rejected: pollutes the pure
  layers with metrics concerns; the adapter/controller boundary already brackets each
  slice cleanly.
- **Correlation id via a request body field only (no header/filter).** Rejected:
  non-body endpoints (`/retrieve`, `/answer`, future GETs) would have no id, and there
  would be no continuity mechanism for a generated id; a filter guarantees an id
  always exists and is always cleared.

## Addendum (2026-07-29, TASK-OBS-001): OTLP export + accepted pilot residual risk

The full adversarial review (2026-07-28) flagged that neither service exports
**distributed OpenTelemetry data over OTLP**, and that the deviation from the project
OTel rule (DEC-010 / ADR-0010) was documented here but never *formally accepted* as a
pilot residual risk. TASK-OBS-001 resolves both, taking the **hybrid** path.

### 1. Accepted pilot residual risk (governance)

For **V1 / pilot**, the default observability stack stays:

- **Backend:** Micrometer meters (`voice_support.slice` timer + `prompt_chars` /
  `answer_chars` / `answer_language` / `guardrail_block`) exposed via actuator, plus
  `[TELEMETRY]`/`[CONVERSE]`/… structured logs carrying the `correlation_id` (MDC).
- **Voice runtime:** `TelemetryRecorder` events/spans/metrics serialized to **stderr**
  per turn/call.

This is **accepted as sufficient for pilot QA**: latency slices are queryable
(actuator percentiles) and reportable (stderr dumps), and a turn is followable
runtime → backend under one `correlation_id` (the cross-service **join key**). No
metrics/tracing collector runs in the pilot, so distributed OTLP export is **not**
required to meet pilot acceptance.

**Mandatory-export trigger.** OTLP export (below) becomes **mandatory** — no longer
optional — as soon as **any** of the following holds:

- the system runs as **more than one deployed service** in a shared (non-localhost)
  environment where log/stderr correlation is no longer practical;
- **real channels** are onboarded (telephony/Genesys/WhatsApp per ADR-0010) or any
  non-localhost / multi-tenant deployment;
- an SLO is claimed to an external stakeholder (needs queryable, retained
  p50/p95/p99 across services, not per-run stderr dumps).

Until a trigger fires, running with export **off** is an explicitly accepted residual
risk (owner: architecture; revisit at the Sprint 10/11 channel/telephony work).

### 2. Env-gated OTLP export (wiring, additive, default off)

OTLP export is **additive** — the Micrometer/actuator and stderr evidence above are
never removed.

- **Backend.** Added `micrometer-registry-otlp` (metrics) and
  `micrometer-tracing-bridge-otel` + `opentelemetry-exporter-otlp` (spans). No
  instrumented call site changed — the existing meters export over OTLP and HTTP
  server spans are produced by Spring's observation autoconfig. Gating (all default to
  **inert**): `management.otlp.metrics.export.enabled=${OTEL_METRICS_EXPORT_ENABLED:false}`
  and `management.tracing.sampling.probability=${OTEL_TRACES_SAMPLER_ARG:0.0}` — with
  export disabled and 0.0 sampling, nothing is recorded or shipped and no collector
  connection is attempted, so `mvn test` (no `@SpringBootTest`) and normal startup are
  unchanged. Endpoints default to `http://localhost:4318` and are overridable via the
  standard `OTEL_EXPORTER_OTLP_*` env vars.
- **Voice runtime.** `voice_common/otel_export.py` translates a `TelemetryRecorder`'s
  spans/events/metrics into OTel spans (with `correlation_id` / `conversation_id` /
  `turn_index` as attributes) and ships them over OTLP/HTTP. It is called best-effort
  next to the existing stderr dump (`_log_telemetry`, `_log_turn`) and is a **no-op**
  unless `OTEL_EXPORTER_OTLP_ENDPOINT` (or `VOICE_OTEL_EXPORT`) is set; the
  `opentelemetry` SDK is imported lazily and any failure is swallowed (stderr note),
  so offline runs and the test suite are unaffected.
- **Cross-service.** The shared `correlation_id` remains the join key on both sides
  (attribute on spans, MDC in logs). Full **W3C `traceparent`** propagation on the
  runtime → backend HTTP call (one trace id end to end) is the remaining step of the
  full-export path and is deferred with option (a) validation.

### 3. Local collector recipe (opt-in)

`deploy/observability/` ships an opt-in OpenTelemetry Collector (`docker-compose.otel.yml`
+ `otel-collector-config.yaml`, `debug`/Prometheus exporters) plus a README with the
env vars to flip export on for both services. It is **not** wired into any default run.

### 4. What is validated now vs deferred

- **Validated offline:** export is inert by default (backend suite + startup unchanged;
  voice suite unchanged); the voice translation `TelemetryRecorder → OTel spans` is unit
  tested with an in-memory span exporter (no network).
- **Deferred (needs a running collector, option a full validation):** a single voice
  turn producing one **correlated trace** across runtime and backend exported to the
  collector, and `traceparent` propagation on the HTTP hop. Tracked as the remainder of
  TASK-OBS-001 / the mandatory-export trigger.
