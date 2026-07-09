# STT Validation Technical Tasks

These technical tickets support the first sprint dedicated to validating
speech-to-text behavior before broader Voice2Voice delivery.

They do not replace the product user stories. They make the product stories
testable from an empty implementation baseline.

## TASK-STT-001 - Create The Voice Runtime STT Validation Scaffold

**Parent:** EPIC-006, EPIC-010  
**Related stories:** US-019, US-036  
**Classification:** V1 enabler  
**Status:** Done
**Priority:** High  
**Branch:** `task/TASK-STT-001-stt-validation-scaffold`

### Objective

Provide a minimal validation path that can accept controlled audio fixtures and
return a transcript result for QA review.

### Scope

- Establish the minimal voice runtime scaffold needed for STT validation.
- Accept recorded audio fixtures for repeatable validation.
- Return final transcript, provider identity, outcome and timing metadata.
- Keep the STT provider replaceable behind the target voice-provider boundary.

### Acceptance Criteria

```gherkin
Scenario: Audio fixture produces a transcript result
  Given QA has a controlled audio fixture
  When the fixture is submitted to the STT validation path
  Then a final transcript result is available
  And the result includes provider, outcome and timing metadata
```

```gherkin
Scenario: STT provider remains replaceable
  Given the STT validation path is implemented
  When a provider implementation is selected for the environment
  Then the product-facing validation behavior remains the same
```

### Required Evidence

- Developer tests for nominal and failed fixture processing.
- QA can run a repeatable fixture-based validation.
- OpenTelemetry traces, metrics and structured logs identify the STT validation
  attempt, provider, outcome and duration.

### Review Evidence

- `voice-agent/stt_validation/`
- `voice-agent/tests/test_stt_validation_runner.py`
- `voice-agent/README.md`
- Validated by the user on 2026-07-09.

---

## TASK-STT-002 - Validate STT Transcription Quality With Audio Fixtures

**Parent:** EPIC-006, EPIC-010  
**Related stories:** US-019, US-036  
**Classification:** V1 pilot gate  
**Status:** Done  
**Priority:** High  
**Branch:** `task/TASK-STT-002-stt-quality-fixtures`

### Objective

Validate whether the selected STT path can produce acceptable transcripts across
the first controlled fixture set.

### Scope

- Define the first QA audio fixture set.
- Cover short utterance, longer question, noisy audio, silence and accented
  speech where fixtures are available.
- Record transcript result, confidence/quality indicator if available, failure
  reason and provider metadata.
- Mark missing fixture categories explicitly instead of pretending coverage
  exists.

### Acceptance Criteria

```gherkin
Scenario: STT quality is reviewed across fixture categories
  Given QA has the STT fixture set
  When each fixture is processed
  Then transcript quality is reviewed per fixture category
  And missing fixture categories are explicitly reported
```

```gherkin
Scenario: Silence or unusable audio is handled safely
  Given the audio fixture contains silence or unusable speech
  When the STT validation path processes it
  Then the outcome is reported as unavailable or failed
  And no invented transcript is accepted as valid
```

### Required Evidence

- QA fixture inventory.
- Transcript results for each available fixture.
- Defect tickets for failed categories that block STT readiness.

### Delivery Evidence

- Quality harness: `voice-agent/stt_validation/quality.py` (WER, quality gate,
  missing-category reporting, silence/no-invented-transcript handling).
- Fixture set + manifest: `voice-agent/fixtures/` (short, long, noisy, silence,
  accented) run via `python3 -m stt_validation.quality_cli fixtures/manifest.json`.
- QA inventory + results: `docs/qa/stt-transcription-quality.md`
  (`ready: true`, no missing/failed categories).
- Tests: `voice-agent/tests/test_quality.py`, `tests/test_manifest.py`
  (17 tests passing overall).
- No blocking defects for the current fixture set; bug-ticket process documented
  for future failures.

---

## TASK-STT-003 - Add OpenTelemetry Instrumentation For STT Validation

**Parent:** EPIC-010  
**Related stories:** US-036  
**Classification:** V1 pilot gate  
**Status:** Done  
**Priority:** High  
**Branch:** `task/TASK-STT-003-stt-opentelemetry`

### Objective

Expose the STT latency and outcome data required for monitoring, QA validation
and pilot readiness decisions.

### Scope

- Emit a correlation id for each STT validation run.
- Emit OpenTelemetry spans or timing markers for audio accepted, STT request
  started, final transcript available and failure outcome.
- Emit metrics suitable for p50, p95 and p99 reporting.
- Emit structured logs with sanitized outcome details.
- Avoid logging raw customer audio, unnecessary transcript content or sensitive
  billing information.

### Acceptance Criteria

```gherkin
Scenario: STT latency is observable
  Given an audio fixture is processed through STT
  When QA reviews the validation evidence
  Then STT duration can be isolated from channel ingress and backend processing
  And the sample can contribute to p50, p95 and p99 reporting
```

```gherkin
Scenario: STT failure is observable without leaking sensitive data
  Given the STT provider fails or times out
  When the failure is recorded
  Then the correlation id, provider, outcome and sanitized reason are available
  And sensitive audio or billing data is not logged
```

### Required Evidence

- OpenTelemetry trace sample or local equivalent.
- Metrics sample showing STT duration and outcome.
- Structured log sample with sanitized fields.

### Delivery Evidence

- Spans `stt.audio.accept` / `stt.request` isolate the STT slice; `LatencyReport`
  provides p50/p95/p99 from `stt.request.duration_ms` samples.
- Sanitized failure path (`error_code` + `<redacted-path>`) in
  `voice-agent/stt_validation/sanitization.py`.
- Evidence document: `docs/observability/stt-validation-telemetry.md`.
- Tests: `voice-agent/tests/test_stt_validation_runner.py`,
  `voice-agent/tests/test_latency_report.py` (7 passing).

---

## TASK-STT-004 - Produce The STT QA Report And Gherkin Scenarios

**Parent:** EPIC-010  
**Related stories:** US-019, US-036  
**Classification:** V1 pilot gate  
**Status:** Draft  
**Priority:** High  
**Branch:** `task/TASK-STT-004-stt-qa-report`

### Objective

Prepare the QA validation package that proves what was tested, what passed, what
failed and whether STT is ready for the next Voice2Voice sprint.

### Scope

- Write Gherkin scenarios for STT fixture validation.
- Define the STT QA report structure.
- Include functional transcript results and latency measurements.
- Include open risks, missing fixture categories and required bug tickets.
- Provide a go/no-go recommendation for broader Voice2Voice delivery.

### Acceptance Criteria

```gherkin
Scenario: STT QA evidence supports a readiness decision
  Given the STT validation run is complete
  When the QA report is reviewed
  Then it includes tested fixtures, transcript outcomes, latency distribution,
  defects, open risks and a go/no-go recommendation
```

```gherkin
Scenario: STT defects become explicit bug tickets
  Given QA finds a blocking STT defect
  When the defect is recorded
  Then a bug ticket is created with reproduction steps, evidence, expected result,
  actual result and retest criteria
```

### Required Evidence

- Gherkin scenarios.
- QA report.
- Bug tickets for defects found during STT validation.
