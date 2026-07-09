# STT Validation Telemetry Evidence (TASK-STT-003)

**Ticket:** TASK-STT-003 - Add OpenTelemetry instrumentation for STT validation
**Related story:** US-036 (measure key voice journey timings by pipeline slice)
**Scaffold:** `voice-agent/stt_validation/`
**Status:** Delivered on branch `task/TASK-STT-003-stt-opentelemetry`

## Purpose

Make the STT slice of the voice pipeline observable so QA and pilot readiness
decisions can rely on:

- a correlation id per validation run,
- OpenTelemetry-compatible spans that isolate the STT request from channel
  ingress (audio acceptance) and downstream backend processing,
- metrics suitable for p50 / p95 / p99 reporting,
- structured logs with sanitized outcome details,
- failure evidence that never leaks raw audio, filesystem paths, transcript
  content beyond what is required, or billing information.

## Telemetry model

The recorder (`stt_validation/telemetry.py`) emits four signal types. Names use
OpenTelemetry-style dotted namespaces so a real exporter can adopt them later
without renaming.

### Spans (slice isolation)

| Span | Meaning | Isolates |
|---|---|---|
| `stt.audio.accept` | Time to accept/validate the incoming audio | Channel ingress slice |
| `stt.request` | Time spent in the STT provider call only | STT slice (the measured target) |

The total run duration (`duration_ms`) is reported separately from the isolated
`stt_request_ms`, so the STT slice can be reasoned about independently of
acceptance overhead and any future backend processing.

### Events (ordered phase markers)

`stt.validation.started` -> `stt.audio.accepted` -> `stt.request.started` ->
`stt.transcript.final` (success) **or** `stt.failure` (failure) ->
`stt.validation.completed`.

### Metrics

| Metric | Use |
|---|---|
| `stt.request.duration_ms` | Percentile source for the STT slice (p50/p95/p99) |
| `stt.validation.duration_ms` | Total validation duration |

`LatencyReport.from_samples([...])` aggregates the per-run `stt_request_ms`
samples into `count`, `min`, `max`, `p50`, `p95`, `p99` (nearest-rank). A single
run contributes to the distribution; percentiles become meaningful as sample
size grows.

### Structured logs

Success emits an `info` log (`STT validation completed`); failure emits a
`warning` log (`STT validation failed`) carrying `correlation_id`, `provider`,
`outcome`, `error_code` and a sanitized `error_reason`.

## Evidence: success run (isolated STT slice + latency distribution)

Command (2 fixtures, shared correlation prefix):

```bash
python3 -m stt_validation.cli short-question.wav greeting.wav --correlation-id demo-run
```

Spans isolating the STT slice from acceptance:

```json
{ "name": "stt.audio.accept", "duration_ms": 0.022,
  "attributes": { "correlation_id": "demo-run-0", "provider": "fixture-stt", "audio_accepted": true } }
{ "name": "stt.request", "duration_ms": 0.045,
  "attributes": { "correlation_id": "demo-run-0", "provider": "fixture-stt", "outcome": "success" } }
```

Aggregate latency report (contributes to p50/p95/p99):

```json
{ "count": 2, "min_ms": 0.027, "max_ms": 0.045,
  "p50_ms": 0.027, "p95_ms": 0.045, "p99_ms": 0.045 }
```

Metric sample (percentile source):

```json
{ "name": "stt.request.duration_ms", "value": 0.045,
  "attributes": { "correlation_id": "demo-run-0", "provider": "fixture-stt", "outcome": "success" } }
```

## Evidence: failure run (observable, sanitized)

Command (missing transcript sidecar):

```bash
python3 -m stt_validation.cli short-question.wav --correlation-id demo-fail
```

Failure event and structured log — the absolute path is redacted and a stable
`error_code` is exposed:

```json
{ "name": "stt.failure",
  "attributes": { "correlation_id": "demo-fail", "provider": "fixture-stt",
                  "error_code": "fixture_missing",
                  "error_reason": "Transcript fixture not found: <redacted-path>",
                  "stt_request_ms": 0.017 } }
```

```json
{ "level": "warning", "message": "STT validation failed",
  "attributes": { "correlation_id": "demo-fail", "provider": "fixture-stt",
                  "outcome": "failed", "error_code": "fixture_missing",
                  "error_reason": "Transcript fixture not found: <redacted-path>" } }
```

## Sanitization guarantees

`stt_validation/sanitization.py`:

- maps the exception type to a stable `error_code`
  (`fixture_missing`, `invalid_fixture`, `stt_timeout`, `stt_error`),
- replaces any token containing a path separator with `<redacted-path>`,
- caps the reason at 160 characters,
- never emits raw audio bytes, transcript payloads beyond the returned result,
  or billing data.

Covered by `tests/test_stt_validation_runner.py::test_failure_reason_is_sanitized_without_leaking_path`.

## Acceptance criteria coverage

| Scenario | Evidence |
|---|---|
| STT latency is observable, isolable, percentile-ready | `stt.request` span + `stt.request.duration_ms` metric + `LatencyReport` |
| STT failure observable without leaking sensitive data | `stt.failure` event + warning log with `error_code` and `<redacted-path>` |

## Reproduce

```bash
cd voice-agent
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m stt_validation.cli <audio1.wav> <audio2.wav> --correlation-id <run>
```
