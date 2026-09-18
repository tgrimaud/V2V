# BUG-022 — KB sync hangs in the chunk-embedding store phase (English corpus)

**Type:** Bug · **Severity:** High (blocks full KB sync + would abort deploys) · **Status:** 🟢 Fixed (2026-09-18, pending QA/merge)
**Found:** 2026-09-18 during TASK-OPS-013 (switch pilot RAG corpus to English)
**Area:** backend KB sync / embedding (Ollama sidecar) · **Related:** TASK-OPS-009, ADR-0048, ADR-0030, BUG-021

## Symptom

`POST /api/knowledge/sync` on the English corpus (`articles-en.csv`, 306 articles + 3 markdown
FAQ) **parses all sources fine** (per-article `[KB-SYNC] audience=…` logs flow to the last
article), then **hangs indefinitely in the store phase** (chunk → embed → upsert):

- No further logs, backend request thread stuck, **Ollama sidecar goes idle (~0.6% CPU)** — the
  embedding call neither progresses nor errors.
- The sync HTTP call never returns its `SyncReport` (observed hung > 25 min, then again on a
  restart+retry — **deterministic**, freezes at the same point).
- While hung, the stuck sync **saturates the embedding path**: concurrent live `/converse`
  retrieval starts returning **503 `ERR_UPSTREAM`** (query embedding times out at ~6 s).

## Impact

1. The full corpus sync never completes cleanly (no `SyncReport`, deploy gate never satisfied).
2. With `kb_sync_after_deploy: true` + `serial:1`/`max_fail_percentage:0` + 90×30 s polling, a
   redeploy would burn ~45 min then **abort the whole rollout** — a real deploy hazard.
3. A hung sync **degrades live retrieval** (503s) until the backend is restarted.

## Interim mitigation (superseded by the fix above — kept for history)

- `deploy/ansible/group_vars/backend.yml`: `kb_sync_after_deploy: false` (auto-sync OFF until
  fixed). The EN corpus is **already ingested and persistent** in pgvector — a redeploy does not
  need the sync.
- **Manual gated procedure** to (re)load KB (tolerates the partial tail):
  1. `podman restart voice-support-backend` (frees any stuck thread).
  2. Warm-up gate: poll `POST /api/conversation/warm-up` (x-api-key) until `200` (avoids BUG-021).
  3. Fire async: `curl -X POST -H "x-api-key: $KEY" .../api/knowledge/sync` (`ansible … -B -P0`).
  4. Monitor `[KB-SYNC]` log timestamp advancing + Ollama CPU; if it freezes, restart + rerun
     (idempotent `content_hash` skip resumes; already-stored chunks are kept).
- **State after the TASK-OPS-013 manual sync:** `vector_store` holds **4872 `csv-article`/en
  chunks + 44 markdown (EN content)**; EN grounding verified on both nodes (slow-internet,
  billing, FTTC→FTTH, cancellation; confidence 0.69–0.83). A small **tail** of articles may be
  un-ingested (the store hung near the end) — acceptable for the pilot, to be closed by the fix.

## Root cause (confirmed)

`PgVectorStoreAdapter.storeChunks` batched **all chunks of a document into one
`vectorStore.add(...)`** (TASK-BE-014, for one embedding + one multi-row insert per document). A
large HTML article (e.g. article 241, ~135 KB → hundreds of ~500-char chunks) therefore produced
**one huge embedding request**. The embedding client's timeout *is* configured
(`voice-support.embedding.timeout-ms` ~5 s, `SimpleClientHttpRequestFactory.setReadTimeout`) and
works fine for the per-query retrieval path — but a `SimpleClientHttpRequestFactory` read timeout
is a **per-read-gap `SO_TIMEOUT`, not an overall request budget**. On a very large batch the
sidecar trickles / stays busy just enough that no single read gap exceeds 5 s, so the timeout
**never fires** and the call blocks indefinitely (sidecar near-idle, no `SyncReport`, live
retrieval starved → 503). This is why parse (one small embed per article) succeeded while the
store phase hung, and why it was deterministic (same oversized article every run).

## Fix (implemented)

1. **Bounded store batches** — `PgVectorStoreAdapter.storeChunks` now embeds chunks in batches of
   `voice-support.knowledge.store.batch-size` (`KB_STORE_BATCH_SIZE`, default **32**) instead of
   one call per document. Each request is small enough that the existing per-read timeout bounds
   it, so a slow/hung batch **fails fast** instead of trickling forever.
2. **Skip-on-failure** — a batch whose `vectorStore.add(...)` throws (read timeout, embed error) is
   **skipped and logged** (`WARN [KB-SYNC] skipped embedding batch source_type=… source_id=…
   skipped_chunks=… error_code=…`) and the sync continues; `storeChunks` returns the count actually
   stored. One bad batch can no longer stall or abort the whole corpus sync.
3. **Blank-chunk guard** — empty/whitespace-only chunks are dropped before embedding (a blank
   carries no signal and can hang the embedder).
4. **No silent data loss (adversarial-review fix)** — `storeChunks` now returns a
   `StoreResult(stored, attempted)`. `KnowledgeSyncService.reingest` **only commits the document's
   `content_hash`** (`upsertState`) when the store is **complete** (`stored == attempted`). An
   incomplete store (a sub-batch was skipped) is left **uncommitted** — since `deleteBySource` ran
   first, the next idempotent sync **retries the whole document** and it self-heals, instead of
   being marked done and silently dropping the missing chunks from the RAG forever. The partial
   ingestion is observable: `SyncObserverPort.batchSkipped(...)` → counter
   `voice_support.kb_sync_skipped` (tag `source_type`) + `WARN [KB-SYNC] op=batch-skipped …`.
5. **Auto-sync re-enabled** — `kb_sync_after_deploy: true` restored in
   `deploy/ansible/group_vars/backend.yml`; a (re)deploy sync now always terminates (idempotent —
   unchanged sources skip by `content_hash`).

**Tests:** `PgVectorStoreAdapterTest` — bounded batching (70 chunks → add() sizes `[32,32,6]`),
a failing batch is skipped and the rest still store (`stored=38`, `isComplete()==false`), blank
chunks dropped. `KnowledgeSyncServiceTest.partially_stored_document_is_not_committed_and_self_heals_next_sync`
— an incomplete store is not committed, is reported via `batchSkipped`, and is re-ingested on the
next sync once the failure clears. Full backend suite green (581 tests, 0 failures).

**Follow-up lever (only if a trickle-hang ever recurs on small batches):** give the embedding
client an **overall** request timeout (e.g. a `JdkClientHttpRequestFactory` whose timeout covers
send+receive, not just a read gap). Not needed for the observed hang — bounding the batch already
makes the per-read timeout effective — so deferred to keep the retrieval path unchanged.

## Repro

`POST /api/conversation/warm-up` (200), then `POST /api/knowledge/sync` with the English
`articles-en.csv` mounted (`KB_CSV_PATH`, `KB_CSV_LANGUAGE=en`) → parse completes, store hangs,
Ollama idle, no `SyncReport`.
