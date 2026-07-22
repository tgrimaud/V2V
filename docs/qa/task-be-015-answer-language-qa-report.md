# QA Functional And Latency Report — TASK-BE-015 (Answer Language Handling)

_Date: 2026-07-21 · Branch: `task/TASK-BE-015-answer-language` · Owner: QA_

## Executive Summary

- **Overall readiness:** **CONDITIONAL** — the automated suite passes and the live run
  (real Mistral + Ollama + corpus) confirms correct FR/EN behavior on all clear-language
  turns and per-turn telemetry, **but the live run surfaced one Medium functional defect**
  (`BUG-002`): on an **ambiguous** follow-up inside an established French conversation, the
  turn language is *decided* and *recorded* as French (stickiness) yet the guardrail
  **fallback wording is spoken in English**. This violates BR3/BR4 on the fallback path.
- **Main blockers:** `BUG-002` (Medium) must be fixed for full BR2/BR3/BR4 compliance before
  the ticket is merge-ready. Grounded answers and clear-language refusals are already correct.
- **Residual risks:**
  - Voice path: STT/TTS must operate in the answered language so the customer *hears* the
    right language — a voice-runtime concern tracked as an open question, not validated here.
  - Answer *fidelity* on the FR↔EN content mismatch: validated live (fluent, consistent
    answers) — see Live Run Results.
  - Retrieval-confidence asymmetry between the English CSV corpus and the French markdown KB
    (an English billing phrasing fell to a low-confidence fallback while its French counterpart
    grounded) — a **retrieval/KB** observation, not a language defect; owner = KB/retrieval.

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

## Live Run Results (real Mistral + Ollama + corpus)

- **Environment:** backend `task/TASK-BE-015-answer-language` @ `46c1155` on port 8081; LLM
  `mistral-api` (`mistral-small-latest`), embeddings Ollama `nomic-embed-text`; Postgres
  pgvector with **5177 chunks** (5136 `csv-article` English Eir corpus + 41 `markdown` FR KB).
- **Method:** `POST /api/conversation/converse`, one unique `correlation_id` per turn, language
  cross-checked against the `[LANGUAGE]` structured log.

| Turn | Question (lang) | Answer lang | Grounded | `[LANGUAGE]` telemetry | Verdict |
|---|---|---|---|---|---|
| L-EN-BILL | "Why is my bill higher…" (EN) | EN | fallback | `provider=mistral-api language=en` | ✅ language OK (see retrieval note) |
| L-FR-BILL | "Pourquoi ma facture est-elle plus élevée…" (FR) | FR | ✅ (0.72) | `provider=mistral-api language=fr` | ✅ fluent FR, offers *conseiller* |
| L-EN-TECH | "My internet connection keeps dropping…" (EN) | EN | ✅ (0.66) | `provider=mistral-api language=en` | ✅ fluent EN troubleshooting |
| L-FR-TECH | "Ma connexion internet n'arrête pas de se couper…" (FR) | FR | ✅ (0.76) | `provider=mistral-api language=fr` | ✅ fluent FR troubleshooting |
| L-EN-OFF | "What's the weather like today?" (EN) | EN | refusal | `provider=n/a language=en` | ✅ EN off-topic refusal |
| L-FR-OFF | "Quel temps fera-t-il demain ?" (FR) | FR | refusal | `provider=n/a language=fr` | ✅ FR off-topic refusal |
| L-AMBIG | "ok" (ambiguous, no context) | EN | fallback | `provider=n/a language=en` | ✅ default EN |
| L-STICK-1 | "Pourquoi ma facture a-t-elle augmenté…" (FR) | FR | fallback | `provider=mistral-api language=fr` | ✅ FR |
| L-STICK-2 | "ok" (ambiguous, after FR turn) | **EN message** / decided **fr** | fallback | `provider=n/a language=fr` | ❌ **BUG-002** — decided FR, spoke EN |

**Findings:**
- **BR1/BR4/BR5/BR7 confirmed live:** EN questions → fluent EN answers, FR questions → fluent
  FR answers, off-topic refusals in the question language, all grounded on the mixed corpus.
- **Fidelity (BR5) confirmed:** French answers grounded on the corpus are fluent and coherent
  (proration, hors-forfait, congestion réseau…); English answers likewise. No cross-language
  leakage observed.
- **Per-turn observability confirmed live:** every turn emitted `[LANGUAGE]` with the correct
  language; LLM turns tagged `provider=mistral-api`, guardrail-fallback turns `provider=n/a`.
- **BUG-002 (Medium):** ambiguous follow-up in a French conversation → decided/recorded FR but
  the guardrail fallback wording is English (root cause: `GuardrailMessages` detects per-message
  with a hardcoded EN default, ignoring stickiness and the configurable default). See
  `product-backlog/bugs/BUG-002-*.md`.
- **Retrieval note (out of scope):** an English billing phrasing fell to a low-confidence
  fallback while the French billing question grounded — a corpus/retrieval asymmetry, not a
  language defect; language stayed correct.

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| `AnswerLanguage` (VO: detect + directive + hand-off markers) | ✅ | Deterministic FR/EN scoring; ambiguity returns empty so stickiness/default can decide; ArchUnit value-object rule satisfied (enum is implicitly final). | None |
| `LanguageDetector` (domain service) | ✅ | question → history stickiness → configurable default; single per-turn decision. | None |
| `AnswerService` / `StreamingConversationService` | ✅ | Decide language once per turn; thread to the LLM on the answerable path; record language (`provider=n/a`) on guardrail-fallback turns. | None |
| Guardrails (`InputGuardrail` / `GuardrailMessages` / `OutputGuardrail`) | ✅ | Canned wording now renders from the **decided** per-turn `AnswerLanguage` threaded into every guardrail (BUG-002 fix) — no per-message re-detection, so wording can't diverge from the answer language on ambiguous turns; English refusal hand-off still caught like French. | None |
| Observability (`BackendTelemetry.recordAnswerLanguage`) | ✅ | Per-turn counter `voice_support.answer_language{provider,language}` + `[LANGUAGE]` log with correlation id, on **both** LLM and fallback paths; no transcript/answer content logged. | Confirm metric/log surface in a live run |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| **Medium (fixed)** | **BUG-002** — ambiguous follow-up in a French conversation returned an **English** guardrail fallback. **Fixed** on `fix/BUG-002-fallback-language-stickiness`: the decided per-turn `AnswerLanguage` is threaded into every guardrail (single source of truth); regression tests added (unit + BDD), 212 tests green. Live retest pending. | French customer hears an English canned message mid-conversation (BR3/BR4 violation on the fallback path). | Backend developer |
| Low (out of scope) | Retrieval-confidence asymmetry: an English billing phrasing fell to low-confidence while its French counterpart grounded. | Some EN questions get a fallback instead of a grounded answer; language stays correct. | KB / retrieval |
| Medium (cross-team) | Voice STT/TTS language selection on the spoken path is unvalidated; a mismatch means the customer hears the wrong-language voice regardless of the text answer. | Voice UX correctness on the pilot. | Architecture / voice runtime |
| Low (resolved) | Answer *fidelity* on FR↔EN content mismatch — **validated live** (fluent, coherent FR/EN answers on the mixed corpus). | — | QA (done) |

## Open Questions

- **Product:** none — the 6 acceptance criteria are unambiguous and covered.
- **Architecture:** How does the chosen answer language propagate to STT/TTS on the voice
  path so the spoken reply matches? (Ticket open question — escalate to `software-architect`.)
- **Technical:** none blocking.

## Recommendation

- **Go / No-go:** **GO (merge-ready, pending user validation)** — the core FR/EN answer-language
  behavior, fidelity and per-turn observability are validated live, and **`BUG-002` is now fixed
  and QA-verified live** (see Live retest 2026-07-22). Grounded answers and clear-language refusals
  need no further work. Merge on the user's explicit request.
- **Live run: done** (real Mistral/Ollama + real corpus) — FR/EN fidelity confirmed, one Medium
  defect found (`BUG-002`).
- **Required before merge:**
  1. ~~Fix `BUG-002` + regression test (sync + streaming) + ADR-0031 update; QA retest.~~
     **Done (code + docs + unit/BDD):** language threaded into all guardrails, ADR-0031 updated,
     regression tests added, 212 tests green. **Live retest still pending** to close.
- **Required before pilot (not before merge):**
  2. **Voice STT/TTS language** validation on the spoken path (Architecture / voice runtime).

## BUG-002 Fix Retest (2026-07-22)

- **Branch:** `fix/BUG-002-fallback-language-stickiness`
- **Change:** one language decision per turn (`LanguageDetector`) is threaded into
  `GroundQueryUseCase.ground(...)`, `InputGuardrail`, `RetrievalConfidenceGuardrail`,
  `OutputGuardrail` and `GuardedSentenceEmitter`; `GuardrailMessages` renders wording from the
  decided `AnswerLanguage` (no more per-message re-detection / hard-coded English default).
- **Regression tests:**
  - BDD `answer-language.feature` → *"An ambiguous follow-up keeps the language on a fallback turn
    (BUG-002)"*: French history + ambiguous "ok" + insufficient evidence ⇒ **French** fallback +
    human-advisor offer (fails on old code, passes on the fix).
  - Unit `InputGuardrailTest.wordingFollowsDecidedLanguageNotInput`: canned wording follows the
    DECIDED language, not the input text.
- **Result:** `mvn -o test` → **211 tests, 0 failures** (unit + BDD + ArchUnit; a now-dead
  `AnswerLanguage.detect(text, fallback)` overload + its test were removed during adversarial-review
  remediation). Telemetry and the returned message language now always agree by construction.
- **Adversarial review:** 94/100, QA gate **Pass**.

### Live retest (2026-07-22) — PASS

Real `mistral-api` + Ollama `nomic-embed-text` + pgvector (5177 chunks), `POST
/api/conversation/converse`, branch `fix/BUG-002-fallback-language-stickiness`.

| Correlation id | Transcript | History | Decided lang | Reply | Result |
|---|---|---|---|---|---|
| `L-STICK-FR2` | "ok" | French convo (same id) | fr | French low-confidence + "conseiller" | ✅ (was EN pre-fix) |
| `L-AMBIG` | "ok" | none | en | English low-confidence + "support agent" | ✅ control |
| `L-OT-FR` | "Quel temps fera-t-il demain ?" | none | fr | French off-topic refusal | ✅ |
| `L-OT-EN` | "What's the weather like today?" | none | en | English off-topic refusal | ✅ |
| `L-EN-GRD` | "How can I reset my router password?" | none | en | grounded EN answer (conf 0.71) | ✅ grounded intact |

Decisive contrast: the **identical** transcript "ok" yields **French** wording in a French
conversation (stickiness) and **English** with no history (configurable default) — BUG-002's
divergence is eliminated. `[LANGUAGE]` telemetry matches the spoken language on every turn.
Latency: fallback 0–90 ms (no LLM), grounded EN ~1090 ms (`llm_wording` 1011 ms) — no regression.

**BUG-002 is fixed and QA-verified.** Remaining before pilot (not before merge): voice STT/TTS
language on the spoken path (Architecture / voice runtime).
