# BUG-014 — Backend loses `ollama` name resolution after container/network churn

## Header

- **Bug ID:** BUG-014
- **Title:** After a container/network restart the backend can no longer resolve the `ollama` service name (`UnknownHostException: ollama`, then a 10s connect timeout), so RAG retrieval fails with `ERR_UPSTREAM` until the compose project network is recreated
- **Status:** New
- **Severity:** High
- **Priority:** P1
- **Detected by:** User validation (pilot voice-journey validation)
- **Detected date:** 2026-08-14
- **Related user story:** TASK-DEPLOY-001 (backend tier compose) / ADR-0039 (embeddings placement)
- **Related epic:** EPIC-012 (V1 pilot deployment)
- **Branch:** worked around live on the pilot; fix pending on a dedicated ticket branch
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

- [ ] The backend reliably reaches Ollama across container restarts without a manual
      network teardown (candidate fixes: pin an alias/`extra_hosts`, `depends_on` +
      restart ordering, a stable network, or host networking for the Ollama hop).
- [ ] A readiness/health signal reflects embedding reachability so a broken Ollama hop
      does not pass as healthy (align with the retrieval slice).
- [ ] Deterministic reproduction + verification steps captured (restart → converse 200).
- [ ] OpenTelemetry: retrieval slice already records `outcome`; confirm a DNS/connect
      failure is a distinct, alertable signal.
- [ ] Adversarial review ≥ 90%; QA retest passes on the pilot.

## Developer Notes

- **suspected root cause:** aardvark-dns / resolv.conf state goes stale when the backend
  container is recreated without recreating the project network; `--force-recreate`
  keeps the old network wiring, `down && up` rebuilds it.
- **live workaround applied:** `podman compose down && up` on `t03`/`t04` (RAG restored).
- **residual risk:** until a durable fix lands, document "on backend restart, run
  `down && up`, not just `--force-recreate`" in the runbook.

## Closure

- **Closed by:** —
- **Closed date:** —
- **Closure reason:** —
