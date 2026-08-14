# BUG-011 — KB sync fails with 503 (`ERR_UPSTREAM`): embedding read-timeout too short for batch embedding

## Header

- **Bug ID:** BUG-011
- **Title:** Ollama embedding client read-timeout (5 s) is sized for single-query retrieval but KB sync embeds a large batch → `SocketTimeoutException: Read timed out` → sync returns 503
- **Status:** Ready for adversarial review
- **Severity:** High
- **Priority:** P1
- **Detected by:** User validation (first pilot deploy — first RAG sync)
- **Detected date:** 2026-08-14
- **Related user story:** TASK-BE-025 (embedding/retrieval client timeouts) / KB ingestion (EPIC-005)
- **Related epic:** EPIC-012 (V1 pilot deployment)
- **Branch:** fixed inline on `feat/sprint-11-remote-deployment` (found during deploy; no dedicated `fix/` branch)
- **Owner:** Backend developer

## Problem Statement

The first `POST /api/knowledge/sync` after deploy fails after ~5–6 s with HTTP 503 `ERR_UPSTREAM`. The knowledge base is never ingested, so the vector store stays empty and all answers fall back to "not enough info".

## Environment

- **Environment:** pilot (eir-ai4cc-tst), backend `.105`/`.106`, embeddings on Ollama (`nomic-embed-text`, 768-dim, CPU)
- **Channel:** backend-only (RAG ingestion)
- **Build or commit:** backend `0.5.0`; embedding client default read-timeout 5000 ms
- **Provider configuration:** Ollama CPU inference, cold model on first call

## Reproduction Steps

1. Given a freshly deployed backend with an empty vector store and a cold Ollama model.
2. When `POST /api/knowledge/sync` runs (embeds all markdown/CSV chunks in one ingestion pass).
3. Then the embedding HTTP call exceeds the 5 s read-timeout (cold model + many chunks) → `SocketTimeoutException: Read timed out` → wrapped as `ERR_UPSTREAM` → HTTP 503; the sync aborts. Retries can pile up concurrently and saturate Ollama CPU, degrading live `/converse` too.

## Expected Result

A first KB sync completes and populates the vector store; the per-query retrieval path keeps a short, protective timeout so a live turn fails fast instead of hanging.

## Actual Result

Sync returns 503 within ~6 s; vector store empty; grounded answers impossible. Under retries, Ollama CPU is saturated and concurrent `/converse` calls also slow down / error.

## Evidence

- Backend log: `org.springframework.web.client...`/`SocketTimeoutException: Read timed out` on the embedding call, surfaced as `ERR_UPSTREAM` 503 on `/api/knowledge/sync`.
- After raising the embedding read-timeout, the same sync completes and `/converse` returns grounded answers at 0.77–1.4 s.

## Impact

- **Customer / functional:** without a successful sync the bot cannot ground any answer — the core RAG value proposition is down.
- **Operational / latency:** retry storms saturate Ollama CPU and degrade live voice turns.
- No security/privacy impact.

## Acceptance Criteria For Fix

- [x] The defect no longer reproduces (first sync completes on a cold model).
- [ ] A regression test covers the timeout wiring (embedding vs retrieval timeouts are distinct + configurable).
- [x] OpenTelemetry: sync already emits outcome/duration; verify the embedding-slice timing is captured (see follow-up).
- [ ] Adversarial code review ≥ 90%.
- [ ] QA retest passes.
- [x] Documentation/backlog updated (group_vars comment + this ticket).

## Developer Notes

- **root cause:** the embedding client read-timeout (default 5000 ms) is sized for a single-query embedding at retrieval time, but KB **sync** batches many chunks into one long call on a cold CPU model, blowing past 5 s.
- **files changed:** `deploy/ansible/group_vars/backend.yml` — `java_opts` adds `-Dvoice-support.embedding.timeout-ms=120000` (5 s → 120 s). Retrieval stays protected by the separate `voice-support.retrieval.timeout-ms` (~6 s) so live turns still fail fast.
- **tests added/updated:** none yet (see AC).
- **OpenTelemetry added/updated:** existing sync outcome/duration logs; embedding-slice span to confirm.
- **residual risk:** deploy-config workaround. The batch-embedding timeout being coupled to a single JVM property is coarse; the proper fix is an ingestion-specific embedding timeout + chunked/async sync so a slow cold model can't block or be retried into contention. **Follow-up (out of this fix):** split ingestion vs query embedding timeouts in the backend config and make sync resilient to a cold model (batching / backpressure).

## QA Retest

- **Retested by:** (pending)
- **Retest date:** —
- **Scenarios rerun:** backend restarted to clear concurrent syncs; re-ran `POST /api/knowledge/sync` → completed; `/converse` grounded at 0.77–1.4 s.
- **Result:** Passed (live, informal) — formal QA retest pending.
- **Retest evidence:** pilot 2026-08-14, grounded answers from Redis-backed memory across turns.

## Closure

- **Closed by:** —
- **Closed date:** —
- **Closure reason:** —
