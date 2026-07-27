# BUG-005 — Internal agent-facing KB content (R6/ION, VAA) spoken to the end user on a vague, low-confidence turn

## Header

- **Bug ID:** BUG-005
- **Title:** On a low-information utterance ("vas-y"), retrieval surfaces internal agent-desk articles (R6/ION appointment tooling, VAA) and the LLM voices them to the end user; confidence drops to ≈0.52 but still PASSES the gate instead of asking to clarify
- **Status:** Fixed — pending QA live retest (implemented on `fix/BUG-005-internal-kb-content-leak`, Sprint 9)
- **Severity:** High
- **Priority:** P1
- **Detected by:** User validation (live WebRTC test)
- **Detected date:** 2026-07-23
- **Related user story:** US-042 (surfaced during live voice testing)
- **Related epic:** EPIC-005 (Answer engine / knowledge base)
- **Branch:** `fix/BUG-005-internal-kb-content-leak` (to be created)
- **Owner:** Backend developer

## Problem Statement

During a live billing conversation, a vague follow-up turn ("vas-y.") caused the bot to
answer with **internal, agent-facing content** — it described how to modify an appointment
in the operator's internal tooling (**"R6/ION"**, **"VAA" — Vérification d'Aptitude**), which
is meaningless and inappropriate for an end user. This is the **opposite** failure mode of
[BUG-003](BUG-003-kb-chunking-brittle-retrieval-handoff.md) / [BUG-004](BUG-004-llm-intermittent-handoff-despite-grounded-evidence.md)
(false low-confidence fallback on covered topics): here the pipeline **over-answers** with
wrong-audience material. Two distinct facets:

1. **KB audience governance:** the ingested CSV KB (`articles.csv` / `articles-fr.csv`) mixes
   customer-facing articles with **internal agent/back-office** procedures. Nothing prevents an
   internal article from being retrieved and voiced to a customer.
2. **Confidence policy on weak input:** on a low-information utterance the retrieval confidence
   dropped to **≈0.52** (from ≈0.76 on the previous, well-formed turn) yet still passed the gate
   (`grounded=true`). A weak/ambiguous turn should trigger a clarification prompt, not the
   voicing of a weakly-matched internal article.

## Environment

- **Environment:** local
- **Channel:** web voice (WebRTC, `stt_mode=streaming`, `tts_mode=streaming`), `--backend http`
- **Provider configuration:** LLM `mistral-small-latest` (`mistral-api`), embeddings Ollama
  `nomic-embed-text` (768d), Postgres pgvector (**10 163 chunks** from `articles.csv` +
  `articles-fr.csv`)
- **Build or commit:** `feat/restart-from-scratch`
- **Correlation ID:** `b4fa2735-af04-4ca7-9b25-9ac2abe9a73e` (conversation reused across turns)

## Reproduction Steps

1. Given the full live stack is up (Postgres+Ollama, Java backend on :8080 with the CSV KB
   synced, voice runtime on :8090 `--provider gradium --backend http`).
2. And a WebRTC session in which a first, well-formed billing question was answered normally
   (e.g. "Pourquoi ma facture a augmenté ce mois-ci ?", confidence ≈0.76).
3. When the customer then says a vague follow-up such as **"vas-y."** (no clear intent).
4. Then the bot answers with internal agent tooling content ("modifier un rendez-vous dans
   **R6/ION**… via le **VAA**…"), `grounded=true`, confidence ≈**0.52**, ~782 chars.

## Expected Result

- Internal / agent-only KB content is **never** surfaced to an end-user channel.
- On a low-information or ambiguous turn (weak retrieval confidence), the bot **asks the
  customer to clarify** (or offers a safe menu) instead of voicing a weakly-matched article.

## Actual Result

- The bot voiced an internal back-office procedure referencing internal tool names (R6/ION,
  VAA) that are irrelevant and confusing for a customer, with a low-but-passing confidence.

## Evidence

- Logs (voice runtime `[TURN]`): `cid=b4fa2735… transcript='vas-y.' -> outcome=success answer="Je vois que vous souhaitez modifier un rendez-vous dans R6/ION… via le **VAA** (Vérification d'Apt…"`
- Backend `[CONVERSE]`: `correlation_id=b4fa2735… grounded=true confidence=0.5213 chars=782 duration_ms=1874`
- Contrast (previous turn, same session): `grounded=true confidence=0.7592 chars=569` (legitimate billing answer).

## Impact

- **Customer impact:** confusing, off-topic answer; erodes trust in the assistant.
- **Security/privacy/operational impact:** leaks internal tooling names and back-office
  procedures (R6/ION, VAA) to an external end user — an information-exposure concern.
- **Pilot-readiness impact:** wrong-audience content is a blocker for exposing the CSV KB to
  real customers; the KB needs an audience boundary before pilot.

## Acceptance Criteria For Fix

- [x] Internal / agent-only KB content cannot be retrieved or voiced on an end-user channel
      (`audience` tag at ingestion — customer vs internal — with the customer runtime
      fail-closed filtering to `audience == customer`, AND-combined with the `domain` filter).
- [x] On a weak/ambiguous turn (low retrieval confidence), the bot asks for clarification
      instead of voicing a weakly-matched article (three-band confidence policy +
      [TASK-WEB-012](../tasks/web-voice-tasks.md) / RF-022).
- [x] The defect no longer reproduces on the "vas-y" follow-up (and similar low-info turns) —
      covered by unit + BDD tests; **live voice retest pending** (see QA Retest).
- [x] A regression test covers both facets (internal content not retrievable for a customer
      channel; low-confidence/vague turn → clarification).
- [x] Relevant OpenTelemetry traces, metrics and structured logs are present (guardrail-block
      counter per verdict/channel; internal-audience ingestion audit log).
- [x] Adversarial code review is at least 90% satisfied (92/100, Pass).
- [ ] QA retest passes (backend-only reproduction + live voice).
- [x] Related documentation / backlog notes updated (ADR-0034, sprint-9, backlog-index, OQ).

## Developer Notes

- **root cause:** two independent gaps. (1) The CSV corpus (ADR-0030) mixes customer-facing and
  internal agent-desk articles with **no audience column**, and the vector search filtered only by
  `domain` — so an internal article (R6/ION, VAA) was retrievable on a customer turn. (2) The
  post-retrieval guardrail was a single pass/fail threshold (0.5): a middle-confidence match
  (≈0.52) passed and was voiced. A contentless continuer ("vas-y") also went straight to retrieval.
- **fix (2 facets):**
  - **Audience boundary:** new `AudienceClassifierPort` + deterministic `KeywordAudienceClassifierAdapter`
    (lowercase + accent-fold, word-boundary acronyms) tags each `SourceDocument` `audience`
    (`customer` default / `internal`) at ingestion; `PgVectorStoreAdapter` stores it in JSONB
    metadata and its search is **fail-closed** on `audience == customer` (AND domain).
  - **Weak-confidence clarify:** `RetrievalConfidenceGuardrail` now three-band (floor 0.5 → advisor
    hand-off; floor→clarify-ceiling 0.62 → `CLARIFY`; ≥ ceiling → answer). `InputGuardrail` detects
    vague/low-info turns (≤3 continuer tokens) pre-retrieval → `CLARIFY`. New `GuardrailDecision.CLARIFY`
    verdict + fr/en clarify wording. Python client-side floor made env-tunable (RF-022,
    `VOICE_BACKEND_CONFIDENCE_THRESHOLD`).
- **files changed:** `AudienceClassifierPort`, `KeywordAudienceClassifierAdapter`, `SourceDocument`,
  `CsvArticleConnector`, `PgVectorStoreAdapter`, `KnowledgeConfig`, `GuardrailDecision`,
  `GuardrailMessages`, `RetrievalConfidenceGuardrail`, `InputGuardrail`, `ConversationConfig`,
  `AnswerService`, `StreamingConversationService`, `BackendTelemetry`, `application.yml`,
  `voice_pipeline/answer.py`; tests + BDD features; ADR-0034.
- **tests added/updated:** `KeywordAudienceClassifierAdapterTest`, `PgVectorStoreAdapterTest`,
  `InputGuardrailTest` (vague), `RetrievalConfidenceGuardrailTest` (bands), `BackendTelemetryTest`
  (guardrail counter), `CsvArticleConnectorTest` (audience), 2 BDD scenarios (grounding), 3
  language BDD scenarios adjusted, `test_answer_processor.py` (RF-022 boundaries). Java 262 /
  Python 353 + behave 27 green.
- **OpenTelemetry added/updated:** `voice_support.guardrail_block` counter (tags: verdict, channel)
  + `[GUARDRAIL]` structured log in both sync and streaming pipelines; `[KB-SYNC] audience=internal`
  ingestion audit log for the excluded partition.
- **residual risk:** the retrieval filter is **fail-closed** on a metadata field legacy chunks lack,
  so **deploying without a full KB re-sync empties the customer KB** (every chunk lacks `audience`
  → 0 results → everything degrades to hand-off). Mitigation: the KB re-sync (`POST /api/knowledge/sync`)
  is a mandatory release step; documented in ADR-0034, `CLAUDE.md` and `application.yml`.

## QA Retest

- **Retested by:**
- **Retest date:**
- **Scenarios rerun:**
- **Result:** Passed / Failed / Reopened
- **Retest evidence:**

## Closure

- **Closed by:**
- **Closed date:**
- **Closure reason:** Fixed / Duplicate / Not reproducible / Accepted risk / Out of scope

## Related

- **[BUG-003](BUG-003-kb-chunking-brittle-retrieval-handoff.md) / [BUG-004](BUG-004-llm-intermittent-handoff-despite-grounded-evidence.md):** opposite failure mode (false fallback / false refusal on covered topics). BUG-005 is over-answering with wrong-audience content.
- **TASK-BE-013 (embedding `DomainClassifier`, Sprint 8):** the audience boundary may extend the classifier (customer vs internal) at ingestion.
- **[TASK-WEB-012](../tasks/web-voice-tasks.md) (confidence policy):** the weak-confidence-→-clarify behavior belongs to that policy.
