# STT Follow-up Technical Tasks

Follow-up tickets created from non-blocking adversarial-review findings recorded
in `product-backlog/review-findings.md`. They are not part of the core STT
validation sprint scope and should be scheduled deliberately.

## TASK-STT-005 - Redact Bare Sensitive Identifiers In Failure Sanitization

**Parent:** EPIC-010
**Related finding:** RF-001 (TASK-STT-003)
**Classification:** V1 pilot gate
**Status:** Draft
**Priority:** Medium
**Branch:** `task/TASK-STT-005-redact-bare-identifiers`

### Objective

Ensure sanitized failure reasons never leak sensitive identifiers even when the
STT provider surfaces a bare filename or id without a path separator.

### Scope

- Extend `stt_validation/sanitization.py` to redact filename/identifier-like
  tokens (e.g. `*.wav`, `*.mp3`, customer/id patterns), not only tokens with a
  path separator.
- Preserve the stable `error_code` and the length cap.
- Add tests covering bare-filename and id-like tokens.

### Acceptance Criteria

```gherkin
Scenario: A bare sensitive identifier is redacted
  Given an STT failure reason contains a bare filename or identifier
  When the reason is sanitized
  Then the identifier is replaced by a redaction marker
  And the stable error_code is still exposed
```

### Required Evidence

- Unit tests for bare-token redaction.
- Updated `docs/observability/stt-validation-telemetry.md` sanitization section.

---

## TASK-STT-006 - Add A Dedicated UNAVAILABLE STT Outcome

**Parent:** EPIC-010
**Related finding:** RF-004 (TASK-STT-002)
**Classification:** V1 pilot gate
**Status:** Draft
**Priority:** Low
**Branch:** `task/TASK-STT-006-unavailable-outcome`

### Objective

Distinguish "no usable speech detected" (silence/unusable audio) from a genuine
processing error, so QA and telemetry can tell them apart.

### Scope

- Introduce `SttOutcome.UNAVAILABLE` and map silence/no-speech to it.
- Audit all four telemetry surfaces and the quality harness for the new value.
- Keep "no invented transcript" behaviour intact.

### Acceptance Criteria

```gherkin
Scenario: Silence is reported as unavailable, not failed
  Given the audio fixture contains silence
  When the STT validation path processes it
  Then the outcome is UNAVAILABLE
  And no transcript is invented
```

### Required Evidence

- Unit tests for the new outcome.
- Updated telemetry and quality docs.

---

## TASK-STT-007 - Expand The STT Fixture Set With Multiple Samples Per Category

**Parent:** EPIC-010
**Related finding:** RF-005 (TASK-STT-002)
**Classification:** V1 pilot gate
**Status:** Draft
**Priority:** Medium
**Branch:** `task/TASK-STT-007-expand-fixture-samples`

### Objective

Make per-category quality and p95/p99 latency statistically meaningful by adding
multiple fixtures per category.

### Scope

- Add several fixtures per category (short, long, noisy, silence, accented).
- Extend the manifest and QA report to summarise quality per category.
- Define the minimum sample size before p95/p99 is reported as meaningful.

### Acceptance Criteria

```gherkin
Scenario: Category quality is reported over multiple samples
  Given each category has multiple fixtures
  When the quality run completes
  Then per-category quality and latency percentiles are reported
  And categories below the required sample size are flagged as not yet significant
```

### Required Evidence

- Expanded fixture set and manifest.
- Updated `docs/qa/stt-transcription-quality.md` with per-category summaries.
