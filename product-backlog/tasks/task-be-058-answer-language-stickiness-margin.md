# TASK-BE-058 — Auto-mode answer-language stickiness margin (BUG-026 secondary)

**Type:** Backend / runtime task · **Status:** 📋 Planned (non-blocking)
**Branch:** `task/TASK-BE-058-answer-language-stickiness-margin` (off `feat/restart-from-scratch`, when started)
**Related:** BUG-026 (UI language selector session lock — primary fix shipped), US-042, ADR-0031 (answer language handling), TASK-BE-015

## Context

BUG-026 shipped the **primary** fix: the web-voice UI language selector now locks the answer
language for the whole session (`?language=` → per-session envelope → backend `forcedCode`). That
covers the product requirement "be able to fix the session language".

The **secondary** root cause identified in BUG-026 is a separate, pre-existing design weakness in
the backend and was explicitly deferred here: in **auto** mode (no forced language) the answer
language can still oscillate turn by turn.

Why it oscillates (confirmed in code):

```
LanguageDetector.resolve(question, history, forcedCode):
    return AnswerLanguage.detect(question)      // per-turn detection
            .or(() -> stickyLanguage(history))   // stickiness ONLY consulted when detect() is empty
            .orElse(defaultLanguage);
```

`AnswerLanguage.detect` scores French vs English markers and gives French **+1 for any accented
character** (`FRENCH_ACCENTS`). Stickiness is consulted **only on an exact tie** (`detect` returns
empty). So a single stray French marker or one accented character in an otherwise-English turn tips
`french > english`, `detect` returns a non-empty (wrong) verdict, and stickiness never runs → the
session flips language for that turn (observed live: conv `a3667221`, flip turn had
`history_chars=1169` yet resolved `fr`).

## Scope

Strengthen the **auto-mode** decision so an established conversation language is kept unless the
current turn clearly detects the *other* language, without regressing legitimate mid-conversation
language switches or the forced-language (US-042) path.

Candidate levers (pick the smallest that passes the tests; keep the heuristic deterministic and
no-LLM per ADR-0031):

1. **Stickiness margin.** When history has an established language `L`, keep `L` unless the current
   turn detects the other language with a **margin** (e.g. `other - L >= MARGIN` distinct markers),
   instead of flipping on any `>` difference. A lone marker/accent no longer flips the session.
2. **Attenuate the lone-accent signal.** The `+1` accent bonus should not by itself outvote an
   otherwise-English marker count (e.g. require an accent AND ≥1 French marker, or weight it below a
   marker). Accented characters occur in names/imports and in STT artifacts.
3. Make the margin env-tunable (mirror the project's env-tunable philosophy) with a safe default.

Keep the ordering intent: an explicit `forcedCode` (US-042) always wins; a genuinely bilingual/clear
switch is still honoured.

## Out Of Scope

- The BUG-026 primary WS session-lock fix (already shipped on `fix/BUG-026-...`).
- Any UI change or new backend endpoint.
- A runtime query-domain classifier (OQ-008) — unrelated.

## Acceptance

- [ ] In auto mode, given an established English conversation history, a short English turn that
      contains a single French marker or one accented character still resolves **English** (no flip).
      Symmetric FR case covered.
- [ ] A genuine, clear language switch mid-conversation is still honoured (the customer switching to
      the other language for a full, unambiguous turn changes the answer language).
- [ ] The `forcedCode` (US-042) path is unchanged — an explicit UI selection always wins over both
      detection and stickiness.
- [ ] Margin/attenuation is deterministic and (if introduced as config) env-tunable with a safe
      default; documented in ADR-0031.
- [ ] `LanguageDetectorTest` + `AnswerLanguageTest` cover the margin/accent cases (GIVEN/WHEN/THEN,
      manual fakes, no Mockito); existing language tests still pass unchanged on default config.
- [ ] `[LANGUAGE]` telemetry unchanged in shape; a forced/auto session shows a single stable
      language across turns on covered inputs.
- [ ] Adversarial code review ≥ 90%; QA retest on the pilot (an auto-mode EN session stays EN).

## Notes

- Files: `backend/.../conversation/domain/service/LanguageDetector.java` (stickiness margin),
  `backend/.../conversation/domain/model/valueobject/AnswerLanguage.java` (`detect`/accent weight),
  tests `LanguageDetectorTest` + `AnswerLanguageTest` (+ `AnswerLanguageSteps` if a scenario is added).
- Pure domain (no Spring annotations); wire any new config through `DomainServiceConfig` +
  `application.yml`.
