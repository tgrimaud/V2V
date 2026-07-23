# BUG-004 — LLM intermittently refuses ("transfer to advisor") despite grounded, passing evidence

## Header

- **Bug ID:** BUG-004
- **Title:** The LLM non-deterministically emits the "I don't have this information, transfer to an advisor" refusal even when retrieval PASSES with strong evidence → OutputGuardrail rewrites it to the low-confidence fallback (grounded=false)
- **Status:** New
- **Severity:** High
- **Priority:** P1
- **Detected by:** User validation (live WebRTC test) + backend-only reproduction
- **Detected date:** 2026-07-23
- **Related user story:** US-042 (surfaced while validating BUG-003 live)
- **Related epic:** EPIC-005 (Answer engine / knowledge base)
- **Branch:** `fix/BUG-004-llm-handoff-despite-evidence` (to create)
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

## Impact

- **Customer impact:** the bot refuses questions it has content for, unpredictably — the same
  question works or fails on retry. Erodes trust and defeats the RAG value on covered topics.
- **Operational impact:** inflates hand-off/escalation rate for no real reason.
- **Pilot-readiness impact:** blocks a reliable Voice2Voice demo; retrieval quality gains from
  BUG-003 are masked by an unstable answer layer.
- **Not** a security/amount issue: DEC-002 (never voice an unbacked amount) is unrelated here; the
  refusal fires on troubleshooting content that has no amounts.

## Acceptance Criteria For Fix

- [ ] For a KB-covered question with passing retrieval, the assistant answers from the evidence
      **stably across repeated calls** (no non-deterministic refusal), with and without history.
- [ ] The LLM only emits the transfer sentence when the evidence truly does not address the question.
- [ ] A regression test covers "passing retrieval + relevant evidence → grounded answer, not a
      hand-off" (ideally with a deterministic/fake generator, plus a guardrail-level test).
- [ ] Relevant OpenTelemetry (the existing per-turn grounded/confidence + language logs) still present.
- [ ] Adversarial code review ≥ 90% satisfied.
- [ ] QA retest passes.

## Developer Notes

Candidate directions (to validate, not yet decided):

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

- **Retested by:**
- **Retest date:**
- **Scenarios rerun:**
- **Result:**
- **Retest evidence:**

## Closure

- **Closed by:**
- **Closed date:**
- **Closure reason:**
