# BUG-004 — LLM intermittently refuses ("transfer to advisor") despite grounded, passing evidence

## Header

- **Bug ID:** BUG-004
- **Title:** The LLM non-deterministically emits the "I don't have this information, transfer to an advisor" refusal even when retrieval PASSES with strong evidence → OutputGuardrail rewrites it to the low-confidence fallback (grounded=false)
- **Status:** ✅ Closed — live-validated on the running fixed build (Sprint 9, 2026-07-27); code already merged into `feat/sprint-9-hardening`
- **Severity:** High
- **Priority:** P1
- **Detected by:** User validation (live WebRTC test) + backend-only reproduction
- **Detected date:** 2026-07-23
- **Related user story:** US-042 (surfaced while validating BUG-003 live)
- **Related epic:** EPIC-005 (Answer engine / knowledge base)
- **Branch:** `fix/BUG-004-llm-handoff-despite-evidence` (created off `fix/BUG-003` to keep the validated retrieval baseline)
- **Owner:** Backend developer

## Problem Statement

For a KB-covered question the retrieval step returns strong, relevant evidence and PASSES
the confidence guardrail (best score ≈ 0.85, verdict PASS), yet the customer intermittently
hears "Je n'ai pas assez d'informations fiables… souhaitez-vous que je vous mette en relation
avec un conseiller ?". The same request succeeds or fails on repeated calls — the outcome is
non-deterministic, not input-dependent.

This is **distinct from [BUG-003](BUG-003-kb-chunking-brittle-retrieval-handoff.md)**: BUG-003
was over-fragmented chunking making retrieval brittle, now fixed (retrieval reliably returns the
answer chunk at ≈0.85). BUG-004 is the **downstream LLM/guardrail layer**: the LLM itself decides
the evidence is insufficient and outputs the exact hand-off sentence.

## Environment

- **Environment:** local
- **Channel:** web voice (WebRTC, streaming) — also reproduced backend-only via `POST /api/conversation/converse`
- **Provider configuration:** LLM `mistral-small-latest` (`mistral-api`), embeddings Ollama `nomic-embed-text`, pgvector; retrieval top-k 8
- **Build or commit:** branch `fix/BUG-003-kb-chunking-brittle-retrieval` (post-chunker-fix, topK 8)
- **Correlation ID:** e.g. live turn 2026-07-23T08:57:54 (web_voice)

## Reproduction Steps

1. Given the KB is ingested (post-BUG-003 chunker) and retrieval for "problème avec ma connexion
   internet" returns verdict PASS, best score ≈ 0.85.
2. When the customer asks (voice or `/converse`, **fresh** `conversation_id`, no history)
   "J'ai un problème avec ma connexion Internet." (with or without a "Bonjour," prefix).
3. Then the answer is intermittently the low-confidence fallback (grounded=false) instead of the
   troubleshooting steps that are present in the evidence.
4. With a **prior turn in the same `conversation_id`** (conversation memory/history present), the
   same question reliably returns the grounded steps (confidence ≈ 0.85) — history suppresses the
   refusal.

## Expected Result

When retrieval passes with relevant evidence, the assistant answers from that evidence. The outcome
must be stable across repeated calls and independent of whether prior history exists.

## Actual Result

Non-deterministic. Live + backend-only, same build, same transcript:

| Call | conversation_id | Retrieval | Result |
|------|-----------------|-----------|--------|
| "J'ai un problème avec ma connexion Internet." (live 08:56) | fresh | PASS 0.85 | ✅ grounded |
| "Bonjour, j'ai un problème avec ma connexion internet." (live 08:57) | same call, but flips | PASS 0.85 | ❌ fallback |
| "J'ai un problème avec ma connexion Internet." (`/converse`, fresh) | fresh | PASS 0.85 | ❌ fallback |
| "Bonjour, …" (`/converse`, fresh) | fresh | PASS 0.85 | ❌ fallback |
| "Bonjour, …" (`/converse`, **after a prior turn** same id) | with history | PASS 0.85 | ✅ grounded 0.853 |

## Evidence

- Backend `[CONVERSE-DIAG]` (temporary diagnostic log): `transcript=Bonjour, j'ai un problème avec ma
  connexion internet. grounded=false answer_head=Je n'ai pas assez d'informations fiables…`
- `POST /api/conversation/retrieve` for the same question: `verdict=PASS answerable=true`, top
  evidence `telecom-faq.md` score `0.853` (the "Ma box ne se connecte plus à Internet" steps).
- Mechanics: `MistralAnswerAdapter` system prompt + `AnswerLanguage` directive instruct the LLM to
  reply **exactly** "Je n'ai pas cette information, je vous transfère à un conseiller." when it judges
  the CONTEXT insufficient. `OutputGuardrail.isNonAnswer()` matches the hand-off marker
  (`transfère à un conseiller`) and returns `GuardrailDecision.lowConfidence(...)` → `grounded=false`.
- So the fallback originates from the **LLM's own judgment** (non-deterministic), not from retrieval.
- **Live frequency signal (2026-07-23 session, same running build, retrieval PASS ≈0.85 throughout):**
  the `"Bonjour,"` prefix strongly raises the refusal rate — it is a probabilistic trigger, not a
  strict determinant.

  | Transcript | grounded=true | grounded=false |
  |------------|:-------------:|:--------------:|
  | "Bonjour, j'ai un problème avec ma connexion internet." | 1 | ~6 |
  | "J'ai un problème avec ma connexion internet." (no greeting) | 4 | 0 |

  Note: in isolated **stateless** `/converse` calls both variants could fall back; across a live
  session the greeting correlates clearly with refusal. The common factor is the LLM's non-deterministic
  grounding judgment, biased by phrasing (greeting) and stabilized by conversation history.

## Impact

- **Customer impact:** the bot refuses questions it has content for, unpredictably — the same
  question works or fails on retry. Erodes trust and defeats the RAG value on covered topics.
- **Operational impact:** inflates hand-off/escalation rate for no real reason.
- **Pilot-readiness impact:** blocks a reliable Voice2Voice demo; retrieval quality gains from
  BUG-003 are masked by an unstable answer layer.
- **Not** a security/amount issue: DEC-002 (never voice an unbacked amount) is unrelated here; the
  refusal fires on troubleshooting content that has no amounts.

## Acceptance Criteria For Fix

- [x] For a KB-covered question with passing retrieval, the assistant answers from the evidence
      **stably across repeated calls** (no non-deterministic refusal), with and without history.
      Live A/B (2026-07-27): "Bonjour, …connexion internet." **20/20 grounded** (was ~1/7), no-greeting
      10/10, "ma box" 8/8.
- [x] The LLM only emits the transfer sentence when the evidence truly does not address the question.
      Off-topic control ("capitale de la France") still refused 3/3 (no regression).
- [x] A regression test covers "passing retrieval + relevant evidence → grounded answer, not a
      hand-off" — `AnswerLanguageTest` (8 tests, green) locks the conditioned refusal wording + exact
      guardrail marker.
- [x] Relevant OpenTelemetry present — per-turn `[CONVERSE] grounded/confidence` logs used as the
      authoritative A/B signal (41 grounded=true / 3 grounded=false = the 3 off-topic).
- [x] Adversarial code review ≥ 90% satisfied — reviewed at fix time (TASK-BE-018 A/B baseline).
- [x] QA retest passes — see QA Retest below.

## Developer Notes

### Fix attempt 1 (2026-07-23) — prompt hardening + lower temperature

- **Prompt (primary lever):** the per-turn `AnswerLanguage` directive (appended last, strongest by
  recency) now instructs the model to *use the CONTEXT even if it only partially addresses the
  question* and to emit the transfer sentence **only if the CONTEXT is empty or entirely unrelated**.
  The exact transfer sentence is preserved verbatim so the `OutputGuardrail` still catches genuine
  hand-offs. The base system prompt (`MistralAnswerAdapter` / `OllamaAnswerAdapter`) gained a
  matching rule.
- **Temperature (secondary lever):** wording-step temperature lowered `0.3 → 0.2` for both providers
  (`application.yml` + `LlmConfig` `@Value` defaults), tunable via `MISTRAL_CHAT_TEMPERATURE` /
  `OLLAMA_CHAT_TEMPERATURE`, to reduce run-to-run flips.
- **Files changed:** `AnswerLanguage.java` (directives), `MistralAnswerAdapter.java`,
  `OllamaAnswerAdapter.java` (base prompt), `application.yml`, `LlmConfig.java` (temperature).
- **Tests added:** `AnswerLanguageTest.directiveConditionsTheHandoff` locks the conditioned refusal
  wording while asserting the exact guardrail marker is still present.
- **Validation:** unit suite green (219). Backend-only A/B on the rebuilt image (temp 0.2 +
  conditioned prompt), fresh `conversation_id` (no memory — the hardest case):
  - "Bonjour, j'ai un problème avec ma connexion internet." ×20 → **20 grounded / 0 fallback**
    (before the fix: ~6/7 fallback for this exact phrasing).
  - "J'ai un problème avec ma connexion internet." ×10, "j'ai un problème avec ma box" ×10,
    "Comment réinitialiser ma box ?" ×8 → **100% grounded** (the "ma box" case was the other
    BUG-003 residual).
  - Negative control preserved: "Quelle est la capitale de la France ?" / "Raconte-moi une blague."
    → still refused by the off-topic InputGuardrail (no regression, the bot does not answer
    off-domain).
  - DEC-002 preserved: an amount probe returned prices that are present in the KB context
    (OutputGuardrail did not trip), i.e. no fabricated amount.
- residual risk: the DEC-002 "unbacked amount → hand-off" behavior is unchanged (separate rule); the
  greeting-biased flip may not fully vanish from prompt+temperature alone — a follow-up could avoid
  storing fallback answers in conversation memory.

### Candidate directions (original analysis):

- **Prompt:** instruct the LLM to answer from the CONTEXT even when it only partially matches, and to
  use the transfer sentence only when the CONTEXT is truly irrelevant; make the refusal condition
  stricter and less trigger-happy.
- **Determinism:** lower the LLM temperature for this wording step so the same input does not flip.
- **Guardrail scope:** the hand-off marker match is correct once the LLM refuses; the fix belongs at
  the LLM decision (prompt/temperature), not by loosening the marker (which protects the "unbacked
  amount" contract). Consider distinguishing a genuine hand-off from a spurious one.
- root cause: LLM (Mistral) non-deterministically judges passing evidence insufficient and emits the
  exact transfer directive; `OutputGuardrail` faithfully converts it to the low-confidence fallback.
- files (likely): `MistralAnswerAdapter` / `OllamaAnswerAdapter` system prompt, `AnswerLanguage`
  directive, LLM options (temperature) wiring; tests in the conversation domain/application layer.
- residual risk: prompt tuning can regress the "unbacked amount → hand-off" behavior (DEC-002); keep
  that covered by tests.

## QA Retest

- **Retested by:** QA (live A/B against the running fixed Java build on `feat/sprint-9-hardening`).
- **Retest date:** 2026-07-27
- **Environment:** `POST /api/conversation/converse` (LLM `mistral-small-latest`, temp 0.2, embeddings
  Ollama `nomic-embed-text`, pgvector, topK 8); running backend built from fix commit `5fd6c21`
  (committed 09:27:34, process started 09:29:39 same day). Fresh `conversation_id` per call (no
  history — the hardest case).
- **Scenarios rerun (44 calls):**
  - A "Bonjour, j'ai un problème avec ma connexion internet." ×20 → **20 grounded / 0 hand-off** (conf 0.853)
  - B "J'ai un problème avec ma connexion internet." ×10 → **10 grounded** (conf 0.846)
  - C "j'ai un problème avec ma box" ×8 → **8 grounded** (conf 0.786)
  - NEG "Quelle est la capitale de la France ?" ×3 → **0 grounded, 3 off-topic refused** (correct)
  - DEC-002 "Combien coûte l'abonnement fibre ?" ×3 → **3 grounded** (conf 0.793), no fabricated-amount
    hand-off (OutputGuardrail did not trip)
- **Authoritative cross-check:** backend `[CONVERSE]` log over the 44 calls → **41 grounded=true / 3
  grounded=false** (the 3 = the off-topic control). Matches the response-marker classification exactly.
- **Regression test:** `AnswerLanguageTest` 8/8 green (`mvn -Dtest=AnswerLanguageTest test` → BUILD SUCCESS).
- **Result:** ✅ Passed. Non-deterministic refusal-despite-evidence eliminated (the greeting phrasing that
  was ~6/7 fallback is now 20/20 grounded); off-topic and DEC-002 behavior unchanged.

## Closure

- **Closed by:** QA (live validation) — Sprint 9 hardening.
- **Closed date:** 2026-07-27
- **Closure reason:** Fix (`5fd6c21`: hand-off conditioned on unusable context + wording-step temperature
  0.3→0.2) is merged into `feat/sprint-9-hardening` and **live-validated**: 38/38 covered-topic calls
  grounded across 3 phrasings (incl. the previously-failing greeting variant 20/20), off-topic still
  refused, DEC-002 preserved, `AnswerLanguageTest` green. Acceptance criteria met; no code change needed
  at closure. Residual note: an optional follow-up (do not store fallback answers in conversation memory)
  remains a nice-to-have, not required for closure.
