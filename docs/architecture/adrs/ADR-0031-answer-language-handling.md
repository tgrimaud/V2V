# ADR-0031: Answer Language Handling (FR/EN, Per-Turn, Pilot Default English)

## Status

Accepted — implemented by TASK-BE-015. Builds on the answer engine of
[ADR-0014](ADR-0014-answer-guardrails-and-grounding.md) (input/output guardrails,
grounding pipeline) and the provider-agnostic LLM wording of
[ADR-0006](ADR-0006-mistral-chat-and-ollama-embeddings.md) / DEC-011. Closes the answer-language
open question left by [ADR-0030](ADR-0030-csv-knowledge-connector-and-domain-classification.md)
(English Eir corpus coexisting with the French development framing in one vector store).

## Context

The Eir knowledge base is **English**; the development default framing (system prompt, canned
fallbacks) is **French**. In the Sprint 8 live test an **English** question received a **French**
answer: the provider system prompt is written in French and its buried line *"Réponds dans la
langue de la question"* was not reliably honored by `mistral-small`. In addition, the fixed
refusal sentence and the human-escalation hand-off were French-only, and the output guardrail
detected only the French hand-off sentence — so even the non-answer paths were language-bound.

The product decision (TASK-BE-015, user-validated):

- Answer in the **language of the customer's question** (BR1).
- **Configurable default = English** for the Eir pilot when a turn is too ambiguous to detect
  and no session language is established (BR2).
- **Per-turn** decision with **session stickiness** on ambiguity (BR3).
- **Consistent** language across grounded answer, insufficient-evidence fallback, off-topic
  refusal and escalation (BR4/BR7).
- Answer in the customer's language even when the evidence is only in the other language (BR5).
- **French + English** in V1, extensible (BR6).

## Decision

### 1. `AnswerLanguage` value object (domain)

An enum `FRENCH`/`ENGLISH` in `conversation.domain.model.valueobject` owns, as a single source of
truth: the deterministic FR/EN **detection heuristic** (`detect(text) -> Optional`, marker-word
scoring per language plus a French accent signal; empty on a tie/no signal), the per-call **LLM
directive** (a forceful, explicit instruction plus the exact hand-off sentence in that language),
the **hand-off markers** the output guardrail matches, and `fromCode(...)` for config parsing.

### 2. `LanguageDetector` domain service — one decision per turn

`resolve(question, history)` = detect from the question; if ambiguous, keep the current
conversation language (stickiness, inferred from the most recent detectable history turn);
otherwise the configured default. Wired as a `@Bean` with the default from
`voice-support.conversation.default-language` (`en` for the Eir pilot). This is the answer
language, distinct from `voice-support.knowledge.default-language` (the KB ingestion tag).

### 3. Language threaded to the LLM, not left to a buried prompt line

The decided `AnswerLanguage` is passed through `AnswerGeneratorPort` /
`StreamingAnswerGeneratorPort` (new parameter) to the provider adapter, which appends the
language directive **last** in the system message (recency reliably overrides the French base
framing). The two provider prompts (Mistral, Ollama) drop the old *"answer in the question's
language"* line and the hardcoded French refusal sentence — both now come from the per-call
directive. The domain still owns all wording; the SDK stays in infrastructure.

### 4. Consistent guardrail wording + language-independent hand-off

`GuardrailMessages` delegates detection to `AnswerLanguage.detect(text, ENGLISH)` (the same
heuristic and pilot default), so greeting / off-topic / insufficient-evidence wording matches the
LLM answer language. `OutputGuardrail.isNonAnswer` matches the hand-off markers of **every**
`AnswerLanguage`, so an English refusal is caught and surfaced as a safe hand-off exactly like the
French one (BR7).

### 5. Observability

`BackendTelemetry.recordAnswerLanguage(provider, language)` emits a counter
`voice_support.answer_language{provider,language}` and a `[LANGUAGE]` structured log with the
correlation id, recorded when the LLM system message is built. The chosen answer language is
therefore observable per turn for QA, with no transcript/answer content logged.

## Consequences

- English customers get English answers over the English Eir corpus; French dev keeps French.
  Fallbacks, refusals and escalation follow the same language.
- The ambiguous default changed from French to **English** (pilot). Deterministic tests that
  relied on the old French default for an ambiguous input were updated to use a clearly French
  question; per-deployment behavior is configurable.
- `AnswerGeneratorPort` / `StreamingAnswerGeneratorPort` gained a parameter → all implementers
  and test fakes updated (no Mockito).
- The detection heuristic is deterministic and cheap (regex marker scoring), adding negligible
  latency; the language decision is recorded per turn.

## Known Limitations / Follow-ups

- Per-turn language is recorded on the **LLM answer path**; guardrail-only fallback turns follow
  the same detector but are not separately counted — a lightweight extension if QA needs it.
- The heuristic covers FR/EN; adding a language means extending the enum's marker sets (and a
  stronger detector, e.g. a language-id model, can replace the heuristic behind the same API).
- **Voice STT/TTS language** on the spoken path must match the answered language — a voice-runtime
  dependency tracked with the ticket, not solved by this backend ADR.

## Alternatives Considered

- **Keep the "answer in the question's language" prompt line only**: already present and proven
  unreliable with a French-framed prompt; rejected.
- **Thread the language through every guardrail signature**: larger blast radius for no product
  gain — the guardrails already localize from the turn text via the shared detector; rejected.
- **Detect the language inside the adapter from the question**: loses session stickiness and the
  single per-turn decision point; rejected in favor of deciding in the application service.
- **LLM/most-accurate language identification**: heavier per turn; the enum keeps the detector
  swappable behind `AnswerLanguage.detect` if needed later.
