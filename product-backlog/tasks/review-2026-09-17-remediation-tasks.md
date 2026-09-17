# Remediation tickets — Full Adversarial Review 2026-09-17

Source: `docs/architecture/reviews/full-adversarial-review-2026-09-17.md` (whole-branch review after
the Sprint 15 OpenAI default flip). These tickets close the review's **P1** and **P2** findings.
Delivered on `feat/sprint-16-review-remediation` (off `feat/restart-from-scratch`); merge only on the
user's explicit request.

| Ticket | Priority | Finding | Status |
|--------|----------|---------|--------|
| TASK-DOC-008 | P1 | C3 — no decision record for the OpenAI default | ✅ Done |
| TASK-DOC-007 | P1/P2 | C1 + C4 — docs still say "Mistral is the default"; internal contradictions | ✅ Done |
| TASK-INFRA-019 | P1 | C2 — deploy config cannot serve the new default (`OPENAI_*` missing) | ✅ Done |
| TASK-BE-051 | P1 | A1 — dirty-`target/` breaks `mvn test` (`RunKnowledgeBddTest`) | ✅ Done |
| TASK-BE-053 | P2 | Code — DEC-002 system prompt triplicated across 3 adapters | ✅ Done |
| TASK-BE-054 | P2 | Code — telemetry channel allow-list mismatch (`genesys`) | ✅ Done |
| TASK-BE-052 | P2 | Code — provider-selection wiring untested | ✅ Done |

---

## TASK-DOC-008 — Record the OpenAI-default decision (ADR-0051 + DEC-011 + ADR-0045)

**Type:** Documentation / decision · **Priority:** P1 · **Closes:** review C3

**Context.** BE-050 made OpenAI `gpt-5` the default LLM wording provider with no ADR/DEC. ADR-0045
(Mistral/OpenAI benchmark) is still Proposed and benchmarks `gpt-4o-mini`; DEC-011 still frames
OpenAI as an unvalidated future target.

**Changes.**
- New **ADR-0051** "OpenAI `gpt-5` as the default LLM wording provider" (Accepted) — context, decision,
  consequences (deploy must set `OPENAI_*`), alternatives (keep Mistral default), links to DEC-011.
- Update **DEC-011** to reflect BE-049 live+E2E validation and the OpenAI default (was: Mistral dev
  default, OpenAI gated on credentials not yet available).
- Reconcile **ADR-0045** status note (benchmark still open under TASK-BE-033; default already flipped).
- Add ADR-0051 to the ADR index; refresh the stale "Reserved IDs" meta note (ADR-0046/0047 now exist).

**Acceptance.** ADR-0051 present + indexed; DEC-011 and ADR-0045 no longer contradict the code truth.

---

## TASK-DOC-007 — Documentation truth sweep (default → OpenAI) + internal contradictions

**Type:** Documentation (+ 2 comment-only code edits) · **Priority:** P1/P2 · **Closes:** review C1, C4

**Context.** ~15 authoritative docs still say "Mistral is the default" and omit OpenAI; two code
comments do too.

**Changes (state: three chat providers; OpenAI `gpt-5` default, built in `LlmConfig`).**
- Root: `README.md`, `CLAUDE.md` (also fix wrong bean location `DomainServiceConfig`→`LlmConfig`),
  `AGENTS.md`.
- Docs: `docs/architecture/architecture.md`, `docs/engineering/development-guide.md`,
  `docs/knowledge-base/knowledge-base-technical.md`, `voice-agent/README.md`.
- ADR bodies: `ADR-0006` (add OpenAI + default note, keep Accepted), `ADR-0031` ("two provider
  prompts" → three).
- Code comments: `VoiceSupportApplication` header, `MistralAnswerAdapter` class comment.
- Contradictions (C4): `sprint-15-llm-providers.md` DoD ("Mistral remains default"),
  `llm-provider-tasks.md` BE-049 "two selectable", `docs/qa/task-be-049-...md` "Mistral stays the
  default" (annotate as superseded by BE-050), `docs/README.md` "through Sprint 11" marker.

**Acceptance.** No doc/comment claims Mistral as the default; OpenAI documented as the default third
provider; no self-contradiction within a file.

---

## TASK-INFRA-019 — Deploy config for the OpenAI default + source-of-truth

**Type:** Deployment / ops docs · **Priority:** P1 · **Closes:** review C2 (highest operational risk)

**Context.** App defaults to `openai` but no deploy path ships `OPENAI_*`; compose/Ansible silently
pin `mistral-api`. Any env relying on the default without `OPENAI_*` 401s on the first turn.

**Decision (source-of-truth).** The **pilot deploy explicitly pins `LLM_PROVIDER=mistral-api`** for
now (Mistral is the validated pilot path); OpenAI is the **application/local default** and a
**deploy option**. Both must be wired and documented so switching the pilot to OpenAI is a config
change, not a code change.

**Changes.**
- `deploy/compose/backend/.env.example`: add `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_CHAT_MODEL`,
  `OPENAI_REASONING_EFFORT`; document the pin + the app default.
- `deploy/ansible/roles/compose_tier/templates/backend.env.j2` + `group_vars/backend.yml`: render
  `OPENAI_*` from vars (empty defaults; vault for the key) so `llm_provider: openai` is deployable.
- root `.env.example`: add the `OPENAI_*` block; drop the stale "backend not runnable on this branch".
- Runbooks (`deployment-eir-ai4cc-tst.md`, `first-deploy-runbook.md`): add `LLM_PROVIDER` + `OPENAI_*`
  to the secret/egress tables; note the Azure Foundry egress when OpenAI is selected.

**Acceptance.** A reader can deploy either provider from config; the app-default(openai) vs
pilot-pin(mistral-api) tension is documented, not hidden.

---

## TASK-BE-051 — `RunKnowledgeBddTest` robust to a stale `target/`

**Type:** Backend test/build · **Priority:** P1 · **Closes:** review A1

**Context.** A stale gitignored artifact `target/test-classes/features/billing-explanation.feature`
(no `src` feature, no glue) makes `mvn test` fail with 10 undefined-step errors; `mvn clean test` is
green. The Cucumber runner scans the whole `features` classpath root.

**Changes.** Point the runner at the specific feature files/dir that have glue (e.g. explicit
`features` subpaths or a `@SelectFile`/`cucumber.features` narrowing), or configure Cucumber to not
fail on stale/undefined features outside the known set. Add a short comment explaining the
dirty-`target` hazard. (No CI change assumed; make the local `mvn test` deterministic.)

**Acceptance.** `mvn test` (without `clean`) passes even with a stale feature left in `target/`.

---

## TASK-BE-053 — Extract the shared DEC-002 voice prompt (de-triplicate)

**Type:** Backend code · **Priority:** P2 · **Closes:** review B (prompt triplication)

**Context.** `MistralAnswerAdapter`, `OllamaAnswerAdapter`, `OpenAiAnswerAdapter` hold a byte-identical
French `SYSTEM_PROMPT`. `OutputGuardrail` matches hand-off wording → drift is a correctness risk.

**Changes.** Introduce one shared constant (e.g. `VoiceSystemPrompt.DEC002_FR` or a protected default
in `AbstractChatClientAnswerAdapter`); each adapter overrides only `providerName()` unless it needs a
different prompt. Keep the existing `OpenAiAnswerAdapterTest` prompt assertions green.

**Acceptance.** Single source for the DEC-002 prompt; three adapters reference it; tests green.

---

## TASK-BE-054 — Align the telemetry channel allow-list default

**Type:** Backend config · **Priority:** P2 · **Closes:** review B (channel tag mismatch)

**Context.** `BackendTelemetry` default CSV includes `genesys`; `application.yml` default omits it →
Genesys metrics may collapse to tag `other`.

**Changes.** Add `genesys` to the `application.yml` channel allow-list default (match the code
default). Verify `BackendTelemetryTest` still green.

**Acceptance.** `genesys` is an accepted channel tag by default on both surfaces.

---

## TASK-BE-052 — Provider-selection wiring tests

**Type:** Backend test · **Priority:** P2 · **Closes:** review B (untested wiring)

**Context.** No test asserts that `@ConditionalOnProperty` activates the correct adapter bean per
`voice-support.llm.provider`. Only adapter unit tests exist.

**Changes.** Add lightweight `@SpringBootTest`-style context smoke tests (properties-driven) or a
focused `ApplicationContextRunner` test asserting: `openai`→`OpenAiAnswerAdapter`,
`mistral-api`→`MistralAnswerAdapter`, `ollama`→`OllamaAnswerAdapter`, and unknown→startup failure
(`validateProvider`). Prefer `ApplicationContextRunner` (no full context, no external calls).

**Acceptance.** A wiring regression (wrong/duplicate provider bean) fails a test.
