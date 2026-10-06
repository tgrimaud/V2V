# TASK-BE-068 — Reduce method/class size-budget overruns (adversarial review B1/B2)

**Type:** Technical task (backend refactor — `code-guidelines` hygiene, behavior-preserving)
**Status:** 🚧 Done on `task/TASK-BE-068-size-budget-refactor` (off `feat/restart-from-scratch`) — backend `mvn test` green (incl. 3 ArchUnit suites). Awaiting user validation (not merged).
**Adversarial review 93/100 (Pass, 2026-10-06)** — no blocking finding; behavior-preserving (per-change audit). Residual (non-blocking): the two `@Configuration` splits lack an `ApplicationContextRunner` wiring test (no `@SpringBootTest` in repo; mitigated — no duplicate beans, mechanical split). Recommended fix: add wiring slices mirroring `LlmConfigWiringTest`. Full review: `docs/qa/task-be-068-adversarial-review.md`.
**Priority:** Low
**Epic:** EPIC-012
**Surfaced by:** `docs/qa/2026-10-05-full-codebase-adversarial-review.md` (findings B1/B2).

## Context

The `code-guidelines` budgets (methods ≤ 20 non-blank lines, classes ≤ 200 non-blank
lines) are not ArchUnit-enforced, so a few files had drifted over. Re-counting by
**non-blank** lines (the rule's unit) showed only 4 classes genuinely over 200 — the
other 4 flagged by the review's raw `wc -l` (EirB2cSampleFixtures 195, PgVectorStoreAdapter
197, InvoiceTextParser 190, AbstractChatClientAnswerAdapter 190) were already compliant and
were left untouched (Boy-Scout "scope to what you touch").

## Changes (behavior-preserving)

### B2 — methods > 20 lines
- `InputGuardrail.check` (29 → 16 non-blank): refusal ladder extracted to an ordered
  `Optional` chain (`greetingDecision` → `vagueDecision` → `tooShortDecision` →
  `unsafeDecision` → `offTopicDecision` → `problemOpenerDecision`), preserving the
  `< MIN_QUESTION_LENGTH` early-PASS short-circuit exactly.
- `AbstractChatClientAnswerAdapter.buildSystemMessage` + streaming `generate`: extracted
  `renderContext`, `historyBlock`, `concisionSuffix`, `recordPromptTelemetry`, and
  `streamFailure`; assembly order (base → history → concision → language directive LAST
  for recency, TASK-BE-015) unchanged.

### B1 — classes > 200 non-blank lines (cohesion splits / helper extraction)
| Class | Before | After | How |
|---|---|---|---|
| `BillingConfig` | 225 | 102 | out-adapter selection → new `BillingAdapterConfig`; use-case wiring stays |
| `ConversationConfig` | 205 | 154 | memory + idempotency beans → new `ConversationMemoryConfig` (same pattern as `EscalationHandoffConfig`) |
| `BackendTelemetry` | 215 | 183 | Micrometer builder boilerplate → package-private `MeterEmitter` (public API unchanged) |
| `ConverseStreamSession` | 216 | 183 | SSE emission + sanitized error contract → package-private `SseStreamWriter` |

New files: `BillingAdapterConfig`, `ConversationMemoryConfig`, `MeterEmitter`,
`SseStreamWriter` (all ≤ 140 non-blank). No public API, bean name, REST contract, or
observability output changed; cross-`@Configuration` bean injection resolves as before.

## Test / review evidence

- `cd backend && mvn test` → **BUILD SUCCESS** (exit 0), incl. `HexagonalArchitectureTest`,
  `ContextBoundaryTest`, `NamingConventionsTest` — the architecture suites would fail on any
  boundary/naming violation introduced by the new classes.
- Pure refactor: no new behavior, no new dependency, no runtime-affecting change (telemetry
  tags/logs byte-for-byte identical).

## Acceptance

- [x] All touched classes ≤ 200 non-blank lines; the 3 touched methods ≤ 20.
- [x] `mvn test` green incl. ArchUnit.
- [x] No behavior/API/contract change.
