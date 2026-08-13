# Knowledge Base Ingestion — Technical Tasks

Follow-up ingestion connectors built on the **KB ingestion socle** delivered in
`TASK-BE-003` (pivot `SourceDocument`, `KnowledgeSourceConnector` port, idempotent
`KnowledgeSyncService` with the `kb_source_state` ledger, pgvector + Ollama
embeddings). New sources plug in as additional `KnowledgeSourceConnector` beans and
are picked up automatically by the sync service — no core change.

These form the **Sprint 8** theme (CSV KB ingestion), scheduled after the Sprint 7
answer-engine core, per product decision (2026-07-18, sprint set 2026-07-21).

> Note: this connector was drafted as `TASK-BE-011`, but that ID was used and
> delivered in Sprint 7 for the backend latency levers. It is renumbered to
> **TASK-BE-013** here; the batch embedding/insert work is split out as
> **TASK-BE-014**.

| Task | Title | Classification | Depends on | Status |
|---|---|---|---|---|
| TASK-BE-013 | `CsvArticleConnector` + embedding `DomainClassifier` — bulk KB ingestion from `articles.csv` | V1 core (KB content) | TASK-BE-003 | ✅ Merged into `feat/restart-from-scratch` (Sprint 8, user-validated 2026-07-21, `23cb49b`; sprint closed `365251d`) — adversarial 92/100, QA functional PASS (bulk latency → BE-014) |
| TASK-BE-014 | Batch embedding/insert (`VectorStorePort.storeChunks`) + sync progress metrics/logs | V1 core (KB content) | TASK-BE-013 | In review — implemented + live-validated (150-article batched sync 75s→44.7s, 42.7 chunks/s), 178 tests green; awaiting adversarial review + QA acceptance |
| TASK-BE-017 | French translation of the `articles.csv` corpus for dev FR RAG coverage (`csv-article-fr` connector) | Dev tooling (KB content, non-prod) | TASK-BE-013, TASK-BE-014 | ✅ Delivered (2026-07-22) — 306 articles translated → `articles-fr.csv`, ingested `csv-article-fr` = **4989 chunks**; TextChunker hard-split fix for oversized FR paragraphs; FR questions now ground on FR content |
| TASK-BE-027 | Retrieval-quality eval harness + baseline measurement (offline) — labeled FR/EN eval set with phrasing variants, run against `/api/conversation/retrieve`, compute recall@k / MRR / phrasing-stability; the OQ-008 / ADR-0032 gate | V1 quality (RAG measurement) | TASK-BE-003, BUG-003 (fixed) | Proposed — offline, needs no pilot access. Baseline = current stack (fixed chunker, top-K=8, dense-only). EPIC-005 / ADR-0032 / OQ-008 |
| TASK-BE-028 | Retrieval lever 2b — MMR (diversity) over the over-fetched candidates so near-duplicate header chunks stop evicting the answer chunk | V1 quality (RAG) | TASK-BE-027 | Proposed — **gated** on the TASK-BE-027 baseline showing eviction-by-near-duplicates persists. Cheap, pgvector-native. EPIC-005 / ADR-0032 |

---

## TASK-BE-027 — Retrieval-Quality Eval Harness + Baseline Measurement (Offline)

**Parent:** EPIC-005 (Answer engine / knowledge base)
**Related decision:** ADR-0032 (retrieval-quality strategy) — this ticket is its measurement gate
**Related:** OQ-008, BUG-003 (fixed chunking), BUG-004 (closed)
**Classification:** V1 quality (RAG measurement) — offline, needs no pilot/external access
**Status:** Proposed
**Priority:** Medium

### Trigger

BUG-003 fixed chunking and top-K was raised to 8, but OQ-008 (pgvector + hybrid/rerank vs
Qdrant) cannot be resolved by intuition. ADR-0032 states the choice between the remaining
levers (MMR → hybrid → rerank → Qdrant) must be **measured**. There is no repeatable
retrieval-quality eval today — every judgement is a one-off manual `/retrieve` check.

### Objective

Build a small, versioned, repeatable **offline** eval that scores retrieval quality on the
loaded corpus, so each lever's marginal gain (and the eventual engine decision) is
evidence-driven. Record the **baseline** for the current stack.

### Scope

- A versioned, labeled **eval set** (~20–40 questions) across the covered domains
  (internet/box troubleshooting, résiliation/billing), in **FR and EN**, each labeled with
  the article/section that holds the answer, and each carrying **phrasing variants** (bare,
  greeting-prefixed, reworded).
- A runner that calls `POST /api/conversation/retrieve` (backend-only, deterministic) for
  every query/variant and computes **recall@k (k=4,8)**, **MRR**, and a **phrasing-stability**
  score, reported **per language and per domain** (not just an aggregate).
- A committed **baseline report** for the current configuration (fixed chunker, top-K=8,
  dense-only, no MMR).
- OpenTelemetry: reuse existing `/retrieve` retrieval spans/metrics; the harness is a client,
  so mark runtime instrumentation N/A beyond what `/retrieve` already emits.

### Out of scope

- No change to the retrieval algorithm itself (MMR/hybrid/rerank land in later tickets).
- No engine change; no pilot/live-voice run required (the harness is deterministic backend).

### Acceptance

- The eval set and runner are committed and reproducible; a single command produces the
  report.
- The baseline report exists with recall@k, MRR and phrasing-stability per FR/EN and domain.
- ADR-0032's proposed acceptance bar (recall@8 ≥ 0.9 & stability ≥ 0.9) is confirmed or
  adjusted against the baseline, and OQ-008 records the next lever decision.
- Tests cover the metric computation (GIVEN labeled hits WHEN scored THEN recall/MRR correct).
- `git diff --check` clean.

---

## TASK-BE-028 — Retrieval Lever 2b: MMR Diversity Over Over-Fetched Candidates

**Parent:** EPIC-005 (Answer engine / knowledge base)
**Related decision:** ADR-0032 (lever 2b)
**Related:** TASK-BE-027 (baseline gate), OQ-008
**Classification:** V1 quality (RAG)
**Status:** Proposed — **gated** on the TASK-BE-027 baseline showing near-duplicate eviction persists
**Priority:** Low

### Objective

If the TASK-BE-027 baseline confirms near-duplicate header/fragment chunks still crowd out
the answer chunk within the over-fetched set, apply **MMR (Maximal Marginal Relevance)**
diversity re-ranking over the top-K candidates before they reach the LLM, so the answer chunk
is retained. Cheap, pgvector-native, store-independent.

### Scope

- MMR selection over the over-fetched candidates behind the existing `VectorSearchPort`
  boundary (no engine change), env-tunable λ (relevance vs diversity).
- Re-run TASK-BE-027 to record the marginal gain vs baseline.

### Acceptance

- MMR is applied over the over-fetched set; the answer chunk is retained where the baseline
  evicted it, with a measured recall@8 / stability improvement in the TASK-BE-027 report.
- OpenTelemetry: retrieval span records that MMR ran (candidate count in/out).
- Tests cover MMR selection (GIVEN near-duplicate candidates WHEN MMR selects THEN diverse
  set keeps the answer chunk).
- If the baseline already clears the bar without MMR, this ticket is closed as **not needed**
  with that evidence.

---

## TASK-BE-013 — CsvArticleConnector + Embedding DomainClassifier (bulk KB ingestion)

**Parent:** EPIC-005 (Answer engine / knowledge base)
**Related enabler:** TASK-BE-003 (ingestion socle + Markdown connector)
**Related decision:** ADR-0030 (to create — KB connector deps + HTML-to-text +
`DomainClassifier`)
**Classification:** V1 core — provides the real operator KB content the answer
engine retrieves from.
**Status:** ✅ Validated by user (2026-07-21) — adversarial 92/100, QA PASS, live-validated.
Merge-ready; merge awaiting explicit user request.
**Priority:** High
**Branch:** `task/TASK-BE-013-csv-article-connector` (included in `task/TASK-BE-014-batch-embedding`)

### Review & QA outcome

- **Adversarial code review:** 92/100 — QA gate **Pass**. No blocking findings.
  Remediations applied during review: classifier resilience (embedding failure →
  `general`, sync continues) + ADR-0030 wording corrected (classification uses its own
  embedding, not the storage vectors). Non-blocking items routed to TASK-BE-014
  (bulk streaming/batch + per-row isolation + sync observability/throughput) and
  TASK-BE-015 (FR/EN mixing).
- **QA functional:** PASS — unit tests + Cucumber BDD (`csv-knowledge-ingestion.feature`,
  3 scenarios) prove clean HTML→text, per-article domain classification, blank-row
  skipping and idempotent `csv-article` sync. Report:
  `docs/qa/task-be-013-csv-kb-ingestion-qa-report.md`.
- **Live run (2026-07-21):** 150-article sample of the real Eir corpus against real
  pgvector + Ollama. Ingest `processed 150 / ingested 150` in **75 s** (~0.5 s/article,
  1 901 chunks); idempotent re-sync `ingested 0 / skipped 150` in 7.5 s; **0** residual
  HTML tags; retrieval returns the right domain with strong scores (handset→support 0.79,
  credit vetting→billing 0.75, wifi→support 0.70). **Classifier threshold calibrated to
  0.55** (was 0.50): the low-confidence tail routed to `general` is genuinely
  cross-cutting (GDPR, Right to be Forgotten, agent tooling, Eircodes). Distribution
  @0.55: support 91 / billing 25 / general 18 / commercial 16. Full details in the QA
  report.
- **QA latency:** bulk ingest time/throughput owned by TASK-BE-014. The corpus is **306
  articles** (~40,900 lines = multi-line HTML, not article count); the single-insert path
  (~0.5 s/article) is why batching was applied (offline admin path, no voice-runtime SLO
  impact).

### Context

The seed dataset `articles.csv` (kept out of git — external ingestion input) is an
extract of all operator support articles to load into the KB. Observed shape:

- Columns: `document_id, title, content`
- **306 articles** / ~40,900 lines (HTML `content` is multi-line) / ~3.9 MB
- **`content` is HTML** (operator support-site articles)
- **No `domain` and no `language` column**

### Objective

Ingest the CSV article corpus into the vector store through a new
`KnowledgeSourceConnector`, reusing the BE-003 idempotent sync + ledger, so RAG can
retrieve grounded operator content at scale.

### Scope

- **`CsvArticleConnector`** (`sourceType = "csv-article"`) reading the configured
  CSV path (external input; `voice-support.knowledge.csv-path`), streaming rows
  (do not load the whole file into memory). Map each row →
  `SourceDocument(sourceId = document_id, title, content, domain, language,
  updatedAt, contentHash)`.
- **CSV parsing** via **Apache Commons CSV** (RFC-4180): the HTML `content` has
  embedded newlines and escaped quotes (`""`), so a hand-rolled split is unsafe.
  Stream rows (do not load the whole file into memory).
- **HTML → plain text** via **jsoup** before the pivot, so chunks and embeddings are
  clean text (strip tags, decode entities, drop `<img>`/scripts, keep link text).
- **Domain classification** (`articles.csv` is mixed — no domain column): a
  `DomainClassifierPort` populates `domain` before `SourceDocument.create(...)`.
  Retained implementation: **`EmbeddingDomainClassifierAdapter`** — embed the article
  text (Ollama `nomic-embed-text`, 768) and pick the closest domain anchor
  (`billing`/`support`/`commercial`) above a configurable threshold (calibrated 0.55),
  else `general`.
  A `DefaultGeneral` impl preserves the current behaviour. Port pure in the domain,
  embedding access in an infra adapter; anchors + threshold configurable; testable
  with a fake `EmbeddingModel` (no network). Reused later by EPIC-011 for query-time
  intent classification.
- **Language**: `en` default for this connector (config `csv-default-language`) — the
  Eir corpus is English (product default language), unlike the French Markdown dev
  FAQ, which coexists.
- **Batch embedding/insert + sync observability**: split out to **TASK-BE-014**.

### Acceptance

- A sync run ingests all CSV articles; a second run is a no-op (idempotent via
  `content_hash`); editing/removing rows re-ingests/purges via the ledger.
- Stored chunk content is plain text (no HTML tags); every chunk carries a
  **classified** `domain` (via `DomainClassifier`, fallback `general`) and
  `source_type = "csv-article"`.
- `DomainClassifier` is exercised: articles clearly in a domain get that domain,
  ambiguous ones fall back to `general`; classification is deterministic and
  covered by unit tests with a fake `EmbeddingModel`.
- Bulk ingest uses the batched embedding/insert delivered in **TASK-BE-014**; total
  ingest time and throughput are reported (latency evidence).
- `mvn test` stays infra-free (domain fakes for the connector, sync and classifier);
  a small live/IT run validates the real corpus against Postgres + Ollama.

### Open questions

- **Domain taxonomy source**: can the real Eir export provide a category/section per
  article (or a `document_id → domain` sidecar)? If yes, a source-provided classifier
  beats the heuristic; otherwise keep `EmbeddingDomainClassifier`. (To record as an
  OQ.)
- **Answer language** (English default for Eir) + FR(dev)/EN(prod) mix in the same
  vector store (retrieval pollution risk; possible future `language` filter) —
  tracked as **TASK-BE-015** (scope TBD: this sprint or later).
- Whether the corpus is a one-off load or a periodically-refreshed source (affects
  scheduling and the ledger diff semantics).
- Licensing/PII review of the third-party operator content before pilot.

---

## TASK-BE-014 — Batch Embedding/Insert + Sync Observability

**Parent:** EPIC-005 (Answer engine / knowledge base)
**Related enabler:** TASK-BE-003 (ingestion socle), TASK-BE-013 (CSV connector)
**Classification:** V1 core — makes bulk CSV ingestion viable (performance).
**Status:** ✅ Validated by user (2026-07-21) — adversarial 93/100 (gate Pass), QA PASS, live-validated.
Merge-ready; merge awaiting explicit user request.
**Priority:** High
**Branch:** `task/TASK-BE-014-batch-embedding`

### Review & QA outcome

- **Live run (2026-07-21, same 150-article Eir sample, real pgvector + Ollama):** batched
  sync **75 s → 44.7 s** (~40% faster), throughput **42.7 chunks/s** (1 901 chunks), and
  the classification distribution is **unchanged** (support 91 / billing 25 / general 18 /
  commercial 16 @0.55) — batching is a pure performance change. Idempotent re-sync stays a
  no-op (0 ingested / 150 skipped, no batch emitted).
- **Observability:** `[KB-SYNC] op=sync-detail source_type=csv-article processed=150
  ingested=150 skipped=0 deleted=0 total_chunks=1901 duration_ms=44504 chunks_per_sec=42.7`;
  Micrometer meter `voice_support.kb_sync_batch` exposed via actuator (COUNT=150,
  TOTAL_TIME=35.0 s, MAX=1.09 s, tag `source_type`), plus `kb_sync_chunks` and `kb_sync`.
- **Tests:** **184 green** (unit + Cucumber BDD + ArchUnit), infra-free — assert one batched
  `storeChunks` call per document, the observer's per-batch + completion events, and the
  **failure path** (fault-injected sync aborts fail-fast, emits `syncFailed`, resumes via ledger).
- **Adversarial review:** 93/100 (gate Pass) — `docs/qa/task-be-014-adversarial-review.md`. The
  silent-failure-path finding was fixed in-loop (`SyncObserverPort.syncFailed` +
  `voice_support.kb_sync_failures` counter + `[KB-SYNC] op=sync-failed` log).
- **QA report:** `docs/qa/task-be-014-batch-embedding-qa-report.md` (idempotent full-corpus
  re-sync 306 skipped in 16.7 s; retrieval `verdict=PASS`; recommendation **Go**).
- **Full corpus measured:** the corpus is **306 articles** (not ~40 900 — that is the
  multi-line HTML line count). The full corpus ingests in **~73 s** live (156 new + 150
  skipped; `chunks_per_sec=44.1`), ~92 s from scratch — well within one HTTP request.
  Embedding (classification + chunk embeds on Ollama) is now the dominant cost, not inserts.
  The async job / status open question is therefore **not needed at this size** (only for a
  hypothetical far larger corpus).

### Context

`PgVectorStoreAdapter` currently stores one chunk per `vectorStore.add(List.of(one))`
call (~40 ms/chunk on CPU Ollama observed in BE-003). Across the full CSV corpus
(306 articles, ~3 235 chunks) this per-chunk round-trip is too slow, so chunks are batched
per document to keep `POST /api/knowledge/sync` within one request.

### Objective

Store chunks in batches so a full-corpus sync completes within a documented bound,
and expose ingestion progress/throughput for monitoring.

### Scope

- Extend `VectorStorePort` with a batched `storeChunks(...)` (group `add` → batch
  embedding) and use it from `KnowledgeSyncService.reingest`. Update **all**
  implementers, including test fakes (e.g. `FakeVectorStorePort`).
- `[KB-SYNC]` structured logs + metrics: docs processed, chunks, per-batch timing,
  total duration and chunk throughput; report a documented ingest-time bound.
- Keep idempotency and deletion-diff semantics unchanged.

### Acceptance

- A full `articles.csv` sync completes within the documented bound and reports
  throughput; a second run is a no-op (idempotent).
- `VectorStorePort` change is reflected in every implementer + fake; `mvn test`
  stays infra-free; a live/IT run validates real bulk ingest against Postgres +
  Ollama.

### Open questions

- Optimal batch size vs Ollama embedding throughput and Postgres insert size.
- Whether to make sync asynchronous (job + status) if the bound is still too long
  for a single HTTP request.

---

## TASK-BE-015 — Answer Language Handling

**Parent:** EPIC-005 (Answer engine / knowledge base)
**Related:** TASK-BE-013 / TASK-BE-014 (English Eir corpus now ingested), Sprint 7 answer engine
**Classification:** V1 core — answer quality; runtime-affecting (requires observability).
**Status:** ✅ Validated by user + merged into `feat/restart-from-scratch` (2026-07-23, Sprint 8
closure). Implemented (backend, infra-free tests + BDD), adversarial review closed, functional
QA + live run (Mistral+Ollama+corpus) confirm FR/EN answers, FR↔EN fidelity and per-turn
telemetry. QA-found **BUG-002** (ambiguous-follow-up guardrail fallback ignored session
stickiness / configurable default) fixed + adversarial passed + **live QA retest PASS**.
Report: `docs/qa/task-be-015-answer-language-qa-report.md`; bug: `bugs/BUG-002…md`.
**Priority:** High
**Branch:** `task/TASK-BE-015-answer-language`

### Implementation notes (2026-07-21)

- `AnswerLanguage` value object (FR/EN): detection heuristic (`detect`), per-call LLM directive
  (with the exact hand-off sentence), hand-off markers, `fromCode` for config.
- `LanguageDetector` domain service: per-turn decision = question language → session stickiness
  (from history) → configured default; `@Bean` reading `voice-support.conversation.default-language`
  (`en`, Eir pilot).
- Language threaded through `AnswerGeneratorPort` / `StreamingAnswerGeneratorPort` to the LLM
  adapter, which appends the directive last (recency overrides the French base prompt). Mistral/
  Ollama prompts dropped the old language line + hardcoded FR refusal.
- `GuardrailMessages` uses the shared detector; `OutputGuardrail` matches every language's hand-off
  markers (English refusal caught like French). Ambiguous default flipped FR → EN (pilot).
- Observability: `voice_support.answer_language{provider,language}` counter + `[LANGUAGE]` log
  (correlation id) recorded per LLM turn.
- ADR-0031 records the decision; closes the ADR-0030 answer-language open question.

### Context

The Eir knowledge base is in **English**; the development default framing is **French**.
In the Sprint 8 live test, an **English** question received a **French** answer, and the
insufficient-evidence, off-topic and escalation messages are currently tied to a fixed
language. This produces answers the customer cannot reliably understand and erodes trust.

### Product Objective

The customer always hears the assistant **in their own language**, consistently across
grounded answers, fallbacks, refusals and human-escalation wording — for both French and
English — so the pilot (English) and development (French) both behave correctly.

### Target Users

End customers (voice and text) of the operator support assistant, in French or English.

### In Scope

- Answering each customer turn in the **language of that turn's question**.
- Consistent language across **all** assistant utterances in a turn: grounded answer,
  insufficient-evidence fallback, off-topic refusal, and the human-escalation sentence.
- A **configurable default language** used when the turn's language cannot be confidently
  determined (English for the Eir pilot).
- **Per-turn** language decision with **session stickiness** as the tie-breaker on ambiguity.
- Answering in the **customer's language even when the relevant knowledge is only available
  in the other language** (FR↔EN) for V1.
- **French and English** support, designed to allow adding languages later without reworking
  the flow.

### Out Of Scope

- Languages beyond French and English.
- Translating or storing the knowledge base in multiple languages (KB stays as ingested).
- Any change to which documents are retrieved (retrieval scope is unchanged).

### Business Rules

- **BR1** — The assistant answers a customer turn in the language of that turn's question.
- **BR2** — When the turn's language is not confidently determined (very short/ambiguous
  input, or a first greeting with no question), the assistant uses the deployment default
  language (English for the Eir pilot; the default is configurable per deployment).
- **BR3** — Language is decided per turn; on ambiguity the assistant keeps the current
  conversation language rather than switching arbitrarily (session stickiness).
- **BR4** — Every assistant utterance in a turn is in the chosen language: grounded answer,
  insufficient-evidence fallback, off-topic refusal, and the escalation/hand-off sentence.
- **BR5** — If the relevant knowledge exists only in the other supported language, the
  assistant still answers in the customer's language based on that content (FR↔EN).
- **BR6** — V1 supports French and English; adding a language must not require reworking the
  conversation flow.
- **BR7** — Escalation and safety behaviors (human hand-off, unsafe/off-topic refusal) must
  trigger identically in every supported language.

### Non-Functional Expectations

- The chosen answer language is **observable per turn** (correlation id) for QA and
  troubleshooting (OpenTelemetry: structured log + attribute; metric by language when enough
  samples exist).
- The language decision must **not materially degrade the voice latency SLO**
  (`time_to_first_audio`); any added step is measured per the latency slices.

### Acceptance Criteria

```gherkin
Scenario: English question gets an English answer
  Given the knowledge base contains the relevant English content
  When the customer asks a support question in English
  Then the assistant answers in English

Scenario: French question gets a French answer
  When the customer asks a support question in French
  Then the assistant answers in French

Scenario: Fallbacks and escalation follow the customer's language
  Given the assistant cannot find enough evidence to answer
  When the customer asked in English
  Then the insufficient-evidence message and the human-escalation offer are in English

Scenario: Off-topic refusal follows the customer's language
  When the customer asks an out-of-scope question in English
  Then the refusal is in English

Scenario: Customer language wins over content language
  Given the only relevant knowledge is in English
  When the customer asks in French
  Then the assistant answers in French based on that content

Scenario: Ambiguous turn uses the default / current language
  Given the customer's turn is too short to determine a language
  Then the assistant replies in the current conversation language, or the deployment
    default (English for the Eir pilot) if none is established yet
```

### Dependencies

- English corpus ingested (TASK-BE-013 / TASK-BE-014) — done.
- Voice runtime STT/TTS must operate in the answered language on the voice path — see open
  question (a mismatch would make the customer hear the wrong-language voice regardless of
  the text answer).

### Risks / Open Questions

- **Voice STT/TTS language** (Architecture / voice runtime): does the voice path select
  STT/TTS per language, and how does the chosen answer language propagate to TTS so the
  spoken reply matches? Escalate to `software-architect` / voice runtime before the voice
  acceptance run.
- **Fidelity of a French answer grounded on English content** (and vice-versa): QA to
  validate comprehension quality.
- Detection approach and prompt/guardrail changes are implementation details owned by the
  backend developer (kept out of this product ticket).

---

## TASK-BE-017 — French translation of the CSV corpus (dev FR RAG coverage)

**Parent:** EPIC-005 (Answer engine / knowledge base)
**Related enabler:** TASK-BE-013 / TASK-BE-014 (English `csv-article` corpus ingested),
TASK-BE-015 (answer language — FR↔EN answers on an EN-only corpus)
**Classification:** Dev tooling — KB content for development/testing only (not a prod
data decision). Non-runtime-affecting at request time (offline admin ingestion path).
**Status:** ✅ Delivered (2026-07-22). 306 articles translated to `articles-fr.csv` (Mistral
translation script), ingested as `csv-article-fr` = **4989 chunks** (vs 5136 EN, 41 markdown).
A `TextChunker` fix (hard-split of oversized single paragraphs) was required: the FR corpus
flattened article bodies into single paragraphs that exceeded the nomic-embed-text token limit;
the chunker now guarantees no chunk exceeds `chunk-size`. Live: French questions
(router setup, SIM activation, wifi password) now ground on FR content (conf ~0.76–0.83) where
they previously fell back. Merge-ready; merge awaiting explicit user request.
**Priority:** Medium (dev enablement — reduces FR insufficient-evidence fallbacks in local testing)
**Branch:** `task/TASK-BE-017-fr-csv-translation` (chunker fix committed on the stacked
`us/US-042-ui-language-selector` branch alongside US-042).

### Context

The KB is ~99% English: 5 136 `csv-article` chunks (306 Eir articles) in English vs 41
hand-written French FAQ (`markdown`) chunks. TASK-BE-015 lets the assistant answer in
French from English content, but in live testing many French questions still fall back to
the insufficient-evidence hand-off: the retrieved English chunks are only loosely relevant
to the French phrasing, so Mistral honestly declines. For **development testing** we want a
French copy of the corpus so French questions retrieve French content directly.

TASK-BE-015 explicitly kept "translating/storing the KB in multiple languages" out of
scope; this task is the **dev-only** follow-up that does exactly that, for local testing —
translation fidelity is explicitly *not* required to be production-grade.

### Objective

Provide a French-translated copy of the `articles.csv` corpus, ingested as a distinct
`csv-article-fr` KB source (language `fr`), so French questions in local testing retrieve
grounded French content and fall back less often — without touching the English source.

### Scope

- Parameterize `CsvArticleConnector.sourceType` (constructor arg; keep `csv-article` as the
  EN default) so a second FR instance can register `csv-article-fr` without a source_id
  collision (sync keys on `(source_type, source_id)`).
- Second `@Bean` `csvArticleFrConnector` in `KnowledgeConfig`: path
  `voice-support.knowledge.csv-fr-path` (default `../articles-fr.csv`), language `fr`,
  `source_type = csv-article-fr`; auto-picked up by `KnowledgeSyncService`
  (`List<KnowledgeSourceConnector>`).
- A **translation script** (`scripts/translate_csv_kb.py`, stdlib + Mistral API via the
  configured `MISTRAL_API_KEY`): read `articles.csv` (raise CSV field limit), HTML→text,
  translate `title` + `content` to French, write `articles-fr.csv`
  (`document_id,title,content`, same `document_id`). Resumable/idempotent (skip rows
  already present in the output).
- Ingest via `POST /api/knowledge/sync/csv-article-fr`.

### Out Of Scope

- Production KB language strategy (a real prod decision, not this dev task).
- Human-quality translation / review of the French content.
- Any change to retrieval scope, guardrails, or the English `csv-article` source.

### Acceptance

- `articles-fr.csv` exists with 306 French articles (same `document_id`s).
- After sync, `vector_store` holds `csv-article-fr` chunks tagged `language=fr`; the English
  `csv-article` source is unchanged.
- A French question that previously fell back now grounds in French with a plausible answer
  (live check on Mistral + Ollama + pgvector).
- `mvn test` stays infra-free (the connector change is covered by the existing CSV connector
  tests / a fake; the translation script is a dev tool, not wired into the app).

### Risks / Open Questions

- Machine-translation quality is dev-grade; some French chunks may be awkward — acceptable
  for local testing, must not be promoted to prod without review.
- Domain classifier anchors are English; FR articles are classified on their own embedding —
  distribution may drift slightly vs the EN source (acceptable for dev).
- Mistral rate/throughput on 306 articles: script batches/paces calls and is resumable.
