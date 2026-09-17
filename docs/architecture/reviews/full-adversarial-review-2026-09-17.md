# Full Adversarial Review — Code + Documentation (2026-09-17)

**Scope:** whole-branch adversarial review of `feat/restart-from-scratch` right after the Sprint 15
closure (OpenAI `gpt-5` added as a third LLM chat provider **and made the default**, TASK-BE-049 /
TASK-BE-050). Covers the Java backend (`backend/`), the Python voice runtime (`voice-agent/`), and
the documentation/backlog set (`docs/`, root `README.md`/`CLAUDE.md`/`AGENTS.md`, `deploy/`,
`product-backlog/`).

**Method:** applied `.cursor/skills/adversarial-code-review` (score 0–100, QA gate) and
`.cursor/skills/adversarial-architecture-review` (score 0–5 per dimension). Evidence separated into
**proven by code/tests** vs **only stated in docs**. Backend test suite executed both dirty and
`clean`.

**Reviewers:** parent synthesis over three evidence-gathering explorations
([Backend code evidence](4d7a2ba3-9096-4144-ac74-86776db2c01b),
[Voice runtime evidence](7232ba0c-0827-4290-9eb1-442e609fedc6),
[Documentation drift evidence](51d343a6-a30a-4523-9718-1870d4429bc5)).

---

## Verdict

**Proceed with conditions.**

- The **code** is sound: the LLM provider seam (DEC-011) is now a genuine 3-provider swap behind
  `AnswerGeneratorPort`/`StreamingAnswerGeneratorPort`, DEC-002 grounding is enforced pre- and
  post-LLM, failure modes are bounded, observability is per-provider, and `mvn clean test` is green.
- The **dominant risk is documentation/config drift**, not behaviour: the default-provider flip to
  OpenAI is invisible in ~15 authoritative docs (still "Mistral is the default"), and **no deploy
  path ships `OPENAI_*` config**, so any environment relying on the new default without
  `LLM_PROVIDER=mistral-api` will 401 on the first LLM call. This is shippable but must be corrected
  before the next deploy and before onboarding anyone off these docs.
- Two decisions were shipped **without an ADR/DEC** (BE-050 default flip) — a process gap for a
  runtime-affecting change.

---

## Part A — Code Review (skill: adversarial-code-review)

### Satisfaction Score

**Score: 88/100**
**QA gate: Pass (with conditions)** — no core functional bug; conditions are the CI-hygiene fix (A1)
and the documentation/deploy drift in Part C, which is tracked separately and does not change code
behaviour.

> The isolated Sprint 15 change (BE-049) was reviewed at **94/100** in
> `docs/qa/task-be-049-openai-provider-review.md` and is confirmed here. The 88 is the **full-branch**
> code score, reflecting pre-existing debt surfaced by a complete pass.

### Blocking / High Findings

| Sev | Finding | Evidence | Required fix |
|---|---|---|---|
| **Medium** | `mvn test` (without `clean`) **FAILS**: `RunKnowledgeBddTest` → 46 scenarios / **10 errors** (undefined steps). Root cause is a **stale, gitignored build artifact** `backend/target/test-classes/features/billing-explanation.feature` (no matching feature under `src/test/resources/features/`, no `BillingExplanationSteps` glue) — most likely copied into `target/` during an earlier build on the billing branch and never cleaned. `mvn clean test` is **green (exit 0, 470 tests)**. | `/tmp` run: `MVN_EXIT=1`, `Errors: 10` on `RunKnowledgeBddTest`; `find` shows the feature only under `target/`; `git check-ignore` confirms `target/` ignored; `mvn clean test` → `CLEAN_EXIT=0` | Make the Cucumber runner robust to stale `target/` (scan `src/test/resources/features` explicitly, or add a `clean` in CI, or fail-on-undefined only for known glue). Correct the closure-note wording: the 10 errors are **not** "pre-existing on mainline source" — they are a local dirty-`target` artifact. |

There are **no core functional-bug blocking findings**. The remaining items are non-blocking.

### Non-Blocking Findings

| Sev | Finding | Evidence | Recommendation |
|---|---|---|---|
| Med | **Non-currency hallucination is not output-guarded.** `OutputGuardrail` only rejects (a) currency amounts not present in evidence and (b) refusal/non-answer markers, plus retrieval-confidence gating. Invented **dates, plan names, procedures, phone numbers** can pass. Acceptable for KB-grounded QA (amounts are the main money risk and are covered), but a real exposure for the future billing core. | `OutputGuardrail.java:29-39` (amount set match); `isNonAnswer` `:46-58` | Track as a hardening ticket before billing V1; consider evidence-span attribution or a broader claim-check. |
| Med | **Provider-selection wiring is untested.** No `@SpringBootTest` anywhere; nothing asserts that `@ConditionalOnProperty` actually activates the OpenAI/Mistral/Ollama bean for a given `voice-support.llm.provider`. Only adapter unit tests exist (and only OpenAI has a provider-name test). | no `@SpringBootTest` in `backend/`; `OpenAiAnswerAdapterTest` only | Add a lightweight `@SpringBootTest(properties="voice-support.llm.provider=openai")` context smoke per provider (or a slice test on `LlmConfig`) so a wiring regression is caught. |
| Low-Med | **DEC-002 system prompt triplicated** (byte-identical) across `MistralAnswerAdapter`, `OllamaAnswerAdapter`, `OpenAiAnswerAdapter`. A DEC-002 wording change now needs 3 edits; `OutputGuardrail` matches hand-off wording, so drift is a correctness risk, not just style. | `MistralAnswerAdapter.java:16-31` ≡ `OpenAiAnswerAdapter.java:19-33` (≡ Ollama) | Extract a shared voice-prompt constant (e.g. `VoiceSystemPrompt`); each adapter overrides only `providerName()`. Already flagged in the BE-049 review as a follow-up. |
| Low-Med | **Stale code comments contradict the shipped default.** `VoiceSupportApplication` header and `MistralAnswerAdapter` class comment still call Mistral the "(development) default". | `VoiceSupportApplication.java:18-21`; `MistralAnswerAdapter.java:6-7` | One-line comment fixes alongside the doc sweep (Part C). |
| Low | **4 production classes exceed the 200-line guideline.** `ConversationConfig` (238), `KnowledgeConfig` (214), `BackendTelemetry` (212), `ConverseStreamSession` (204). `InputGuardrail.check` ≈ 21 lines (>20). | file line counts | Soft breach; split configs by concern when next touched. |
| Low | **Telemetry channel allow-list mismatch.** `BackendTelemetry` default CSV includes `genesys`; `application.yml` default omits it → Genesys metrics may collapse to tag `other`. | `BackendTelemetry.java:44` vs `application.yml:319` | Align the `application.yml` default with the code default. |
| Low | **No explicit cross-tier `traceparent` handling in the backend.** The voice tier derives a deterministic `traceparent` and injects it; the backend relies on the Micrometer→OTel bridge default propagation, with no test asserting continuity. | no `traceparent` refs in `backend/src/main`; voice `trace_context.py` | Add one assertion that an inbound `traceparent` is continued (or document the reliance explicitly). |
| Low | **Fail-open API key + empty 401 body on converse.** Empty `CONVERSATION_API_KEY` opens all endpoints (intentional for local); `/converse*` 401 returns an empty body while interceptor paths return `ErrorResponse`. | `ApiKeyGuard.java:23-24`; `WebSecurityMvcConfig.java:12-13` | Deployment guardrail: assert a non-empty key in every non-local env; unify the 401 body shape. |

### Story / Change Coverage (Sprint 15)

| Criterion | Covered? | Evidence |
|---|---|---|
| `openai` selectable, no domain change | ✅ | `LlmConfig` conditional beans; adapter-only change |
| OpenAI is now the default | ✅ | `application.yml:269` `${LLM_PROVIDER:openai}`; `LlmConfig:100,163` `matchIfMissing=true` on OpenAI |
| Mistral/Ollama still selectable | ✅ | conditional beans on `mistral-api`/`ollama` |
| Embeddings stay Ollama (768d) | ✅ | OpenAI embedding auto-config excluded |
| Grounded DEC-002 prompt | ✅ | `OpenAiAnswerAdapterTest.usesGroundedDec002Prompt` |
| `reasoning_effort=minimal` latency lever | ✅ | `LlmConfig.openAiChatModel` blank-guard; ~2.6 s→~0.95 s (ticket) |
| Build green | ⚠️ | `mvn clean test` green; **dirty `mvn test` red** (finding A1) |

### Observability & Failure Modes (confirmed strong)

- Per-provider slices `llm_wording` / `llm_first_token` tagged via `providerName()` → OpenAI is
  benchmarkable with zero extra code (`AbstractChatClientAnswerAdapter.java:64-65,97-105`).
- Bounded LLM call (`BoundedLlmCall`) + reactive stream `timeout` → `UpstreamUnavailableException`
  → 503 `ERR_UPSTREAM`, no upstream text echoed (`GlobalExceptionHandler`).
- `WarmUpService` never throws; records a miss instead — cannot block the first turn.
- Voice runtime: bounded timeouts, session ceilings (WebRTC 8 / aiohttp WS 8 / interim 1 / Genesys
  3, WS 1013 refusal), `drain()` on teardown, interrupted-stream cleanup with
  `except asyncio.CancelledError` + `finally aclose()`.

### Voice-runtime code notes

| Sev | Finding | Evidence |
|---|---|---|
| Med | **BUG-018 reliability fixes are planning-only.** Turn wall-clock deadline (TASK-WEB-045) and guaranteed terminal control-signal + browser watchdog (TASK-WEB-046) are **not implemented**; a dropped connection can strand the streaming UI in "thinking". | no `VOICE_TURN_DEADLINE_MS` in `voice-agent/`; backlog rows "Planned (P1)"; `app.js` has no streaming watchdog |
| Low | **Stale comment** in `session_factory.py:281-282` ("unset → 500 ms") — the effective streaming default is **350 ms** (`PILOT_END_OF_TURN_SILENCE_MS`, always passed). | `session_factory.py:48-52,113-133` |
| Low | **Client-side confidence degrade duplicates a backend policy** (`VOICE_BACKEND_CONFIDENCE_THRESHOLD`). Not a business rule, but a second place to keep in sync. | `voice_pipeline/answer.py:52-55,164-180` |
| Info | Silero VAD still not integrated (energy/amplitude only) — known deferral (ADR-0025). Genesys native control mode idle; live-org AudioHook event map is a `TODO(live-measurement)`. | `genesys_barge_in_eot.py:25-30` |

---

## Part B — Architecture Review (skill: adversarial-architecture-review)

### Scorecard

| Dimension | Score /5 | Rationale |
|---|---:|---|
| NFR / SLA fitness | **3** | Latency honestly measured; ADR-0029 mouth-to-ear gate still **FAIL at the base** (~2.1–4.4 s p95 depending on pass), no production SLO claimed. Bounded timeouts everywhere. Gate remains open by design (DEC-015 decouple). |
| SLA failure modes | **3** | Strong: bounded LLM/stream/retrieval timeouts, degraded wording, warm-up never throws, session ceilings, drain. Gaps: BUG-018 stuck-UI fixes (WEB-045/046) planning-only; Genesys degraded modes (WEB-044) open; live-org fail-safe unproven. |
| Modularity & boundaries | **4** | Clean hexagonal backend; transport-agnostic voice `SessionFactory` (WebRTC/WS/Genesys as thin adapters); Genesys stays contact-center SoR, no business logic in the runtime. Minor: duplicated confidence policy client-side. |
| External dependency replaceability | **4** | LLM is now a **proven** 3-provider swap behind a port (Easy) — the headline improvement this sprint. Embeddings Ollama, STT/TTS Gradium, Genesys behind adapters. Not 5: provider selection untested at wiring level; deploy config only wires Mistral. |
| Evolvability & industrialization | **3** | Good seams and honest measurement, but a **runtime default was shipped without an ADR/DEC**, docs/deploy config diverge from code truth, and dirty-`target` breaks `mvn test` — industrialization discipline slipped. |
| **Overall** | **≈3.4** | Solid, evolvable MVP; corrective hygiene (docs, deploy config, decision record) needed before the next deploy. |

### External Dependency Review

| Dependency | Role | Replaceability | Concern | Recommendation |
|---|---|---|---|---|
| LLM chat (OpenAI/Mistral/Ollama) | Wording only | **Easy** (port + 3 adapters) | Wiring untested; only Mistral wired in deploy | Add wiring smoke tests; wire `OPENAI_*` in deploy |
| Embeddings (Ollama) | Vectorization 768d | Moderate (dimension-coupled) | Model swap = re-embed + re-DDL | Documented already |
| STT/TTS (Gradium) | Voice I/O | Moderate | Provider details in runtime adapters | OK for pilot |
| Genesys | Contact-center SoR / media | Moderate | Live-org legs unproven; native EOT/barge-in idle | OQ-006 live measurement |
| pgvector / Postgres | RAG store + memory | Moderate | Liquibase-owned schema, byte-parity with Spring AI | Schema-parity test exists |

### Hard Questions

1. Is OpenAI (Azure Foundry) the intended **pilot** default, or only the local/benchmark default?
   The app now defaults to OpenAI while the deploy stack pins Mistral — which is the source of truth?
2. Where is the ADR/DEC that records "OpenAI is the default"? A runtime provider change of this
   weight should be an accepted decision, not only `application.yml` comments + a task row.
3. What is the intended cost/latency posture of `gpt-5` + `reasoning_effort=minimal` vs Mistral for
   the pilot? The benchmark harness (ADR-0045 / TASK-BE-033) is still "Proposed".

---

## Part C — Documentation Review (the dominant finding)

The OpenAI default flip (BE-050) is **not reflected** across the authoritative docs, and the new
default is **not deployable** from the shipped config. Ground truth (code): `application.yml:269`
`provider: ${LLM_PROVIDER:openai}`, `LlmConfig:38,100,163`.

### C1 — "Mistral is the default" drift (STALE — P1)

| File:line | Stale statement |
|---|---|
| `README.md:73` | "Chat LLM = **Mistral** … default; Ollama alternative" (OpenAI absent entirely) |
| `CLAUDE.md:112` | "LLM/chat = **Mistral AI** … (`mistral-api` default) … Built manually in **`DomainServiceConfig`**" (also wrong: it's `LlmConfig`) |
| `AGENTS.md:97` | "Chat uses Mistral (API)…" (no OpenAI) |
| `docs/architecture/architecture.md:30,211-212,514,673` | "Chat = Mistral (default)"; provider table has no OpenAI row; "configurable: `mistral-api` by default, `ollama` alternative" |
| `docs/engineering/development-guide.md:112-113,202` | "Chat = Mistral … default"; sample comment "`# or mistral-api (default)`" |
| `docs/knowledge-base/knowledge-base-technical.md:50` | "(`mistral-api` default, `ollama` alternative)" |
| `voice-agent/README.md:316` | "Java answer engine … (Mistral chat + Ollama embeddings…)" |
| `docs/architecture/adrs/ADR-0006-…md:19-20` | "The default chat LLM is Mistral AI" (status still Accepted) |
| `docs/architecture/adrs/ADR-0031-…md:55` | "The two provider prompts (Mistral, Ollama)" (three now) |
| `product-backlog/decisions/v1-decisions.md:267,277-281,310-311` | DEC-011: "Mistral = development default", "OpenAI … live validation gated on credentials not yet available" (both now false — BE-049 live+E2E validated) |

### C2 — Deploy config cannot serve the new default (STALE / MISSING — P1, highest operational risk)

The app defaults to `openai`, but **no deploy path provides `OPENAI_*`**, and the deploy stack
silently overrides back to Mistral:

| File:line | Issue |
|---|---|
| `deploy/compose/backend/.env.example:41-44` | Only `LLM_PROVIDER=mistral-api` + `MISTRAL_*`; no `OPENAI_API_KEY`/`OPENAI_BASE_URL`/`OPENAI_CHAT_MODEL`/`OPENAI_REASONING_EFFORT` |
| `deploy/compose/backend/docker-compose.yml:28` | `LLM_PROVIDER: "${LLM_PROVIDER:-mistral-api}"` — **compose overrides the app default** (undocumented tension) |
| `deploy/ansible/roles/compose_tier/templates/backend.env.j2:23-25` | Renders `LLM_PROVIDER` + `MISTRAL_*` only — **cannot deploy OpenAI** without extending the template + vault |
| `deploy/ansible/group_vars/backend.yml:44-46` | `llm_provider: "mistral-api"` (fine as an explicit pin, but label says only "Mistral cloud") |
| `docs/operations/deployment-eir-ai4cc-tst.md:183`, `first-deploy-runbook.md:95,275`, `genesys-live-measurement-runbook.md:74` | Secrets/egress tables list `MISTRAL_API_KEY` only; no `LLM_PROVIDER`, no `OPENAI_*`, no Azure Foundry egress |
| root `.env.example:3-6,32-33` | `# LLM_PROVIDER=mistral-api` / `MISTRAL_*`; also still says backend "not runnable on this branch" |

**Consequence:** `mvn spring-boot:run` (or any env without `LLM_PROVIDER=mistral-api`) now starts on
OpenAI with an empty key/base-url → **401 / call to public `api.openai.com`** on the first turn.

### C3 — No decision record for BE-050 (MISSING — P1)

- No ADR and no new `DEC-*` records "OpenAI is the default". ADR-0045 (Mistral/OpenAI benchmark) is
  still **Proposed / deferred to TASK-BE-033** and benchmarks `gpt-4o-mini`, not `gpt-5`.
- DEC-011 wording still frames OpenAI as an unvalidated future target.

### C4 — Internal contradictions & stale review artifacts (STALE — P2)

| File:line | Issue |
|---|---|
| `product-backlog/sprints/sprint-15-llm-providers.md:30-31` vs `:39-44` | DoD says "Mistral remains the default" while the closure note (same file) says OpenAI is the default |
| `product-backlog/tasks/llm-provider-tasks.md:71-72` | BE-049 context: "two selectable LLM providers" (now three; historical, but reads as current) |
| `docs/qa/task-be-049-openai-provider-review.md:36` | "Mistral stays the default ✅" — true at BE-049, stale after BE-050 |
| `docs/qa/adversarial-review-2026-08-28-docs-architecture.md:152` | Cites `${LLM_PROVIDER:mistral-api}` as the matching current value |
| `docs/architecture/adrs/README.md:53-55` | Meta note "ADR-0046/0047 not present on this branch" — both files now exist (49 ADRs, index otherwise matches) |
| `docs/README.md:3-4` | "through Sprint 11" (Sprint 15 not reflected) |

### C5 — Confirmed OK

- ADR index count matches disk (49/49).
- `docs/` English-only rule holds (French only in intentionally quoted UI phrases/corpus).
- The Sprint 15 backlog rows that we authored are accurate: `application.yml:262-269`,
  `llm-provider-tasks.md` TASK-BE-050 section, `backlog-index.md` registry, sprint closure note.

---

## Recommended Changes (prioritized)

### 1 — Must fix before the next deploy / onboarding
1. **Deploy config for the new default (C2).** Add `OPENAI_API_KEY`, `OPENAI_BASE_URL`,
   `OPENAI_CHAT_MODEL`, `OPENAI_REASONING_EFFORT` to `deploy/compose/backend/.env.example`, the
   Ansible `backend.env.j2` template + `group_vars`/vault, and the runbooks — **or** make the
   explicit pilot pin (`LLM_PROVIDER=mistral-api`) a documented, deliberate decision. Resolve the
   app-default (openai) vs compose-default (mistral-api) source-of-truth question.
2. **Record the decision (C3).** Add an ADR (or a `DEC-*`) "OpenAI `gpt-5` is the default LLM
   wording provider"; update DEC-011 and move ADR-0045 forward (or supersede it) to match reality.
3. **Fix the CI/DX build (A1).** Make `RunKnowledgeBddTest` immune to a dirty `target/` (or clean in
   CI); correct the "pre-existing on mainline" wording in the closure note.
4. **Doc sweep (C1).** Update `README.md`, `CLAUDE.md`, `AGENTS.md`, `architecture.md`,
   `development-guide.md`, `knowledge-base-technical.md`, `ADR-0006`, `ADR-0031`, and the two stale
   code comments to state: three chat providers, OpenAI `gpt-5` is the default, built in `LlmConfig`.

### 2 — Should fix before pilot
5. Add provider-selection wiring tests (A: `@SpringBootTest(properties=…)` per provider).
6. Extract the shared DEC-002 voice prompt (remove triplication).
7. Align the telemetry channel allow-list (`application.yml` ↔ `BackendTelemetry`).
8. Resolve internal contradictions (C4): sprint-15 DoD, sprint/tasks "two providers", stale QA
   review notes, ADR-README meta note, `docs/README.md` sprint marker.

### 3 — Can defer safely
9. Implement BUG-018 reliability fixes (TASK-WEB-045/046) before claiming streaming-UI robustness.
10. Broaden `OutputGuardrail` beyond currency before the billing core (non-currency hallucinations).
11. Split the four >200-line production classes when next touched; fix the 350 ms EOT comment.

---

## Residual Risk If Accepted As-Is

- Any environment that starts the backend on the new default **without** `OPENAI_*` set (and without
  pinning `LLM_PROVIDER=mistral-api`) fails on the first LLM turn — the single highest operational
  risk from this sprint.
- A runtime default provider changed with no accepted decision record → weak auditability.
- Contributors onboarding from `README`/`CLAUDE`/`AGENTS` will configure the wrong (Mistral-only)
  mental model.
- Code behaviour itself carries no unaccepted functional risk; `mvn clean test` is green.
