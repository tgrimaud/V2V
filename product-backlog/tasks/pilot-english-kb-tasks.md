# Pilot English KB Tasks

Switch the Eir pilot RAG corpus to **English** so English questions retrieve grounded content
instead of deflecting to an advisor. Retrieval relevance only — the answer language is already
per-request (ADR-0031).

---

## TASK-OPS-013 — Pilot English KB corpus (Eir) + English FAQ markdown

**Type:** Ops / content task · **Status:** ✅ Validated (user, 2026-09-18) — merged to `feat/restart-from-scratch`, pilot backend re-synced to the English corpus
**Branch:** `task/TASK-OPS-013-pilot-english-kb` (off `feat/restart-from-scratch`)

### Context / decision

The pilot is deployed for **Eir** and must answer in **English** (see TASK-BE-056). The RAG corpus,
however, was pinned to the **French** translation (`articles-fr.csv`, ADR-0048 single-corpus pilot),
so English questions retrieved weakly and deflected to an advisor. The **original English Eir corpus
already exists in-repo** (`articles-sample.kb.csv`, 306 articles) — the source `articles-fr.csv` was
translated from. No translation of the corpus is needed.

Decision (user, 2026-09-18): **English-only** single-corpus pilot — point the `csv-article` connector
at the English corpus and re-sync (replaces the FR content). Bilingual (load both + retrieval language
filter) stays the documented target **TASK-BE-034**, not enabled here. Also **translate the 3 markdown
FAQ files** to English so the whole pilot KB is English.

### Changes

- **CSV corpus**: renamed `articles-sample.kb.csv` → `articles-en.csv` (repo root, git-ignored data
  file; added `/articles-en.csv` to `.gitignore` alongside `/articles-fr.csv`).
- **Deploy config** (`deploy/ansible/group_vars/backend.yml`): `kb_csv_filename: articles-en.csv`,
  `kb_csv_language: en`; comment block rewritten (EN Eir pilot); deploy-gate comment updated
  (EN corpus adds ~306). No code change.
- **Markdown FAQ** (`knowledge-base/{billing,telecom,commercial}-faq.md`): translated FR → EN,
  front-matter `language: en`, **`domain` unchanged** (billing / support / commercial) so audience/
  domain routing is preserved. Fictional placeholders anglicised (Example Telecom, My Account,
  www.example-telecom.com); phone numbers/prices kept.

### No image rebuild needed

Both the CSV and the markdown FAQ are **mounted assets** (Ansible `kb_assets.yml` copies
`knowledge-base/` + the repo-root CSV into `KB_HOST_PATH` → `/app/kb-assets/`), not baked into the
image. So this ships at the current image tag `0.9.1` via a **deploy + KB re-sync** (no release).

### Re-sync behaviour

The `csv-article` source currently holds the FR content. Re-sync keys on `(source_type, source_id)`:
EN docs upsert (content_hash changed → re-embed) and any FR-only ids are removed by the deletion-diff,
so `csv-article` ends up fully English. The markdown FAQ re-embeds (content changed). First full
re-sync ~15-30 min on the pilot Ollama sidecar (idempotent afterwards).

### Tests

- `mvn test` — backend suite unaffected (the FAQ `.md` and CSV are runtime assets, not test fixtures;
  no test loads `knowledge-base/*.md`). Green.

### Acceptance

- [x] Pilot corpus = English (`articles-en.csv`, `kb_csv_language: en`); FR kept only as bilingual-
      target reference (TASK-BE-034).
- [x] 3 markdown FAQ translated to English (domain routing preserved).
- [x] No image rebuild (mounted assets); shipped at `0.9.1` via deploy + re-sync.
- [x] User validation (2026-09-18).
- [x] Pilot re-synced + grounded English answers verified on **both** nodes (slow-internet,
      billing, FTTC→FTTH, cancellation; confidence 0.69–0.83) — no advisor deflection.

### Deploy outcome (2026-09-18)

- Backend redeployed on t03+t04 at `0.9.1` (assets recopied: `articles-en.csv` + EN FAQ). Auto
  KB sync was run **manually with a warm-up gate** (avoided the BUG-021 cold-start 401).
- `vector_store` now holds **4872 `csv-article`/en chunks + 44 markdown (EN content)**; the FR
  `csv-article` rows were fully replaced by English. EN grounding is **live**.
- ⚠️ **BUG-022 discovered**: the CSV sync **hangs deterministically in the chunk-embedding store
  phase** (Ollama idle, no timeout; saturates embedding → live 503s). The store commits
  incrementally, so the bulk of the corpus is ingested (4872 chunks) but a small **tail** may be
  missing, and the sync never returns a `SyncReport`. Mitigation shipped: `kb_sync_after_deploy:
  false` (so future deploys don't hang/abort) + manual gated procedure. Full fix tracked in
  **BUG-022** (`tasks/bug-022-kb-sync-store-hang.md`).
