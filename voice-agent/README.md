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

Run from this folder:

```bash
python3 -m unittest discover tests
python3 -m stt_validation.cli fixtures/question.wav --correlation-id corr-demo
```

The CLI outputs JSON with:

- transcript result;
- provider identity;
- outcome;
- duration in milliseconds;
- correlation id;
- structured telemetry events;
- metric samples;
- structured logs.

The scaffold emits local OpenTelemetry-compatible evidence without adding a
runtime dependency yet. `TASK-STT-003` will connect the same evidence shape to
full OpenTelemetry traces, metrics and structured logs.
