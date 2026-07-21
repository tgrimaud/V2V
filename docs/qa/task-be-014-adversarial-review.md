# Adversarial Code Review — TASK-BE-014 (batched KB `storeChunks` + sync observability)

Reviewed: 2026-07-21 · Branch: `task/TASK-BE-014-batch-embedding` · Reviewer: adversarial-code-review skill

## Verdict

**Proceed** (after in-loop fixes). The batching + observability change satisfies the
story; the one material finding (silent failure path on an observability-focused story)
was fixed within this review loop and covered by tests.

## Satisfaction Score

Score: **93/100**
QA gate: **Pass**

Initial score before fixes: ~87/100 (Fix required) — the success path was well
instrumented but the **failure path was unobservable** and untested.

## Blocking Findings (all resolved in this loop)

| Severity | Finding | Evidence | Required fix | Status |
|---|---|---|---|---|
| Medium | Failure path was silent on an observability story: a mid-sync `storeChunks` error propagated straight to the generic 500 handler — no `[KB-SYNC]` failure log, no failure metric, `syncCompleted` skipped, no partial progress surfaced. | `KnowledgeSyncService.syncConnector` (no try/catch) + `KnowledgeController.timedSync` (no catch). | Emit a failure event (metric + structured log) with progress-so-far, keeping fail-fast semantics. | **Fixed** — added `SyncObserverPort.syncFailed(...)`; service wraps the sync body and emits it before re-throwing; adapter increments `voice_support.kb_sync_failures{source_type,error_code}` + `[KB-SYNC] op=sync-failed` WARN. |
| Medium | No test for the failure/degraded path (bulk-ingest story changing failure handling). | `KnowledgeSyncServiceTest` had happy-path + idempotency only. | Add a fault-injection test. | **Fixed** — `failedBatchAbortsSyncButIsObservableAndResumable` (asserts fail-fast, `syncFailed` captured with `ingestedSoFar=1`, no completion, first doc committed to ledger → resumable) + `syncFailedIncrementsFailureCounterTaggedByErrorCode`. |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | No correlation/run id in `[KB-SYNC]` logs, so two concurrent/consecutive runs of the same source can't be told apart in logs. | `LoggingSyncObserverAdapter` logs `source_type` only. | Offline admin path (not the voice per-turn flow); add a per-sync run id if sync tracing becomes needed. Tracked as follow-up. |
| Low | No **per-article failure isolation** — one bad article aborts the whole run (fail-fast). | `syncConnector` loop re-throws. | Accepted residual risk (ADR-0030): committed docs are skipped on the next idempotent run, so a re-run resumes. Per-item isolation is a separate hardening ticket if needed at larger scale. |
| Cosmetic | `VectorStorePort` javadoc said "thousands of articles"; corpus is 306. | port comment. | **Fixed** — reworded to "a bulk corpus sync". |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| Batched `storeChunks` on `VectorStorePort` (one embedding + insert per document) | Yes | `PgVectorStoreAdapter.storeChunks` → single `vectorStore.add(documents)`; `eachDocumentIsStoredInOneBatchedCall` |
| Sync progress metrics/logs (perf / anti-timeout) | Yes | `voice_support.kb_sync_batch` (p50/p95/p99), `kb_sync_chunks`, `kb_sync` timers; throttled `op=progress`; `op=sync-detail` with `chunks_per_sec` |
| Idempotency preserved | Yes | `secondSyncWithUnchangedContentSkipsEverything`, `unchangedDocumentsEmitNoBatchButStillComplete` |
| Deletion-diff preserved | Yes | `removedSourceIsDeletedViaLedgerDiff` |
| Failure path observable + resumable | Yes (added) | `syncFailed` + `failedBatchAbortsSyncButIsObservableAndResumable` |
| Domain stays pure (no Micrometer/SLF4J) | Yes | `SyncObserverPort` domain out-port; metrics/logs only in `LoggingSyncObserverAdapter` |

## Test Evidence

- Developer tests: 184 backend tests green (0 failures/errors), incl. batching, observer
  totals, idempotency, failure path (service + adapter), ArchUnit boundaries.
- Missing tests: none blocking. (Progress-cadence log content not asserted — logs are not a contract.)
- QA scenarios to run: full-corpus live sync + throughput, idempotent re-sync, retrieval
  correctness post-batching, failure-path smoke (optional).

## Observability And Latency

- Relevant slices: KB bulk ingest (offline admin path — not the voice per-turn SLO).
- Metrics: `kb_sync_batch` (per-document embed+insert latency, p50/p95/p99, tag `source_type`),
  `kb_sync_chunks` (chunks/document), `kb_sync` (full-sync wall clock), `kb_sync_failures`
  (counter, tags `source_type`,`error_code`). Cardinality bounded (no per-document tags).
- Structured logs: `[KB-SYNC]` `op=batch` (DEBUG), `op=progress` (throttled INFO),
  `op=sync-detail` (INFO, throughput), `op=sync-failed` (WARN, progress-so-far). No PII/content.
- Missing: per-run correlation id (non-blocking, offline path).
- Risk: low.

## Security And Privacy

- Sensitive data risk: none — logs carry `source_id` (internal doc id), counts, durations; no article content or PII.
- Identity/access risk: n/a (admin sync path, read-only BSS unaffected).
- Logging risk: none identified; `error_code` is a bounded exception class name.

## Required Developer Actions

All resolved in this loop:
1. Add failure-path observability (`syncFailed`) — done.
2. Add failure-path tests — done.
3. Fix stale port comment — done.

## Residual Risk If Accepted

- Fail-fast (no per-article isolation): accepted — resumable via idempotent ledger on re-run.
- No per-run correlation id in sync logs: accepted for the offline admin path; follow-up if needed.
