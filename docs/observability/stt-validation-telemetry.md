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
`stt.transcript.final` (success) **or** `stt.unavailable` (no usable speech)
**or** `stt.failure` (processing error) -> `stt.validation.completed`.

The three terminal outcomes carried on `stt.validation.completed` (and the
`stt.request` span) are:

| `outcome` | Meaning | Emitted event | Log level |
|---|---|---|---|
| `success` | A transcript was produced | `stt.transcript.final` | `info` |
| `unavailable` | Audio processed but held **no usable speech** (silence / no-speech); never carries an invented transcript. `error_code` is the stable `no_speech` **(TASK-STT-006)** | `stt.unavailable` | `info` |
| `failed` | A genuine processing error (missing/invalid fixture, timeout, provider error) | `stt.failure` | `warning` |

`unavailable` is deliberately distinct from `failed` so QA and dashboards can
tell "the caller said nothing" apart from "the STT path broke".

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

Success emits an `info` log (`STT validation completed`); a no-usable-speech run
emits an `info` log (`STT reported no usable speech`) with `error_code=no_speech`;
a processing error emits a `warning` log (`STT validation failed`). All three
carry `correlation_id`, `provider`, `outcome`, and — for the non-success
outcomes — `error_code` and a sanitized `error_reason`.

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

## Evidence: unavailable run (no usable speech, safe) — TASK-STT-006

When the provider processes the audio but finds no speech (silence fixture, or a
Gradium `200` response with no text tokens), the runner emits `stt.unavailable`
and reports the `unavailable` outcome — not `failed` — with no invented
transcript:

```json
{ "name": "stt.unavailable",
  "attributes": { "correlation_id": "demo-silence", "provider": "fixture-stt",
                  "error_code": "no_speech",
                  "error_reason": "Transcript fixture contains no usable speech",
                  "stt_request_ms": 0.014 } }
```

```json
{ "level": "info", "message": "STT reported no usable speech",
  "attributes": { "correlation_id": "demo-silence", "provider": "fixture-stt",
                  "outcome": "unavailable", "error_code": "no_speech",
                  "error_reason": "Transcript fixture contains no usable speech" } }
```

Providers signal this by raising `NoSpeechDetectedError` (provider-agnostic, in
`stt_validation/providers.py`); the runner maps that single exception to the
`UNAVAILABLE` outcome, so no message string-matching is required.

## Sanitization guarantees

`stt_validation/sanitization.py`:

- maps the exception type to a stable `error_code`
  (`fixture_missing`, `invalid_fixture`, `stt_timeout`, `stt_error`),
- replaces any token containing a path separator with `<redacted-path>`,
- **(TASK-STT-005)** replaces a **bare filename** (media/data extension, no path
  separator — e.g. `secret-customer.wav`, `export.json`) with `<redacted-file>`,
- **(TASK-STT-005)** replaces an **identifier-like token** with `<redacted-id>`:
  UUIDs, secret-prefixed tokens (`gsk_…`, `sk_…`, `bearer_…`), long digit runs
  (≥ 7 digits, e.g. account/phone numbers) and mixed letter+digit ids
  (`CUST0009812`). Trailing/leading punctuation is stripped before matching.
- keeps ordinary words, short numbers (`HTTP 401`) and plain dates (`2026-07-10`)
  readable so the reason stays diagnostic,
- caps the reason at 160 characters,
- never emits raw audio bytes, transcript payloads beyond the returned result,
  or billing data.

Covered by `tests/test_stt_validation_runner.py::test_failure_reason_is_sanitized_without_leaking_path`
and the dedicated `tests/test_sanitization.py` (path, bare filename, UUID, secret
prefix, digit run, mixed-alnum id redaction; words/dates preserved; length cap).

## Acceptance criteria coverage

| Scenario | Evidence |
|---|---|
| STT latency is observable, isolable, percentile-ready | `stt.request` span + `stt.request.duration_ms` metric + `LatencyReport` |
| STT failure observable without leaking sensitive data | `stt.failure` event + warning log with `error_code`; sensitive tokens replaced by `<redacted-path>` / `<redacted-file>` / `<redacted-id>` (TASK-STT-005) |
| Silence reported as UNAVAILABLE, not a processing error (TASK-STT-006) | `stt.unavailable` event + `info` log, `outcome=unavailable`, `error_code=no_speech`, empty transcript; behave `Silence is reported as unavailable...` |

## Reproduce

```bash
cd voice-agent
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m stt_validation.cli <audio1.wav> <audio2.wav> --correlation-id <run>
```
