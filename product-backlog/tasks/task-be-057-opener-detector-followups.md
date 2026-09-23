# TASK-BE-057 — Problem-opener detector maintainability follow-ups (BUG-025)

**Type:** Backend / maintainability task · **Status:** 📋 Planned (non-blocking)
**Branch:** `task/TASK-BE-057-opener-detector-followups` (off `feat/restart-from-scratch`, when started)
**Related:** BUG-025 (vague opener → targeted clarify), ADR-0034 (three-band confidence), InputGuardrail

## Context

BUG-025 added `ProblemOpenerDetector` (deterministic redirect of a generic problem opener to a
targeted clarify) and shipped it to the pilot (`0.9.3-blf3`). The adversarial review (91/100, Pass)
raised two **non-blocking** maintainability findings, explicitly deferred to this ticket. Neither is
runtime-affecting on its own; they reduce future delivery friction and improve consistency.

## Scope

1. **Make the opener phrase sets configurable per deployment/language** (mirror the existing
   `voice-support.conversation.vague-markers` `@Value` pattern in `ConversationConfig`). Today the
   `ProblemOpenerDetector` patterns (problem words, help phrasings, bare topics, specific markers,
   billing topics, escalation-request bypass) are hardcoded. Externalise them so the opener nouns,
   billing-topic tokens and escalation-bypass phrases can be tuned without a rebuild — consistent
   with the project's env-tunable-guardrails philosophy (`VOICE_FAREWELL_*`, `vague-markers`).
2. **Extract a shared text normaliser.** `normalize()` (lower-case + NFD accent-fold +
   punctuation→space) is duplicated between `InputGuardrail` and `ProblemOpenerDetector`. Extract a
   small `TextNormalizer` domain util and have both depend on it (DRY; single source for the folding
   rule the guardrail matching relies on).

## Out Of Scope

- Any change to the opener → clarify behaviour or wording (that is BUG-025, already shipped).
- The BUG-024 output-grounding-gate reliability work (separate ticket).

## Acceptance

- [ ] Opener phrase sets (problem/help/bare-topic/specific-marker/billing-topic/escalation) are
      injectable via `@Value` (or a config record) with the current values as safe defaults; a
      deployment can override them via env without a code change.
- [ ] `normalize()` lives in one shared `TextNormalizer`; `InputGuardrail` and
      `ProblemOpenerDetector` both use it (no duplicated folding logic).
- [ ] Existing BUG-025 tests still pass unchanged (behaviour identical with default config);
      add a test proving an overridden phrase set changes detection.
- [ ] Classes stay within the size budget; no Spring annotations in the domain.
- [ ] Not runtime-behaviour-changing under default config → no new OpenTelemetry required (note it).

## Notes

- Keep the `reason=problem_opener` telemetry sub-tag (BUG-025) intact.
- Optionally fold the escalation-bypass phrase list into the same config surface as the
  reactive-escalation vocabulary if/when a deterministic user-initiated escalation trigger lands
  (ADR-0019 extension), to avoid two divergent lists.
