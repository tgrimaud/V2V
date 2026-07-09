# Voice Agent Scaffold

This folder starts the rebuilt voice runtime area for the STT validation sprint.

## STT Fixture Validation

`stt_validation` provides the minimal scaffold for `TASK-STT-001`.

It accepts a controlled audio fixture and uses a deterministic sidecar transcript
provider so QA can validate the path before a real STT provider adapter is
connected.

Fixture convention:

```text
fixtures/question.wav
fixtures/question.txt
```

The `.wav` file represents the controlled audio input. The `.txt` file contains
the expected transcript used by the replaceable fixture provider.

Run from this folder (one or more fixtures can be passed for aggregate latency):

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m stt_validation.cli fixtures/question.wav --correlation-id corr-demo
python3 -m stt_validation.cli fixtures/short.wav fixtures/long.wav --correlation-id run
```

The CLI outputs JSON with:

- per-fixture transcript result, provider, outcome and correlation id;
- `stt_request_ms` (isolated STT slice) and total `duration_ms`;
- an aggregate `latency_report` (`count`, `min`, `max`, `p50`, `p95`, `p99`);
- OpenTelemetry-compatible spans (`stt.audio.accept`, `stt.request`);
- ordered phase events (started, audio accepted, request started, transcript
  final / failure, completed);
- metric samples (`stt.request.duration_ms`, `stt.validation.duration_ms`);
- structured logs (`info` on success, `warning` with a sanitized reason on
  failure).

## Observability (TASK-STT-003)

The scaffold emits local OpenTelemetry-compatible evidence without adding a
runtime dependency yet:

- the `stt.request` span isolates the STT slice from channel ingress
  (`stt.audio.accept`) and total run duration;
- `stt.request.duration_ms` samples feed p50/p95/p99 via
  `LatencyReport.from_samples`;
- failures are sanitized in `sanitization.py` (stable `error_code`, redacted
  filesystem paths, length-capped reason) so no raw audio, path or billing data
  is logged.

Evidence samples and acceptance-criteria coverage are documented in
`docs/observability/stt-validation-telemetry.md`.
