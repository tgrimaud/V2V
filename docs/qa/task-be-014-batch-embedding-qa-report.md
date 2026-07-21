# QA Report — TASK-BE-014 (Batch embedding/insert + sync observability)

**Ticket:** TASK-BE-014 — Batch embedding/insert (`VectorStorePort.storeChunks`) + sync
progress metrics/logs
**Parent:** EPIC-005 (Answer engine / knowledge base)
**Branch:** `task/TASK-BE-014-batch-embedding`
**Depends on:** TASK-BE-013 (CSV connector + domain classifier)
**Date:** 2026-07-21

## Executive Summary

- **Overall readiness:** Functional acceptance **PASS** — batched write path implemented,
  **184 tests green** (unit + Cucumber BDD + ArchUnit, infra-free), and **live-validated** on
  the real Eir corpus against Postgres (pgvector) + Ollama.
- **Adversarial review:** **93/100 — QA gate Pass** (`docs/qa/task-be-014-adversarial-review.md`).
  The one material finding (silent failure path) was fixed in-loop: `SyncObserverPort.syncFailed`
  now emits a failure metric + `[KB-SYNC] op=sync-failed` log with progress-so-far, covered by tests.
- **Performance:** batched sync of 150 articles / 1 901 chunks dropped **75 s → 44.7 s
  (~40% faster)**, throughput **42.7 chunks/s**, with the classification distribution
  **unchanged** (pure performance change).
- **Observability:** per-batch and full-sync Micrometer meters exposed via actuator +
  `[KB-SYNC]` structured logs with throughput.
- **Corpus size clarified:** the corpus is **306 articles** (the ~40,900 line count is
  multi-line HTML, not article count). The **full corpus** ingests in **~73–92 s** in a
  single request, so no async job is needed at this size — it becomes relevant only if the
  corpus grows by orders of magnitude.

## Scope Under Test

- `VectorStorePort.storeChunk` → **`storeChunks(document, chunks)`** (batched, returns count).
- `PgVectorStoreAdapter`: one `vectorStore.add(...)` per document (batch embed + multi-row
  insert) via a `toDocument(...)` helper.
- New domain out-port **`SyncObserverPort`** (`batchStored`, `syncCompleted`, `syncFailed`)
  driven by `KnowledgeSyncService`; infra **`LoggingSyncObserverAdapter`** (Micrometer + logs).
- `KnowledgeSyncService`: per-document store timing, chunk totals, per-document ledger
  commit (resumable), completion event.

## Functional Results

| Check | Result |
|---|---|
| Batched write (one `add` per document) | PASS — unit test asserts one `storeChunks` call per document |
| Chunk totals & observer events | PASS — batch events per ingested doc + one completion with matching totals |
| Idempotency preserved | PASS — full-corpus re-sync `0 ingested / 306 skipped` (unit + live 16.7 s) |
| Deletion-diff preserved | PASS — existing ledger-diff tests unchanged |
| Retrieval correctness post-batching | PASS — live `verdict=PASS`, billing top hits ~0.75 for "credit vetting" |
| Failure path observable + resumable | PASS — `syncFailed` metric + `[KB-SYNC] op=sync-failed` log; fault-injection test asserts fail-fast, progress-so-far, ledger resume |
| Classification unaffected | PASS — full-corpus distribution support 181 / billing 56 / general 35 / commercial 34 @0.55 |
| ArchUnit (hexagonal, naming, boundaries) | PASS — `SyncObserverPort` is a domain interface; `LoggingSyncObserverAdapter` respects the `*Adapter` naming rule |

## Latency / Throughput Results

| Metric | BE-013 baseline | BE-014 batched | Delta |
|---|---:|---:|---:|
| 150-article sync (1 901 chunks) | 75.0 s | **44.7 s** | −40% |
| Throughput | ~25 chunks/s | **42.7 chunks/s** | +71% |
| Per-document store (embed+insert), timer TOTAL | n/a | 35.0 s (MAX 1.09 s) | — |
| Idempotent full-corpus re-sync (306 unchanged) | n/a | **16.7 s** (0 ingested) | — |
| **Full corpus (306 articles, 3 235 chunks)** — measured | n/a | **~73 s** (156 new + 150 skipped) | — |

Full corpus measured live: `processed=306 ingested=156 skipped=150 duration_ms=73393
chunks_per_sec=44.1`; a from-scratch full ingest is ~92 s. Offline admin/sync path — no
voice-runtime SLO (`time_to_first_audio`) impact.

**Note (non-blocking):** an idempotent re-sync still costs ~16.7 s because the CSV connector
classifies (embeds) every article in `fetchAll()` **before** the content-hash skip check, so
domain classification is re-run even for unchanged articles. Cheap at 306 articles; a
"skip classification when hash unchanged" optimization is a possible follow-up if the corpus grows.

## Observability Evidence

- **Completion log:** `[KB-SYNC] op=sync-detail source_type=csv-article processed=150
  ingested=150 skipped=0 deleted=0 total_chunks=1901 duration_ms=44504 chunks_per_sec=42.7`.
- **Metrics (actuator `/actuator/metrics`):**
  - `voice_support.kb_sync_batch{source_type=csv-article}` — COUNT 150, TOTAL_TIME 35.0 s,
    MAX 1.09 s, p50/p95/p99 published.
  - `voice_support.kb_sync_chunks{source_type=csv-article}` — chunks-per-document summary.
  - `voice_support.kb_sync{source_type=csv-article}` — full-sync wall clock.
  - `voice_support.kb_sync_failures{source_type,error_code}` — aborted-run counter (bounded tags).
- **Cadence:** per-batch detail at DEBUG (avoids 40k INFO lines); `op=progress` INFO every
  `voice-support.knowledge.sync-progress-every` (default 500) documents.
- No sensitive data in logs (`source_id` is the article `document_id`, not PII).

## Test Evidence

- **Unit (domain, fakes):** `KnowledgeSyncServiceTest` — batched-call-per-document, observer
  per-batch + completion totals, unchanged-docs-emit-no-batch. Existing idempotency /
  deletion-diff tests still green.
- **Unit (infra, in-memory registry):** `LoggingSyncObserverAdapterTest` — batch timer +
  chunk summary + full-sync timer registered with the `source_type` tag.
- **BDD:** `RunKnowledgeBddTest` (20) — CSV + markdown ingestion scenarios unaffected.
- **Live:** real pgvector + Ollama run (numbers above).

## Residual Risks (accepted)

- **Full-corpus single-request sync** is fine at the real corpus size (306 articles,
  ~73–92 s). An async job + status stays a documented follow-up only for a hypothetical
  order-of-magnitude larger corpus; embedding on Ollama is the dominant cost.
- **Per-document failure** (embedding/DB error mid-run) aborts the sync fail-fast; because
  the ledger is committed per document, a re-run resumes (already-ingested docs skip). This
  is now **observable** (`syncFailed` → `voice_support.kb_sync_failures` counter +
  `[KB-SYNC] op=sync-failed` log with progress-so-far). Per-article isolation (continue past
  one bad article) is a possible hardening follow-up, not required at this corpus size.
- **Idempotent re-sync re-classifies** all articles (~16.7 s) — see latency note; follow-up only.
- FR(dev)/EN(prod) mixing in one vector store — tracked as TASK-BE-015.

## Recommendation

- **Go** — QA functional + latency acceptance **PASS**; adversarial review 93/100 (gate Pass).
- No required fixes before merge. Follow-ups (non-blocking): TASK-BE-015 (answer language),
  optional skip-classification-on-unchanged-hash, optional per-article failure isolation.
- Merge remains gated on explicit user validation (user is the final validator).
