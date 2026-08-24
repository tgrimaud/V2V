# QA Report — BUG-014 durable Ollama-DNS fix

- **Ticket:** [BUG-014](../../product-backlog/bugs/BUG-014-backend-ollama-dns-lost-after-container-churn.md)
- **Branch:** `fix/BUG-014-ollama-dns-durable` (off `feat/sprint-11-remote-deployment`)
- **Date:** 2026-08-24
- **Severity / Priority:** High / P1
- **Verdict:** **GO** (merge-ready) — adversarial review 93/100 (Pass). Live pilot restart
  retest deferred to the gated live-deploy window (open input #1); all offline gates green.

## Scope tested

The durable fix removes aardvark-dns from the critical path (static IP + `extra_hosts`),
adds an embedding-hop indicator to the deep `/actuator/health`, and hardens JVM DNS
(zero negative-TTL) + a connect-scoped bounded retry on the embedding call.

## Functional results

| # | Case | Expectation | Result |
|---|------|-------------|--------|
| 1 | `ollama` name pinned via `extra_hosts` on a static IP | compose renders `ollama=10.123.0.11` + `ipv4_address` on `backend_net` | PASS (compose 25/25) |
| 2 | Name resolution independent of aardvark-dns | `/etc/hosts` entry present regardless of network recreation → `--force-recreate` restores RAG | PASS (config-verified; live retest deferred) |
| 3 | Embedding-hop readiness UP when reachable | `OllamaEmbeddingHealthAdapter` → UP, detail `hop=embedding/ollama` | PASS (unit) |
| 4 | Embedding-hop readiness DOWN on `UnknownHostException` | health DOWN, error = `UnknownHostException`, no host/path leaked | PASS (unit) |
| 5 | Readiness gated OFF locally / ON pilot | `@ConditionalOnProperty(voice-support.embedding.health.enabled)`; env `EMBEDDING_HEALTH_ENABLED` | PASS (config) |
| 6 | Connect/DNS failure self-heals on retry | `RetryingClientHttpRequestInterceptor` retries `UnknownHostException`/`ConnectException` | PASS (unit) |
| 7 | Slow-but-reachable Ollama not doubled | read timeout (`SocketTimeoutException`) is NOT retried | PASS (unit) |
| 8 | Retry cap clamped | `maxAttempts < 1` → single attempt | PASS (unit) |
| 9 | JVM negative-DNS-TTL disabled | `hardenDnsCaching()` sets `networkaddress.cache.negative.ttl=0` | PASS (unit) |

## Test evidence

- Backend `mvn test`: **399** green (+7 vs 392), ArchUnit (Naming/Hexagonal/ContextBoundary) OK.
- Compose `deploy/compose/qa-validate.sh`: **25/25** (new BUG-014 invariants: static-IP pin,
  `ipv4_address`, embedding-readiness flag).
- Ansible `deploy/ansible/qa-validate-ansible.sh`: **69/69** (also repaired 3 stale assertions
  left by the podman migration / re-enable-hook extraction — QA-script only, no behavior change).
- Backend `.env` template render verified with the 3 new vars.

## Observability

- Retrieval slice keeps recording `outcome` (success/timeout/error) — a runtime embedding
  failure is already an alertable signal (`BackendTelemetry`).
- The new readiness signal turns `/actuator/health` DOWN (503) on a broken hop, which HAProxy
  (TASK-INFRA-007 deep health) uses to drain the node — a distinct, alertable state.
- Health detail is PII-safe (exception class name only, never host/path/message).

## Security / privacy

- No secrets added; the static IP/subnet are non-sensitive network config.
- Health payload exposes no host, URL, or exception message.

## Residual risk (accepted)

- **Live pilot retest deferred** (restart → `converse` 200 without `down && up`) until the
  gated live-deploy window (open input #1). Offline config + unit evidence cover the contract.
- Default subnet `10.123.0.0/24` is chosen outside podman's `10.89.0.0/16` pool; if it collides
  with a pre-existing network on a VM, override `BACKEND_NET_SUBNET`/`OLLAMA_STATIC_IP` in `.env`.
