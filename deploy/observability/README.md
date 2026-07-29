# Local OpenTelemetry export (opt-in) — TASK-OBS-001

OTLP export is **additive and off by default** on both services (see ADR-0028 addendum).
The default pilot observability stack stays Micrometer + actuator (backend) and stderr
telemetry dumps (voice runtime); nothing here runs unless you start it explicitly.

## 1. Start a local collector

```bash
docker compose -f deploy/observability/docker-compose.otel.yml up
```

This exposes OTLP on `localhost:4317` (gRPC) and `localhost:4318` (HTTP), prints received
spans/metrics (`debug` exporter), and serves collector metrics at
`http://localhost:8889/metrics`.

## 2. Enable export on the backend (Java)

Env vars (all default to inert):

| Env var | Default | Effect |
|---|---|---|
| `OTEL_METRICS_EXPORT_ENABLED` | `false` | `true` exports Micrometer meters over OTLP |
| `OTEL_TRACES_SAMPLER_ARG` | `0.0` | trace sampling probability (`1.0` = all HTTP server spans) |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | `http://localhost:4318/v1/metrics` | metrics endpoint |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `http://localhost:4318/v1/traces` | traces endpoint |

```bash
cd backend && set -a && . ../.env && set +a && \
  OTEL_METRICS_EXPORT_ENABLED=true OTEL_TRACES_SAMPLER_ARG=1.0 \
  mvn -q spring-boot:run
```

## 3. Enable export on the voice runtime (Python)

`voice_common/otel_export.py` ships each per-turn / per-call `TelemetryRecorder` as OTel
spans (with `correlation_id` / `conversation_id` / `turn_index` attributes). It is a no-op
unless enabled:

| Env var | Default | Effect |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(unset)_ | set (e.g. `http://localhost:4318`) to enable export |
| `VOICE_OTEL_EXPORT` | _(unset)_ | `1`/`true` also enables export |

```bash
cd voice-agent && \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
  ./.venv/bin/python -m web_voice.server   # or the relevant runtime entrypoint
```

## Cross-service correlation

`correlation_id` is the join key on both sides today (span attribute + backend log MDC).
Full W3C `traceparent` propagation on the runtime → backend HTTP hop (one trace id end to
end) is the remaining step of the full export path; see the ADR-0028 addendum
"deferred" note and the mandatory-export trigger.
