# Adversarial Code Review — Java Backend (pre-sprint cleanliness gate)

- **Date:** 2026-08-28
- **Reviewer skill:** `.cursor/skills/adversarial-code-review` (+ `code-guidelines`, `test-guidelines`, `java-backend-developer`)
- **Repo:** `voice-support-bot` (separate git repo)
- **Branch:** `feat/sprint-12-external-voice-websocket` (read-only; no branch switch, no edits, no commit)
- **Target:** everything under `backend/` (`com.voicesupport` conversation engine + knowledge context + shared)

---

## Scope

Reviewed the full backend as requested:

- Domain purity (no Spring in `..domain..`), ports `in`/`out`, `@Bean` wiring in `ConversationConfig` / `LlmConfig` / `KnowledgeConfig`.
- RAG: `PgVectorStoreAdapter` (metadata, fail-closed audience + domain filter), embeddings (Ollama), retrieval/grounding services.
- Guardrails: `InputGuardrail`, `RetrievalConfidenceGuardrail`, `OutputGuardrail` (DEC-002), and streamed per-sentence `GuardedSentenceEmitter`.
- Confidence policy (three-band), conversation memory (in-memory + Redis).
- Endpoints: `converse`, `converse-stream`, `answer`, `retrieve`, `warm-up` and their controllers/sessions.
- `WarmUpService` (BE-017 sync warm-up + BE-020 streaming-path warm-up) and its wiring.
- Liquibase changelogs (app master vs superuser bootstrap; `vector_store` DDL parity with Spring AI 1.0.0).
- Security: constant-time api-key gate, sanitized errors, log-injection defenses.
- OpenTelemetry-style instrumentation (`BackendTelemetry`, `CorrelationId`, per-slice timings).
- LLM/embedding provider ports (Mistral chat / Ollama embeddings) and the TASK-BE-033 provider work.

## Method

- Read the four mandatory skills first, then read the actual source (not assumptions) via Grep/Glob/Read across all 106 main files.
- Static checks: class/method size ranking, nesting, `TODO/FIXME/HACK`, `System.out`/`printStackTrace`, Spring imports in `..domain..`, REST mappings, secrets in `application.yml`, thread-safety (defensive copies) of caches/memory.
- Cross-checked the `CLAUDE.md` / `AGENTS.md` "issues historically hit" list for regressions (LLM history placement, greeting/duplication, `conversation_id` snake_case, DEC-002 amount-collision, Liquibase DDL drift, DNS negative-TTL, channel cardinality, CR/LF log injection).
- **Test run (read-only):** `cd backend && mvn -q test` → **BUILD SUCCESS**, exit 0.
  Aggregated Surefire: **403 tests run, 0 failures, 0 errors, 0 skipped** across **56 test classes** (includes ArchUnit + Cucumber BDD + Liquibase parity + schema/security slices). The single stack trace visible in the log is the deliberate degraded-path assertion in `ConverseDegradedTest` / `GlobalExceptionHandler` (logged, not a failure).

## Overall score

**96 / 100**

## Verdict

**CLEAN** — the backend is ready for the next sprints. No blocking or major findings; only minor/advisory items and one task-premise clarification.

---

## Blockers (must-fix)

None.

## Majors

None.

## Minors

| # | Severity | Finding | Evidence | Remediation |
|---|----------|---------|----------|-------------|
| M1 | Minor (accepted) | REST paths use action verbs, deviating from the mandatory "no verbs in paths" guideline. | `RetrievalController.java:45` `/retrieve`, `AnswerController.java:39` `/answer`, `ConverseController.java:56` `/converse`, `ConverseStreamController.java:55` `/converse-stream`, `WarmUpController.java:38` `/warm-up`, `KnowledgeController.java:47,76,87` `/ingest`,`/sync`. | Keep as-is: these are the documented RPC-style voice-runtime contract routes (CLAUDE.md), consumed by the Python bridge. Renaming would break the runtime contract with no functional gain. Record as accepted residual risk; do not "fix" opportunistically. |
| M2 | Minor | `@Configuration` wiring classes approaching the 200-line class budget. | `KnowledgeConfig.java` = 198 non-blank lines; `ConversationConfig.java` = 172. | Config classes are a reasonable size exemption, but `KnowledgeConfig` is one bean away from the ceiling. Split by cohesion (e.g. connector beans vs sync/scheduler beans) the next time a bean is added there. |
| M3 | Minor (clarification) | The review brief refers to "the OpenAI adapter added for TASK-BE-033" — no such adapter exists in the backend. | `LlmConfig.java:32` `SUPPORTED_PROVIDERS = {"mistral-api","ollama"}`; no `openai` symbol anywhere in `src/main`. TASK-BE-033 shipped as an **external provider benchmark** (`scripts/llm_benchmark/`, currently untracked) — not a backend adapter. | No code action. Flagged so the next sprint plan does not assume an in-tree OpenAI provider. If OpenAI is later wanted in-runtime, add it as a third `AbstractChatClientAnswerAdapter` subtype behind the same `voice-support.llm.provider` switch (the abstraction already supports it). |
| M4 | Minor | Local dev DB password default is hardcoded in config. | `application.yml:8` `password: ${DB_PASSWORD:voicesupport}`. | Acceptable: it is an env-overridable local default and the pilot deploy injects a vaulted `DB_PASSWORD`. Keep ensuring prod/pilot never runs on the default (already the case). No change required. |
| M5 | Minor | `BoundedLlmCall` hard-codes `MAX_LLM_THREADS = 16` while the sibling SSE pool is env-configurable. | `BoundedLlmCall.java:23` vs `ConversationConfig.java:176` (`sseStreamExecutor` reads `stream.max-threads`). | Optional consistency: promote the sync-LLM ceiling to a property if pilot load ever needs tuning. The value is documented and matches the SSE default, so this is advisory only. |

## Concrete remediation per finding

- **M1** — no edit; add an "accepted residual risk: RPC contract routes" line to the sprint's review notes so it is not re-raised.
- **M2** — when adding the next `@Bean` to `KnowledgeConfig.java`, extract a second `@Configuration` (e.g. `KnowledgeConnectorsConfig`) to stay under 200 lines.
- **M3** — none (documentation/expectation only).
- **M4** — none (verify deploy sets `DB_PASSWORD`, already vaulted).
- **M5** — optional: `BoundedLlmCall.java:23` → read from a property mirroring `voice-support.conversation.stream.max-threads`.

---

## What was verified clean (evidence)

- **Domain purity:** zero `org.springframework` / `jakarta` / Spring-annotation imports under `..domain..` (grep clean); enforced by `HexagonalArchitectureTest` (`domainShouldNotUseSpring`, `domain→infra/app` forbidden, `noFieldInjection`, ports are interfaces, value objects are records/final). All green.
- **Hexagonal wiring:** every domain service is a pure class registered via `@Bean` (`ConversationConfig`, `KnowledgeConfig`); no `@Service`/`@Component` in domain.
- **Security:** `ApiKeyGuard.authorized` uses constant-time `MessageDigest.isEqual` and **fails closed** (`ApiKeyGuard.java:22-32`); central `ApiKeyAuthInterceptor` gates `knowledge/**`, `answer`, `retrieve`, `warm-up`; `converse`/`converse-stream` keep their own inline gate with the same rule. Sanitized `ErrorResponse` never echoes `ex.getMessage()` (`GlobalExceptionHandler.java`); client-controlled `correlation_id`/`channel`/`conversation_id` are run through `CorrelationId.sanitize` (ISO-control strip + 200-char cap) before logging / response headers — CR/LF log-injection & header-splitting closed (`CorrelationId.java:26-39`).
- **DEC-002 (no fabricated amounts):** enforced on the sync path (`AnswerService.java:66`) and, critically, per-sentence on the streamed path before emission (`GuardedSentenceEmitter.emit`). The amount-collision regression is fixed — `OutputGuardrail.canonical` keys on `(currency, 2-dp value)`, not a digit-only strip.
- **Observability:** `BackendTelemetry` emits per-slice Micrometer timers with p50/p95/p99, prompt/answer size distributions, answer-language and guardrail-block counters, and structured logs carrying the correlation id; **no transcript/answer text or secrets** in tags/logs; `channel` tag is bounded to an allow-list to cap cardinality. First-token vs full-stream latencies recorded separately; interrupted/timeout outcomes kept distinct so p95 isn't skewed.
- **Failure modes:** LLM sync bounded by executor + backstop timeout → sanitized 503; streaming bounded by Reactor inter-signal timeout → distinct `timeout` outcome; SSE pool rejects beyond the ceiling → 503 (no unbounded queueing); Redis memory outage degrades to empty history with a `*.degraded` counter rather than failing the turn; DNS negative-TTL hardened (BUG-014).
- **Memory thread-safety:** `InMemoryConversationMemoryAdapter` synchronizes on the backing LRU map and returns `List.copyOf(...)` (no cache leak); Redis adapter tolerates a single corrupt entry.
- **Warm-up correctness:** `WarmUpService` takes **no `ConversationMemoryPort`** (structurally side-effect-free), discards output, never throws (records a warm-up miss), and warms embedding + sync LLM + reactive stream path; a null streaming generator disables the stream warm-up without penalizing `fullyWarmed` (`WarmUpService.java:86-99`). Endpoint always returns 200.
- **Liquibase:** app master runs only `001-vector-store` + `002-kb-source-state` (no privileged changeset at startup); superuser bootstrap is separate; `vector_store` DDL is byte-for-byte Spring AI 1.0.0 (`metadata json`, `vector(768)`, HNSW cosine) with a `not tableExists / MARK_RAN` guard, all locked by `LiquibaseChangelogTest`.
- **Providers replaceable:** chat behind `AnswerGeneratorPort` + `StreamingAnswerGeneratorPort` via `AbstractChatClientAnswerAdapter`; Mistral/Ollama selected by `voice-support.llm.provider` with fail-fast validation (`LlmConfig.validateProvider`); embeddings pinned to Ollama (Mistral chat/embedding/moderation auto-configs excluded in `VoiceSupportApplication`).
- **Hygiene:** no `TODO/FIXME/HACK`, no `System.out`/`printStackTrace`, no method/class over budget except the config note in M2, no `list.get(index)` data access, snake_case JSON via global Jackson config.
- **Historical-regression sweep:** none of the CLAUDE.md/AGENTS.md "issues historically hit" recurred (LLM history in system message, first-message greeting logic, `conversation_id` snake_case, amount-collision, Liquibase drift + `commons-io` pin, channel cardinality, CR/LF injection all still handled).

## Residual risk accepted

- **M1** RPC-style verb routes are intentional and load-bearing (voice-runtime contract); renaming is out of scope and would break the pilot. Accepted.
- **M3** No in-tree OpenAI adapter — expected; provider comparison lives in the external benchmark. Accepted.
- **M4** Dev-only DB password default, env-overridden in deploy. Accepted.
- **M2 / M5** advisory maintainability items, no functional risk. Accepted for now.

## QA gate

**Pass.** The backend is clean for the next sprints (no blockers, no majors, 403/403 tests green). Recommend addressing M2 opportunistically (Boy Scout Rule) and clarifying the M3 expectation in sprint planning.
