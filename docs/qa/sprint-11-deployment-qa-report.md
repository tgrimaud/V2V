# QA Functional And Latency Report — Sprint 11 (TASK-DEPLOY-001, TASK-DEPLOY-002, TASK-BE-021)

Date: 2026-08-03 · Environment: local dev (macOS, Docker 29.1.3, Postgres `pgvector:pg16` on `:5433`, Ollama up) · Frameworks: JUnit 5 + ArchUnit (backend), `unittest` + Behave (voice runtime).

## Executive Summary

- **Overall readiness:** GO for merge-readiness of the three tickets. Each passed adversarial review ≥ 90% and QA.
- **Main blockers:** none open. The one adversarial blocking finding (Actuator Redis health indicator flipping `/actuator/health` DOWN in default `memory` mode once the Redis starter is present) is **fixed and verified** (gated OFF by default; live-proven UP with no `redis` component).
- **Residual risks:** live multi-instance shared-context behind the VIP, and the combined *image + Redis* health behavior, are integration checks that materialize when the ticket branches merge to the sprint branch (owned by INFRA-001). Backend runtime here validated on Java 25 (target is JRE 17 in the image); image-level boot was validated on the DEPLOY branches.

## Scope Tested

- **Tickets:** TASK-DEPLOY-001 (backend Java image), TASK-DEPLOY-002 (voice bridge Python image), TASK-BE-021 (Redis-backed shared conversation memory + review fixes).
- **Channels:** N/A (packaging + backend memory adapter); voice runtime exercised via its own BDD suite.
- **Providers / fakes:** manual `FakeConversationTurnStore` (no Mockito, no live Redis) for the adapter; live Postgres + Ollama for the backend boot smoke; `SmallWebRTC`/fixture providers in the voice suite.
- **Environment:** local; container images built and boot-smoked in the prior session and present locally (`voice-support-backend:dev-test` 593 MB, `voice-support-voice:dev-test` 1.82 GB).

## Functional Results

| Area | Status | Evidence | Notes |
|---|---|---|---|
| BE-021 default `memory` mode unchanged | PASS | `mvn test` 330 green; startup log `[CONVERSATION-MEMORY] store=memory … process-local` | No behavior change for single-node/dev/tests |
| BE-021 Redis round-trip, bound, isolation, special chars, TTL | PASS | `RedisConversationMemoryAdapterTest` (fake store) | Oldest-first, LTRIM bound, per-conversation key isolation |
| BE-021 Redis outage degrades (no turn failure) | PASS | `redisOutageDegradesSafely`; WARN `[CONVERSATION-MEMORY]` + `voice_support.conversation_memory.degraded` counter | Read → empty history; write → skipped, turn still answered |
| BE-021 corrupt/legacy entry tolerated | PASS | `corruptEntryIsSkipped` | Corrupt entry dropped, surrounding valid turns preserved in order |
| BE-021 **health gate (blocking fix)** | PASS | `RedisHealthIndicatorGateTest` + **live**: memory → `/actuator/health` UP, no `redis` component; `REDIS_HEALTH_ENABLED=true` → `redis` component participates | Prevents HAProxy/HEALTHCHECK dropping healthy instances in `memory` mode |
| DEPLOY-001 backend image builds, non-root, boots, env-driven | PASS | prior `docker build` (593 MB), uid 1001, Spring Boot 3.4.1 boots `:8080`, fails only on absent DB; `HEALTHCHECK /actuator/health` | Artifact on `task/TASK-DEPLOY-001-backend-image` |
| DEPLOY-002 voice image builds, serves API, non-root | PASS | prior `docker build` (1.82 GB), uid 1001, `GET /` 200 + openapi 200, binds `0.0.0.0:8090` | Artifact on `task/TASK-DEPLOY-002-voice-image` |
| DEPLOY-002 packaged runtime behavior | PASS | voice suite **462 unittest OK**, **Behave 13 features / 36 scenarios / 169 steps** | Validates the runtime the image ships |

## Latency Results

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| Backend cold start | ~3.7–4.5 s | n/a | n/a | 2 | Cold | JVM 25 fat-jar boot to `Started VoiceSupportApplication` (Postgres+Ollama up) |
| `/actuator/health` response | <1 s | n/a | n/a | 3 | Warm | 200/UP composite (db, diskSpace, ping, ssl, liveness, readiness) |

Voice-path per-slice latency (STT/LLM/TTS/end-of-turn) is **not in scope** of these three tickets and is not re-measured here; it stays owned by the voice runtime stories (US-036 pipeline timing). This is a packaging/infra + backend-memory sprint, so end-to-end voice SLOs are explicitly **not** claimed from it.

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| Redis conversation memory adapter | GREEN | Hexagonal seam (`ConversationTurnStore`), graceful degrade, bounded list + TTL, review fixes applied | Prove multi-instance shared-context live (INFRA-001) |
| Actuator health composition | GREEN | Redis indicator correctly gated by `REDIS_HEALTH_ENABLED` | Set `REDIS_HEALTH_ENABLED=true` only in the redis-store `.env` |
| Backend image (DEPLOY-001) | GREEN | Builds, non-root, env-driven, healthcheck endpoint correct | Re-run build on the sprint branch after merge (now carries Redis starter) |
| Voice image (DEPLOY-002) | GREEN | Builds, serves API, packaged runtime fully green | Consider `opencv-python-headless` to shrink 1.82 GB (post-pilot) |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| — | No open defect from this QA cycle | — | — |
| Low (tracked) | Combined *backend image + Redis starter* health behavior validated at jar level, not yet at image level | Image-level re-validation pending branch integration | INFRA-001 |
| Low (tracked) | Voice image size 1.82 GB | Slower pulls | Post-pilot optimization |

## Open Questions

- **Product:** none for these tickets.
- **Architecture:** confirm Redis auth/TLS for the pilot (open input in ADR-0038); embeddings placement (INFRA-003).
- **Technical:** JRE 17 image vs local JVM 25 — image is the source of truth for the pilot; keep boot smoke on the sprint branch after merge.

## Recommendation

- **Go / No-go:** **GO** — all three tickets are merge-ready (adversarial ≥ 90%, QA passed).
- **Required fixes before pilot:** none from this cycle. At sprint-branch integration, set `REDIS_HEALTH_ENABLED=true` in the redis tier `.env`, and re-run the backend image boot smoke on the merged tree (INFRA-001 / DOC-003).
