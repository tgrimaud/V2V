# Remediation tickets — Full Adversarial Review 2026-09-17

Source: `docs/architecture/reviews/full-adversarial-review-2026-09-17.md` (whole-branch review after
the Sprint 15 OpenAI default flip). These tickets close the review's **P1**, **P2** and **P3**
findings (plus the minor residual). Delivered on `feat/sprint-16-review-remediation` (off
`feat/restart-from-scratch`); merge only on the user's explicit request.

| Ticket | Priority | Finding | Status |
|--------|----------|---------|--------|
| TASK-DOC-008 | P1 | C3 — no decision record for the OpenAI default | ✅ Done |
| TASK-DOC-007 | P1/P2 | C1 + C4 — docs still say "Mistral is the default"; internal contradictions | ✅ Done |
| TASK-INFRA-019 | P1 | C2 — deploy config cannot serve the new default (`OPENAI_*` missing) | ✅ Done |
| TASK-BE-051 | P1 | A1 — dirty-`target/` breaks `mvn test` (`RunKnowledgeBddTest`) | ✅ Done |
| TASK-BE-053 | P2 | Code — DEC-002 system prompt triplicated across 3 adapters | ✅ Done |
| TASK-BE-054 | P2 | Code — telemetry channel allow-list mismatch (`genesys`) | ✅ Done |
| TASK-BE-052 | P2 | Code — provider-selection wiring untested | ✅ Done |
| TASK-WEB-045 | P3 | §3.9 / BUG-018 #1 — no overall wall-clock deadline on a streamed turn | ✅ Done |
| TASK-WEB-046 | P3 | §3.9 / BUG-018 #2 — UI can stay stuck in "thinking" (no browser watchdog) | ✅ Done (client watchdog); server `turn_error` signal deferred |
| TASK-BE-055 | P3 | §3.10 — `OutputGuardrail` only guards currency amounts | 📋 Designed / deferred to billing V1 (review-recommended) |
| Code hygiene | P3 | §3.11 — `ConversationConfig` > 200 lines; stale 350 ms EOT comment | ✅ Done |
| Residual (minor) | — | `architecture.md` Mermaid showed 2 LLM adapters | ✅ Done (3 adapters) |

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

---

# P3 findings (review §3 — "can defer safely") + minor residual

## TASK-WEB-045 — Overall wall-clock deadline for a streamed voice turn (BUG-018 fix #1)

**Type:** Voice runtime · **Priority:** P3 · **Closes:** review §3.9 (first half) · **Status:** ✅ Done

**Context.** On the streamed path a turn was bounded **only** by the per-read socket timeout: a
backend that trickles sub-timeout bytes but never emits a terminal `done`/`error` held the turn
open indefinitely (the architectural hang-until-refresh risk behind BUG-018).

**Changes.**
- `StreamedAnswerRunner` gains an optional `deadline_ms`; `run()` wraps the consume loop in
  `asyncio.wait_for`. On timeout it aborts the stream (closes the socket so the blocked `next()`
  unblocks) and degrades to the safe fallback — already-spoken sentences are **kept**, never un-said
  (DEC-002). A `voice.turn.deadline_exceeded` event records elapsed + where in the turn it fired.
- `voice_pipeline/answer.py`: `resolve_turn_deadline_ms()` (`VOICE_TURN_DEADLINE_MS`, default
  13000 ms; `<= 0` disables), threaded through `AnswerProcessor` → the runner.
- Tests: a never-terminating stream ends bounded + degraded + records the event; a fast turn records
  none.

**Acceptance.** A live-but-never-terminating backend turn ends within the deadline with the safe
fallback and a deadline-hit telemetry event; a normal fast turn is unaffected. ✅

---

## TASK-WEB-046 — Guaranteed terminal signal + browser watchdog (BUG-018 fix #2)

**Type:** Voice runtime + `web_voice` client · **Priority:** P3 · **Closes:** review §3.9 (second
half) · **Status:** ✅ Done (browser watchdog) — server-side explicit `turn_error` signal **deferred**

**Context.** The streaming WS UI leaves "Thinking…" only when bot audio (or a terminal signal)
arrives. A dropped/dead connection or an unsignalled dead-end left the UI stuck until a manual
refresh, and the client had **no watchdog**.

**Changes (delivered).**
- `web_voice/static/ws.js`: a bounded **thinking watchdog** (`WATCHDOG_MS`, default 20 s, `?watchdog=`
  override) armed when a turn enters "Thinking…" and cleared as soon as the bot produces audio, the
  user speaks again, a terminal signal arrives, or the call ends. If it fires (no audio, nothing
  playing) the UI leaves "Thinking" and invites a retry — it never fabricates an answer (DEC-002).
  The window sits **above** the TASK-WEB-045 server deadline so a slow-but-progressing turn (runtime
  degrades and still speaks a fallback) is not cut early. A defensive `turn_error` control handler is
  also wired client-side.

**Deferred (tracked, not blocking).** Emitting a **new** server-side `turn_error` terminal control
signal on **every** WS/WebRTC/Genesys error/teardown path is a cross-transport protocol change (new
`ControlSignalType`, per-transport teardown wiring, Genesys AudioHook mapping, Behave coverage). The
browser watchdog already guarantees the AC ("the UI can never be permanently stuck"), because a
backend error on the streamed path already degrades to spoken fallback audio (which leaves
"Thinking"); the only truly unsignalled case is a dropped connection, which the watchdog catches. The
explicit server signal is a belt-and-suspenders follow-up on TASK-WEB-046.

**Acceptance.** A broken/dead connection mid-turn leaves "Thinking" within the watchdog window and
offers a retry; a long-but-progressing turn (audio flowing) is not cut. ✅ (client watchdog)

---

## TASK-BE-055 — Broaden `OutputGuardrail` beyond currency amounts

**Type:** Backend domain · **Priority:** P3 · **Closes:** review §3.10 · **Status:** 📋 Designed /
deferred to billing V1 (review-recommended: *"Track as a hardening ticket before billing V1"*)

**Context.** `OutputGuardrail` (DEC-002) rejects fabricated **currency amounts** and non-answer
markers, plus retrieval-confidence gating. Invented **dates, plan names, procedures, phone numbers**
can still pass. Acceptable for KB-grounded QA (amounts are the main money risk and are covered), but
a real exposure for the future billing core.

**Why deferred (not implemented now).** Broadening the guard is a **behaviour-changing** correctness
feature with real **false-positive** risk: a fuzzy claim-check on dates/plan-names could block valid
grounded answers and degrade the pilot KB-QA path for a marginal pre-billing safety gain. The review
itself recommends tracking it as a hardening ticket **before the billing core**, not shipping it now.

**Design (for billing V1).**
- Prefer **evidence-span attribution** over more regex allow/deny sets: an answer claim must be
  traceable to a retrieved evidence span, else it is flagged (mirrors the amount-set membership but
  generalised).
- Add a **false-positive eval** fixture set (grounded answers that must pass) before enabling any new
  claim class, and gate each new class behind a flag so it can be rolled out per deployment.
- Candidate high-precision first classes (low false-positive, matchable like amounts): phone numbers,
  URLs/emails present in the answer but absent from evidence. Dates / plan-names need the span
  attribution above.

**Acceptance (when scheduled).** Non-currency fabricated claims of the enabled classes are blocked
with no regression on a grounded-answer false-positive eval set.

---

## Code hygiene (review §3.11) + minor residual — ✅ Done

**§3.11 — class > 200 lines + stale EOT comment.**
- The 200-line guideline counts **non-blank** lines. On that metric only `ConversationConfig` (218)
  breached; `KnowledgeConfig` (198), `BackendTelemetry` (195) and `ConverseStreamSession` (184) are
  compliant (the review used total line counts). Split the escalation-hand-off concern out of
  `ConversationConfig` into a new `EscalationHandoffConfig` (Spring wires by type; behaviour
  preserved) → `ConversationConfig` is now **191** non-blank.
- Fixed the stale `session_factory.py` end-of-turn comment ("unset → 500 ms"): the streaming runtime
  default is **350 ms** (`PILOT_END_OF_TURN_SILENCE_MS`); the 500 ms library default is batch/fixture
  only.
- (`InputGuardrail.check` ≈ 21 lines is a 1-line soft breach left as-is — not touched this pass.)

**Residual (minor).** `docs/architecture/architecture.md` Mermaid + the outbound-flow / port-adapter
tables showed only 2 LLM adapter boxes (Mistral, Ollama). Added the **OpenAI** adapter box + external
node + edges and updated the tables to three providers (OpenAI default, Mistral pinned pilot, Ollama
alt).
