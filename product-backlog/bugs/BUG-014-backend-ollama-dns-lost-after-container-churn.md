# BUG-014 — Backend loses `ollama` name resolution after container/network churn

## Header

- **Bug ID:** BUG-014
- **Title:** After a container/network restart the backend can no longer resolve the `ollama` service name (`UnknownHostException: ollama`, then a 10s connect timeout), so RAG retrieval fails with `ERR_UPSTREAM` until the compose project network is recreated
- **Status:** ✅ **Closed** — adversarial review 93/100 (Pass) + functional QA GO + **live pilot retest PASSED (2026-08-24)**. Merged to `feat/restart-from-scratch` (`f153257` → sprint close `6bf8de2`); image `sha-6bf8de2` deployed to backend tier t03+t04. **Live-verified:** `/etc/hosts` pin `10.123.0.11 ollama`, resolution off aardvark-dns, backend container churn (`--force-recreate --no-deps`) → `converse` **200** grounded with **no `UnknownHostException`/`ERR_UPSTREAM`**, and `/actuator/health` **503↔200** on ollama stop/start (embedding-hop gate). Backend `mvn test` **399** green (+7), ArchUnit OK; compose `qa-validate.sh` **25/25**; ansible `qa-validate-ansible.sh` **69/69**. [QA report](../../docs/qa/bug-014-ollama-dns-durable-qa-report.md).
- **Severity:** High
- **Priority:** P1
- **Detected by:** User validation (pilot voice-journey validation)
- **Detected date:** 2026-08-14
- **Related user story:** TASK-DEPLOY-001 (backend tier compose) / ADR-0039 (embeddings placement)
- **Related epic:** EPIC-012 (V1 pilot deployment)
- **Branch:** worked around live on the pilot; durable fix on `fix/BUG-014-ollama-dns-durable` (to create at implementation start — before Sprint 12)
- **Owner:** Backend / deployment developer

## Problem Statement

The backend container reaches Ollama by the compose service name `ollama`. After a
container or podman-network restart, name resolution breaks: the backend logs
`java.net.UnknownHostException: ollama` on `POST http://ollama:11434/api/embed` (and,
in an intermediate state, a ~10s connect timeout), while Ollama itself is healthy and
reachable **by IP** from the host. Query embedding fails, so RAG retrieval returns
`ERR_UPSTREAM` (HTTP 503) on every `/api/conversation/converse` call.

## Environment

- **Environment:** pilot (eir-ai4cc-tst); backend nodes `vla-ai4cc-t03/t04`
- **Channel:** backend-only (conversation `/converse`, retrieval slice)
- **Build or commit:** backend image `0.5.x`; compose network `backend_default` (podman + aardvark-dns)
- **Provider configuration:** `OLLAMA_BASE_URL=http://ollama:11434`, `nomic-embed-text`

## Reproduction Steps

1. Given a running backend tier (backend + ollama on `backend_default`).
2. When the backend (or the podman network) is restarted / churns.
3. Then `POST /api/conversation/converse` returns HTTP 503 `ERR_UPSTREAM`; backend logs
   show `UnknownHostException: ollama` (or a 10s timeout) at
   `OllamaApi.embed → PgVectorStore.getQueryEmbedding`, even though
   `curl http://<ollama-ip>:11434/api/tags` from the host is instant.

## Expected Result

The backend resolves and reaches `ollama` reliably across container restarts, without a
manual network teardown. RAG retrieval succeeds (`slice=retrieval outcome=success`).

## Actual Result

`--force-recreate backend` alone did **not** restore resolution; a full
`podman compose down && up` (which recreates the `backend_default` network + refreshes
aardvark-dns) was required. After that, retrieval succeeded in ~330 ms and DNS+TCP from
inside the backend container worked (`CONNECT_OK`, `HTTP/1.0 200`).

## Evidence

- Fresh log: `ResourceAccessException: I/O error on POST request for "http://ollama:11434/api/embed": ollama` → `Caused by: java.net.UnknownHostException: ollama`.
- Both containers on `backend_default` with alias `ollama`; `dns_enabled=true`; aardvark-dns running; Ollama reachable at `10.89.0.2:11434` (200) from host.
- After `down && up`: backend `/etc/resolv.conf` → `nameserver 10.89.1.1`; in-container `exec 3<>/dev/tcp/ollama/11434` → `CONNECT_OK`; retrieval telemetry `outcome=success duration_ms≈330`.
- `-Djava.net.preferIPv4Stack=true` alone did **not** fix it (ruling out an AAAA-only cause).

## Impact

- **Customer / pilot-readiness:** any backend restart can silently take RAG offline
  (503 on every turn); the voice journey degrades to the safe fallback.
- **Operational:** the health check stays green (Tomcat up) while conversation is
  broken; needs a manual `down && up` to recover — not acceptable for the pilot.

## Acceptance Criteria For Fix

- [x] The backend reliably reaches Ollama across container restarts without a manual
      network teardown — the `ollama` name is pinned via `extra_hosts: "ollama:<static-ip>"`
      on the backend + a static `ipv4_address` on a user-defined network (`backend_net`).
      `/etc/hosts` wins over DNS (nsswitch), so resolution no longer depends on aardvark-dns
      rebuilding; `--force-recreate backend` re-writes `/etc/hosts` and restores RAG.
- [x] A readiness/health signal reflects embedding reachability — `OllamaEmbeddingHealthAdapter`
      contributes an `embedding` indicator to the aggregated `/actuator/health` (deep health,
      TASK-INFRA-007), returning DOWN so HAProxy drains the node when the Ollama hop is broken.
      Gated ON only on the pilot backend tier (`EMBEDDING_HEALTH_ENABLED`).
- [x] Deterministic verification captured — compose `qa-validate.sh` locks the static-IP +
      extra_hosts + embedding-readiness invariants (25/25); unit tests cover UP/DOWN + retry +
      DNS hardening. Live restart → `converse` 200 retest on the pilot **PASSED 2026-08-24**
      (image `sha-6bf8de2` on t03+t04; churn survived, health-gate DOWN/UP verified).
- [x] OpenTelemetry: the retrieval slice already records `outcome` (success/timeout/error); a
      DNS/connect failure now also surfaces as a distinct, alertable `/actuator/health` DOWN
      (the `embedding` indicator carries the failing exception class, PII-safe).
- [ ] Adversarial review ≥ 90%; QA retest passes on the pilot.

## Fix Implementation (2026-08-24)

Three coordinated changes, matching the decided approach:

1. **Stable reachability (primary).** `deploy/compose/backend/docker-compose.yml`: a
   user-defined `backend_net` (pinned subnet, default `10.123.0.0/24` — outside podman's
   `10.89.0.0/16` pool), the `ollama` sidecar bound to a static `ipv4_address`
   (`OLLAMA_STATIC_IP`, default `10.123.0.11`), and the backend given
   `extra_hosts: ["ollama:${OLLAMA_STATIC_IP}"]`. `OLLAMA_BASE_URL=http://ollama:11434`
   is unchanged — the name now resolves via `/etc/hosts`, independent of aardvark-dns.
   Mirrored in `.env.example`, `group_vars/backend.yml`, `backend.env.j2`.
2. **Embedding reachability in readiness.** `OllamaEmbeddingHealthAdapter` (a `HealthIndicator`
   probing `GET /api/tags` with short timeouts), registered via `@ConditionalOnProperty`
   (`voice-support.embedding.health.enabled`) so it is inert locally and ON in the pilot.
3. **JVM DNS + retry hardening.** `VoiceSupportApplication.hardenDnsCaching()` sets
   `networkaddress.cache.negative.ttl=0` (no negative-DNS caching), and the embedding
   `RestClient` gets a bounded `RetryingClientHttpRequestInterceptor`
   (`voice-support.embedding.max-attempts`, default 2) so a single stale lookup self-heals.

## Developer Notes

- **suspected root cause:** aardvark-dns / resolv.conf state goes stale when the backend
  container is recreated without recreating the project network; `--force-recreate`
  keeps the old network wiring, `down && up` rebuilds it.
- **live workaround applied:** `podman compose down && up` on `t03`/`t04` (RAG restored).
- **residual risk:** until a durable fix lands, document "on backend restart, run
  `down && up`, not just `--force-recreate`" in the runbook.

## Chosen Fix Approach (decided 2026-08-15, global-review decision #3)

**Decision:** take `aardvark-dns` out of the critical path rather than trying to make
compose DNS survive churn. Since ADR-0039 runs Ollama as a **per-VM CPU sidecar**, the
backend does not need service discovery to find it — a stable, restart-independent path
is both simpler and more robust. Three coordinated changes:

1. **Stable reachability (primary fix).** Point the backend at Ollama over a path that
   does not depend on aardvark-dns rebuilding after churn. Preferred: reach Ollama on the
   **host** (published `:11434` on the VM) via a fixed address, or pin a **static IP on a
   stable user-defined network + `extra_hosts: "ollama:<ip>"`** so the `ollama` name always
   resolves regardless of network recreation. `--force-recreate backend` must then restore
   RAG without a `down && up`.
2. **Embedding reachability in readiness/health.** Extend the deep `/actuator/health`
   (already DB + Redis) with an **embedding-hop indicator** so a broken Ollama path returns
   503 and HAProxy pulls the node out of rotation — instead of staying green while
   conversation is broken. Align the indicator with the retrieval slice outcome.
3. **JVM DNS + retry hardening.** Cap the JVM **negative DNS TTL**
   (`networkaddress.cache.negative.ttl`) so a transient `UnknownHostException` is not cached
   for the process lifetime, and add a bounded retry on the embedding call so a single stale
   lookup self-heals instead of failing the turn.

**Timing:** dedicated P1 fix on `fix/BUG-014-ollama-dns-durable`, **before Sprint 12**
(pilot-blocking reliability). Standard loop: implement → adversarial review ≥ 90% → QA
retest on the pilot (restart → `converse` 200, no manual `down && up`).

**Runbook (interim, until the fix is deployed):** on backend restart run `podman compose down && up`
(recreates `backend_default` + refreshes aardvark-dns), **not** just `--force-recreate`. Once the
durable fix (static-IP `extra_hosts`) is deployed on the pilot, `--force-recreate backend` alone
restores RAG and this interim step is no longer needed.

## Closure

- **Closed by:** —
- **Closed date:** —
- **Closure reason:** —
