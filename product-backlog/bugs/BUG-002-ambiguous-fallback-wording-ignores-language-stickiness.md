# BUG-002 — Guardrail fallback wording ignores language stickiness / configurable default

## Header

- **Bug ID:** BUG-002
- **Title:** Ambiguous follow-up in a French conversation gets an English guardrail fallback message
- **Status:** ✅ Closed — validated by user + merged into `feat/restart-from-scratch` (2026-07-23, Sprint 8 closure); fix + adversarial review + live QA retest PASS
- **Severity:** Medium
- **Priority:** P2
- **Detected by:** QA (live run)
- **Detected date:** 2026-07-21
- **Related user story:** TASK-BE-015 (answer language handling)
- **Related epic:** EPIC-005 (Answer engine / knowledge base)
- **Branch:** `fix/BUG-002-fallback-language-stickiness`
- **Owner:** Backend developer

## Problem Statement

On an **ambiguous** turn (a question with no French/English markers, e.g. "ok", "oui",
"merci") inside an already-French conversation, the assistant **decides** the answer language
is French (session stickiness) and **records** it as French, but the **canned guardrail
fallback message it actually speaks is in English**. Every utterance of the turn should be in
the chosen language (BR4), keeping the current conversation language on ambiguity (BR3).

## Environment

- **Environment:** local
- **Channel:** backend-only (`POST /api/conversation/converse`), applies to every channel
- **Provider configuration:** LLM `mistral-api` (`mistral-small-latest`), embeddings Ollama
  `nomic-embed-text`; Postgres pgvector (5177 chunks: 5136 csv-article + 41 markdown)
- **Build or commit:** `task/TASK-BE-015-answer-language` @ `46c1155`
- **Correlation ID:** `L-STICK-2`

## Reproduction Steps

1. Given a conversation whose first turn is in French (e.g. "Pourquoi ma facture a-t-elle
   augmenté ce mois-ci ?") on a fixed `conversation_id`.
2. When the customer sends an ambiguous follow-up on the **same** `conversation_id`, e.g. "ok",
   that lands on a guardrail fallback (low-confidence / off-topic).
3. Then the spoken fallback message is returned in **English**, not French.

## Expected Result

The fallback message (insufficient-evidence / off-topic / escalation offer) is in **French**,
matching the current conversation language (BR3/BR4). More generally, the fallback wording must
follow the **same** per-turn language decision as the LLM answer path — including session
stickiness and the **configurable default** language (BR2).

## Actual Result

- Decided/recorded language: **French** — `[LANGUAGE] provider=n/a language=fr correlation_id=L-STICK-2`.
- Spoken fallback message: **English** — "I don't have enough reliable information to answer
  this question. Would you like me to connect you with a support agent?"

## Evidence

- Logs (`/tmp/be015-live.log`):
  - `[LANGUAGE] provider=mistral-api language=fr correlation_id=L-STICK-1` (French turn)
  - `[LANGUAGE] provider=n/a language=fr correlation_id=L-STICK-2` (ambiguous follow-up → decided FR)
- API response for `L-STICK-2`: English low-confidence message (see Actual Result).
- Control (no divergence): `L-AMBIG` ("ok", no prior context) → decided EN + English message
  (consistent, because the ambiguous default coincides with English).

## Root Cause (preliminary)

Two language decisions coexist and can disagree:

1. `LanguageDetector.resolve(question, history)` — used by the **LLM answer path** and the
   per-turn telemetry. Applies **session stickiness** and the **configurable default**.
2. `GuardrailMessages.isEnglish(text) = AnswerLanguage.detect(text, ENGLISH)` — used to render
   the **guardrail fallback wording** inside the grounding pipeline (`InputGuardrail`,
   `RetrievalConfidenceGuardrail`). It sees **only the current message** (no history → no
   stickiness) and hard-codes **English** as the ambiguous fallback (ignores the configured
   default). So on an ambiguous turn the canned wording diverges from the decided language.

This is the alternative ADR-0031 explicitly rejected ("thread the language through the
guardrails … no product gain"); the live run shows there **is** product loss on ambiguous
follow-ups, so the decision must be revisited.

## Impact

- **Customer impact:** a French customer who says "ok" (or any short ambiguous turn) hears an
  English canned message mid-French-conversation — confusing, erodes trust (the very failure
  TASK-BE-015 set out to fix, on the fallback path).
- **Configurable default impact:** a deployment configured with a non-English default
  (`voice-support.conversation.default-language=fr`) would still emit English canned wording on
  ambiguous turns.
- **Scope:** only ambiguous turns that reach a guardrail fallback; grounded answers and
  clear-language refusals are already correct (validated live). No security/SLO impact.

## Acceptance Criteria For Fix

- [x] An ambiguous follow-up in a French conversation returns the **French** fallback wording.
- [x] The fallback wording honors the **configurable default** language (non-EN deployments).
- [x] The fallback wording uses the **same** per-turn decision as the LLM path (single source
      of truth for the turn language).
- [x] A regression test covers ambiguous-follow-up stickiness on the fallback path (sync +
      streaming).
- [x] `[LANGUAGE]` telemetry and the returned message language always agree.
- [x] Adversarial code review ≥ 90 % (scored 94/100, QA gate Pass; dead-code remediation applied).
- [x] QA retest passes (unit + live). Unit + BDD (211 tests green incl. the BUG-002 scenario);
      **live retest passed** (real Mistral/Ollama + 5177-chunk corpus) — see QA Retest below.
- [x] ADR-0031 updated (reopen the "thread language into guardrails" alternative).

## Developer Notes

- root cause: see above (two divergent language decisions).
- suggested direction: render the fallback wording from the **already-decided**
  `AnswerLanguage` at the single decision point (application service) — re-localize the blocked
  decision's message by verdict in the decided language — or thread the decided language into
  the guardrail message factory. Keep one language decision per turn.
- files likely changed: `GuardrailMessages`, `AnswerService`, `StreamingConversationService`
  (and possibly the grounding pipeline / `GroundQueryUseCase` signature + fakes).

### Resolution (implemented)

Chose the **single-source-of-truth** direction (the ADR-0031 alternative): the per-turn
`AnswerLanguage` decided by `LanguageDetector` (question → stickiness → configurable default) is
now **threaded into every guardrail**, and `GuardrailMessages` no longer re-detects language
from the message text. There is now exactly **one** language decision per turn, reused by the
LLM answer, the telemetry, and every canned guardrail message.

- `GuardrailMessages`: all methods now take `AnswerLanguage` (removed per-message text detection
  and the hard-coded English default).
- `InputGuardrail.check(question, alreadyGreeted, language)`,
  `RetrievalConfidenceGuardrail.check(evidence, language)`,
  `OutputGuardrail.check(answer, evidence, language)` — language passed in; dead `question`
  params removed where they only fed detection.
- `GroundQueryUseCase.ground(..., language)` / `RetrievalGroundingService` forward the language.
- `GuardedSentenceEmitter(evidence, guardrail, onChunk, confidence, language)` — streamed
  fallback wording now uses the decided language (fixes the streamed path too).
- `AnswerService` / `StreamingConversationService` already resolved the language before grounding;
  they now pass it through. `RetrievalController` resolves via `LanguageDetector` (no history).
- Fakes/tests updated (`FakeGroundQueryUseCase`, guardrail tests, controller `@WebMvcTest`
  configs given a `LanguageDetector` bean).

### Tests added

- BDD regression (`answer-language.feature`): *"An ambiguous follow-up keeps the language on a
  fallback turn (BUG-002)"* — French history + ambiguous "ok" + insufficient evidence → **French**
  spoken fallback + human-advisor offer. Fails on the old code (English), passes on the fix.
- Unit regression (`InputGuardrailTest.wordingFollowsDecidedLanguageNotInput`): the canned
  wording follows the DECIDED language, not the input text.
- Full suite: **212 tests green** (`mvn -o test`).

## QA Retest

- **Retested by:** QA (live run)
- **Retest date:** 2026-07-22
- **Environment:** local — backend `spring-boot:run` @ `fix/BUG-002-fallback-language-stickiness`
  (`732cc82`), LLM `mistral-api` (`mistral-small-latest`), embeddings Ollama `nomic-embed-text`,
  Postgres pgvector (5177 chunks), endpoint `POST /api/conversation/converse`.
- **Scenarios rerun (decisive contrast — identical transcript "ok"):**

  | Correlation id | Turn | History | Decided lang | Spoken reply | ✓ |
  |---|---|---|---|---|---|
  | `L-STICK-FR2` | "ok" | French convo (same `conversation_id`) | fr | "Je n'ai pas assez d'informations fiables… **un conseiller** ?" | ✅ (was EN before fix) |
  | `L-AMBIG` | "ok" | none (fresh) | en | "I don't have enough reliable information… **a support agent**?" | ✅ control |
  | `L-OT-FR` | "Quel temps fera-t-il demain ?" | none | fr | French off-topic refusal | ✅ |
  | `L-OT-EN` | "What's the weather like today?" | none | en | English off-topic refusal | ✅ |
  | `L-EN-GRD` | "How can I reset my router password?" | none | en | grounded English answer (conf 0.71) | ✅ grounded path intact |

- **Result:** **PASS.** The same ambiguous transcript "ok" returns **French** wording inside a
  French conversation (stickiness) and **English** with no history (configurable default) — the
  exact divergence BUG-002 reported is gone. `[LANGUAGE]` telemetry matches the spoken language on
  every turn (`L-STICK-FR2` → `provider=n/a language=fr`; `L-AMBIG` → `provider=n/a language=en`).
- **Latency (indicative):** fallback turns 0–90 ms (no LLM); grounded EN turn ~1090 ms
  (`llm_wording` 1011 ms). No regression.
- **Retest evidence:** `/tmp/be002-live.log` (`[LANGUAGE]` + `[CONVERSE]` lines per correlation id).

## Closure

- **Closed by:** pending user validation (final validator; merge on explicit request)
- **Closed date:**
- **Closure reason:** Fix implemented, adversarial review 94/100, unit+BDD green (211), live QA
  retest PASS. Ready to merge on the user's go.
