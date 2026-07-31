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
| TASK-QA-018 | Mutation testing (PIT) for the backend domain guardrails/classifier — measure test *effectiveness*, not just coverage | V1 hardening / test quality | TASK-BE-004, BUG-001, BUG-005 | ✅ Done — merged 2026-07-27 into `feat/restart-from-scratch` (`58cdb2c`); 97 % killed / 97 % strength, threshold 95 |
| TASK-BE-019 | Authenticate/isolate the unauthenticated backend endpoints (`/api/knowledge/ingest`, `/sync`, `/api/conversation/answer`, `/retrieve`) | V1 security hardening | TASK-BE-006, TASK-BE-012 | 🚧 Implemented on `task/TASK-BE-019-endpoint-auth` (2026-07-28) — central `ApiKeyAuthInterceptor` gates the 4 endpoints (same rule as `/converse`), sanitized 401 `ERR_401`; `mvn test` **312** green (+7). ✅ Adversarial review 93/100 + QA GO (live gate smoke on :8081) — ✅ Merged into `feat/restart-from-scratch` (2026-07-28, merge commit `e5cb64a`) |

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
**Status:** ✅ Merged into `feat/restart-from-scratch` (2026-07-28, fast-forward `bf9ec5c..f000d2d`)
as part of the Sprint 9 closure. Adversarial review **94/100** (no blocking findings). Post-merge
integration green: backend **305**, voice-agent unittest 390, behave 30/140. Live-confirmed on the
RF-019 warm stack (springdoc active, `Started VoiceSupportApplication`, `/v3/api-docs` + Swagger UI
served, `/api/conversation/converse` answering). Added `springdoc-openapi-starter-webmvc-ui` (pinned **2.8.14**) → live OpenAPI **3.1.0**
doc at `/v3/api-docs` (+ `.yaml`) and Swagger UI at `/swagger-ui.html`, paths pinned in
`application.yml`. `OpenApiConfig` (shared) sets the API info + an optional `x-api-key` security
scheme and an `OperationCustomizer` that documents the cross-cutting `X-Correlation-Id` request
header + response header on every operation. All 6 controllers `@Tag`/`@Operation`-annotated
(Conversation group + Health + Knowledge base), infra DTOs + `ErrorResponse` `@Schema`-annotated;
`/ingest` marked `consumes=multipart/form-data`, streaming as `text/event-stream`, 401/503 error
paths documented. Two version traps hit & fixed (see Gotchas). `mvn test` **305** green (+2
`OpenApiConfigTest`), ArchUnit OK. Live-verified: `/v3/api-docs` 200, all 8 paths, api-key scheme,
correlation-id header, multipart/SSE content types, `ErrorResponse` schema.
**Priority:** Medium
**Branch:** `task/TASK-BE-016-openapi-swagger`

### Context

No `springdoc`/`openapi`/`swagger` dependency exists in `backend/pom.xml`; the REST
surface (`KnowledgeController`, `ConverseController`, `HealthController`, streaming)
is undocumented as OpenAPI.

### Gotchas (springdoc + Spring Boot 3.4.1)

- **springdoc 2.8.15+ breaks on Boot 3.4.1**: it registers the swagger-ui pattern
  `/swagger-ui/**/*swagger-initializer.js`, which Spring Web's `PathPatternParser` rejects
  ("No more pattern data allowed after ** pattern element"). Fixed in Spring Web 6.2.8
  (Boot 3.4.7). We are on Boot 3.4.1 → pinned springdoc **2.8.14** (last known-good). Bump it
  only together with a Spring Boot ≥ 3.4.7 upgrade (springdoc issue #3210).
- **Duplicate swagger annotations package**: Spring AI (`spring-ai-model`) pulls the non-jakarta
  `io.swagger.core.v3:swagger-annotations:2.2.25`, whose `io.swagger.v3.oas.annotations` package
  duplicates springdoc's `swagger-annotations-jakarta:2.2.38`. The stale 2.2.25 classes can win on
  the classpath and lack `Parameter.validationGroups()` → `NoSuchMethodError` on `/v3/api-docs`.
  Fixed by aligning the non-jakarta variant to **2.2.38** in `dependencyManagement`.

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
**Status:** ✅ Done — merged 2026-07-27 into `feat/restart-from-scratch` (fast-forward, `58cdb2c`).
Sprint 9 (hardening/assainissement). Requested by user 2026-07-27 after the BUG-001/BUG-005
guardrail work, to prove the guardrail/classifier tests actually *kill* mutations (catch real
logic changes), not just execute lines. Final: 318 mutations, 309 killed (97 %), 97 % test
strength, `mutationThreshold=95`; 9 residual survivors accepted as equivalent/non-deterministic.
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

### Scope extension (2026-07-27)

Per user request, the PIT scope was widened from the initial guardrails+classifier to **all
pure business logic**: added `conversation.application.service.*` (AnswerService,
ConversationService, RetrievalGroundingService, StreamingConversationService) and
`knowledge.domain.service.*` (TextChunker, KnowledgeIngestionService,
KnowledgeRetrievalService, KnowledgeSyncService). Ports (interfaces) stay out of scope.
Most value objects (records) are plain data holders, but a few carry decision logic
(e.g. `AnswerLanguage.detect()`); these are covered indirectly today and are candidates
for a later PIT-scope ratchet rather than an assumed no-op.

- **Widened baseline:** 318 mutations, 87 % killed, 88 % test strength, ~30 s run.
- **TextChunker cluster hardened (2026-07-27):** added 7 deterministic exact-content tests that
  pin the flush edge (`sum > chunkSize`), the hard-split edge (`length <= chunkSize`), the
  word-boundary overlap tail (guard negate, `substring(i+1)` word-snap, whole-tail return,
  `buffer.length() <= chunkOverlap` edge) and the heading-only `chunks.isEmpty()` fallback.
  TextChunker survivors dropped from ~11 to **2**, both genuinely **equivalent mutants**
  (`overlapTail` `chunkOverlap <= 0` → `< 0`, and `snapBackToBoundary` `i > start` → `i >= start`
  — same observable output), documented as accepted.
- **New score:** 318 mutations, **286 killed (90 %)**, **test strength 91 %**.
  `mutationThreshold` ratcheted **85 → 88** (below the 90 baseline).
- **Remaining survivors (accepted / lower value):** peripheral `SentenceSegmenter`,
  `EmbeddingDomainClassifierAdapter`, `LanguageDetector`, `ConversationHistoryFormatter`,
  `OutputGuardrail`/`GuardedSentenceEmitter`; `KnowledgeSyncService` (elapsed-time math,
  stale-removal void call) and application services (null pass-throughs, telemetry void calls) —
  several near-equivalent. Tracked as a follow-up; ratchet the threshold further as they are killed.

### Survivor grind-down — remaining scope (2026-07-27)

Per user request ("continue à les grignoter"), the peripheral survivors outside the TextChunker
cluster were ground down with targeted deterministic tests (no production code changed):

- **InputGuardrail** — pinned the `length < MIN_QUESTION_LENGTH` boundary (a 3-char unsafe term
  "gun" must still be refused), the short-input pass return (`ab`) and the `isVague` blank-normalise
  return (contentless `...` must not clarify), plus a short "continuer + real word" turn ("ok facture")
  that must pass (allVagueTokens non-vague return).
- **SentenceSegmenter** — pinned the `isBoundary` digit-guard line: a digit-then-`.`-then-space is
  not a boundary ("Prix 5. suite."), `!`/`?` still split after a digit ("Total 5!"), and a leading
  terminator at index 0 is a boundary without reading `charAt(-1)` (". Bonjour.").
- **LanguageDetector** — the `defaultLanguage()` getter is now asserted, and stickiness must scan
  back to the **oldest** history turn (pins the `i >= 0` lower bound).
- **GuardedSentenceEmitter** — a single token completing two safe sentences emits both (pins the
  not-blocked guard inside the accept loop).
- **AnswerService / StreamingConversationService** — the blocked-verdict telemetry
  (`voice_support.guardrail_block`) is now asserted on both fallback paths; AnswerService also
  asserts the prior history is forwarded verbatim to the LLM (null-guard branch).
- **ConversationService** — the produced answer is asserted as the return value (both overloads).
- **KnowledgeIngestionService** — chunks are stored with an ascending 0-based index (increment).
- **KnowledgeSyncService** — `sync(sourceType)` returns the matching connector's report (predicate
  + non-null return); `removeStale` deletion is isolated and asserted against the vector store.
- **EmbeddingDomainClassifierAdapter** — cosine normalises by **both** magnitudes (non-unit anchor),
  a score exactly equal to the threshold is accepted (`>=`), and a title-only signal classifies.

**Final score: 318 mutations, 309 killed = 97 % detected, 97 % test strength, 0 no-coverage.**
`mutationThreshold` ratcheted **88 → 95** (below the 97 baseline).

**Accepted residual survivors — all 9 equivalent or timing-non-deterministic** (cannot be killed
without a semantic change; documented, not chased):

| Mutant | Why it is equivalent / untestable |
|---|---|
| `TextChunker.overlapTail:91` (`<= 0` → `< 0`) | `chunkOverlap` is never negative; both branches behave identically. |
| `TextChunker.snapBackToBoundary:82` (`> start` → `>= start`) | Same snap-back result for the boundary index. |
| `SentenceSegmenter.extractComplete:37` (`start > 0` → `>= 0`) | When `start == 0`, `buffer.delete(0, 0)` is a no-op. |
| `EmbeddingDomainClassifierAdapter.classificationText:78` (`>` → `>=`) | `substring(0, maxChars)` when `length == maxChars` returns the identical string. |
| `KnowledgeSyncService.elapsedMs:108` ×3 (sub→add, div→mult, return 0) | A `System.nanoTime()` duration; not deterministically assertable without an injected `Clock`. |
| `OutputGuardrail.amountsIn` filter (`!isEmpty` → `true`) | `CURRENCY_AMOUNT` always matches ≥1 digit, so `canonical()` is never empty — the filter is a no-op. |
| `ConversationHistoryFormatter.format:18` (`size*2` → `size/2`) | `ArrayList` initial-capacity hint only; no behavioural effect. |

### Review & QA outcome

_Not runtime-affecting_ (test-tooling + tests + skill docs only; **zero `src/main` changes**;
no production behaviour change), so the mandatory OpenTelemetry rule and QA latency gate are
genuinely N/A here — the mutation run is itself the evidence.

**Independent adversarial code review (a posteriori, 2026-07-27): 96/100 — QA gate Pass,
no blocking findings.** An independent reviewer (not the author) re-ran the build and reproduced
the headline numbers (`mvn test` 303 green; PIT 318 mutations / 309 killed / 97 % score / 97 %
strength / 0 no-coverage / threshold 95 passed), confirmed zero `src/main` changes, verified each
of the 9 accepted survivors against the production source (all genuinely equivalent or
timing-non-deterministic — none a killable gap in disguise), and judged the new tests to be real
behavioural contracts rather than mutation-chasing. Non-blocking notes recorded:
- Test method naming (camelCase vs the skill's mandated underscore convention) was resolved by
  applying the **Boy Scout rule**: every test file this ticket touched (13 files, 119 methods) was
  migrated to the descriptive underscore convention while `@DisplayName` was preserved. Fake/helper
  methods that override ports keep camelCase (they implement interfaces). Untouched test files are
  left for a future ratchet — cleaned as they are next edited, not big-banged.
- 4 of the 309 kills are PIT `TIMED_OUT` detections on loop-guard mutants (`TextChunker.hardSplit`,
  `snapBackToBoundary`), a weaker-but-valid form of kill; they cannot flip to SURVIVED from machine
  speed, so the threshold-95 gate carries no CI-flake risk.
- The `elapsedMs` timing survivors would require a production `Clock`/time port to kill — tracked as
  a future follow-up, out of this test-only scope.

---

## TASK-BE-019 — Authenticate/Isolate The Unauthenticated Backend Endpoints

**Parent:** EPIC-009 (Trust, security and auditability) — cross-cutting API hardening
**Classification:** V1 security hardening
**Status:** ✅ Merged into `feat/restart-from-scratch` (2026-07-28, merge commit `e5cb64a`) —
adversarial review (93/100, Pass) + functional QA (GO) passed; done.
**Priority:** High
**Branch:** `task/TASK-BE-019-endpoint-auth`
**Surfaced by:** full adversarial code+doc review 2026-07-28
(`docs/architecture/reviews/full-adversarial-review-2026-07-28.md`, blocking finding).
**Relates to:** `ConverseController`/`ConverseStreamController` (the existing optional
`x-api-key` gate), TASK-BE-012 (error contract), ADR-0010 (industrialization: contracts
+ security before real channels).

### Context

Only `POST /api/conversation/converse` and `/converse-stream` honour the optional
`x-api-key` gate (and only when `CONVERSATION_API_KEY` is set). The following endpoints
have **no authentication at all**:

- `POST /api/knowledge/ingest` and `POST /api/knowledge/sync` — **write** to the vector
  store (an unauthenticated write surface / KB-poisoning + DoS vector);
- `POST /api/conversation/answer` and `POST /api/conversation/retrieve` — read the RAG
  surface (retrieval can echo full KB chunk text, a data-exposure surface).

When `CONVERSATION_API_KEY` is empty, `authorized()` also returns true for any/missing
header, so nothing is protected. This is acceptable for a strictly localhost pilot but
is a blocking exposure for any non-localhost deployment.

### Objective

Bring every state-changing and evidence-reading endpoint under the same auth boundary
as `/converse`, or bind them to an internal-only network surface, and make the failure
mode explicit (fail-closed) — without breaking the localhost pilot.

### Scope

- Apply the existing `x-api-key` check (or a shared filter/interceptor) to
  `/api/knowledge/ingest`, `/api/knowledge/sync[/{sourceType}]`,
  `/api/conversation/answer`, `/api/conversation/retrieve`.
- Decide and document the empty-key behaviour: either **fail-closed** (reject when no key
  is configured) or explicitly bind these routes to localhost/internal for the pilot;
  record the decision (short ADR note or in this ticket).
- Return the sanitized `ErrorResponse` (TASK-BE-012) `401`/`403` with `correlation_id`,
  never a stack/verbose body.
- Keep OpenAPI (TASK-BE-016) accurate: mark the newly-gated endpoints with the
  `x-api-key` security scheme.

### Acceptance

- An unauthenticated call to `/api/knowledge/ingest`, `/sync`, `/answer`, `/retrieve`
  (with a key configured) returns a sanitized `401/403`, not a 200.
- The localhost pilot path still works with the configured key (or documented
  localhost binding).
- `@WebMvcTest` security tests cover each newly-gated endpoint (authorized + rejected).
- `mvn test` + ArchUnit green; OpenAPI reflects the security scheme.

### Notes

- Not RAG/LLM behaviour — purely the transport auth boundary; keep domain/application
  layers free of transport concerns (gate in `shared/web`).
- Runtime-affecting (adds a rejection path): record a `guardrail`/auth-reject outcome or
  structured log with the correlation id so QA can observe rejections.

### Implementation notes (2026-07-28)

Delivered on `task/TASK-BE-019-endpoint-auth` (branched from `feat/restart-from-scratch`):

- **Central gate in `shared/web/security`** (no transport concern leaks into
  domain/application):
  - `ApiKeyGuard` — a plain (non-Spring) class holding the single shared-secret rule
    (`apiKey == null || blank || equals(provided)`), so `/converse` and the newly-gated
    paths share one definition of "authorized".
  - `ApiKeyAuthInterceptor` (`HandlerInterceptor`) — reads `x-api-key`, delegates to
    `ApiKeyGuard`, and on failure writes the sanitized `ErrorResponse` (**401 `ERR_401`**,
    generic message, `correlation_id`) via the configured `ObjectMapper` **before** any
    use case runs. Logs a privacy-safe `[AUTH] rejected … method/path/correlation_id`
    (no header value) so QA can observe rejections.
  - `WebSecurityMvcConfig` (`WebMvcConfigurer`) — registers the interceptor on
    `/api/knowledge/**`, `/api/conversation/answer`, `/api/conversation/retrieve`. Reads
    the key via `@Value` and builds `ApiKeyGuard` itself (no injected `@Component`) so the
    auto-loaded `WebMvcConfigurer` resolves cleanly under every `@WebMvcTest` slice.
- **Empty-key decision (documented):** kept the **existing pilot semantics** — an empty
  `voice-support.conversation.api-key` (`CONVERSATION_API_KEY`) leaves the endpoints open
  (localhost pilot),   and any configured key is enforced identically across `/converse`
  and the four newly-gated endpoints. This is consistent with `/converse` (ADR-0021) and
  does not break the dev/localhost KB-sync flow. **Any non-localhost deployment MUST set
  `CONVERSATION_API_KEY`** — documented in `application.yml` and this ticket (ADR-0021 owns
  the `/converse` gate this reuses). (Full fail-closed
  by default is intentionally deferred to avoid diverging from the converse contract and
  breaking the pilot; revisit if/when a hardened default profile is introduced.)
- **Converse endpoints** kept their own inline gate (same rule) and their documented
  **empty-body** 401 to avoid touching already-tested controllers; the newly-gated paths
  use the richer `ErrorResponse` 401 body. This minor body-shape difference is noted for a
  future unification.
- **OpenAPI (TASK-BE-016) updated:** `/answer`, `/retrieve` and all `/api/knowledge/*`
  operations now document the **401** response (`ErrorResponse` schema); the existing
  `x-api-key` security scheme already covers the header.
- **Tests (`mvn test` 312 green, +7):** `ProtectedEndpointsApiKeyTest` (`@WebMvcTest` over
  Answer/Retrieval/Knowledge controllers) proves each path is rejected **401 + `error_code`**
  without a key and with a wrong key, accepted **200** with the matching key, and that the
  use cases never run on a rejected request (fakes throw if invoked). All pre-existing slice
  tests stay green (gate open-by-default when no key is set), ArchUnit OK.

### Adversarial review remediation (2026-07-28)

Self-review before QA (adversarial-code-review skill, score **93/100**, QA gate **Pass**). Two
non-blocking findings fixed in-loop:

- **Constant-time key comparison:** `ApiKeyGuard.authorized` now uses
  `MessageDigest.isEqual(...)` instead of `String.equals` — a plain equals short-circuits on the
  first differing byte and leaks the shared secret through response timing on a security gate.
- **Dead code:** removed the unused `isEnforced()` helper (YAGNI).

Remaining non-blocking (accepted): the converse endpoints keep their empty-body 401 vs the new
paths' `ErrorResponse` 401 (documented, future unification); CORS preflight `OPTIONS` is not a
concern (server-to-server callers, no browser CORS on these routes). `mvn test` **312** green.

### QA validation (2026-07-28)

QA (skill `qa-functional-latency`) — **GO**, functional + live smoke passed:

- **Live gate smoke** — a dedicated backend instance on port `8081` (`CONVERSATION_API_KEY=s3cret`,
  real pgvector + Ollama + Mistral; the running `8080` instance untouched):
  - `POST /api/conversation/answer`, `/retrieve`, `/api/knowledge/sync` **without** key → **401**;
    wrong key → **401**.
  - `POST /api/conversation/retrieve` with the valid key + valid body → **200** (full RAG path);
    `/converse` no-key → **401**, good-key → **200** (pre-existing gate intact, no regression).
  - Unauthenticated surfaces stay open: `actuator/health` → **200**, `v3/api-docs` → **200**
    (no over-gating).
  - 401 body sanitized: `{"error_code":"ERR_401","message":"…","correlation_id":"…"}` — no secret
    leak, correlation id present.
- **Regression automation** — `ProtectedEndpointsApiKeyTest` **7/7** green (interceptor exercised
  through the real MVC stack; confirmed live that the interceptor is wired in the full app context,
  not just the `@WebMvcTest` slice).
- **Latency** — transport-layer header check + constant-time compare is sub-ms and not a measured
  ADR-0018 pipeline slice; 401s short-circuit **before** LLM/DB (faster-failing than the open path).
- **Residual (non-blocking):** `/converse` empty-body 401 vs new-endpoints' `ErrorResponse` 401
  (cosmetic; future unification).

---

## TASK-BE-017 — Backend Support For Voice Latency Levers (Warm-Up Path + Vetted-Stream Contract Confirmation)

**Parent:** EPIC-005 (Answer engine) — perceived-latency support for EPIC-010
**Related decisions:** ADR-0037 (voice latency levers), ADR-0013 (guarded-sentence SSE streaming),
DEC-002 (no invented / ungrounded amounts), ADR-0029 (pilot latency criterion)
**Depends on:** — (backend already has `converse-stream` + grounding/guardrail pipeline)
**Blocks:** TASK-WEB-020 (lever 1 confidence-at-open, optional), TASK-WEB-021 (lever 2 warm-up)
**Classification:** V1 pilot gate (perceived latency — backend side)
**Status:** ✅ **Validated by user 2026-07-31** (Sprint 10, branch
`task/TASK-BE-017-voice-latency-support` off `feat/sprint-10-pilot-latency`; created
2026-07-29 as the backend dependency of the TASK-WEB-020/021 voice latency levers).
**Delivered:** (1) warm-up path — `WarmUpUseCase` (port in) + `WarmUpResult` (VO) +
`WarmUpService` (exercises embedding via `KnowledgeRetrievalPort.retrieve` + LLM via a
dummy converse; embedding/LLM failure non-blocking, recorded as a warm-up miss; records
`warmup_embedding`/`warmup_llm` latency slices; no memory/history side-effect) +
`POST /api/conversation/warm-up` (`WarmUpController`/`WarmUpResponse`, body-less), wired as
a `@Bean` in `ConversationConfig`; (2) vetted-stream contract confirmation — investigation
found `converse-stream` already emits vetted-only, locked with an incremental-delivery
contract test in `StreamingConversationServiceTest` (first vetted sentence reaches the
consumer before the whole answer; blocked → safe hand-off terminal chunk) plus
`GuardedSentenceEmitterTest` cases. **Checks re-run 2026-07-31: `mvn test` 320 green
(0 fail/err), ArchUnit OK** (`WarmUpServiceTest` 5, `WarmUpControllerTest` 2). Mechanism
proven live 2026-07-30 (`voice.backend.warmup=success` against the real backend in the
combined lever-1+2 pass). Optional early-confidence/grounding signal **deferred** (levers 1
& 2 do not need it — DEC-002 already enforced per sentence). **Merge-ready — merge on the
user's explicit request.**
**Priority:** High

### Objective

Provide the two backend-side supports the voice latency levers need: (1) a **cheap warm-up path**
so the runtime can pre-warm the LLM + embedding models on WebRTC connect (lever 2), and (2) a
**confirmed, contract-tested "vetted-only" guarantee** on the streaming answer so the runtime can
safely speak sentence-by-sentence (lever 1) — plus, if TASK-WEB-020 needs it, expose the
grounding/confidence verdict early enough to preserve the confidence policy before the first spoken
sentence.

### Context (code reality — investigated 2026-07-29)

- `POST /api/conversation/converse-stream` (SSE, ADR-0013) **already** emits `chunk` events one
  **guardrail-vetted sentence at a time**: `GuardedSentenceEmitter` grounds first, checks the
  output guardrail on each sentence **before** emission, and stops + emits the safe hand-off on a
  blocked sentence. So DEC-002 is already enforced on the stream; lever 1's contract exists.
- The **confidence** returned today arrives on the terminal `done` event; the grounded confidence
  is a grounding-time value (`bestScore(evidence)`) known **before** the first token — so it can be
  surfaced earlier if lever 1 needs a pre-speech confidence gate.
- There is **no warm-up path**: the first grounded turn pays cold LLM + embedding latency (part of
  the ≈ −450 ms turn-1 penalty the live baseline shows).

### Scope

- **Warm-up path (lever 2 dependency):** a lightweight, side-effect-free way to warm the LLM and
  embedding models (e.g. a tiny warm request) that the voice runtime can trigger on connect. It
  must not pollute conversation memory, must be cheap, and must be safe to call repeatedly.
- **Vetted-stream contract confirmation (lever 1 dependency):** an explicit **contract test**
  asserting no `chunk` is emitted before grounding + per-sentence guardrail vetting, and that a
  blocked sentence stops the stream and yields the safe hand-off — locking the DEC-002 invariant the
  voice path will now rely on for early speech.
- **(Conditional) early confidence/grounding signal:** if TASK-WEB-020 decides it needs the
  confidence/grounded verdict before speaking the first sentence, expose it at stream open (or on a
  first metadata event) without changing the existing `chunk`/`done`/`error` semantics.
- OpenTelemetry: warm-up path is observable (outcome, duration, correlation id) and clearly
  distinguishable from real turns; no secret logged.

### Out Of Scope

- The voice-runtime wiring of warm-up / streaming consumption (TASK-WEB-020 / TASK-WEB-021).
- Any change to grounding, guardrail or confidence **logic** (only exposure/warm-up, not policy).
- Provider swaps.

### Acceptance Criteria

```gherkin
Scenario: The backend can be warmed without side effects
  Given the models are cold
  When a warm-up is requested
  Then the LLM and embedding models are exercised so the next real answer is warm
  And no conversation memory or user-visible state is changed by the warm-up
```

```gherkin
Scenario: The streamed answer never emits unvetted content
  Given a streamed answer whose second sentence would state an unsupported amount
  When the answer is streamed
  Then only vetted sentences are emitted before it
  And the blocked sentence stops the stream and the safe hand-off is emitted, per DEC-002
```

### Required Evidence

- Unit/integration tests (manual fakes, no Mockito): warm-up path (no memory side effect,
  repeatable), and the vetted-stream contract test (no chunk before vetting, blocked-sentence
  hand-off). If the early confidence signal is added: a test that it matches the `done` verdict.
- `mvn test` green + ArchUnit OK; OpenAPI updated if a new endpoint is added.
- Docs: `voice-runtime-http-contract.md` (contract the runtime consumes) + ADR-0037 evidence.
- No secret / raw provider text leak in warm-up telemetry.

## TASK-BE-020 — Shorten Time-To-First-Vetted-Sentence In The Backend Answer Stream (Latency Lever)

**Parent:** EPIC-010 (+ EPIC-005)
**Related decisions:** ADR-0029 (pilot latency criterion — this lever helps close it),
ADR-0013 (backend SSE guarded-sentence streaming), ADR-0037 (first-sentence streaming to TTS),
DEC-002 (no invented / ungrounded amounts — must stay enforced per sentence)
**Related stories:** US-036 (per-slice timing)
**Depends on / follows:** TASK-WEB-020 (lever 1) validated — the runtime now speaks on the
first vetted sentence, so the backend's time-to-first-vetted-sentence is directly on the
critical path.
**Classification:** V1 pilot gate (perceived latency)
**Status:** To do (future improvement, out of Sprint 10 scope). Created 2026-07-31 from the
TASK-WEB-020 cold/combined live passes.
**Priority:** Medium

### Objective

Reduce the `backend_first_token` slice = the time for `converse-stream` to emit its **first
vetted sentence** (`GuardedSentenceEmitter`: grounding + output guardrail before the first
`chunk`). After levers 1 + 2 it is the dominant residual contributor to the ADR-0029 gap:
measured live 2026-07-31 at p50 **~733 ms** / p95 **~1052 ms** (warm-steady), and it is the
slice that spikes to ~2042 ms on a cold turn without warm-up.

### Scope

- Profile the first-sentence path server-side: LLM time-to-first-sentence (Mistral streaming vs
  whole-answer), RAG/pgvector retrieval, guardrail + grounding first-hit cost, and any
  per-request setup on the converse-stream worker.
- Levers to evaluate (non-exhaustive): stream tokens from the LLM and vet as soon as the first
  sentence boundary is reached; bias the answer prompt toward a short, high-value first
  sentence; cache/prewarm the RAG + guardrail first-hit path (ties into TASK-BE-017 warm-up —
  consider a full dummy converse at warm-up so RAG/guardrail JIT off the critical path);
  overlap retrieval with generation where safe.
- **DEC-002 stays enforced per sentence** — no sentence may be emitted before it is grounded +
  guardrail-vetted; the safe hand-off terminal behaviour is unchanged.

### Acceptance Criteria

- A measured before/after (backend micro-benchmark on `converse-stream` first-sentence time +
  a live streaming pass) showing the `backend_first_token` reduction, warm and cold.
- The mouth-to-ear composite re-evaluated against ADR-0029 with this lever combined with
  levers 1 + 2 (+ TASK-STT-014).
- DEC-002 preserved: contract test still proves no chunk is emitted before vetting; grounded /
  blocked-sentence behaviour unchanged. `mvn test` green + ArchUnit OK; no secret / raw
  provider text leak in telemetry.
