# Full-codebase & documentation adversarial review — 2026-10-05

**Scope:** whole repository on `feat/restart-from-scratch` — backend Java
(`backend/`, 219 main + 140 test sources), voice runtime Python
(`voice-agent/`, 191 sources), and documentation + backlog (`docs/`,
`product-backlog/`, `README.md`, ~245 markdown files). Requested as an
adversarial review "de tout le code et de la doc".
**Reviewer skill:** `.cursor/skills/adversarial-code-review/SKILL.md`.
**Method:** three parallel code/doc audits + direct verification of every
load-bearing claim by git ancestry and by re-running the full test suites.

---

## Verdict

**PASS — overall satisfaction 90/100.** No blocking finding in the shipped
runtime. All three test suites are green (see Test Evidence). The dominant
residual debt is **documentation current-state drift** (billing shipped +
deployed, but several entry banners still read "target-only") and a short list
of **non-blocking code hygiene** items (class/method size budgets, a few
log-sanitization edge paths, one HMAC length edge). None block the pilot; they
are tracked as Required Actions below.

> Scope note: this is a whole-repo health review, not a single-ticket QA gate.
> The 90/100 is an aggregate posture score; per-ticket QA gates stay in their own
> `docs/qa/<ticket>-adversarial-review.md` files.

---

## Corrections to the audit inputs (verified directly)

Two claims from the sub-audits were **wrong** and are corrected here so they do
not propagate:

| Claim (sub-audit) | Verification | Reality |
|---|---|---|
| "No ArchUnit / architecture tests exist" (backend audit) | `rg -l ArchRule backend/src/test` | **False.** Three ArchUnit suites exist and are green: `architecture/HexagonalArchitectureTest.java`, `ContextBoundaryTest.java`, `NamingConventionsTest.java`. Hexagonal boundaries **are** enforced. |
| BE-066/BE-067/BUG-028 "Awaiting user validation (not merged)" (doc audit flagged as suspicious) | `git log --merges`; `git tag --contains` | **Stale.** `d408a57` / `ffea869` / `a5f1948` are `--no-ff` merge commits on `feat/restart-from-scratch`, all contained in `v0.9.4`. Fixed in this pass. |

---

## Blocking findings

**None.** The runtime is safe to keep in pilot.

---

## Non-blocking findings

### Backend (Java)

| # | Finding | Evidence | Recommendation |
|---|---|---|---|
| B1 | Classes over the 200-line budget | `ConverseStreamSession` ~240, `BillingConfig` ~244, `BackendTelemetry` ~234, `ConversationConfig` ~224, `EirB2cSampleFixtures` ~223, `PgVectorStoreAdapter` ~220, `InvoiceTextParser` ~214, `AbstractChatClientAnswerAdapter` ~209 | Extract collaborators (config split, parser helpers). `code-guidelines` budget; not caught by ArchUnit. |
| B2 | Methods over the 20-line budget | `InputGuardrail.check` (111–139), `AbstractChatClientAnswerAdapter.generate` / `buildSystemMessage` | Decompose. |
| B3 | 400 handler logs `ex.getMessage()` server-side | validation exception handler | Low risk (server log only); keep client body generic (it already is). |
| B4 | `BillingExplanationService` depends on the concrete `BillingIntentDetector`, not a port | billing service wiring | Introduce an inbound port for symmetry; functionally fine. |
| B5 | Confidence-gate edge: one invoice with lines + one empty still proceeds | invoice comparison guard | Add an explicit "both invoices must have lines" precondition or document the intended behaviour. |
| B6 | `GalaxionBillRunDocumentAdapter.listDocuments` always returns empty | adapter | Known / tracked by **OQ-003** (B2C uses the raw PDF; no B2B line endpoint for V1). |
| B7 | `/answer` lacks a top-level `backend_request` latency slice and omits `correlation_id` in some logs | answer controller/telemetry | Add the slice + id for parity with `/converse*`. |

### Voice runtime (Python)

| # | Finding | Evidence | Recommendation |
|---|---|---|---|
| V1 | `exc_info=True` on **text**-format logging bypasses `scrub_message` (scrubbing only runs under `VOICE_LOG_FORMAT=json`) | `websocket_app.py:577-578`, `genesys_app.py:221-222`, `server.py:422-425` | A raised stack could carry unsanitized data in text mode. Sanitize before logging, or default pilots to json format. |
| V2 | Warm-up HTTP hop omits the deterministic `traceparent` | `http_backend.py:142-156` | Inject it for trace parity (warm-up is best-effort, so low impact). |
| V3 | Records exception **type name** instead of `sanitize_error(...)` | `streaming_answer.py:130-133, 267-268` | Use the shared sanitizer for consistency. |
| V4 | `_stop_filler` uses `except Exception` (misses `CancelledError`, a `BaseException`) | `answer.py:394-406` | Add `except asyncio.CancelledError` + `finally` (same pattern already used for barge-in TTS). |
| V5 | `hmac.compare_digest` on unequal-length keys can raise `ValueError` → 500 instead of 401 | `genesys_auth.py:145-151` | Length-check / wrap so a malformed signature fails **closed** as 401. Genesys is default-off, so pilot-safe. |
| V6 | Genesys HMAC `@request-target` may not match an edge-rewritten path | `genesys_*` auth | Already fail-closed with a TODO; confirm on the real tenant (TASK-INFRA-012 / TASK-WEB-042 live-measurement seams). |

### Documentation & backlog

| # | Finding | Evidence | Recommendation |
|---|---|---|---|
| D1 | **Current-state drift**: billing/BSS/PDF comparison shipped + deployed in `v0.9.4`, but entry banners still say "target-only / not yet built" | `README.md:87-89`; `docs/README.md:11-13`; `docs/architecture/adrs/README.md:34-37` | Update the feature lists / banners to reflect shipped billing. Largest doc risk. |
| D2 | "Only runnable code is the Python voice slice" vs both tiers runnable | `docs/engineering/development-guide.md:32` vs `:3-20` | Reconcile; backend is runnable + released. |
| D3 | Wrong ADR cite: `billing-explain (ADR-0051)` | `README.md:79` | Billing-explain is ADR-0052; ADR-0051 is the OpenAI-default LLM. |
| D4 | ADR README index rows lag shipped state (billing "NOT implemented"; ADR-0047 "impl. pending" though shipped `v0.7.0`) | `docs/architecture/adrs/README.md:34-37, :111` | Refresh index status column. |
| D5 | Stale sprint banners ("Sprint 9") | `docs/knowledge-base/knowledge-base-guide.md:7`, `docs/architecture/channel-identity-boundary.md:3` | Already partly scoped by TASK-DOC-005. |
| D6 | French prose under `docs/` (English-only rule) is almost entirely quoted product copy / QA utterances, not author narrative | `voice-runtime-http-contract.md:54,66-69`; ADR-0031:14-17; `agent-system-prompt.md:89`; QA transcripts | Acceptable as quoted strings; a zero-French-outside-examples pass is TASK-DOC-005. |

Fixed in this pass (git-verified, low-risk doc corrections): the three stale
"not merged" billing rows (D-origin #2 above) and the broken
`BUG-025 → ../tasks/backend-tasks.md` link (now
`task-be-057-opener-detector-followups.md`).

---

## Story / feature coverage

- **Voice2Voice loop** (STT→backend→TTS, streaming + barge-in + end-of-call
  confirmation): covered by unit + behave suites; green.
- **RAG** (pgvector, domain tagging, cross-domain `/converse`): covered;
  null-domain contract locked by regression tests.
- **Billing V1** (real eir B2C PDF → deterministic comparison, no LLM for
  amounts): shipped in `v0.9.4`, E2E `EirB2cBillingComparisonE2eTest`, and
  **smoke-tested live on the pilot this session** (account 99224964 → €55.47
  delta, residual €0.00).
- **Guardrails / confidence / escalation / warm-up**: covered.
- **Genesys Audio Connector**: built, default-off, fail-closed; live-org legs
  still pending (documented).

---

## Test evidence (re-run 2026-10-05)

| Suite | Command | Result |
|---|---|---|
| Backend | `cd backend && mvn -q test` | **BUILD SUCCESS** (exit 0) — incl. 3 ArchUnit suites |
| Voice unit | `voice-agent/.venv/bin/python -m unittest discover tests` | **723 tests, OK** |
| Voice BDD | `voice-agent/.venv/bin/behave` | **15 features / 43 scenarios / 194 steps — 0 failed** |

All `TODO`/`FIXME` in the tree are the ticketed live-measurement seams
(`TASK-INFRA-012` / `TASK-WEB-042`) in `voice-agent/web_voice/genesys_*.py`;
no un-ticketed debt markers.

---

## Observability & latency

- Shared `correlation_id`, deterministic BLAKE2b `traceparent` propagation
  voice→backend, per-slice pipeline timing, structured guardrail/language
  events: present and tested.
- Gaps: `/answer` missing a top-level `backend_request` slice (B7); warm-up hop
  omits `traceparent` (V2). Both non-blocking.

## Security & privacy

- **Solid:** pure Spring-free domain; read-only BSS GETs; PDF path fail-closed;
  constant-time api-key compare; api-key gate; Genesys default-off + fail-closed;
  no committed secrets; shared log sanitization; barge-in cleanup correct.
- **Watch:** text-mode `exc_info` can bypass scrubbing (V1); HMAC unequal-length
  edge (V5); dev-default DB password `voicesupport` (local-only — must never be a
  pilot value; pilot uses vault-rendered `.env`); pilot API open when key unset
  (operational toggle).

---

## Required developer actions

1. **(Doc, high value — DONE)** Reconciled current-state drift D1–D4: flipped the
   "target-only / not built" billing banners (`README.md`, `docs/README.md`, ADR
   README) and the ADR-0047 index status to "shipped", fixed the billing-explain
   cite to ADR-0052 (+ ADR-0055 routing), and corrected the dev-guide "only
   runnable code" claim (both tiers run).
2. **(Code, hygiene)** V1/V4/V5 log-sanitization + CancelledError + HMAC-length
   edges — small, isolated fixes; ticket as a backend/voice hardening follow-up.
3. **(Code, budget)** B1/B2 size-budget extractions when those files are next
   touched.
4. **(Done this pass)** Stale "not merged" billing statuses + broken BUG-025
   link corrected and committed.

## Residual risk (accepted for the pilot)

- Doc banners lag shipped billing until action 1 lands (narrative only; code is
  correct and deployed).
- Genesys live-org legs (TLS trust, native barge-in/EOT, Architect fail-safe)
  and degraded modes remain target-only and are tracked.
- B2C billing is anchored to the fixed eir sample set / raw-PDF path (OQ-003);
  live Galaxion B2C fetch is TASK-BE-063.
