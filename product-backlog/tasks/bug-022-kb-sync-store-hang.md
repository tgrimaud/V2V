# BUG-022 — KB sync hangs in the chunk-embedding store phase (English corpus)

**Type:** Bug · **Severity:** High (blocks full KB sync + would abort deploys) · **Status:** 🔴 Open
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

## Current mitigation (shipped in this branch)

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

## Root-cause hypotheses (to confirm)

- The chunk-embedding HTTP call to Ollama has **no effective read timeout** on the sync path (the
  per-query retrieval timeout `voice-support.embedding.timeout-ms` ~5 s does not cover the batch
  store embed), so a single stuck/half-open call blocks forever with the sidecar idle.
- A **degenerate chunk** (empty/whitespace-only after `htmlToText`, or a single very long
  unbroken token from a large HTML article) makes `nomic-embed-text` hang instead of error.

## Proposed fix (not yet implemented)

1. Add a bounded **read timeout** to the sync/store embedding call + **skip-on-timeout** that
   records a miss (like WarmUpService) and continues, so one bad chunk cannot stall the whole
   sync; surface skipped chunks in the `SyncReport`.
2. Guard `TextChunker`/store against **degenerate chunks** (drop empty/whitespace-only; hard-cap
   chunk char/token length so no chunk exceeds the embedding context).
3. Regression: a sync over a fixture containing an oversized/degenerate article completes with a
   `SyncReport` (skipped>0) instead of hanging.
4. Re-enable `kb_sync_after_deploy: true` once the sync always terminates.

## Repro

`POST /api/conversation/warm-up` (200), then `POST /api/knowledge/sync` with the English
`articles-en.csv` mounted (`KB_CSV_PATH`, `KB_CSV_LANGUAGE=en`) → parse completes, store hangs,
Ollama idle, no `SyncReport`.
