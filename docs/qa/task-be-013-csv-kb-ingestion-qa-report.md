# QA Functional And Latency Report — TASK-BE-013 (CSV KB Ingestion + Domain Classification)

## Executive Summary

- **Overall readiness:** Functional acceptance **PASS** for the connector + classifier
  slice (unit + BDD, infra-free) **and** validated on a **live run** against real
  Postgres (pgvector) + Ollama (`nomic-embed-text`) on a 150-article sample of the real
  Eir corpus: end-to-end ingest, idempotency, clean text, domain classification and
  retrieval all confirmed. The classifier threshold was **calibrated to 0.55** on this
  run.
- **Main blockers:** none for the BE-013 scope. **Full-corpus** (~40,900 rows) ingest
  time/throughput is explicitly deferred to **TASK-BE-014** (batch embedding/insert) —
  the live run measured ~0.5 s/article single-insert, i.e. ~5–6 h extrapolated, which
  is exactly what BE-014 must fix.
- **Residual risks:** classification is best-effort (anchor cosine, no ground-truth
  labels) — calibrated but not benchmarked; FR(dev)/EN(prod) mixing in one vector store
  (TASK-BE-015); one malformed CSV row aborts the whole sync (BE-014).

## Scope Tested

- **Epic / task:** EPIC-005 / TASK-BE-013.
- **Components:** `CsvArticleConnector` (commons-csv RFC-4180 + jsoup HTML→text),
  `EmbeddingDomainClassifierAdapter` (`DomainClassifierPort`), wiring into the
  BE-003 idempotent `KnowledgeSyncService` + ledger.
- **Providers / fakes:** manual fakes only — `FakeEmbeddingModel`,
  `FakeDomainClassifier`, `FakeVectorStorePort`, `FakeKnowledgeSourceStatePort`
  (no DB, no Ollama). `mvn test` stays infra-free.
- **Environment:** JVM unit + Cucumber-for-Java BDD (`RunKnowledgeBddTest`).

## Functional Results

| Area | Status | Evidence | Notes |
|---|---|---|---|
| HTML → clean text (tags stripped, entities decoded, paragraph breaks kept) | PASS | `CsvArticleConnectorTest.shouldParseCleanHtmlAndClassifyDomain`; BDD `csv-knowledge-ingestion.feature` (scenario 1) | jsoup; `<script>/<style>` removed |
| RFC-4180 parsing (embedded newlines + escaped `""`) | PASS | `CsvArticleConnectorTest` (row with embedded `\n` and `""`) | commons-csv |
| `document_id` → `sourceId`, `source_type = csv-article`, `language = en` | PASS | `CsvArticleConnectorTest` | — |
| Domain classified per article (closest anchor above threshold, else general) | PASS | `EmbeddingDomainClassifierAdapterTest` (billing / below-threshold / blank / no-anchors) | deterministic with fake `EmbeddingModel` |
| Classifier fed cleaned text (never raw HTML) | PASS | `CsvArticleConnectorTest.shouldPassCleanedTextToTheClassifierNotRawHtml` | — |
| Blank id / empty content rows skipped | PASS | `CsvArticleConnectorTest`; BDD scenario 3 | — |
| Missing CSV file degrades to empty sync (no startup failure) | PASS | `CsvArticleConnectorTest.shouldReturnEmptyListWhenFileMissing` | logged `[KB-SYNC]` warn |
| Idempotent sync via content hash (2nd run no-op) | PASS | BDD `csv-knowledge-ingestion.feature` (scenario 2) reuses `KnowledgeSyncService` + ledger | inherited from BE-003 socle |
| Classifier resilience (embedding failure → general, sync continues) | PASS | `EmbeddingDomainClassifierAdapterTest.shouldDegradeToGeneralWhenEmbeddingFails` | added during adversarial review |

Test totals after change: **173** unit/integration + **20** BDD scenarios, 0 failures;
ArchUnit (hexagonal + naming + context boundary) green.

## Live Run (150-article sample, real Postgres + Ollama)

- **Environment:** backend on this branch; pgvector `pg16` on :5433; Ollama
  `nomic-embed-text` on :11434 (embed ~65 ms warm). Sample = first 150 valid records of
  `articles.csv` (ids 196–932), extracted with a CSV-aware reader so embedded
  newlines/quotes stay intact; kept out of git (`*.kb.csv`).
- **Ingest:** `POST /api/knowledge/sync/csv-article` → `processed 150, ingested 150,
  skipped 0` in **75 s** (~0.5 s/article; 150 articles → 1 901 chunks). Single-insert +
  per-article classification embed — the known-slow path BE-014 must batch.
- **Idempotency:** 2nd sync → `ingested 0, skipped 150` in **7.5 s** (content-hash
  ledger; note it still re-classifies during `fetchAll` → BE-014 can skip that too).
- **Clean text:** `0` rows with residual HTML tags among the 1 901 chunks.
- **Classifier calibration:** max-cosine distribution on the sample (nomic, no task
  prefix → compressed range) `min 0.49 / p25 0.58 / median 0.60 / p75 0.64 / max 0.80`.
  Threshold sensitivity: `general` share = 1/150 @0.50, **20/150 @0.55**, 73/150 @0.60.
  Chosen **0.55**: the low-confidence tail routed to `general` is genuinely
  cross-cutting/off-domain (GDPR, Right to be Forgotten, Personal Injury Claims,
  Genesys agent coaching, Address Search, Eircodes, Age Friendly Programme) — the
  correct bucket. Their 2nd-best anchor score is near-tied with the best, confirming
  those picks were unreliable and belong in `general`.
- **Domain distribution @0.55 (articles / chunks):** support 91/1205, billing 25/280,
  general 18/180, commercial 16/236. Support-heavy is expected for a support-site
  corpus. (@0.50 it was support 99, billing 32, commercial 19, general 0 — everything
  force-committed, which is why 0.50 was rejected.)
- **Retrieval sanity (`POST /api/conversation/retrieve`, unfiltered):**
  "unlock my mobile handset" → support (top score 0.79); "what is credit vetting?" →
  billing (0.75); "WiFi no connection troubleshoot" → support (0.70). Correct domains,
  strong scores.

## Latency Results

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| KB ingest (per article, sample) | ~0.5 s | — | — | 150 | warm | Single-insert + classify embed; **full-corpus bound owned by TASK-BE-014** (batching). |
| KB re-sync (idempotent, whole sample) | — | — | — | 1 | warm | 7.5 s for 150 unchanged (classification still runs in `fetchAll`). |

This story is an **offline admin/sync path**, not the customer voice runtime critical
path (no `time_to_first_audio` / mouth-to-ear impact). Full-corpus throughput and a
documented ingest-time bound are reported under TASK-BE-014.

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| `CsvArticleConnector` | OK | Streaming CSV parse; materializes `List<SourceDocument>` (port contract). One malformed row aborts the sync (no per-row isolation). | Consider per-row try/catch + streaming/batch in BE-014 |
| `EmbeddingDomainClassifierAdapter` | OK | Separate article-level embedding (not reused from storage); resilient to embedding errors (→ general). | Reuse storage vectors as a BE-014 optimization |
| Sync integration | OK | Plugs into BE-003 sync; idempotency + deletion-diff inherited and BDD-covered for `csv-article`. | — |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Medium | Bulk ingest latency/throughput unmeasured at scale | Cannot claim full-corpus ingest bound yet | TASK-BE-014 |
| Low | One malformed CSV row aborts the whole sync | Operational robustness on a 40k-row file | TASK-BE-014 (streaming/batch) |
| Low | Classification quality unverified on real corpus (threshold calibration) | Possible mis-domained chunks; mitigated by `general` fallback + `OR general` retrieval | Live/IT run |
| Low | FR(dev)/EN(prod) coexist in one vector store | Retrieval pollution risk | TASK-BE-015 |

## Open Questions

- **Product:** does the real Eir export provide a category/section (or `document_id →
  domain` sidecar)? If yes, a source-provided classifier beats the heuristic.
- **Architecture:** should bulk ingest become an async job (status endpoint) if the
  BE-014 bound still exceeds a single HTTP request?
- **Technical:** optimal batch size vs Ollama embedding throughput and Postgres insert.

## Recommendation

- **Go** for the BE-013 functional slice (connector + classifier): acceptance criteria
  1–3 and 5 are covered by unit + BDD tests; the adversarial review is satisfied
  (see `## Verdict` in the chat / commit).
- **Required before pilot / bulk claim:** TASK-BE-014 (batch insert + sync
  observability with throughput) and a live/IT run against Postgres + Ollama to
  produce the ingest-time evidence and to calibrate the classifier threshold on the
  real corpus.
