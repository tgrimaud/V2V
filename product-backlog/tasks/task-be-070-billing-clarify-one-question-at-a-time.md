# TASK-BE-070 — Billing clarify increment D: broaden the opener detector + one question at a time

**Type:** Technical task (backend — conversation guardrails)
**Status:** 🟢 Open (2026-10-08) — not started. Increment **D** of US-043 (deliver first; low risk).
**Priority:** Medium
**Epic:** EPIC-005 (Answer engine / knowledge base)
**Delivers:** US-043 (first increment). Target increment C is **TASK-BE-071** (build on top of this).
**Related:** BUG-025 (`ProblemOpenerDetector` + `problemOpenerClarify`), DEC-002, ADR-0034,
TASK-BE-018 (concision budget), ADR-0019 (escalation).
**Surfaced by:** user feedback (2026-10-08) — the bot answers billing problems too directly and just
enumerates the bill; it should question a bit more to understand the problem first.

## Context

Billing problem turns are answered in a single RAG turn. The only existing clarify
(`ProblemOpenerDetector` + `InputGuardrail.problemOpenerDecision` + `GuardrailMessages.problemOpenerClarify`,
BUG-025) fires **only** on a fully vague opener with no concrete marker, and when it does it offers
four billing sub-types **in one breath** (not voice-friendly). As soon as a turn carries a marker
(`pourquoi/combien/why/how/…` or a digit) it bypasses the clarify and the LLM answers directly, pushed
toward a terse enumeration by the TASK-BE-018 concision directive.

Increment D is the smallest safe step: make the existing deterministic clarify a little smarter and
voice-friendly, **without** adding multi-turn state or LLM variance (that is increment C / TASK-BE-071).

## Scope & decision

**Backend (deterministic, no LLM):**
1. **One question at a time.** Change `GuardrailMessages.problemOpenerClarify` (billing variant) from a
   four-option single sentence to **one** short targeted question (voice-friendly, FR/EN), e.g. ask the
   broad nature first ("is it an amount that looks wrong, an increase, a charge you don't recognise, or
   a payment issue?") kept as a single clause, or a genuinely single-ask opener. Keep the general
   (non-billing) variant one-question too.
2. **Broaden the billing trigger (carefully).** Extend `ProblemOpenerDetector` so a **billing** turn
   that states a problem but is still under-specified reaches the clarify even when it carries a weak
   marker — while a **specific, answerable** billing question ("pourquoi ma facture a augmenté de 5 €",
   "combien coûte le forfait") still bypasses it and is answered. Precisely: only broaden the BILLING
   topic path; do not change the GENERAL path. Keep the escalation-request and specific-number guards.
3. **Keep the guardrail ladder order** (`InputGuardrail.check`): greeting → vague → too-short → unsafe →
   off-topic → problem-opener, so the broadened opener can never soften an unsafe/off-topic block or
   intercept an explicit advisor request (BR5).

**Observability (mandatory, runtime-affecting):**
- Reuse / extend the existing `problem_opener` clarify signal so a billing clarify is countable
  (clarify asked; topic=billing). Record it on the backend telemetry already used by the guardrail
  path so QA can measure trigger frequency (US-043 analytics).

**Out of scope (→ TASK-BE-071 / increment C):**
- Multi-turn clarifying dialogue / clarify counter / slot state across turns.
- Any LLM-driven follow-up wording.
- The system-prompt "clarify-first" directive.

## Acceptance criteria

- An under-specified billing problem (vague opener, or opener with only a weak marker) produces a
  **single** short clarifying question (FR/EN per session language), not a four-option list and not a
  bill enumeration.
- A specific, answerable billing question is still answered directly (no spurious clarify) — locked by
  a regression test (the BUG-025 "specific marker bypasses clarify" invariant must still hold).
- An explicit advisor request, an off-topic or unsafe turn are not intercepted by the broadened trigger
  (ladder order preserved) — covered by tests.
- The clarify never contains an amount/price (DEC-002) — the message is canned, so this holds by
  construction; add an assertion.
- Backend `mvn test` green incl. ArchUnit; new/updated unit tests for `ProblemOpenerDetector` (broadened
  billing cases + preserved bypass) and `GuardrailMessages`/`InputGuardrail` (one-question wording,
  ladder order). Manual fakes, GIVEN/WHEN/THEN, no Mockito.
- Clarify telemetry present and asserted.

## Risks / open questions

- OQ: exact broadened billing trigger must not swallow answerable questions — tune the regex against a
  table of example turns and lock both directions with tests. (Decision: keep the specific-marker guard;
  only widen the "bare/weak billing opener" set.)
- OQ-043-a (max questions) is **not** needed for D (single clarify, no counter) but is for C.
