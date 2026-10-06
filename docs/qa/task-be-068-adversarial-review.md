# TASK-BE-068 — Adversarial code review (size-budget refactor)

**Date:** 2026-10-06
**Branch:** `task/TASK-BE-068-size-budget-refactor` (commit `47366a7`, off `feat/restart-from-scratch`)
**Reviewer skill:** `.cursor/skills/adversarial-code-review/SKILL.md`
**Scope:** 10 backend `.java` files (B1/B2 from `docs/qa/2026-10-05-full-codebase-adversarial-review.md`) — a behavior-preserving refactor, no behavioral ticket.

## Verdict

**Proceed.** Behavior-preserving refactor; `mvn test` green including the three ArchUnit
suites. The one non-blocking residual flagged in the first pass (config-split wiring not
covered by a context test) was **closed in follow-up commit** by adding two
`ApplicationContextRunner` wiring slices — no residual remains.

## Satisfaction Score

Score: 97/100 (93/100 at first pass; +4 after the config-split wiring slices closed the only Medium finding)
QA gate: Pass

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Medium (RESOLVED) | **Config-split wiring not covered by a test.** `mvn test` does not boot the full Spring context (no `@SpringBootTest`), so the `BillingConfig`→`BillingAdapterConfig` and `ConversationConfig`→`ConversationMemoryConfig` cross-`@Configuration` bean wiring was only validated at deploy/startup, not by the suite. | No `@SpringBootTest` in `src/test`; only `ApplicationContextRunner` slices (`LlmConfigWiringTest`). | **Closed:** added `BillingConfigWiringTest` (2 tests: default mock mode + `source=eir`/`pdf=pdfbox`) and `ConversationMemoryConfigWiringTest` (loads both configs with fake external ports), each asserting `context.hasNotFailed()` and that the moved + cross-config consuming beans (`explainBillingUseCase`/`bssBillingPort`, `converseUseCase`/`converseStreamUseCase`/`conversationMemoryPort`) resolve. Full suite now 718 tests, BUILD SUCCESS. |
| Low | `InputGuardrail` grew to 197 non-blank + 6 new tiny helper methods | the refusal ladder is now 6 one-liner `*Decision` methods | Acceptable — each is ≤4 lines and single-purpose; readability improved over the nested `if` chain. |
| Info | `AbstractChatClientAnswerAdapter` is exactly 200 non-blank after adding 4 helpers | at the budget ceiling | Fine (≤200); watch on the next edit. |

## Story Coverage

| Acceptance criterion (TASK-BE-068) | Covered? | Evidence |
|---|---|---|
| All touched classes ≤200 non-blank lines | Yes | BillingConfig 102, BillingAdapterConfig 140, ConversationConfig 154, ConversationMemoryConfig 64, BackendTelemetry 183, MeterEmitter 27, ConverseStreamSession 183, SseStreamWriter 56, InputGuardrail 197, AbstractChatClientAnswerAdapter 200 |
| 3 target methods ≤20 non-blank | Yes | `check` 29→16; `buildSystemMessage`/streaming `generate` decomposed |
| No behavior / API / contract change | Yes (reasoned) | see Behavior-preservation audit below |
| `mvn test` green incl. ArchUnit | Yes | BUILD SUCCESS, exit 0 |

### Behavior-preservation audit (per change)

- **`InputGuardrail.check`** → ordered `Optional.or(...)` chain. Order identical
  (greeting → vague → tooShort → unsafe → offTopic → problemOpener → pass); `.or(Supplier)`
  is lazy, so later predicates run only when earlier ones are empty — same short-circuit as
  the nested `if`s. `tooShortDecision` returns `Optional.of(pass())`, preserving the
  `< MIN_QUESTION_LENGTH` early-PASS that skips the unsafe/off-topic/opener checks. Predicates
  are pure (no side effects), so eager evaluation of the first is safe.
- **`AbstractChatClientAnswerAdapter`** → `renderContext`/`historyBlock`/`concisionSuffix`/
  `recordPromptTelemetry`/`streamFailure`. Assembly string is identical: base → history (""
  when empty) → concision ("" when disabled) → language directive LAST (TASK-BE-015 recency);
  telemetry call order (answer-language then prompt-size) and `historyBlock.length()`/
  `chunkCount` args unchanged. `streamFailure` reproduces the timeout-vs-error outcome tag +
  reason + `UpstreamUnavailableException` exactly.
- **`BackendTelemetry`→`MeterEmitter`** → `Tags.of(...)` replaces chained `.tag()`; Micrometer
  meter identity is tag-order-independent, so meter names/tags/percentiles are byte-identical.
  Public API (every `recordX`) unchanged.
- **`ConverseStreamSession`→`SseStreamWriter`** → `send`/`completeExceptionally`/`abort` +
  `SseSendException` moved verbatim; `MediaType.APPLICATION_JSON`, the ERR_UPSTREAM/ERR_INTERNAL
  contract, and the client-disconnect path are preserved.
- **Config splits** → beans moved 1:1; no duplicates; cross-config injection standard.

## Test Evidence

- Developer tests: full backend suite green (`mvn test` BUILD SUCCESS, 718 tests) incl.
  `HexagonalArchitectureTest`, `ContextBoundaryTest`, `NamingConventionsTest` (the new classes
  respect layer + naming rules), plus the existing guardrail / telemetry / streaming tests that
  exercise the refactored code paths.
- Added: `BillingConfigWiringTest` (2) + `ConversationMemoryConfigWiringTest` (1) —
  `ApplicationContextRunner` slices that load each config split together with fake external ports
  and assert the moved + cross-config consuming beans resolve. Closes the config-split residual.
- QA scenarios to run: none new — behavior unchanged.

## Observability And Latency

- Relevant slices: unchanged. `voice_support.slice` timer, prompt/answer/language, guardrail/
  channel/handoff counters all emit identical names/tags/percentiles via `MeterEmitter`.
- Missing: none. Not a runtime-behavioral change.
- Risk: none to telemetry output.

## Security And Privacy

- Sensitive data risk: none introduced; log sanitization (`CorrelationId.sanitize`, nullSafe
  CR/LF) preserved in `ConverseStreamSession`/`SseStreamWriter`.
- Identity/access risk: none.
- Logging risk: none (same log lines).

## Required Developer Actions

1. ~~Add two `ApplicationContextRunner` wiring tests mirroring `LlmConfigWiringTest`~~ — **done**
   (`BillingConfigWiringTest`, `ConversationMemoryConfigWiringTest`). No further action required.

## Residual Risk If Accepted

- None material. The config-split bean wiring is now covered by `ApplicationContextRunner` slices
  (both splits load together and resolve their moved + cross-config consuming beans), on top of
  compilation + the mechanical nature of the change. No behavioral, latency, security or
  observability risk.
