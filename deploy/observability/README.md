# Centralized OpenTelemetry observability — TASK-OBS-001 + TASK-OPS-007

OTLP export is **additive and off by default** on both services (see ADR-0028 addendum).
When enabled, the backend (Java) and the voice runtime (Python) ship traces + metrics to
**one** OpenTelemetry Collector, which fans metrics out to Prometheus so p50/p95/p99 by
slice are queryable in a single place and a call can be followed across both tiers.

```
 voice runtime ─OTLP┐                          ┌─ debug (stdout: spans + metrics)
                     ├─▶ otel-collector :4318 ─┤
 backend  ─────OTLP─┘        (:8889 /metrics)  └─ prometheus :9090  (slice percentiles)
```

## Pilot pipeline (centralized)

The collector + Prometheus are one opt-in compose stack. Bring it up on the chosen
observability host (any app VM works for the pilot):

```bash
docker compose -f deploy/observability/docker-compose.otel.yml up -d
```

- OTLP in: `:4317` (gRPC) / `:4318` (HTTP)
- Collector-exported metrics scrape: `:8889/metrics`
- Prometheus UI / query API: `:9090`

The backend publishes p50/p95/p99 on the `voice_support.slice` timer
(`management.metrics.distribution` in `application.yml`), so once export is on they land in
Prometheus as `voice_support_slice_*` series filterable by `slice` / `channel` / `provider`
/ `outcome`. Grafana is optional and can be added later pointed at Prometheus.

## Enabling export in the tst deploy (Ansible)

Set one variable — the collector's OTLP-HTTP base URL — and redeploy. The templates derive
everything else and keep export OFF when it is empty (safe default):

```bash
cd deploy/ansible
ansible-playbook deploy.yml -e otel_collector_endpoint=http://<obs-host>:4318
```

| group_vars/all/vars.yml | Default | Effect |
|---|---|---|
| `otel_collector_endpoint` | `""` (OFF) | collector OTLP-HTTP base URL; enables export on both tiers |
| `otel_traces_sampler_arg` | `"1.0"` | backend root-trace sampling when export is on (full for the pilot) |

Rendered effect (from `backend.env.j2` / `voice.env.j2`):

- backend → `OTEL_METRICS_EXPORT_ENABLED=true`, `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=<base>/v1/metrics`,
  `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=<base>/v1/traces`, `OTEL_TRACES_SAMPLER_ARG=1.0`
- voice → `OTEL_EXPORTER_OTLP_ENDPOINT=<base>`

Export is async/best-effort: if the collector is down a turn is never blocked.

## Enabling export locally (per service)

Backend env vars (all default to inert):

| Env var | Default | Effect |
|---|---|---|
| `OTEL_METRICS_EXPORT_ENABLED` | `false` | `true` exports Micrometer meters over OTLP |
| `OTEL_TRACES_SAMPLER_ARG` | `0.0` | trace sampling probability (`1.0` = all backend-originated server spans) |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | `http://localhost:4318/v1/metrics` | metrics endpoint |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `http://localhost:4318/v1/traces` | traces endpoint |

```bash
cd backend && set -a && . ../.env && set +a && \
  OTEL_METRICS_EXPORT_ENABLED=true OTEL_TRACES_SAMPLER_ARG=1.0 \
  mvn -q spring-boot:run
```

Voice runtime (`voice_common/otel_export.py` ships each per-turn `TelemetryRecorder` as OTel
spans). No-op unless enabled:

| Env var | Default | Effect |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(unset)_ | set (e.g. `http://localhost:4318`) to enable export |
| `VOICE_OTEL_EXPORT` | _(unset)_ | `1`/`true` also enables export |

```bash
cd voice-agent && \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
  ./.venv/bin/python -m web_voice.server   # or the relevant runtime entrypoint
```

## Cross-service correlation (one trace end to end)

A voice turn and its backend spans share **one W3C trace** (TASK-OPS-007):

1. `voice_common/trace_context.py` derives a deterministic trace id + span id from the
   turn's `correlation_id` (BLAKE2b — a pure function, no shared state).
2. `conversation_backend/http_backend.py` sends `traceparent: 00-<trace>-<span>-01` on the
   HTTP hop. The backend ships `micrometer-tracing-bridge-otel` with default W3C
   propagation + a ParentBased sampler, so it continues that exact trace id — the `01`
   sampled flag keeps the trace even when `OTEL_TRACES_SAMPLER_ARG` is low.
3. `voice_common/otel_export.py` opens the exported `voice.turn` root span under the *same*
   derived trace id + parent span id, so the voice trace and the backend spans line up
   under one trace id in the collector.

`correlation_id` also remains a first-class attribute on both sides (span attribute +
backend log MDC), so a turn is still filterable even outside a trace view.
