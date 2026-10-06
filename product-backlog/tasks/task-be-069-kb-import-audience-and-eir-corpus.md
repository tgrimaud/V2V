# TASK-BE-069 — KB import: ingest-time audience filter + eir help-centre corpus via unified canonical markdown

**Type:** Technical task (KB ingestion — backend + data/tooling)
**Status:** 🚧 Done on `task/TASK-BE-069-kb-import-audience-and-eir-corpus` (off `feat/restart-from-scratch`) — audience ingest-filter + unified recursive markdown connector + 154-file eir corpus converted; backend `mvn test` 723 green (incl. ArchUnit), eir script 11 tests green. Awaiting user validation (not merged).
**Adversarial review 92/100 (Pass, 2026-10-06)** — no blocking finding. Deploy verified against `deploy/`: the pilot already copies `knowledge-base/` recursively + mounts it (`KB_MARKDOWN_PATH`) + runs a gated post-deploy sync, so the eir corpus ships automatically **once the recursive-connector backend image is rolled** (bump `IMAGE_TAG`) — no new Ansible code. Non-blocking: image roll required (Low); latent FAQ `fr`→`en` fix on next pilot sync, language-filter is ON (Low); line-based extraction precision (Low); `--min-chars` drops nav-index pages (Low, verified no real content lost); `kb_sync_min_processed` comment to refresh (Low). Full review: `docs/qa/task-be-069-adversarial-review.md`.
**Priority:** Medium
**Epic:** EPIC-005 (Answer engine / knowledge base)
**Related:** ADR-0034 (KB audience boundary, fail-closed retrieval), ADR-0030 (domain classification),
ADR-0007 (`SourceDocument` pivot + sync), TASK-BE-013 (`CsvArticleConnector` pattern), BUG-005.
**Surfaced by:** user request (2026-10-06) — (1) only import `audience=customer` content, (2) import a new
eir help-centre `.md` corpus, (3) unify the old KB into the same import method.

## Context

Three asks, one coherent KB-ingestion deliverable:

1. **Import only customer-facing content.** Today the audience boundary (ADR-0034) is enforced
   **only at retrieval** (`PgVectorStoreAdapter` fail-closed `audience == customer`); internal
   documents are still embedded + stored. The request is to also **exclude internal at ingestion**
   (defense-in-depth: a smaller store, nothing internal ever persisted).

2. **New corpus** at `~/Workspace/factrure/01a10c1b-695f-715a-8415-ae4f4b501181/` — **1009 `.md`**
   files scraped from `www.eir.ie/helpandsupport/*`. All **public, customer-facing** (zero ADR-0034
   internal markers). Front-matter is `url` + `title` only (no `domain`/`language`/`audience`), and
   each file carries ~85–90% nav/footer **boilerplate** around the real body. Category split: 832
   per-device smartphone tutorials, 49 fibre-broadband, 42 mobile, 26 eirTV, 10 eir-app, 10 billing,
   8 home-phone, 6 myeir, 6 moving-home, 4 webmail, 4 my-order, misc.

3. **Unify the old KB format** so one import method serves both corpora.

### Decisions (user, 2026-10-06)

- **Scope:** start with the **core support/billing subset** (billing, fibre-broadband, mobile, eirTV,
  eir-app, home-phone, webmail, moving-home, myeir, my-order ≈177 files); **exclude the 832 device
  tutorials** for now (near-duplicate per device → would flood the billing-focused V1 RAG). Keep the
  option to import the rest later.
- **Approach A (preprocess):** a one-shot preprocessing script converts eir raw `.md` → the
  **canonical clean markdown format** (front-matter `domain`/`language`/`audience`/`title`/`url` +
  cleaned body) written under `knowledge-base/eir/`, then the **existing `MarkdownFolderConnector`**
  ingests it (unified method). No runtime scraping/boilerplate logic in the backend critical path.
- **Domain tagging:** deterministic from the URL path (`billing`→billing; `fibre-broadband`/`mobile`/
  `eirtv`/`home-phone`/`smartphonehelp`/`webmail`/`eir-app`→support; `moving-home`/`my-order`→commercial).

## Scope & decision

**Backend (unified import method):**
- `MarkdownFolderConnector` reads **`audience`** and **`language`** from front-matter (language
  overrides the connector default; audience defaults to `customer` when absent — ADR-0034 default).
- `MarkdownFolderConnector` recurses into subfolders (so `knowledge-base/eir/*.md` is picked up) and
  uses the **folder-relative path** as `source_id` (avoids filename collisions across subfolders).
- `KnowledgeSyncService` **skips `audience=internal` documents at ingestion** (not stored/embedded),
  counts them in the `SyncReport` (new `excluded` tally) and logs each exclusion (auditable, mirrors
  the `CsvArticleConnector` internal log). The retrieval fail-closed filter stays as the second line.

**Data / tooling (eir corpus):**
- Preprocessing script (`scripts/kb_eir/`) : strip boilerplate, extract the article body, derive the
  domain from the URL path, set `language: en` + `audience: customer`, write canonical `.md` into
  `knowledge-base/eir/` for the core subset only (device tutorials excluded, list configurable).

**Format unification:**
- The 3 existing `knowledge-base/*.md` get an explicit `audience: customer` (keep `domain`/`language`),
  so hand-written FAQ and converted eir content share one canonical schema under one connector.

## Acceptance

- [x] `MarkdownFolderConnector` parses `audience`/`language` front-matter and recurses; relative-path
      `source_id`; unit tests for front-matter parsing, recursion and the audience/language defaults.
- [x] `KnowledgeSyncService` does not store `audience=internal` docs; `SyncReport` exposes an
      `excluded` count; exclusion is logged (`voice_support.kb_sync_audience_excluded` + `[KB-SYNC]
      op=audience-excluded`). Unit tests: exclusion + customer→internal stale cleanup.
- [x] Preprocessing script converts the core eir subset to canonical markdown; boilerplate removed
      (0 images / 0 footer / 0 dangling tails in body); domain derived from URL; `language: en`,
      `audience: customer`. Spot-checked billing/fibre/mobile — body-only, correct domain. 154 files
      (billing 9, commercial 10, support 135); 834 device tutorials + 21 nav-index pages excluded.
- [x] The 3 existing KB files carry `audience: customer` and still ingest unchanged.
- [x] `backend/`: `mvn test` 723 green (incl. ArchUnit); voice-agent suite unaffected (no files touched).
- [x] Adversarial review 92/100 (Pass), persisted to `docs/qa/task-be-069-adversarial-review.md` + pointer line here.

## Observability / runtime impact

Ingestion-path change only (not the customer answer critical path). The audience exclusion is logged
and counted in the sync report/metrics; no new per-turn telemetry. Not latency-affecting at answer time
(a smaller store is neutral-to-positive for retrieval). A full re-sync is required to apply the new
ingest-time exclusion + eir content (consistent with the ADR-0034 audience re-sync note).

## Notes

- Approach A keeps the backend free of scraping/HTML-stripping logic (lives in a versioned one-shot
  script); the canonical markdown is inspectable in git.
- Device-tutorial import (the 832 excluded files) is a deliberate follow-up, not a V1 need.
