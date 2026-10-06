# TASK-BE-069 — Adversarial Code Review

**Scope reviewed:** ingest-time audience filter (`KnowledgeSyncService`), unified recursive
`MarkdownFolderConnector` (audience/language/url front-matter), `SyncReport.excluded` +
`SyncObserverPort.audienceExcluded` observability, the eir help-centre preprocessing script
(`scripts/kb_eir/`), the 154-file converted corpus (`knowledge-base/eir/`) and the old-KB
front-matter unification.
**Commits:** `ad99bbc` (ticket), `f66db3f` (audience filter + connector), `e3b4f1b` (script +
corpus + unify), size-budget refactor commit.
**Reviewer stance:** delivery gate, not a courtesy pass.

## Verdict

Proceed.

## Satisfaction Score

Score: 92/100
QA gate: Pass

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | **Deploy requires rolling the new backend image** (wiring already exists — corrected after `deploy/` verification): the pilot Ansible `compose_tier` role already copies `knowledge-base/` **recursively** (`kb_assets.yml` `src: knowledge-base/`), the backend bind-mounts it (`${KB_HOST_PATH}:/app/kb-assets:ro`), `KB_MARKDOWN_PATH=/app/kb-assets/knowledge-base`, and a gated post-deploy `POST /api/knowledge/sync` runs (`kb_assets_changed` detects the 154 new files, TASK-OPS-011). So `eir/` ships automatically **once the recursive-connector image is deployed**; the only hard dependency is building/pushing the new backend image + bumping `IMAGE_TAG`. The old (non-recursive) image would ignore the `eir/` subfolder. | `deploy/ansible/roles/compose_tier/tasks/kb_assets.yml` (recursive copy), `deploy/compose/backend/docker-compose.yml` (mount + `KB_MARKDOWN_PATH`), `kb_sync.yml`. | Build + push the backend image, bump `IMAGE_TAG`, run the deploy. No new Ansible code needed. |
| Low (resolved) | **FAQ language `fr`→`en` — initially skipped, then fixed live** (`v0.9.5` pilot, 2026-10-06): the first full sync reported `markdown skipped=3` because `content_hash` is **body-only** (front-matter excluded), so adding `audience: customer` + the now-read `language` did not change the hash → the 3 EN FAQ stayed `language=fr` in the store (the pilot runs the retrieval language-filter **ON**, so they only surfaced on FR queries). **Fixed by a targeted re-ingest**: `DELETE` the 3 FAQ rows from `vector_store` (44 chunks) **and** `kb_source_state`, then `POST /api/knowledge/sync/markdown` (`processed=157 ingested=3 skipped=154`). Verified: `billing/commercial/telecom-faq.md` now `language=en`. | Live `op=sync-detail markdown skipped=3` → DELETE 44 + DELETE 3 ledger → `/sync/markdown ingested=3` → store shows `lang=en` for all 3. | **Resolved.** Deeper fix (optional): include metadata-affecting front-matter in `content_hash` so a metadata-only edit re-ingests automatically. |
| Low | **Extraction heuristic is line-based, not a DOM parse**: a pathological eir page could drop a bare link-only step or keep a stray nav line. Spot-checked billing/fibre/mobile/eir-app (clean; inline content links preserved); residual nav = 0 images / 0 footer / 0 dangling tails; 8 files keep legitimate inline prose links. | `scripts/kb_eir/convert_eir_kb.py` `clean_body`/`_is_scaffolding_only`; residual scan in the session. | Precision-over-recall is the right call for V1. Re-inspect if a specific page reads wrong at QA. |
| Low | **`--min-chars 200` drops thin pages**: 21 core pages (incl. the `billing/my-payments/` *index*) produced <200 chars and were skipped. Verified the dropped billing page is a nav index whose children (`payment-options`, `refunds`, `what-happens-if-i-dont-pay`) are all kept — no real content lost. | Conversion stats `skipped_empty: 21`; raw-vs-converted billing diff. | Threshold is a CLI arg; lower it if QA finds a genuinely short answer was dropped. |
| Info | **Real-corpus ingestion is not exercised in CI** (project rule: no `@SpringBootTest`, no DB in `mvn test`). The 154-file end-to-end sync is validated by the manual spot-check, not an automated test. | Test strategy (manual fakes); `MarkdownFolderConnectorTest` uses `@TempDir`. | Acceptable under the existing no-DB test contract; QA covers live ingestion. |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| Connector parses `audience`/`language`/`url` + recurses; relative-path `source_id`; tests | ✅ | `MarkdownFolderConnector`; `MarkdownFolderConnectorTest` (+3 tests: front-matter, defaults, recursion) |
| `KnowledgeSyncService` skips `audience=internal`; `SyncReport.excluded`; logged | ✅ | `processDocument` skip + `observer.audienceExcluded`; `SyncReport.excluded`; `LoggingSyncObserverAdapter` counter + log; `KnowledgeSyncServiceTest` (+2 tests incl. customer→internal cleanup) |
| Script converts core eir subset to canonical markdown; boilerplate removed; domain from URL; `language: en`/`audience: customer`; spot-check | ✅ | `scripts/kb_eir/` (+11 unit tests); 154 files; residual-boilerplate scan = 0; spot-checked billing/fibre |
| 3 existing KB files carry `audience: customer` and still ingest | ✅ | `knowledge-base/{billing,commercial,telecom}-faq.md`; connector defaults + explicit value |
| `backend/` `mvn test` green incl. ArchUnit; voice-agent unaffected | ✅ | 723 tests, BUILD SUCCESS, Hexagonal/ContextBoundary/Naming green; no voice-agent files touched |

## Test Evidence

- Developer tests: backend 723 (+5: 3 connector, 2 sync-service); eir script 11 unit tests (domain mapping, slug, device detection, boilerplate strip, canonical front-matter, nav-only drop, image-tile/mangled-link strip with inline-link preserved).
- Missing tests: none at the unit level given the no-DB contract; real-folder ingestion is a QA/live step.
- QA scenarios to run: (1) full `POST /api/knowledge/sync` against a DB with `knowledge-base/eir/` present → assert `excluded`/`ingested` counts + a billing answer grounded on an eir article; (2) a synthetic `audience: internal` markdown file is never retrievable.

## Observability And Latency

- Relevant slices: KB ingestion (not the answer critical path).
- OpenTelemetry traces: unchanged (ingestion is batch; existing `kb_sync` timer/metrics preserved).
- Metrics: new `voice_support.kb_sync_audience_excluded` counter (tagged `source_type`); `SyncReport.excluded` surfaced in the REST sync response + `[KB-SYNC] op=sync-detail excluded=…` log.
- Structured logs: `[KB-SYNC] op=audience-excluded source_type=… source_id=… audience=…` per excluded doc (auditable internal partition).
- Missing: none — ingestion-only change, no per-turn telemetry required.
- Risk: low; additive metric/field, no cardinality blow-up (`source_type` is bounded).

## Security And Privacy

- Sensitive data risk: none new. eir content is public help-centre web content (public tariffs like €18.45 are public facts); no PII, no secrets.
- Identity/access risk: strengthened — internal/agent-facing content is now never embedded or stored on the customer answer engine (defense-in-depth over the ADR-0034 fail-closed retrieval filter).
- Logging risk: the audience-excluded log carries `source_id`/`audience` only (no article body); safe.

## Required Developer Actions

1. None blocking. To roll the corpus onto the pilot: build + push the new backend image (recursive connector), bump `IMAGE_TAG`, run the deploy — the recursive `knowledge-base/` copy + mount + post-deploy sync are already wired. Optionally update the `kb_sync_min_processed` comment in `group_vars/backend.yml` ("markdown baseline is 3" → now 157 with the eir corpus), since the gate's "CSV was seen" proof weakens as the markdown count grows.

## Residual Risk If Accepted

- The corpus reaches the pilot automatically on the next backend-image roll (recursive copy + mount + gated post-deploy sync already exist); until that roll it is import-ready but not live (Low).
- Line-based extraction may imperfectly handle an unusual future page layout (Low); re-run the versioned script after a re-scrape.
- The `kb_sync_min_processed` deploy gate now counts 157 markdown docs, so it proves "KB non-empty" more than "CSV specifically ingested" (Low; comment update suggested).
