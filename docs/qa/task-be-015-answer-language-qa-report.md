# QA Functional And Latency Report — TASK-BE-015 (Answer Language Handling)

_Date: 2026-07-21 · Branch: `task/TASK-BE-015-answer-language` · Owner: QA_

## Executive Summary

- **Overall readiness:** GO for merge readiness on the backend answer-language behavior
  (FR/EN). All acceptance criteria are covered by automated, product-observable tests and
  pass. One **cross-component dependency remains open** (voice STT/TTS language selection on
  the spoken path) and is out of scope for this backend ticket.
- **Main blockers:** None for the backend behavior.
- **Residual risks:**
  - Voice path: STT/TTS must operate in the answered language so the customer *hears* the
    right language — a voice-runtime concern tracked as an open question, not validated here.
  - Answer *fidelity* when a French answer is grounded on English content (and vice-versa) is
    an LLM-quality dimension; it is not observable with a fake LLM and needs a small live run.

## Scope Tested

- **Story:** TASK-BE-015 — the assistant answers each turn in the language of that turn's
  question (FR/EN), consistently across grounded answers, insufficient-evidence fallback,
  off-topic refusal and human-escalation offer; configurable default (English, Eir pilot);
  per-turn decision with session stickiness.
- **Business rules covered:** BR1–BR7.
- **Channels:** channel-agnostic backend (sync answer path + streaming voice path).
- **Providers / fakes:** infra-free — real domain (`InputGuardrail`,
  `RetrievalConfidenceGuardrail`, `LanguageDetector`, `OutputGuardrail`, `AnswerLanguage`)
  driven with a **fake LLM generator** and a **fake retrieval port**; real
  `RetrievalGroundingService` + `AnswerService`. No DB/Ollama/Mistral needed.
- **Environment:** `mvn test` (JUnit 5 + Cucumber-JVM), macOS, no external services.

## Functional Results

Automated acceptance suite: `backend/src/test/resources/features/answer-language.feature`
(9 scenarios) + `AnswerLanguageSteps`. Product-observable design: a *grounded* turn is
"answered in X" when the assistant instructs the LLM in language X (`generator.lastLanguage`);
a *fallback/refusal* turn is asserted on the **deterministic message text** (detected language
+ escalation offer), so the checks are not tautological.

| Area | AC / BR | Status | Evidence |
|---|---|---|---|
| English question → English answer | AC1 / BR1 | ✅ Pass | `answer-language.feature` §1 |
| French question → French answer | AC2 / BR1 | ✅ Pass | `answer-language.feature` §2 |
| Customer language wins over content language (FR question, EN content) | AC5 / BR5 | ✅ Pass | `answer-language.feature` §3 |
| Insufficient-evidence fallback + escalation in customer language (EN) | AC3 / BR4·BR7 | ✅ Pass | `answer-language.feature` §4 |
| Insufficient-evidence fallback + escalation in customer language (FR) | AC3 / BR4·BR7 | ✅ Pass | `answer-language.feature` §5 |
| Off-topic refusal in customer language (EN) | AC4 / BR4·BR7 | ✅ Pass | `answer-language.feature` §6 |
| Off-topic refusal in customer language (FR) | AC4 / BR4·BR7 | ✅ Pass | `answer-language.feature` §7 |
| Ambiguous turn → deployment default (EN) | AC6 / BR2 | ✅ Pass | `answer-language.feature` §8 |
| Ambiguous follow-up → keeps current conversation language (FR) | AC6 / BR3 | ✅ Pass | `answer-language.feature` §9 |
| Extensible FR + EN (no flow rework to add a language) | BR6 | ✅ Pass (by design) | `AnswerLanguage` enum + `LanguageDetectorTest`; adding a language = new enum constant |

Supporting unit/component coverage (regression net):

| Area | Status | Evidence |
|---|---|---|
| Language detection heuristic (FR/EN, accents, English hint, tie → empty) | ✅ Pass | `AnswerLanguageTest` (6) |
| Per-turn decision + session stickiness + configurable default | ✅ Pass | `LanguageDetectorTest` (5) |
| Sync path threads the decided language to the LLM | ✅ Pass | `AnswerServiceTest` (8) |
| Streaming path threads the decided language to the LLM | ✅ Pass | `StreamingConversationServiceTest` (7) |
| Input guardrail canned wording in **English** (greeting/off-topic/unsafe) | ✅ Pass | `InputGuardrailTest` (27, incl. 4 new EN cases) |
| Output guardrail catches an **English** refusal hand-off (not only French) | ✅ Pass | `OutputGuardrailTest` (7) |
| Per-turn language observability — LLM path (`provider=<llm>`) | ✅ Pass | `AbstractChatClientAnswerAdapterTest` |
| Per-turn language observability — guardrail-fallback path (`provider=n/a`) | ✅ Pass | `AnswerServiceTest` / `StreamingConversationServiceTest` (fallback telemetry) |

**Suite result:** `mvn test` → **210 tests, 0 failures, 0 errors** (BDD suite 29 scenarios,
ArchUnit 16, all green). Infra-free.

## Latency Results

The language decision is a **deterministic, in-process regex marker-scoring step** on the
turn transcript (and, on ambiguity, on recent history). It performs **no I/O, no model call
and no network hop**, so it does not introduce a new external latency slice.

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| Language decision (`LanguageDetector.resolve`) | sub-ms | sub-ms | sub-ms | n/a | warm | In-process regex over a short string; folded into the backend-orchestration slice. Evidenced by the full 29-scenario BDD suite (each running detector + real grounding) executing in ~0.09 s total. |
| STT / LLM wording / TTS / channel ingress·egress | — | — | — | — | — | **Not measured in this functional run** — requires live Gradium/Mistral/Ollama providers. No regression expected: BE-015 adds no call on these slices, it only sets a prompt directive and the deterministic decision above. |

Conclusion: BE-015 does **not** materially affect `time_to_first_audio`. A live voice run
(next phase) should confirm the voice slices are unchanged and validate STT/TTS language.

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| `AnswerLanguage` (VO: detect + directive + hand-off markers) | ✅ | Deterministic FR/EN scoring; ambiguity returns empty so stickiness/default can decide; ArchUnit value-object rule satisfied (enum is implicitly final). | None |
| `LanguageDetector` (domain service) | ✅ | question → history stickiness → configurable default; single per-turn decision. | None |
| `AnswerService` / `StreamingConversationService` | ✅ | Decide language once per turn; thread to the LLM on the answerable path; record language (`provider=n/a`) on guardrail-fallback turns. | None |
| Guardrails (`InputGuardrail` / `GuardrailMessages` / `OutputGuardrail`) | ✅ | Canned wording localizes from the turn text via the shared detector; English refusal hand-off is now caught like French. | None |
| Observability (`BackendTelemetry.recordAnswerLanguage`) | ✅ | Per-turn counter `voice_support.answer_language{provider,language}` + `[LANGUAGE]` log with correlation id, on **both** LLM and fallback paths; no transcript/answer content logged. | Confirm metric/log surface in a live run |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Low | Answer *fidelity* of a FR answer grounded on EN content (and vice-versa) is not observable with a fake LLM. | Comprehension quality unproven (behavior/routing is proven). | QA (live run) |
| Medium (cross-team) | Voice STT/TTS language selection on the spoken path is unvalidated; a mismatch means the customer hears the wrong-language voice regardless of the text answer. | Voice UX correctness on the pilot. | Architecture / voice runtime |

## Open Questions

- **Product:** none — the 6 acceptance criteria are unambiguous and covered.
- **Architecture:** How does the chosen answer language propagate to STT/TTS on the voice
  path so the spoken reply matches? (Ticket open question — escalate to `software-architect`.)
- **Technical:** none blocking.

## Recommendation

- **Go / No-go:** **GO** for the backend behavior — merge-ready on functional grounds
  (pending the user's explicit merge request, per workflow).
- **Required before pilot (not before merge):**
  1. A short **live run** (real Mistral/Ollama + real corpus) to spot-check EN/FR answer
     fidelity across the language↔content mismatch.
  2. **Voice STT/TTS language** validation on the spoken path (Architecture / voice runtime).
