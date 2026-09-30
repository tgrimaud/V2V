# TASK-WEB-040 — Adversarial Code Review

**Ticket:** TASK-WEB-040 — Emit a `channel_ingress` slice on the streaming (WebSocket) path
**Branch:** `task/TASK-WEB-040-ws-channel-ingress-slice`
**Reviewed:** 2026-09-30
**Scope of change:** `voice-agent/web_voice/streaming_stt_processor.py`,
`voice-agent/voice_common/pipeline_timing.py`, + tests
(`tests/test_streaming_stt_processor.py`, `tests/test_pipeline_timing.py`).
**Parent:** EPIC-010 (observability, latency & pilot validation). ADR-0028 / ADR-0029 / TASK-WEB-030.

## Verdict

**Proceed.**

## Satisfaction Score

Score: **95/100**
QA gate: **Pass**

## Blocking Findings

_None._

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | No per-slice **metric** emitted for `channel_ingress` (only a span + event). | `_record_channel_ingress` calls `telemetry.span` + `telemetry.record`, no `telemetry.metric`. | Acceptable: mirrors the peer completeness slice `voice.end_of_turn` (span + record, no metric); the report percentiles read spans. Add a `voice.channel.ingress.ms` metric only if the OTLP/Prometheus path needs an ingress series once export is on. |
| Low | Semantic of the slice ("session open → finalize" receive window) differs from the batch `web.voice.ingress` ("POST-body read time"). | `self._turn_timer.elapsed_ms()` at finalize. | Documented in code + report mapping comment; the two are kept in separate distributions (distinct span names, first-present-wins). No action required. |
| Info | The ticket text says "On the WebRTC path this slice comes from a `web.voice.ingress` span" — imprecise. | `web.voice.ingress` is emitted **only** on the batch path (`ingress.py` / `stt_service.py`); the streaming WebRTC path uses `StreamingSttProcessor` and emitted no ingress span. | The fix therefore closes the gap for **both** WS and WebRTC. No double-source (verified). |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| A real browser WS turn produces a `channel_ingress` slice (or explicit `measured=false` for headless) | ✅ | `test_emits_channel_ingress_span_on_streaming_turn` (span emitted + attrs + bytes); `test_no_channel_ingress_span_when_no_session_opened` (no fabricated span when no session). |
| The other five canonical slices remain `measured=true` (regression-locked) | ✅ | Existing `test_emits_end_of_turn_and_stt_spans` + `test_streaming_latency_report` suite unchanged & green (691 unittest, 15/43/194 behave). The change is additive (new span name only). |
| Numbers reconcile with emitted `metric_distributions` | ✅ | `test_channel_ingress_measured_from_streaming_span` proves `voice.channel.ingress` resolves the `channel_ingress` slice with the span duration as the percentile. |

## Test Evidence

- Developer tests: +3 — processor emit (attrs + `audio_bytes` multiple of frame size), no-session guard, report slice mapping.
- Missing tests: a multi-turn "one ingress span per turn" assertion would strengthen the per-turn guarantee (the per-turn identity test already drives 2 turns) — non-blocking.
- QA scenarios to run: re-run `scripts/streaming_latency_report.py` against a real browser WS turn → confirm `channel_ingress` populates (`measured=true`) and the other five are unchanged.

## Observability And Latency

- Relevant slices: `channel_ingress` (the target completeness slice).
- OpenTelemetry traces: `voice.channel.ingress` span carries `correlation_id`, `channel`, `provider`, `audio_bytes`; parented under the turn like the other per-turn spans.
- Metrics: none added (parity with `voice.end_of_turn`); report percentiles come from the span.
- Structured logs: `voice.channel.ingress.received` event mirrors the batch `web.voice.ingress.received`.
- Missing: nothing blocking. Not part of the mouth-to-ear composite → **ADR-0029 verdict unaffected** (explicitly documented).
- Risk: none — span-only, no behavioural path touched.

## Security And Privacy

- Sensitive data risk: none — the span carries a byte count, never a transcript.
- Identity/access risk: none.
- Logging risk: none new; reuses the existing sanitized telemetry recorder.

## Required Developer Actions

_None (Pass)._ Optional follow-ups captured as non-blocking notes above.

## Residual Risk If Accepted

- The streaming `channel_ingress` value represents the receive window (session open → finalize),
  not a network-read micro-latency; it must not be compared 1:1 with the batch `web.voice.ingress`
  distribution. This is documented and the distributions are kept separate by span name.
