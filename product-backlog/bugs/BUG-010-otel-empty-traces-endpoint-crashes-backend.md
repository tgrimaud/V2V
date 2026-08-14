# BUG-010 — Backend crash-loops at startup on empty OTLP traces endpoint

## Header

- **Bug ID:** BUG-010
- **Title:** Empty `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` makes Spring Boot 3.4 fail context startup (`Invalid endpoint, must start with http:// or https://`)
- **Status:** Ready for adversarial review
- **Severity:** Critical
- **Priority:** P0
- **Detected by:** User validation (first pilot deploy)
- **Detected date:** 2026-08-14
- **Related user story:** TASK-OPS-007 (centralized OTLP export deploy config) / TASK-OBS-001 (OpenTelemetry instrumentation)
- **Related epic:** EPIC-012 (V1 pilot deployment)
- **Branch:** fixed inline on `feat/sprint-11-remote-deployment` (found during deploy; no dedicated `fix/` branch)
- **Owner:** Backend developer / infra

## Problem Statement

With OTLP export disabled (no collector at the pilot), the deploy renders
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=""` (empty string). The backend container then exits immediately at Spring context init and crash-loops; the health check never turns healthy and the deploy fails.

## Environment

- **Environment:** pilot (eir-ai4cc-tst), backend tier (`.105`/`.106`)
- **Channel:** backend-only
- **Build or commit:** backend image `0.5.0`; `deploy/ansible/roles/compose_tier/templates/backend.env.j2` + `deploy/compose/backend/docker-compose.yml` as merged pre-fix
- **Provider configuration:** Spring Boot 3.4.1, `otel-spring-boot-starter`; `management.otlp.metrics.export.enabled: false`, tracing sampler `0.0`

## Reproduction Steps

1. Given `otel_collector_endpoint` is empty (OTLP export off — the default pilot posture).
2. When `backend.env.j2` emits `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=` (empty) and the container starts.
3. Then the OTLP **tracing** exporter auto-config builds regardless (it has no `enabled` gate like the metrics exporter) and validates the endpoint → `IllegalArgumentException: Invalid endpoint, must start with http:// or https://` → context fails → container exits and crash-loops.

## Expected Result

With export disabled, the backend starts normally and tracing/metrics stay inert (no data shipped), without requiring a live collector.

## Actual Result

Backend never reaches `Started VoiceSupportApplication`; `podman logs` shows the OTLP endpoint `IllegalArgumentException` at bean init; container restarts endlessly; deploy health gate times out.

## Evidence

- `podman logs voice-support-backend`: `... Invalid endpoint, must start with http:// or https://` during OTLP tracing exporter init.
- Metrics exporter is safely gated (`management.otlp.metrics.export.enabled: false`) — only **tracing** breaks on the empty value, confirming the missing gate.
- Setting a syntactically valid endpoint (even a non-reachable localhost) + sampler `0.0` starts cleanly with zero spans shipped.

## Impact

- **Operational / pilot-readiness:** total backend outage in the default "no collector" posture — the exact config used to bring up the pilot. Critical deploy blocker.
- No customer data / security impact (observability plumbing only).

## Acceptance Criteria For Fix

- [x] The defect no longer reproduces (backend starts with export disabled).
- [ ] A regression test covers it (deploy-config lint / a Spring context test asserting startup with export off).
- [x] OpenTelemetry: preserved — export stays OFF (metrics `enabled:false`, tracing sampler `0.0`); no spans/metrics shipped, no behavior change when a real collector is later wired.
- [ ] Adversarial code review ≥ 90%.
- [ ] QA retest passes.
- [x] Documentation/backlog updated (template + compose comments + this ticket).

## Developer Notes

- **root cause:** Spring Boot 3.4's OTLP **tracing** exporter is built whenever the endpoint property is present and validates its value; an empty string fails validation. Unlike the metrics exporter, it has no `export.enabled` switch, so "disable by blanking the URL" crashes instead of no-op'ing.
- **files changed:**
  - `deploy/ansible/roles/compose_tier/templates/backend.env.j2` — emit valid localhost defaults (`http://localhost:4318/v1/traces`, `/v1/metrics`) when `otel_collector_endpoint` is empty, instead of an empty string.
  - `deploy/compose/backend/docker-compose.yml` — harden the fallbacks (`${OTEL_EXPORTER_OTLP_TRACES_ENDPOINT:-http://localhost:4318/v1/traces}`, same for metrics).
- **tests added/updated:** none yet (see AC).
- **OpenTelemetry added/updated:** unchanged semantics — inert (sampler 0.0 + metrics disabled); a valid-but-unused URL only satisfies the validator.
- **residual risk:** low; the localhost default is never contacted while the sampler is 0.0 and metrics export is disabled. Cleaner long-term fix (app-side): omit the property entirely when disabled rather than defaulting it — tracked as follow-up.

## QA Retest

- **Retested by:** (pending)
- **Retest date:** —
- **Scenarios rerun:** backend redeployed with export off → `Started VoiceSupportApplication`, `/actuator/health` = UP, converse turns served.
- **Result:** Passed (live, informal) — formal QA retest pending.
- **Retest evidence:** pilot backend healthy 2026-08-14; grounded converse at 0.77–1.4s.

## Closure

- **Closed by:** —
- **Closed date:** —
- **Closure reason:** —
