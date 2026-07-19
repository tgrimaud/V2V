# ADR-0028: Backend Observability — Correlation Id Continuity And Per-Slice Latency Metrics

## Status

Accepted (2026-07-19). Records the observability approach implemented by
**TASK-BE-009** for the answer-engine backend (`voice-support-bot/backend`), on top
of the modular decomposition (ADR-0027) and the answer contract (ADR-0021).

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
