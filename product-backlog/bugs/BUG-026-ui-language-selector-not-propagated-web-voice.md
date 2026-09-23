# Bug Ticket

## Header

- **Bug ID:** BUG-026
- **Title:** UI language selector is not propagated on the web-voice WS path → the answer language auto-detects and oscillates per turn (no session language lock)
- **Status:** In Progress (primary fix implemented — pending pilot QA)
- **Severity:** High
- **Priority:** P2
- **Detected by:** User validation (remote pilot test) + developer log analysis
- **Detected date:** 2026-09-23
- **Related user story:** US-042 (UI-forced answer language) / TASK-BE-015 (answer-language handling)
- **Related epic:** EPIC-005 (answer engine) / EPIC-006 (voice runtime) / EPIC-012 (pilot)
- **Branch:** `fix/BUG-026-ui-language-selector-web-voice`
- **Owner:** Voice runtime developer (primary) + backend developer (session-lock design)

## Problem Statement

On the web-voice (WebSocket streaming) path, the customer speaks one language but the
bot answers in the **other** language on some turns and back again — the answer language
**oscillates turn by turn** within a single conversation. The UI language selector does
**not** lock the session language: the customer's choice never reaches the backend, so the
backend falls back to **per-turn auto-detection** (ADR-0031), which flip-flops on short or
STT-noisy utterances. There is no way to fix (lock) the language for the whole session.

## Environment

- **Environment:** pilot (eir-ai4cc-tst), backend `voice-support-backend` on t03 + t04 (behind the backend VIP, HAProxy round-robin), voice bridge on t01/t02
- **Channel:** web voice (WebSocket streaming, `channel=web_voice`)
- **Provider configuration:** STT/TTS Gradium streaming, LLM `openai` (pilot), embedding Ollama; answer `CONVERSATION_DEFAULT_LANGUAGE=en`
- **Build or commit:** pilot backend running `feat/restart-from-scratch` line; voice bridge web-voice WS app
- **Correlation ID:** `a3667221-b160-4a4c-ba5a-20d32f927a92` (2026-09-23 ~09:03–09:04 UTC / ~11:03 local), conversation_id `bdbc0ba1-e469-486e-8133-b796e3a9d71e`

## Reproduction Steps

1. Given the web-voice UI connects the WS with a selected language (`?language=en`), and the
   backend api-key gate is open for the conversation.
2. When the customer holds an English conversation over several turns, some utterances being
   short or containing STT artifacts (accented characters, ambiguous tokens).
3. Then the bot answers in French on one or more turns and in English on others, and the UI
   language selection has no locking effect.

## Expected Result

- When the UI selects a language, **every turn of the session** answers in that language
  (session language lock). The selection wins over auto-detection and stickiness (US-042).
- When no language is forced (auto), the answer language stays **stable within a conversation**
  and does not oscillate per turn on covered inputs.

## Actual Result

Answer language decided **per turn** with no session lock. For conversation `a3667221`
the decision oscillated across turns (merged from t03 + t04):

| Time (UTC) | Node | Turn type | Language |
|---|---|---|---|
| 09:03:14 | t04 | clarify (guardrail) | **fr** |
| 09:03:19 | t03 | clarify `problem_opener` | **en** |
| 09:03:32 | t04 | grounded answer (openai) | **en** |
| 09:03:36 | t03 | clarify | **en** |
| 09:03:46 | t04 | low_confidence | **en** |
| 09:03:51 | t03 | grounded answer (413 chars, conf 0.73) | **fr** |
| 09:04:08 | t04 | grounded answer (openai) | **fr** |

The UI declared English (`declared_language: "en"`) but it was dropped
(`effective_language: "auto"`), so the backend never received a forced language.

## Evidence

- Voice-bridge WS telemetry (t02), session `a3667221`:
  `voice.ws.client_connected` → `{"declared_language": "en", "effective_language": "auto"}`
  (the client selected English but nothing was forced).
- Backend `[LANGUAGE]` telemetry (t03 + t04), same `correlation_id`: language values
  `fr, en, en, en, en, fr, fr` across the session's turns (see table above). The flip turn
  at 09:03:51 had `history_chars=1169` (history present) yet still resolved `fr`, proving
  session stickiness was bypassed because `AnswerLanguage.detect(question)` returned a
  non-empty French verdict.
- The literal transcripts are **not logged** (privacy): backend logs only char counts;
  `stt.transcript.final` logs timing/outcome, no text. The exact French-scoring tokens per
  turn are therefore not recoverable from current logs.

## Root Cause (confirmed in code)

Two layers:

1. **Wiring gap (primary, this bug).** The web-voice WS handler builds the turn envelope from
   the **server** `default_language` and only records the client's selection for telemetry —
   it never wires the client's `?language=` into the envelope:

   ```
   voice-agent/web_voice/websocket_app.py:493
       envelope = ChannelEnvelope.for_web_turn(language=default_language)   # server default (unset → auto)
   voice-agent/web_voice/websocket_app.py:507
       declared_language=(request.query.get("language") or "")             # client choice read for telemetry only, then dropped
   ```

   Downstream is correct: `envelope.language` → `http_backend.py` sends `body["language"]`
   only when set (US-042) → backend `LanguageDetector.resolve(question, history, forcedCode)`
   returns `fromCode(forcedCode)` when non-blank (wins over detection + stickiness). The break
   is only at the WS join: the client choice is never placed in the envelope.

2. **Auto-mode instability (secondary, design).** Even without a forced language,
   `LanguageDetector` applies session stickiness **only on an exact detection tie**
   (`detect(question).or(sticky).orElse(default)`). A single French marker/accent tips a short
   English utterance to `french > english`, so detection is non-empty and stickiness is never
   consulted → per-turn oscillation.

## Impact

- customer impact: the bot answers in the wrong language mid-conversation; the language
  selector appears broken (cosmetic only on web voice). Poor pilot demo experience.
- operational/pilot-readiness impact: undermines the language-selection feature (US-042) and
  the "answer in the customer's language, consistently" product rule (ADR-0031 BR3/BR4).
- side effect: `envelope.language` also drives the **per-language STT/TTS provider selection**
  (`session_factory.py`), so the same gap prevents per-language provider routing on web voice.
- security/privacy impact: none.

## Acceptance Criteria For Fix

- [x] **Session language lock via the UI selector (primary requirement).** When the web-voice
      UI selects a language, that language is applied to **every turn of the session**
      (envelope carries the client's `?language=`, forwarded to the backend `language` field,
      `forcedCode` wins). Implemented in code; end-to-end pilot verification (full EN, then full
      FR session) pending QA.
- [x] Targeted wiring fix in `voice-agent/web_voice/websocket_app.py`: build the envelope from
      the client selection, falling back to the server default only when the client sent none
      (`_resolve_session_language(request, default_language)`). `declared_language` and
      `effective_language` telemetry now agree when a supported language is selected.
- [x] Per-language STT/TTS provider selection (`session_factory.py`) receives the selected
      language (follows from the envelope fix — the same `envelope.language` drives it).
- [ ] **Auto-mode stability (secondary):** with no forced language, the answer language does
      not oscillate within a conversation on covered inputs — strengthen session stickiness so
      the established conversation language is kept unless the current turn detects the other
      language with a **margin** (not a lone marker/accent), and/or attenuate the single-accent
      signal. **Deferred to a follow-up** (see Developer Notes) — the primary lock ships here.
- [x] A regression test covers the failure: WS envelope carries the client language
      (`ResolveSessionLanguageTest` + updated lifecycle assertion in `test_websocket_app.py`);
      backend `LanguageDetector` already honours `forcedCode` (existing `LanguageDetectorTest`).
      Stickiness margin test to land with the deferred secondary.
- [x] Relevant OpenTelemetry present: `declared_language`/`effective_language` reflect the lock
      (the WS `client_connected`/`session_started` events read the now-locked `envelope.language`).
- [ ] Adversarial code review is at least 90% satisfied.
- [ ] QA retest passes (pilot web-voice session per language).
- [ ] Docs/backlog updated (ADR-0031 note on the session lock; US-042 wiring).

## Developer Notes

Developer fills this during resolution:

- root cause: web-voice WS envelope built from `default_language`, ignoring the client
  `?language=` (read for telemetry only); backend forced-language path itself is correct.
- fix implemented (primary): `voice-agent/web_voice/websocket_app.py`
  - added `SUPPORTED_ANSWER_LANGUAGES = frozenset({"fr", "en"})` and a pure helper
    `_resolve_session_language(request, default_language)` — returns the client `?language=`
    (case/whitespace-insensitive) when it is a supported code, else the server default (which
    may be `None` = keep auto-detection). An unsupported/junk code is ignored so it can never
    force a wrong language backend-side.
  - `_serve_connection` now builds the per-connection envelope from that resolved language:
    `ChannelEnvelope.for_web_turn(language=_resolve_session_language(request, default_language))`.
    The envelope is created **once per WS connection** and reused for every turn, so the
    selected language locks the **whole session** (US-042 `forcedCode` wins over detection +
    stickiness). The web client already sends `?language=` on connect (`static/ws.js`).
- tests added/updated (voice-agent, `tests/test_websocket_app.py`):
  - new `ResolveSessionLanguageTest` (6 cases): supported client selection wins over server
    default; case/whitespace-insensitive; unset → default; unsupported → default; no default +
    no selection → `None` (auto); supported set is `{fr, en}`.
  - updated the lifecycle test assertion: with server `default_language="fr"` and client
    `?language=en`, `effective_language` is now `"en"` (was `"fr"` — the assertion previously
    encoded the bug).
  - full suite green: `./.venv/bin/python -m unittest discover tests` → 721 tests OK.
- OpenTelemetry: no new spans/metrics needed; the existing WS `session_started` /
  `client_connected` events now report the locked `effective_language` (equals
  `declared_language` when a supported language is selected).
- deferred (secondary, follow-up ticket to open): auto-mode stickiness margin in
  `backend/.../conversation/domain/service/LanguageDetector.java` + `AnswerLanguage.detect`
  (keep established conversation language unless the current turn detects the other language
  with a margin; attenuate the lone-accent signal) with a `LanguageDetectorTest` margin case.
- residual risk: in **auto** mode (no UI selection) the per-turn oscillation described in the
  secondary root cause is not yet addressed. The primary requirement ("fix the session
  language via the UI") is met.

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
