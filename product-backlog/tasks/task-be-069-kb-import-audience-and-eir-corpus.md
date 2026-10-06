# TASK-BE-069 — KB import: ingest-time audience filter + eir help-centre corpus via unified canonical markdown

**Type:** Technical task (KB ingestion — backend + data/tooling)
**Status:** 🚧 In progress on `task/TASK-BE-069-kb-import-audience-and-eir-corpus` (off `feat/restart-from-scratch`).
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

- [ ] `MarkdownFolderConnector` parses `audience`/`language` front-matter and recurses; relative-path
      `source_id`; unit tests for front-matter parsing, recursion and the audience/language defaults.
- [ ] `KnowledgeSyncService` does not store `audience=internal` docs; `SyncReport` exposes an
      `excluded` count; exclusion is logged. Unit test with a mixed customer/internal connector fake.
- [ ] Preprocessing script converts the core eir subset to canonical markdown; boilerplate removed
      (no nav/footer/cookie text in the body); domain derived from URL; `language: en`,
      `audience: customer`. Spot-check N files for body-only, correct domain.
- [ ] The 3 existing KB files carry `audience: customer` and still ingest unchanged.
- [ ] `backend/`: `mvn test` green (incl. ArchUnit); voice-agent suite unaffected.
- [ ] Adversarial review ≥ 90/100, persisted to `docs/qa/task-be-069-adversarial-review.md` + pointer line here.

## Observability / runtime impact

Ingestion-path change only (not the customer answer critical path). The audience exclusion is logged
and counted in the sync report/metrics; no new per-turn telemetry. Not latency-affecting at answer time
(a smaller store is neutral-to-positive for retrieval). A full re-sync is required to apply the new
ingest-time exclusion + eir content (consistent with the ADR-0034 audience re-sync note).

## Notes

- Approach A keeps the backend free of scraping/HTML-stripping logic (lives in a versioned one-shot
  script); the canonical markdown is inspectable in git.
- Device-tutorial import (the 832 excluded files) is a deliberate follow-up, not a V1 need.
