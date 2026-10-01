# Adversarial Code Review — TASK-BE-023 (restrict the unauthenticated ops surface)

Reviewed: 2026-09-29 (in-session) · Branch: `task/TASK-BE-023-restrict-ops-surface` · Base: `feat/restart-from-scratch`

## Verdict

**Proceed.** The change fences the two anonymously-readable ops surfaces (`/actuator/metrics`
and the OpenAPI/Swagger docs) behind the existing api-key seam and a secure-by-default Actuator
exposure, with no conversation-behaviour change. Reuses the BE-019 `ApiKeyGuard`
(constant-time, open-when-blank) and the BE-021 env-gating precedent. No blocking findings.

## Satisfaction Score

Score: **93/100**
QA gate: **Pass**

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | No automated assertion that `/actuator/metrics` returns **404 by default**. It is a Spring exposure-config default (`management.endpoints.web.exposure.include: health,info`), which is heavy to cover without a full `@SpringBootTest`. | `application.yml` `include: ${MANAGEMENT_ENDPOINTS_EXPOSURE:health,info}`; the `@WebMvcTest` gate tests cover the docs paths, not the Actuator exposure filter. | Verify in pilot QA: `curl /actuator/metrics` → 404, `curl /actuator/health` → 200. Acceptable — the exposure list is a well-known Spring mechanism; a `@SpringBootTest(properties=…)` context smoke could be added later. |
| Low | The **docs** closure is conditional on a configured key (`CONVERSATION_API_KEY`) — an ops action on the pilot. When no key is set (localhost pilot) the docs stay open by design. The **metrics** closure is, in contrast, **unconditional** (fenced by default regardless of key). | `ApiKeyGuard.authorized()` returns `true` when the key is blank; `WebSecurityMvcConfig` adds the doc paths to the interceptor. | Documented in the ticket + the env table (`docs/operations/deployment-eir-ai4cc-tst.md`). Set `CONVERSATION_API_KEY` on any externally-reachable deploy to also close the docs. |
| Info | OTLP metrics export (TASK-OPS-007) is **not** impacted: only the **web** `/actuator/metrics` endpoint is fenced. Micrometer keeps collecting and exporting metrics. | `management.endpoints.web.exposure.include` governs only the HTTP surface, not the export pipeline. | — |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| `/v3/api-docs`, `/v3/api-docs.yaml`, grouped docs, `/swagger-ui.html`, `/swagger-ui/**` require `x-api-key` when a key is set | ✅ | `OpsSurfaceApiKeyTest` (`@WebMvcTest`, api-key=`s3cret`): 401 without header, 200 with header, on docs + `.yaml` + grouped + swagger paths |
| The ops surface stays **open when no key is set** (localhost pilot) | ✅ | `OpsSurfaceOpenWithoutKeyTest`: no key → 200 open |
| `/actuator/metrics` not anonymously readable off-box by default | ✅ (config) | `include: health,info` default; `/actuator/health` stays exposed for probes. Verified by config; pilot QA to confirm live 404/200 |
| No conversation-behaviour change; `mvn test` + ArchUnit green | ✅ | Backend **650** tests green incl. ArchUnit (Hexagonal / ContextBoundary / Naming); Ansible `qa-validate` **90/90 PASS** |

## Test Evidence

- Developer tests: `OpsSurfaceApiKeyTest` + `OpsSurfaceOpenWithoutKeyTest` (+ `DocsProbeController` fixture), 8 new tests; backend suite **650** green.
- Deploy parity: `qa-validate-ansible.sh` **90/90 PASS** (new `MANAGEMENT_ENDPOINTS_EXPOSURE` added to both the `.j2` template and `.env.example` → strict key-set-equality holds).
- Missing tests: automated `/actuator/metrics` 404 assertion (see non-blocking Low #1) — deferred to pilot QA.
- QA scenarios to run (pilot): key set → docs 401 / metrics 404 / health 200; key unset → docs 200.

## Observability And Latency

- Not runtime-affecting for the conversation path (no new spans required). The change only fences HTTP endpoints.
- The `/actuator/health` probe stays exposed so container/LB health checks are unchanged.
- OTLP metrics export (TASK-OPS-007) untouched — metrics collection + export continue.

## Security And Privacy

- Sensitive data risk: reduced — `/actuator/metrics` (which can leak internal timings/JVM/topology) is no longer anonymously readable by default; OpenAPI/Swagger (which enumerates the full API surface) is gated behind the api-key when a key is set.
- Identity/access risk: reuses the constant-time `ApiKeyGuard` (`MessageDigest.isEqual`), open-when-blank — same trust model as `/converse` and the BE-019 endpoints. No new bypass.
- Logging risk: none introduced.

## Required Developer Actions

1. None blocking. (Optional follow-up: a `@SpringBootTest(properties=…)` smoke asserting `/actuator/metrics` → 404.)

## Residual Risk If Accepted

- The docs closure depends on `CONVERSATION_API_KEY` being set on the deployment (ops action); the metrics closure is unconditional.
- Live 404/200 verification of the Actuator exposure is deferred to pilot QA.
