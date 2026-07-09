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

---

## TASK-STT-008 - Connect The Gradium STT Provider (Fresh Implementation)

**Parent:** EPIC-006, EPIC-010
**Related finding:** RF-003 (TASK-STT-002)
**Related stories:** US-019, US-036
**Related decision:** DEC-005 (Gradium + Pipecat reference voice path; ADR-0002)
**Classification:** V1 pilot gate
**Status:** Draft
**Priority:** High
**Branch:** `task/TASK-STT-008-gradium-stt-provider`

### Objective

Replace the deterministic `FixtureSttProvider` with a real Gradium STT provider so
transcription quality and STT latency reflect the selected engine, not a fixture
sidecar. This makes RF-003 actionable now that the provider is chosen.

### Constraints

- **Fresh implementation.** Do not restore or port the legacy
  `voice-agent/agent/gradium_stt.py` from `main`/history. Only the functional
  contract may be reused as a target spec: Gradium ASR REST endpoint,
  `x-api-key` auth, audio input formats (`pcm_16000` for web/PCM, `ulaw_8000` for
  telephony), streaming line-delimited `type: text` tokens joined into a
  transcript.
- Implement against the existing `SttProvider` protocol
  (`voice-agent/stt_validation/providers.py`) so the manifest, quality harness,
  telemetry and Behave scenarios stay unchanged.

### Scope

- New `GradiumSttProvider` implementing `SttProvider` (`name`, `transcribe`).
- Configuration via `GRADIUM_API_KEY` (and language/format inputs); no secret in
  code, logs or telemetry.
- Map Gradium HTTP/credit/auth/unreachable failures to stable sanitized
  `error_code`s consistent with `sanitization.py`.
- Emit the same OpenTelemetry spans/metrics as the fixture path so the STT slice
  stays isolated and percentile-ready.
- Provider selection is configurable (fixture vs Gradium) so QA can run either
  without code changes.
- Re-run `fixtures/manifest.json` against Gradium and record real quality/latency.

### Acceptance Criteria

```gherkin
Scenario: Real Gradium transcription flows through the same harness
  Given the Gradium STT provider is configured with a valid API key
  When QA runs the STT validation harness with the Gradium provider
  Then each usable fixture produces a real transcript and quality score
  And the STT slice latency is reported for p50, p95 and p99
```

```gherkin
Scenario: Gradium failure stays observable and sanitized
  Given the Gradium STT provider fails (auth, credits, timeout or unreachable)
  When the failure is recorded
  Then a stable error_code and a sanitized reason are exposed
  And no API key, raw audio or filesystem path is logged
```

### Required Evidence

- Unit tests for `GradiumSttProvider` with a fake HTTP transport (no live call).
- Updated `docs/qa/stt-transcription-quality.md` and `docs/qa/stt-qa-report.md`
  with real Gradium quality and latency numbers.
- Behave scenarios pass against the configured provider.
- Confirmation that no secret is present in logs or telemetry.

### Notes

- Resolving this ticket updates RF-003 from ticketed to closed and re-scopes the
  go/no-go recommendation in `docs/qa/stt-qa-report.md` from "labo slice" to
  "real STT engine".
- RF-002 (channel ingress span is a scaffold analog) stays gated by US-019/US-036,
  which introduce the real channel ingress path.
