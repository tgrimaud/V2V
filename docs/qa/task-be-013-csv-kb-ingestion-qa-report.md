# QA Functional And Latency Report — TASK-BE-013 (CSV KB Ingestion + Domain Classification)

## Executive Summary

- **Overall readiness:** Functional acceptance **PASS** for the connector + classifier
  slice (unit + BDD, infra-free). **Not** yet validated at bulk scale against real
  Postgres + Ollama — that latency evidence is owned by **TASK-BE-014** (batch
  embedding/insert) and by a live/IT run, per the ticket.
- **Main blockers:** none for the BE-013 scope. Bulk-corpus ingest time/throughput is
  explicitly deferred to BE-014 (documented dependency, not a regression).
- **Residual risks:** classification quality (embedding-anchor threshold) is
  calibration-dependent and unverified on the real corpus; FR(dev)/EN(prod) mixing in
  one vector store (TASK-BE-015); per-row parse failure aborts the whole sync.

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

## Latency Results

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| KB bulk ingest (full `articles.csv`) | n/a | n/a | n/a | 0 | — | **Not measured** — owned by TASK-BE-014 (batch insert) + a live Postgres+Ollama run. Current one-chunk-per-`add` path + per-article classification embedding is known-slow by design. |

This story is an **offline admin/sync path**, not the customer voice runtime critical
path (no `time_to_first_audio` / mouth-to-ear impact). Per the ticket, bulk ingest
time and throughput are reported under TASK-BE-014.

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
