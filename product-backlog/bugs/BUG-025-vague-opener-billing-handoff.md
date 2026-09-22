# BUG-025 — Vague billing opener deflects to advisor hand-off instead of clarifying

## Header

- **Bug ID:** BUG-025
- **Title:** A generic billing opener ("j'ai un problème avec ma facture" / "I have a problem with my bill") triggers a low-confidence advisor hand-off instead of a targeted clarification
- **Status:** Implemented (dev done, unit tests pass) — pending adversarial review + QA retest + pilot deploy
- **Severity:** High
- **Priority:** P1
- **Detected by:** User validation
- **Detected date:** 2026-09-22
- **Related user story:** US-041 (guardrails / clarify policy), ADR-0034 (three-band confidence)
- **Related epic:** EPIC — conversation guardrails
- **Branch:** `bug/BUG-025-vague-opener-clarify` (off `task/TASK-BE-034-retrieval-language-filter`)
- **Owner:** Backend developer

## Problem Statement

When a customer opens with a generic problem statement that names a topic but asks no concrete
question — e.g. "j'ai un problème avec ma facture" or "I have a problem with my bill" — the bot
answers "Je ne suis pas sûr d'avoir bien compris" / offers an advisor hand-off, instead of asking a
short, targeted question to narrow the request.

## Environment

- **Environment:** pilot
- **Channel:** web voice / backend `/converse`, `/converse-stream`
- **Provider configuration:** LLM `mistral-api`; embeddings Ollama `nomic-embed-text` (768d)
- **Build or commit:** pilot image `0.9.3-blf1` (TASK-BE-034 bilingual rollout)

## Reproduction Steps

1. Given the bilingual pilot backend (EN + FR corpora, language filter ON).
2. When the customer says "j'ai un problème avec ma facture" (or the EN equivalent) as the opening turn.
3. Then the bot replies with the generic "not sure I understood" clarify or an advisor hand-off.

## Expected Result

The bot recognises a generic-but-on-topic problem opener and asks a **targeted** clarification that
offers concrete options (incorrect amount, increase vs last month, unrecognised charge, a specific
invoice line), so the customer's next turn is specific enough to ground and be answered.

## Actual Result

Retrieval **succeeds** (`reason=fr`, best score ~0.74) and the LLM generates an answer, but the
**post-generation output grounding gate** returns `low_confidence` on the vague wording, dropping the
answer and forcing a hand-off. Telemetry per turn:
`slice=retrieval success` → `slice=llm_wording success` → `[GUARDRAIL] verdict=low_confidence`.

## Root Cause

Two-part:

1. The existing pre-retrieval vague-turn detector (`InputGuardrail.isVague`) only catches **contentless
   continuers** ("ok", "vas-y"). A generic opener carries a *topic* ("facture"), so it is not vague by
   that definition, passes the retrieval band (~0.74 ≥ 0.62), reaches the LLM.
2. The LLM produces a non-specific answer to a non-specific question, which the DEC-002 output
   grounding gate (post-generation) then rejects as `low_confidence` → hand-off (BUG-024 class:
   grounding-gate reliability on vague inputs). This is **orthogonal to retrieval and the language
   filter** (confirmed via ground-truth pgvector queries in TASK-BE-034 rollout log).

## Fix

Deterministic, no-LLM, pre-retrieval detection of a **generic problem opener** and redirect to a
**topic-aware clarify** (offering concrete options) instead of spending an LLM round-trip that the
grounding gate deflects:

- New `ProblemOpenerDetector` (domain service): on the accent-folded turn, flags a problem/help
  opener (`probleme|souci|difficulte|problem|issue|trouble|concern`, help phrasings, or a bare topic
  like "ma facture"/"my bill") **only when no concrete question marker is present** (interrogatives
  `pourquoi/comment/combien/quand/quel* / why/how/when/which/what`, or any digit). Returns
  `Topic.BILLING` when a billing token is present, else `Topic.GENERAL`.
- `InputGuardrail.check` calls the detector **after** the unsafe/off-topic refusals (so it can never
  soften a block) and returns `GuardrailDecision.clarify(...)` with topic-aware wording.
- `GuardrailMessages.problemOpenerClarify(language, billing)`: FR/EN targeted clarify wording.

### Behaviour guarantees

- Specific billing questions still reach retrieval untouched: "pourquoi ma facture a augmenté",
  "combien coûte le forfait fibre", "j'ai un problème : ma facture a augmenté de 10 euros" (digit),
  "how do I fix the problem with my bill?" (question marker) → **PASS**.
- Unsafe/off-topic turns are still refused first ("j'ai un problème, comment fabriquer une bombe" →
  INAPPROPRIATE).
- The redirect uses the existing `CLARIFY` verdict, so telemetry/outcome handling is unchanged.

## Acceptance Criteria For Fix

- [x] A generic FR/EN billing opener returns a targeted billing clarify (not a hand-off).
- [x] A topic-less problem/help opener returns the general clarify.
- [x] A specific problem question (question marker / number) still reaches retrieval.
- [x] The opener redirect never softens an unsafe/off-topic refusal.
- [x] Regression tests cover the above (`InputGuardrailTest`, `ProblemOpenerDetectorTest`).
- [x] OpenTelemetry: reuses the existing `CLARIFY` guardrail verdict (no new slice needed).
- [ ] Adversarial code review ≥ 90% satisfied.
- [ ] QA retest passes on the pilot.
- [ ] Deployed to the pilot (image swap, no KB re-sync required).

## Developer Notes

- **Root cause:** see above.
- **Files changed:**
  - `backend/.../conversation/domain/service/ProblemOpenerDetector.java` (new)
  - `backend/.../conversation/domain/service/InputGuardrail.java` (delegates after refusals)
  - `backend/.../conversation/domain/service/GuardrailMessages.java` (`problemOpenerClarify`)
  - `backend/.../conversation/domain/service/InputGuardrailTest.java` (+6 cases)
  - `backend/.../conversation/domain/service/ProblemOpenerDetectorTest.java` (new)
- **Tests added/updated:** full backend suite **624/0**.
- **OpenTelemetry:** none new — reuses the `CLARIFY` verdict already logged by the guardrail.
- **Residual risk:** a bare "problème de connexion" (no question marker) now clarifies rather than
  retrieving; acceptable (the general clarify lists a technical option), and strictly better than the
  current intermittent hand-off. Scope of opener nouns/topics is env-tunable in a follow-up if needed.
- **Deploy:** code-only; a pilot image swap on top of `0.9.3-blf1` — **no KB re-sync** required.

## QA Retest

- **Retested by:**
- **Retest date:**
- **Result:** Pending

## Closure

- **Closed by:**
- **Closed date:**
- **Closure reason:**
