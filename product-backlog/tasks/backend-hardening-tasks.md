# Backend Answer-Engine — Hardening Tasks

Cross-cutting hardening for the Java answer-engine backend (`voice-support-bot/backend`,
contexts `knowledge` + `conversation`). These are **out of the Sprint 7 core theme**
(answer-engine happy path BE-004…BE-006) and scheduled opportunistically before the
pilot, unless pulled in earlier.

| Task | Title | Classification | Depends on | Status |
|---|---|---|---|---|
| TASK-BE-012 | Backend REST error contract (`GlobalExceptionHandler` + `ErrorResponse`) | V1 hardening | TASK-BE-002 | ✅ Merged into `feat/sprint-7-answer-engine` (2026-07-20) |
| TASK-BE-016 | OpenAPI/Swagger for the Java backend (`springdoc-openapi`) | V1 hardening | TASK-BE-002 | Proposed (2026-07-21) — out of Sprint 8 theme |
| TASK-BE-018 | Concise voice-first answers — cap answer length to cut TTS synthesis time (latency lever) | V1 answer quality / latency | TASK-BE-005 | ✅ Merged into `feat/restart-from-scratch` (2026-07-23, ff `f5467c4..e662f79`) — adversarial 92/100 + QA **Go** (live A/B: answer chars p50 −33 %/p95 −63 %, `llm_wording` p50 −30 %/p95 −34 %, 0 regression); `mvn test` 229 green |
| TASK-QA-018 | Mutation testing (PIT) for the backend domain guardrails/classifier — measure test *effectiveness*, not just coverage | V1 hardening / test quality | TASK-BE-004, BUG-001, BUG-005 | In progress (2026-07-27, Sprint 9) — branch `task/TASK-QA-018-mutation-testing-backend` |

---

## TASK-BE-012 — Backend REST error contract

**Parent:** EPIC-005 (Answer engine) — cross-cutting API hardening
**Classification:** V1 hardening
**Status:** ✅ Validated by user + merged into `feat/sprint-7-answer-engine`
(2026-07-20, ff; stacked on BE-009) — 137 tests green + adversarial review 92/100 +
QA GO on `task/TASK-BE-012-backend-error-contract` (cut from
`task/TASK-BE-009-observability`).
Review fixed one acceptance gap: a provider `RestClientException` (e.g. embedding
endpoint down) now maps to 503 `ERR_UPSTREAM` instead of falling to 500.
**Medium finding fixed pre-merge (2026-07-20):** the LLM timeout executor is now
**bounded** (`ThreadPoolExecutor`, max 16 in-flight, `SynchronousQueue` +
`AbortPolicy`; rejection → sanitized 503) instead of an unbounded cached pool, and the
chat provider now carries a **HTTP read + connect timeout** (`RestClient` request
factory) so a stalled socket is actually closed rather than left hanging on an
abandoned thread. Live-verified with `LLM_TIMEOUT_MS=1`: `SocketTimeoutException: Read
timed out` on the Mistral socket → `UpstreamUnavailableException` → sanitized 503
(`llm_wording` slice `outcome=error`, ~79 ms, well below the 2 s executor backstop).
**Priority:** Medium
**Branch:** `task/TASK-BE-012-backend-error-contract`
**Surfaced by:** TASK-BE-004 adversarial review (2026-07-18) — degraded-mode / privacy
finding.
**Relates to:** TASK-BE-009 (observability / correlation id), ADR-0010
(industrialization: contracts + observability), TASK-WEB-006 (the voice-runtime
equivalent — generic error responses, closes RF-013).

### Context

The backend currently has **no `@RestControllerAdvice`**. When a dependency is down
(Ollama embedding endpoint, Postgres/pgvector) or a request is malformed, the REST
endpoints (`/api/knowledge/sync`, `/api/knowledge/ingest`,
`/api/conversation/retrieve`) fall through to Spring's **default error handling** and
can return a 500 whose body may echo raw exception text (upstream URLs, driver
messages, stack hints).

This mirrors two problems already fixed elsewhere in the workspace:
- voice runtime **RF-013 / TASK-WEB-006** — stop echoing raw provider error text in
  `/stt` `/tty` `/turn` 502 bodies;
- dashboard `GlobalExceptionHandler` — return a generic `ERR_UPSTREAM` + correlation
  id, keep full detail server-side only.

### Objective

Introduce a shared, sanitized REST error contract in the backend:

- `@RestControllerAdvice GlobalExceptionHandler` returning a structured
  `ErrorResponse` (snake_case) with a stable `error_code`, a `correlation_id`, and a
  **generic** client message — never `ex.getMessage()` verbatim.
- Map the common cases:
  - bean-validation / malformed body → **400** (`ERR_400`);
  - upstream dependency failure (embedding / vector store unavailable or timing out)
    → **502/503** (`ERR_UPSTREAM`);
  - not found where relevant → **404**.
- Add request validation: `@NotBlank` on `RetrievalRequest.question`
  (`spring-boot-starter-validation` is already on the classpath) so a blank question
  returns a 400 instead of a silent `LOW_CONFIDENCE`.
- Log the full exception detail server-side with the correlation id (structured),
  nothing sensitive in the client body.

### Acceptance

- A malformed request (blank/missing `question`) returns `400` with an `ErrorResponse`
  (`error_code` + `correlation_id`), not a `LOW_CONFIDENCE` 200 and not a 500.
- A dependency-down request (embedding/vector store unavailable) returns a documented
  `502/503` `ErrorResponse` with a stable `error_code` + `correlation_id` and **no**
  internal detail (no upstream URL, no driver/stack text) in the body.
- The full error detail is available server-side in structured logs with the same
  `correlation_id`.
- Covered by `@WebMvcTest` (contract) + a focused test proving no raw exception text
  leaks into the response body.

### Notes

- Keep the domain/application layers free of transport concerns — the advice lives in
  `shared/web` (or `shared/web/rest`) so both contexts reuse it.
- Correlation-id propagation should align with TASK-BE-009 (OTel); if BE-009 lands
  first, reuse its correlation-id source instead of inventing a second one.

### Implementation notes (2026-07-19)

Delivered on `task/TASK-BE-012-backend-error-contract` (branched from BE-009 so it
reuses the `CorrelationId` source, per the note above):

- `shared/web/rest/GlobalExceptionHandler` (`@RestControllerAdvice`) + `ErrorResponse`
  (`{error_code, message, correlation_id}`, snake_case). Maps bean-validation /
  malformed body → **400 `ERR_400`**, `UpstreamUnavailableException` + `DataAccessException`
  → **503 `ERR_UPSTREAM`**, and a generic fallback → **500 `ERR_INTERNAL`**. Client
  bodies carry only a stable code + generic message + `correlation_id`; the full
  exception (cause/stack) is logged server-side under the same id, never echoed.
- `@NotBlank` on `RetrievalRequest.question` + `@Valid` on `/retrieve` → a blank/missing
  question is a 400, not a silent `LOW_CONFIDENCE` 200.
- Hard LLM timeout in `AbstractChatClientAnswerAdapter` (`voice-support.llm.timeout-ms`,
  default 8000, 0 disables): the chat call runs on a **bounded** daemon executor
  (`ThreadPoolExecutor`, max 16 in-flight, `SynchronousQueue` + `AbortPolicy` — overflow
  is rejected and degrades to 503, never piling up) with
  `future.get(timeout + 2 s backstop)`; a timeout/failure/rejection throws
  `UpstreamUnavailableException` → sanitized 503 (the voice runtime then speaks the safe
  degraded turn). The provider chat API (`LlmConfig`) also sets a **HTTP read timeout =
  `timeout-ms`** and **connect timeout = `voice-support.llm.connect-timeout-ms`
  (default 3000)** on its `RestClient`, so the read timeout normally fires first and
  closes the socket cleanly (the executor timeout is only a backstop for pre-read hangs).
  The timed-out LLM slice is recorded with `outcome=error` (BE-009 telemetry), keeping
  the `tts/llm` success p95 clean.
- Tests (`mvn test` 134 green): `GlobalExceptionHandlerTest` (400 validation, malformed
  JSON, 503 upstream **no-leak**), `ConverseDegradedTest` (upstream → sanitized 503 with
  the runtime correlation id in body + header, no leak).
- Live-verified (pgvector 5433 + Ollama + Mistral, `LLM_TIMEOUT_MS=1`): blank/malformed
  → 400 `ERR_400`; valid non-LLM retrieve still 200; converse LLM timeout → 503
  `ERR_UPSTREAM` (generic message, `correlation_id=cid-degraded-live` in body + header);
  server log kept the full `LLM provider timed out after 1 ms` stack under the id.

---

## TASK-BE-016 — OpenAPI/Swagger For The Java Backend

**Parent:** EPIC-005 (Answer engine) — cross-cutting API hardening
**Classification:** V1 hardening
**Status:** Scheduled — Sprint 9 (hardening/assainissement). Proposed (2026-07-21) — cross-cutting, out of the Sprint 8 CSV theme; paired with TASK-WEB-016 (voice-runtime OpenAPI).
**Priority:** Medium
**Branch:** `task/TASK-BE-016-openapi-swagger`

### Context

No `springdoc`/`openapi`/`swagger` dependency exists in `backend/pom.xml`; the REST
surface (`KnowledgeController`, `ConverseController`, `HealthController`, streaming)
is undocumented as OpenAPI.

### Objective

Expose an OpenAPI 3 spec + Swagger UI for the backend so all project APIs are
consistently documented (paired with TASK-WEB-016 for the Python voice runtime).

### Scope

- Add `springdoc-openapi-starter-webmvc-ui` (managed version) → `/swagger-ui.html`
  + `/v3/api-docs`.
- Annotate controllers/DTOs (`@Tag`, `@Operation`, `@Schema`) with concise
  descriptions; keep JSON naming (snake_case) accurate in the spec.
- Ensure the spec reflects the `ErrorResponse` contract (TASK-BE-012) and the
  correlation-id headers.

### Acceptance

- `/v3/api-docs` returns a valid OpenAPI 3 document covering every endpoint;
  Swagger UI renders it.
- No secret/internal detail leaked in descriptions; `mvn test` + ArchUnit stay green.

---

## TASK-BE-018 — Concise Voice-First Answers (Latency Lever)

**Parent:** EPIC-005 (Answer engine) — answer quality / pilot latency
**Classification:** V1 answer quality / latency lever
**Status:** ✅ Merged into `feat/restart-from-scratch` (2026-07-23, ff `f5467c4..e662f79`) —
adversarial review 92/100 (QA gate Pass) + QA functional & latency **Go**; `mvn test` 229
green, ArchUnit OK.
**Priority:** High
**Branch:** `task/TASK-BE-018-concise-voice-answers`
**Surfaced by:** BUG-004 live voice validation (2026-07-22/23) — grounded answers are
now stable, but long grounded answers dominate synthesis time.
**Relates to:** TASK-BE-005 (provider-agnostic LLM wording), TASK-BE-007 (SSE token
streaming), ADR-0029 (pilot latency criterion), ADR-0033 (WebRTC single live transport).

### Context

With BUG-003 (chunking) and BUG-004 (spurious refusals) fixed, grounded answers are
stable — but they are also **long**. Answer length is now the dominant driver of total
TTS synthesis time:

- **Batch `/turn` path (offline/tests, ADR-0033):** time-to-first-audio equals full
  synthesis time and scales with answer length — a long grounded answer measures
  **≈ 14 s** to first audio.
- **WebRTC streaming path (live, ADR-0033):** first audio is already ≈ 360 ms, but the
  **total** spoken duration and the tail still scale with answer length, and a verbose
  answer degrades the conversational feel and mouth-to-ear perception (ADR-0029).

The LLM currently has no explicit length/conciseness budget for the voice channel: the
directive optimizes for grounded correctness (BUG-004) but not for spoken brevity.

### Objective

Make the answer engine produce **concise, voice-first** answers by default — short
enough to be spoken naturally — **without regressing grounding** (DEC-002, BUG-004:
still refuse/hand off only when context is empty or unrelated; never invent amounts).

### Scope

- Add a **conciseness directive** to the LLM system prompt (both `MistralAnswerAdapter`
  and `OllamaAnswerAdapter`, kept in sync via the shared abstract adapter): answer in a
  few short sentences suitable for speech, lead with the direct answer, no markdown, no
  bullet lists, no restating the question.
- Add a **configurable answer-length budget** (e.g. `voice-support.llm.max-answer-*`,
  a sentence/word/char target) applied as a prompt constraint; keep it env-tunable so
  the batch vs live trade-off can be tuned without a redeploy.
- Ensure the cap is applied **at generation** (prompt), not by post-hoc truncation that
  could cut mid-sentence or drop the grounded core.
- Keep the multilingual behaviour (ADR-0031): the budget applies equally to FR and EN,
  and the concise answer must still respect the language directive and hand-off wording.

### Acceptance

- A typical grounded question yields a spoken answer within the configured budget
  (target to be set with QA, e.g. ≤ 3 short sentences) while still containing the
  grounded facts — verified on a sample of FR + EN questions.
- No grounding regression: the BUG-004 regression cases still answer (do not fall back)
  when evidence is present, and still hand off when context is empty/unrelated
  (`OutputGuardrail` markers unchanged).
- Latency evidence: batch `/turn` time-to-first-audio and WebRTC total spoken duration
  measurably drop for long-answer cases; report before/after with the ADR-0018 method
  and check against the ADR-0029 criterion.
- `mvn test` + ArchUnit green; a focused test locks the concise directive/budget wiring
  in both adapters. Runtime-affecting → BE-009 telemetry still records the `llm_wording`
  slice; note answer length alongside latency in the QA report.

### Notes

- This is a **prompt/answer-shaping** lever, complementary to TASK-BE-007 (SSE token
  streaming) and the ADR-0029 latency work — not a substitute for either.
- Do not lower grounding to hit brevity: if a question genuinely needs more detail,
  concise-but-complete beats truncated. QA sets the concrete budget.

### Implementation notes (2026-07-23)

Delivered on `task/TASK-BE-018-concise-voice-answers` (branched from
`feat/restart-from-scratch` after the BUG-004 stack merged):

- **Per-language concision directive** owned by `AnswerLanguage.concisionDirective(int
  maxSentences)` (FR/EN wording, `%d` sentence cap; a non-positive budget returns an
  empty string = disabled). Kept in the language value object so brevity wording matches
  the answer language and stays beside `llmDirective()`/`handoffMarkers()`.
- **Prompt assembly** (`AbstractChatClientAnswerAdapter.buildSystemMessage`): the
  concision directive is appended **just before** the language directive, so the language
  instruction remains last for recency (TASK-BE-015). Generation-time constraint — no
  post-hoc truncation, so a grounded answer is never cut mid-sentence.
- **Configurable budget** `voice-support.llm.max-answer-sentences` (env
  `LLM_MAX_ANSWER_SENTENCES`, default **3**, `0` disables), threaded into both
  `MistralAnswerAdapter` and `OllamaAnswerAdapter` via `LlmConfig` (shared abstract base,
  no per-adapter duplication). The base voice-style prompt ("phrases courtes") is
  unchanged; the numeric cap is the new explicit lever.
- **Observability:** new `BackendTelemetry.recordAnswerLength(provider, answerChars)` →
  `voice_support.answer_chars` DistributionSummary (p50/p95/p99, `provider` tag) + a
  privacy-safe `[ANSWER]` log with the correlation id (length only, never answer text),
  recorded on both the sync and streaming answer paths so the budget's effect on TTS
  synthesis time is measurable next to `llm_wording`.
- **Grounding preserved (DEC-002 / BUG-004):** the hand-off markers and the
  empty/unrelated-only refusal condition are untouched; concision only shortens a valid
  grounded answer.
- **Tests (`mvn test` 223 green, ArchUnit OK):** `AnswerLanguageTest` (FR/EN cap wording
  + disabled for 0/negative), `AbstractChatClientAnswerAdapterTest` (directive present +
  ordered before the language directive when budget set; absent when budget = 0).

### Review & QA outcome (2026-07-23)

- **Adversarial code review:** 92/100 — QA gate **Pass**, no blocking findings (one
  non-blocking test-symmetry gap fixed: `BackendTelemetry.recordAnswerLength` now covered).
- **QA functional & latency:** **Go** — see `docs/qa/task-be-018-concise-answers-qa-report.md`.
  Live A/B (Mistral `mistral-small-latest`, warm, `api`, 10 163 KB chunks), budget=3 vs 0:
  - answer chars (grounded, n=8): p50 **286 vs 426 (−33 %)**, p95 **336 vs 899 (−63 %)**,
    mean 280 vs 517 (−46 %);
  - `llm_wording`: p50 **846 vs 1200 ms (−30 %)**, p95 **2033 vs 3100 ms (−34 %)**;
  - functional: 8/8 grounded still answered (BUG-004 greeting incl.), 10/10 language-correct,
    2/2 off-topic refused — **no regression** in either arm.
  - Automated net: BDD `answer-concision.feature` (real adapter + capturing `ChatModel`),
    `mvn test` **229 green**.

**Remaining before a latency SLO claim (not blocking merge):** fold in TTS/channel-egress
mouth-to-ear measurement (TASK-WEB-014, ADR-0029) and enlarge the sample; the current
evidence is the backend lever (`answer_chars` + `llm_wording`) with TTS cost as a proxy.
Default budget kept at **3** (env `LLM_MAX_ANSWER_SENTENCES`).

---

## TASK-QA-018 — Mutation Testing (PIT) For The Backend Domain

**Parent:** EPIC-005 (Answer engine) — cross-cutting test-quality hardening
**Classification:** V1 hardening / test quality
**Status:** In progress — Sprint 9 (hardening/assainissement). Requested by user 2026-07-27
after the BUG-001/BUG-005 guardrail work, to prove the guardrail/classifier tests actually
*kill* mutations (catch real logic changes), not just execute lines.
**Priority:** Medium
**Branch:** `task/TASK-QA-018-mutation-testing-backend`
**Relates to:** `test-guidelines` skill (mutation-testing standard) + `java-backend-developer`
skill (PIT/Maven wiring); BUG-001 (`InputGuardrail`), BUG-005 (`RetrievalConfidenceGuardrail`,
audience classifier) — the exact deterministic logic mutation testing protects.

### Context

The backend has strong line/branch coverage on pure-domain logic (guardrails, language
detection, audience classifier, money/comparison to come) but coverage only proves code was
*executed*, not that a test would *fail* if the logic were wrong. The recent P1/P2 guardrail
fixes (three-band confidence, vague-turn clarify, intent-aware cyber rule) are exactly the
kind of boolean/threshold logic where a weak assertion silently passes a broken mutant.

The project is an ideal fit for mutation testing: pure-domain unit tests, manual fakes, no
Mockito, no `@SpringBootTest`, no DB/Ollama needed for `mvn test` → PIT runs fast with high
signal on the classes that matter.

### Objective

Introduce **PIT (pitest)** mutation testing on the backend, scoped first to the
high-value deterministic domain packages, with a starting mutation-score threshold, so
weak tests are surfaced before they ship.

### Scope

- Add `pitest-maven` + `pitest-junit5-plugin` to `backend/pom.xml` (test-only, not a runtime
  dep). Pin a version that runs under the local JDK (see JDK note).
- `targetClasses` scoped to the deterministic domain first (not the whole app):
  `com.voicesupport.conversation.domain.service.*` (guardrails, language, segmenter) +
  `com.voicesupport.knowledge.infrastructure.adapter.out.classifier.*` (audience classifier).
  Widen later (comparison/money when they land).
- `targetTests` = the matching `*Test` classes; exclude Cucumber/ArchUnit suites from the
  mutation run (they are not fast unit oracles).
- Run `mvn -Ppitest org.pitest:pitest-maven:mutationCoverage` (own profile so the normal
  `mvn test` stays fast) and capture the baseline HTML/XML report score.
- Set a **starting** `mutationThreshold` (descriptive, non-CI-breaking at first) — proposal
  **70 %** on the scoped packages — with a short rationale; ratchet up once the baseline is known.

### Acceptance

- `mvn -Ppitest ...:mutationCoverage` runs green on the scoped packages and produces a
  mutation-score report; the baseline score is recorded in this ticket + the QA doc.
- Any surviving mutants that reveal a genuine assertion gap are either killed (test added)
  or explicitly noted as accepted (with reason).
- The standard `mvn test` is unchanged (PIT is behind a profile), so CI/dev speed is unaffected.
- Mutation-testing standard documented in `test-guidelines` (norm) + `java-backend-developer`
  (PIT/Maven how-to); skill edits go through the `skill-creator` process.
- `mvn test` + ArchUnit stay green.

### Notes

- **Java version:** the build targets **Java 17** (`<java.version>17</java.version>`), fully
  supported by modern PIT (1.16.x) + `pitest-junit5-plugin` (1.2.x). The only nuance is the
  **runtime JDK** that executes Maven (currently openjdk **25** on this machine): PIT must be
  a version new enough to run on JDK 25, otherwise pin `JAVA_HOME` to a JDK 17 for the PIT run.
  Validate at first run.
- **Offline builds:** the normal loop uses `mvn -o`; the first PIT run needs network to fetch
  the plugin jars (run once online, then it is cached in `~/.m2`).
- Mutation testing complements, does not replace, coverage — it is the "do my assertions
  actually catch bugs" gate for critical deterministic logic.

### Implementation notes (2026-07-27)

Delivered on `task/TASK-QA-018-mutation-testing-backend` (branched from `feat/restart-from-scratch`):

- **PIT wired behind a `pitest` profile** in `backend/pom.xml` (`pitest-maven` 1.19.1 +
  `pitest-junit5-plugin` 1.2.2). Scoped to `conversation.domain.service.*` +
  `knowledge.infrastructure.adapter.out.classifier.*`. The normal `mvn test` loop is
  unchanged (profile-gated). Run:
  `mvn -Ppitest test-compile org.pitest:pitest-maven:mutationCoverage`.
- **JDK compat validated:** the build targets **Java 17**; PIT 1.19.1 runs cleanly under the
  local **JDK 25** runtime (no ASM major-version failure), so no JDK-17 toolchain is required
  here. Documented the `JAVA_HOME`-on-17 fallback in case a future PIT/JDK combo regresses.
- **Baseline captured:** 193 mutations, **168 killed (87 %)**, **test strength 90 %**, line
  coverage 93 % on the scoped classes.
- **PIT surfaced real assertion gaps in the BUG-001/BUG-005 hot path** (the whole point):
  - `RetrievalConfidenceGuardrail.check` — both band edges (`< floor`, `< clarify-ceiling`)
    were unpinned → added exact-boundary tests (score == 0.5 clarifies, score == 0.62 passes).
  - `InputGuardrail.isCyberOffense` (BUG-001) — no case reached the final `offense-verb?`
    return with the discriminating outcome → added a neutral cyber-term case
    ("C'est quoi le phishing exactement ?") that must **pass** (only PERFORM-intent is refused).
  - `InputGuardrail.isVague` (BUG-005) — the `words.length <= MAX_VAGUE_TOKENS` edge was
    unpinned → added an exactly-3-continuers vague turn ("ok alors donc") that must clarify.
  - `KeywordAudienceClassifierAdapter` — title-only marker (must tag internal) and blank-marker
    config (must not turn every article internal) were unasserted → added both.
- **After strengthening: 174 killed (mutation score 90 %), test strength 93 %.** All six
  targeted survivors killed. `mutationThreshold=85` set (below the 90 baseline) to guard
  regressions without flaking; ratchet up as peripheral survivors are killed.
- **Accepted residual survivors** (out of the BUG-001/005 scope, tracked not chased):
  `SentenceSegmenter` (streaming boundary), `EmbeddingDomainClassifierAdapter` (domain, not
  audience), `LanguageDetector`, `ConversationHistoryFormatter`, `OutputGuardrail` lambda,
  `GuardedSentenceEmitter` — mostly `NO_COVERAGE`/peripheral boundary mutants.
- **Docs:** mutation-testing norm added to the `test-guidelines` skill; PIT/Maven how-to
  (profile, recompile gotcha, JDK note) added to the `java-backend-developer` skill.
- **Verification:** `mvn -o test` = **279 green**; `mvn -Ppitest ...:mutationCoverage` = BUILD
  SUCCESS (90 % ≥ 85 threshold).

### Review & QA outcome

_Not runtime-affecting_ (test-tooling + tests + skill docs only; no production behaviour
change). Adversarial code review / QA latency gates N/A. Awaiting user validation before merge.
