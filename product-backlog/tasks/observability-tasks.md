# Observability Technical Tasks

Cross-cutting observability tasks spanning the Java backend and the Python voice
runtime. Every runtime story must expose correlation id, per-slice latency, outcome
and sanitized error context (project OpenTelemetry rule); these tasks address the
export/tracing layer on top of the per-slice instrumentation already built.

| Task | Title | Classification | Status |
|---|---|---|---|
| TASK-OBS-001 | OpenTelemetry export (OTLP) for backend + voice runtime, or accept the residual risk in ADR-0028 | V1 hardening (observability) | ✅ Merged into `feat/restart-from-scratch` (2026-07-29, ff `bfde816..e79964b`) — hybrid; review 93/100 + QA GO; ticket branch deleted |
| TASK-OBS-002 | Structured JSON logs (correlation_id + sanitization) on both tiers, env-gated default-off — a good log emitter independent of the SRE-owned collector | V1 hardening (observability) | 🔧 Implemented (branch `task/TASK-OBS-002-structured-json-logs`) — voice JSON formatter + per-turn correlation_id contextvar bound on all four ingress paths (WS, Genesys, WebRTC, batch REST) + message/error scrubbing (`VOICE_LOG_FORMAT=json`); backend Spring Boot 3.4 native structured logging carrying MDC `correlation_id`/`channel` (`LOGGING_STRUCTURED_FORMAT_CONSOLE=ecs`); both default text. Voice `unittest` 698 + `behave` 15/43/194 green. Adversarial review 96/100 (Pass); QA pending; not merged |

---

## TASK-OBS-001 — OpenTelemetry Export (OTLP) Or Accepted Residual Risk

**Parent:** EPIC-010 (Observability, latency and pilot validation)
**Classification:** V1 hardening (observability)
**Status:** ✅ Merged into `feat/restart-from-scratch` (2026-07-29, fast-forward
`bfde816..e79964b`; ticket branch deleted) — **hybrid**: option (b) residual-risk acceptance
in ADR-0028 **and** env-gated OTLP wiring (default off) on both services + opt-in collector
recipe. Adversarial code review **93/100 (Pass)**; QA GO (backend `mvn test` green, voice
unittest 396 + behave 11/31/146 green, OTLP-specific tests 5 green, default-off gate verified
inert, live backend→collector smoke exported real traces + metrics, telemetry attributes
confirmed technical-only → no PII egress). Full cross-service correlated-trace validation
(traceparent propagation) remains deferred behind the mandatory-export trigger.
**Priority:** Medium
**Branch:** `task/TASK-OBS-001-otel-export` (merged and deleted)
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

---

## TASK-OBS-002 — Structured JSON Logs (correlation_id + Sanitization), Both Tiers

**Parent:** EPIC-010 (Observability, latency and pilot validation)
**Classification:** V1 hardening (observability)
**Status:** 🔧 Implemented on `task/TASK-OBS-002-structured-json-logs` (from
`feat/restart-from-scratch`). Correlation id bound on all four voice ingress paths.
Adversarial review 96/100 (Pass); QA pending; not merged.
**Priority:** Medium
**Branch:** `task/TASK-OBS-002-structured-json-logs`
**Adversarial review:** 96/100 (Pass) — `docs/qa/task-obs-002-adversarial-review.md`
**Relates to:** ADR-0028 (backend correlation + slice metrics), TASK-OBS-001 (OTLP export),
TASK-OPS-007 (centralized collector — SRE-owned), TASK-BE-009, TASK-WEB-017,
`voice_common/sanitization.py`.

### Context

The centralized OTLP **collector platform is owned by the SRE team** and is not yet in
place, so the aggregated traces/metrics pipeline (TASK-OPS-007) is externally blocked. That
blocker does **not** cover being a good *emitter*: today the two runtimes still log
**human-readable plain text** with no machine-parseable structure and, on the voice side, no
`correlation_id` on the log line. When the collector (or any log shipper / `docker logs`
scrape) does arrive, plain text forces brittle regex parsing and the voice logs can't be
joined to a turn.

This ticket makes both tiers emit **structured JSON logs** carrying the `correlation_id`,
with secret/PII **sanitization**, entirely under our control and independent of the SRE
platform. It is additive and **default-off** (text) so local dev, tests and current pilot
behaviour are unchanged; enabling is a single env var per tier.

### Objective

Emit one JSON log line per event, carrying `correlation_id` (+ `channel` on the backend),
with sanitized message/error content, on both the Java backend and the Python voice runtime —
env-gated, default text.

### Scope

- **Voice runtime (Python).**
  - `voice_common/logging_config.py`: `JsonLogFormatter` (fixed shape `timestamp` (ISO-8601
    UTC), `level`, `logger`, `message`; optional `correlation_id`, optional `error`) +
    `configure_logging(stream, level)` that installs the JSON handler on the root logger
    **only** when `VOICE_LOG_FORMAT=json` (idempotent; returns whether it installed).
  - `voice_common/log_context.py`: a `correlation_id` **`ContextVar`** with
    `set_/get_/reset_correlation_id` + a `correlation_id_scope` contextmanager. Bound on **all
    four** voice ingress paths, each before `session.run()` creates the pipeline tasks (which
    capture the context at creation), so every log line during the turn carries the id:
    - **browser WS** (`web_voice/websocket_app.py::_serve_connection`) — set/reset in `finally`;
    - **Genesys** (`web_voice/genesys_app.py::_serve_genesys_connection`) — set/reset in `finally`;
    - **WebRTC** (`web_voice/webrtc_signaling.py::_start_session_task`) — an **isolated copied
      context** (`copy_context().run(set_correlation_id, …)` + `create_task(context=…)`) so
      concurrent calls on the shared background loop never leak ids into one another;
    - **batch REST** (`web_voice/app.py::handle_turn`) — `correlation_id_scope(...)` around the
      handler, and `_run_blocking` copies the context into the thread executor (`run_in_executor`
      does not propagate contextvars) so the blocking processor's logs are stamped too.
  - `voice_common/sanitization.py`: `scrub_message()` reuses the existing per-token redactor
    (paths/filenames/UUIDs/secret-prefixed/long-id tokens, safe-token allowlist, dates kept)
    and additionally redacts the **value** side of `key=value` tokens common in log lines;
    caps length at 2048 chars. Applied to every JSON `message` and `error`.
  - `web_voice/server.py`: `configure_logging()` at the top of `main()`.
- **Backend (Java / Spring Boot 3.4).** No code change: enable **native structured logging**
  via `LOGGING_STRUCTURED_FORMAT_CONSOLE` (relaxed-binds to
  `logging.structured.format.console`; `ecs`/`logstash`). The existing `CorrelationIdFilter`
  already puts `correlation_id` + `channel` in the **MDC**, which the ECS/Logstash encoders
  serialize into each JSON line automatically. Backend log content is already sanitized
  (generic codes + correlation id, no upstream echo — ADR-0028 / GlobalExceptionHandler).
- **Deploy (both tiers, env-gated, default OFF).** `VOICE_LOG_FORMAT` /
  `LOGGING_STRUCTURED_FORMAT_CONSOLE` passthrough in the voice + backend compose
  `environment:` blocks, the Ansible `voice.env.j2` / `backend.env.j2` templates, and
  `group_vars/voice.yml` (`voice_log_format: ""`) / `group_vars/backend.yml`
  (`backend_log_format: ""`). Additive + opt-in exactly like `otel_collector_endpoint`.

### Acceptance

- Voice: with `VOICE_LOG_FORMAT=json`, each log line is valid JSON with `timestamp/level/
  logger/message`; carries `correlation_id` when a turn is in scope and omits it otherwise;
  secrets (`sk-…`, `key=…`), filesystem paths and UUIDs are redacted in `message`/`error`.
  With the var unset the runtime keeps plain-text logging and existing handlers are untouched.
- Backend: with `LOGGING_STRUCTURED_FORMAT_CONSOLE=ecs`, logs are JSON carrying the MDC
  `correlation_id`/`channel`; unset keeps the current text layout. `mvn test` unchanged
  (config-only; no call site touched).
- Existing suites stay green; enabling is a single env var per tier; nothing depends on the
  SRE collector.

### Notes / follow-ups

- The voice `correlation_id` is bound on **all four** ingress paths (browser WS, Genesys,
  WebRTC, batch REST) — see the scope note above. The batch path needed the extra
  `_run_blocking` context copy because `run_in_executor` does not propagate `ContextVar`s to
  the worker thread; WebRTC needed an isolated copied context because all live sessions share
  one background loop.
- Structured JSON is useful **now**, before any collector: `docker logs` / json-file output
  becomes machine-parseable and shippable by any future SRE log pipeline.
- Sanitization is best-effort and shares the OTLP/telemetry redactor; `k=v` value redaction is
  log-specific and does not change `sanitize_error`'s own tokenization.

### Correlation-binding extension (2026-09-30, same branch)

The initial commit bound the correlation id only on the browser WS path. Extended the bind to
Genesys, WebRTC and batch REST (details in the scope note). +4 tests
(`test_genesys_app::test_correlation_id_is_bound_in_context_during_the_call`,
`test_webrtc_signaling::test_session_task_runs_under_the_call_correlation_id`,
`test_web_voice_app::{test_run_blocking_propagates_correlation_context_into_executor,
test_turn_binds_the_correlation_id_for_the_processor_call}`). Voice `unittest` **698** +
`behave` 15/43/194 green. Adversarial review raised **93 → 96/100 (Pass)**.
