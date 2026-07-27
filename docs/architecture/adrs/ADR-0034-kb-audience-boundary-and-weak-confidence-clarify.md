# ADR-0034: KB audience boundary and weak-confidence clarify policy

## Status

Accepted

## Context

Live WebRTC billing testing surfaced [BUG-005](../../../product-backlog/bugs/BUG-005-internal-kb-content-leaked-to-end-user.md):
on a vague follow-up turn (`"vas-y."`) the assistant voiced **internal, agent-facing**
knowledge — an internal appointment-tooling procedure naming operator back-office
tools (`R6/ION`, `VAA` / *Vérification d'Aptitude*). The retrieval confidence had dropped
to ≈0.52 (from ≈0.76 on the previous well-formed turn) yet still **passed** the gate
(`grounded=true`) and the LLM voiced the weakly-matched internal article.

Two independent defects combine here:

1. **No KB audience boundary.** The target operator corpus (`articles.csv` /
   `articles-fr.csv`, ADR-0030) mixes **customer-facing** self-care articles with
   **internal/back-office agent** procedures. The columns are `document_id,title,content`
   only — there is no audience/visibility signal. At ingestion an article receives a
   `domain` (billing/support/commercial/general, ADR-0030) but nothing marks it as
   internal, so an internal article is embedded, retrieved and voiced to a customer
   exactly like a customer article. This is an information-exposure concern, not only a
   relevance one.

2. **Permissive confidence gate on weak input.** `RetrievalConfidenceGuardrail`
   (ADR-0014) passes when the best evidence score reaches a single threshold
   (`0.5`, strict `<`). A score of `0.52` therefore passes and the LLM answers, even
   though the turn is a low-information continuer with no clear intent. There is no
   distinct "ask the customer to clarify" behavior — only a below-floor advisor hand-off.

BUG-005 is the **opposite** failure mode of BUG-003/BUG-004 (false low-confidence
fallback on covered topics): here the pipeline **over-answers** with wrong-audience,
weakly-matched content. The definitive billing proof threshold is owned by Product/
Billing/Legal ([OQ-002](../../../product-backlog/open-questions/v1-open-questions.md))
and stays open; this ADR scopes only the general RAG weak-match behavior, not the
billing-specific proof level.

## Decision

### 1. KB audience boundary (customer vs internal), deterministic at ingestion

- Introduce a new outbound port `AudienceClassifierPort.classify(title, content) ->
  "customer" | "internal"` in the `knowledge` context, mirroring the existing
  `DomainClassifierPort` (ADR-0030). Audience is a **second, orthogonal** dimension to
  `domain`.
- The V1 implementation is **deterministic and high-precision**:
  `KeywordAudienceClassifierAdapter` tags an article `internal` when its title/content
  matches a configured set of agent-desk markers (e.g. `back office`,
  `vérification d'aptitude`, `R6/ION`, whole-word acronyms `VAA`/`VRD`); otherwise
  `customer`. Markers are configurable (`voice-support.knowledge.audience.internal-markers`)
  so the boundary can be tuned without a rebuild. Precision is preferred over recall:
  over-tagging customer content as internal would hide legitimate answers, so only
  unambiguous agent-desk markers tag `internal`.
- `audience` is carried on the `SourceDocument` pivot and stored as **pgvector JSONB
  metadata** (`audience`), exactly like `domain` — a metadata-only change, no schema or
  embedding-dimension change. `SourceDocument.create(...)` defaults `audience` to
  `customer` so the markdown KB and existing callers stay customer-facing by default.

### 2. Retrieval always excludes internal on the customer answer engine

- `PgVectorStoreAdapter.search(...)` **always** restricts results to
  `audience == customer` (AND-combined with the existing domain filter). The
  `/api/conversation/*` answer engine is the customer channel **by definition**, so no
  per-request channel plumbing is added in V1. The filter is **fail-closed**: a chunk
  without an `audience` value is excluded, so a partial/legacy sync can never leak
  internal content. A full KB re-sync is therefore **required** to activate the boundary
  (every chunk must carry `audience`).
- If a future internal/agent-facing channel needs internal content, retrieval will gain
  an explicit `audience` parameter threaded from the caller — deferred until such a
  channel exists.

### 3. Weak-confidence clarify band + vague-turn detection

- `RetrievalConfidenceGuardrail` gains a **clarify band** between a hard floor and a
  clarify ceiling:
  - best score `< confidence-threshold` (floor, `0.5`) → `LOW_CONFIDENCE` (advisor
    hand-off, unchanged);
  - `confidence-threshold ≤` best score `< clarify-threshold` (`0.62`) → new `CLARIFY`
    verdict: the bot asks the customer to rephrase/clarify instead of voicing a
    weakly-matched article;
  - best score `≥ clarify-threshold` → `PASS`.
- A new `GuardrailDecision.Verdict.CLARIFY` (a *blocked* verdict) carries a canned
  clarify message; both the sync and streaming pipelines already route any blocked
  decision to a spoken fallback, so `CLARIFY` flows through unchanged.
- `InputGuardrail` additionally detects a **vague / low-information turn** (a short
  utterance made only of contentless continuers such as `vas-y`, `allez-y`, `continue`,
  `ok`, `d'accord`) **before** retrieval and returns `CLARIFY` directly — this fixes the
  exact BUG-005 trigger without spending a retrieval + LLM call.
- Thresholds are configurable (`voice-support.conversation.confidence-threshold`,
  `voice-support.conversation.clarify-threshold`) and the vague markers are configurable
  (`voice-support.conversation.vague-markers`). The clarify band is only active when
  `clarify-threshold > confidence-threshold`; the single-threshold constructor keeps the
  legacy no-band behavior for existing callers/tests.

### 4. Observability

- Ingestion logs an audience decision per document (INFO when `internal`) so the size of
  the internal partition is visible after a sync.
- The per-turn guardrail block verdict is recorded as a counter
  (`voice_support.guardrail_block`, tagged `verdict`/`channel`) + a structured log, so
  `clarify` vs `low_confidence` vs `off_topic` rates are observable per channel. The
  audience exclusion itself is a deterministic always-on filter, so per-turn
  exclusion counting is N/A (fail-closed at the store), but the internal-partition size
  is observable at ingestion.

## Consequences

- Internal agent-desk content can no longer be retrieved or voiced on the customer
  answer engine (fail-closed), removing the BUG-005 information-exposure path.
- Activating the boundary **requires a full KB re-sync** (`DELETE FROM vector_store;`
  then `POST /api/knowledge/sync`) so every chunk carries `audience`; until then the
  fail-closed filter returns nothing for untagged chunks. This is documented alongside
  the domain-metadata re-sync note.
- Vague/low-information turns now ask for clarification instead of over-answering, and a
  middle-confidence band clarifies rather than voicing a weak match — at the cost of
  some additional clarify turns on genuinely borderline questions (tunable via the
  clarify threshold; measure before tightening).
- The keyword audience classifier is intentionally simple; recall depends on the marker
  list. It can be upgraded to an embedding/hybrid `AudienceClassifierPort` implementation
  later without touching the domain or the retrieval boundary (same port).
- `SourceDocument` and the pgvector metadata gain one field; all `SourceDocument.create`
  callers and vector-store fakes must set/expect `audience` (defaulted to `customer`).

## Alternatives Considered

- **Embedding-based audience classifier now** (anchors internal vs customer, like the
  domain classifier). Rejected for V1: a security/audience boundary must not rest on a
  probabilistic score that can misclassify; a deterministic high-precision ruleset is
  safer and testable, and the port keeps the embedding/hybrid upgrade open (OQ-008-style
  follow-up).
- **Channel-plumbed audience filter now** (thread `channel` from `ConverseController`
  down to retrieval and map channel→audience). Rejected as premature: the only V1
  consumer of the answer engine is the customer, so always-exclude-internal is correct
  and avoids touching five layers; plumbing is deferred until an internal channel exists.
- **Just raise the single confidence threshold** (`0.5 → 0.6`). Rejected: it still voices
  a weak match up to the new floor and offers no distinct clarify UX; below the floor it
  hands off to an advisor even when a simple clarification would resolve the turn.
- **Resolve OQ-002 first.** Rejected as a blocker: BUG-005 is a P1 exposure defect. The
  general weak-match clarify policy is decoupled from the billing proof threshold, which
  stays owned by Product/Billing/Legal.

## Related Documents

- [ADR-0007](ADR-0007-source-document-knowledge-sync.md) — `SourceDocument` pivot + sync.
- [ADR-0014](ADR-0014-domain-guardrails-before-and-after-rag.md) — pre/post-retrieval guardrails.
- [ADR-0030](ADR-0030-csv-knowledge-connector-and-domain-classification.md) — CSV connector + `DomainClassifierPort`.
- [ADR-0021](ADR-0021-conversation-backend-answer-contract.md) — answer contract + provisional confidence.
- [BUG-005](../../../product-backlog/bugs/BUG-005-internal-kb-content-leaked-to-end-user.md) — the defect this ADR resolves.
- [OQ-002](../../../product-backlog/open-questions/v1-open-questions.md) — billing proof threshold (still open, out of scope here).
