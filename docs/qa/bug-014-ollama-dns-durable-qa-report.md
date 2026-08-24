# QA Report — BUG-014 durable Ollama-DNS fix

- **Ticket:** [BUG-014](../../product-backlog/bugs/BUG-014-backend-ollama-dns-lost-after-container-churn.md)
- **Branch:** `fix/BUG-014-ollama-dns-durable` (off `feat/sprint-11-remote-deployment`)
- **Date:** 2026-08-24
- **Severity / Priority:** High / P1
- **Verdict:** **GO** — adversarial review 93/100 (Pass); merged to `feat/restart-from-scratch`
  (`f153257` → sprint close `6bf8de2`). **Live pilot retest executed and PASSED on 2026-08-24**
  (image `sha-6bf8de2` deployed to the backend tier t03+t04); all offline gates green.

## Scope tested

The durable fix removes aardvark-dns from the critical path (static IP + `extra_hosts`),
adds an embedding-hop indicator to the deep `/actuator/health`, and hardens JVM DNS
(zero negative-TTL) + a connect-scoped bounded retry on the embedding call.

## Functional results

| # | Case | Expectation | Result |
|---|------|-------------|--------|
| 1 | `ollama` name pinned via `extra_hosts` on a static IP | compose renders `ollama=10.123.0.11` + `ipv4_address` on `backend_net` | PASS (compose 25/25) |
| 2 | Name resolution independent of aardvark-dns | `/etc/hosts` entry present regardless of network recreation → `--force-recreate` restores RAG | **PASS (live 2026-08-24)** — see live retest below |
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

## Live pilot retest (2026-08-24, eir-ai4cc-tst)

Image `sha-6bf8de2` (feat/restart-from-scratch HEAD) deployed to the backend tier via
`ansible-playbook deploy.yml --limit backend -e image_tag=sha-6bf8de2` (rolling serial:1,
t03 then t04, health-gated; PLAY RECAP `failed=0` both nodes). Baseline before the deploy: the
pilot ran `voice-support-backend:0.5.0` resolving `ollama` via aardvark-dns (`10.89.1.2
ollama.dns.podman`) — the fragile path.

| Step | Evidence (t03 primary) | Result |
|------|------------------------|--------|
| Fix deployed | backend `sha-6bf8de2` healthy; `.env` has `OLLAMA_STATIC_IP=10.123.0.11`, `BACKEND_NET_SUBNET`, `EMBEDDING_HEALTH_ENABLED=true` | PASS |
| Volet 1 — static pin | `/etc/hosts` → `10.123.0.11 ollama`; `getent hosts ollama` resolves via the pin, **not** aardvark-dns | PASS |
| Volet 1 — **churn** | `podman compose up -d --force-recreate --no-deps backend` (cid `73b64a6c…`→`16e4c521…`), network+ollama untouched; post-churn `getent ollama`=`10.123.0.11` and `converse` → **HTTP 200** grounded (conf 0.79, 1.39 s), **no `UnknownHostException`/`ERR_UPSTREAM`** | PASS |
| Volet 2 — health gate | stop `voice-support-ollama` → `/actuator/health` → **503 DOWN** (immediate); restart → **200 UP** (immediate) → proves the embedding-hop indicator gates the composite health HAProxy drains on | PASS |
| Tier consistency | t04 also on `sha-6bf8de2`, `getent ollama`=`10.123.0.11`, health 200, converse 200 | PASS |

Volet 3 (JVM negative-DNS-TTL=0 + bounded connect-scoped retry) is belt-and-suspenders behind
the static pin; it is covered by unit tests and not separately induced live (would require
forcing a transient lookup failure). The churn test — the actual BUG-014 regression — passed.

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

- **Live pilot retest DONE** (2026-08-24): backend container churn → `converse` 200 without a
  `down && up`, and the health-gate DOWN/UP transition, both verified on t03 (+ t04 consistency).
- Default subnet `10.123.0.0/24` is chosen outside podman's `10.89.0.0/16` pool; if it collides
  with a pre-existing network on a VM, override `BACKEND_NET_SUBNET`/`OLLAMA_STATIC_IP` in `.env`.
