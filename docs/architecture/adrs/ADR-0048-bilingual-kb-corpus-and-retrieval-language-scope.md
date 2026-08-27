# ADR-0048 — Bilingual KB corpus strategy and retrieval language scope

- **Status:** Accepted
- **Date:** 2026-08-27
- **Deciders:** Architecture, Backend, Product (pilot owner)
- **Related:** ADR-0006 (Mistral chat / Ollama embeddings), ADR-0007 (`SourceDocument`
  KB sync socle), ADR-0030 (CSV connector + domain classification), ADR-0031 (answer
  language handling), ADR-0032 (retrieval quality strategy — Proposed), ADR-0034 (KB
  audience boundary, fail-closed customer filter), OQ-008 (retrieval quality)
- **Tickets:** TASK-BE-034 (retrieval language filter — target), TASK-OPS-009 (deploy
  KB sync trigger + FR corpus default — pilot durable config), TASK-BE-035 (KB rebrand
  follow-up), TASK-BE-013/014/015/017 (CSV connectors + answer language + FR translation)

## Context

The pilot answers French support/billing/commercial questions with a RAG engine over
pgvector. Three knowledge corpora exist at the repo root (all git-ignored — external
ingestion inputs, never tracked):

| File | Language | Rows | Shape | Brand |
|---|---|---|---|---|
| `articles.csv` | English | ~40,915 | HTML-heavy | eir / eircom / AT&T |
| `articles-fr.csv` | **French** | ~49,306 | HTML mostly stripped, ~2,573 mobile rows | eir / AT&T (a **translation** of the eir corpus, not rebranded) |
| `articles-sample.kb.csv` | mixed | — | sample | — |

The live pilot `vector_store` currently holds **only 39 chunks, all `source_type=markdown`,
`language=fr`** (the three hand-written FR FAQ files `billing-faq.md`,
`commercial-faq.md`, `telecom-faq.md`, synced 2026-08-14). **No CSV corpus has ever been
synced on the pilot** — `articles.csv` was copied to the host by the Ansible KB-assets task
but no deploy step triggers `POST /api/knowledge/sync`, and the initial markdown sync was
run manually once. Consequently mobile questions such as
*"j'ai un problème avec mon téléphone mobile"* have **no grounded evidence** and correctly
deflect to a human advisor per DEC-002 (insufficient-evidence hand-off).

Two facts about the current backend shape this decision:

1. **Answer language is already per-request and independent of the corpus language**
   (ADR-0031): `LanguageDetector` + `AnswerLanguage` answer each turn in the customer's
   language (FR↔EN) regardless of the retrieved chunk's language. So corpus language
   affects *retrieval relevance*, not the spoken/written answer language.
2. **Retrieval has no language filter.** `PgVectorStoreAdapter.buildSearchFilter` scopes on
   `audience` (customer, fail-closed — ADR-0034) AND optionally `domain`
   (`domain == X OR general`). Each chunk *does* carry `language` metadata
   (`putIfPresent(metadata, "language", …)`), but `VectorSearchPort.search(query, domain,
   topK)` has no language parameter, so ingesting EN and FR corpora into the same store
   would mix EN and FR chunks in the same top-K for every query.

The backend already wires **two CSV connectors**: `csv-article` (`KB_CSV_PATH`,
`KB_CSV_LANGUAGE` default `en`, `source_type=csv-article`) and `csv-article-fr`
(`KB_CSV_FR_PATH` default `../articles-fr.csv`, `language=fr`,
`source_type=csv-article-fr`). On the pilot only `KB_CSV_PATH=/app/kb-assets/articles.csv`
is mounted/configured; `KB_CSV_FR_PATH` is unset, so the FR connector is a no-op.

## Decision

Split the initiative into a **pilot decision** and a **target decision**.

### 1. Pilot (now) — single FR corpus, no language filter

Load **`articles-fr.csv`** as the pilot CSV corpus (not the EN `articles.csv`), because:

- **Pilot users are French** — retrieval relevance is best when the corpus language matches
  the query language (FR query vs FR chunk embeddings). ADR-0031 answers in FR either way,
  but FR-on-FR retrieval grounds far more reliably than FR-on-EN (see TASK-BE-017 live
  evidence: FR questions that fell back on the EN corpus grounded once FR content existed).
- **More mobile coverage** — `articles-fr.csv` has ~2,573 mobile rows, directly addressing
  the deflecting mobile questions.
- **Cleaner text** — HTML is mostly already stripped in the FR file (less chunk noise).

Because there is **no language filter yet and no EN corpus loaded**, a single-language store
serves the pilot cleanly: every chunk is FR-relevant, so mixing is a non-issue. This keeps
the pilot on one corpus and avoids the EN+FR retrieval-mixing problem entirely until the
target filter lands.

### 2. Target (later) — bilingual store behind a retrieval language filter

The same pgvector store should be able to serve FR **and** EN cleanly. The enabler is a
**language predicate in `buildSearchFilter`** mirroring the domain predicate
(`language == requestLanguage OR language absent`), threaded from the request/answer
language through `VectorSearchPort.search(...)` → retrieval adapter → grounding
(**TASK-BE-034**, target only — not implemented now). With that filter in place the
bilingual approach is to ingest **both** `csv-article` (EN) and `csv-article-fr` (FR) and
let each query retrieve only its own language plus untagged/`general` chunks.

## Consequences

- **Positive (pilot):** mobile and broader FR support/billing questions become grounded and
  answered in French; no `.env`/vault edit and no full redeploy needed for the immediate
  load (drop `articles-fr.csv` at the already-mounted `articles.csv` path + trigger sync).
- **Residual — language metadata tag (accepted, tracked):** loading `articles-fr.csv` at the
  `csv-article` path while `KB_CSV_LANGUAGE` is still `en` tags those chunks
  `language=en` even though the content is French. This is **cosmetic today** (no language
  filter; answer language is per-request). It matters only once **TASK-BE-034** lands: the
  FR chunks would then need `language=fr` to be selected by a FR query. Because the
  idempotent sync skips on identical `content_hash`, flipping `KB_CSV_LANGUAGE=fr` alone
  will **not** re-tag existing chunks — a **forced re-sync** (empty `vector_store` for that
  source or a content change) is required. TASK-OPS-009 makes `KB_CSV_LANGUAGE=fr` +
  `KB_CSV_PATH=articles-fr.csv` the durable default so a clean redeploy tags correctly, and
  TASK-BE-034's rollout notes the re-tag requirement.
- **Residual — brand (accepted, tracked as TASK-BE-035):** `articles-fr.csv` is a
  *translation of the eir corpus* and still references eir/eircom/AT&T rather than the
  "telecom-exemple" brand. Acceptable for a pilot that validates grounding behaviour; a
  brand-correct French corpus is required before wider/production use.
- **Retrieval precision (OQ-008):** a single FR corpus avoids EN+FR mixing now; the target
  filter (TASK-BE-034) restores clean per-language scoping when both corpora are loaded.
- **Audience boundary preserved:** the fail-closed `audience==customer` filter (ADR-0034)
  is unchanged and independent of language.

## Alternatives considered

- **Load the EN `articles.csv` on the pilot.** Rejected: pilot users are French; FR-on-EN
  retrieval grounds less reliably, the EN file is HTML-heavy, and it has less mobile
  coverage. (EN remains the target's second corpus once TASK-BE-034 scopes by language.)
- **Load both corpora now (bilingual immediately).** Rejected for the pilot: with no
  language filter, EN and FR chunks would mix in every top-K, degrading FR precision. This
  is exactly what TASK-BE-034 unblocks — deferred to the target.
- **Use the `csv-article-fr` connector (language=fr) for the immediate load.** Rejected for
  the *operational* load because it needs `KB_CSV_FR_PATH` set + the file mounted at that
  path + a container restart, i.e. a vault `.env` edit and redeploy (which also carries the
  known health-gate false-negative risk). The durable config (TASK-OPS-009) instead makes
  `articles-fr.csv` the primary `csv-article` corpus; the `csv-article-fr` connector stays
  available for the bilingual target.
