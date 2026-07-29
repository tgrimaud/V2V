"""Env-gated OTLP export for the voice runtime (TASK-OBS-001, ADR-0028 addendum).

The voice runtime records per-turn / per-call telemetry into an in-memory
``TelemetryRecorder`` and dumps it to stderr (the pilot evidence). This module is an
**additive** bridge that also ships that telemetry as OpenTelemetry spans over OTLP so
a turn can be followed in a collector alongside the backend.

It is a strict no-op unless export is explicitly enabled, so offline runs and the test
suite are unaffected:

- ``OTEL_EXPORTER_OTLP_ENDPOINT`` (or ``VOICE_OTEL_EXPORT=1``) must be set; otherwise
  ``export_recorder`` returns ``False`` without importing the OpenTelemetry SDK.
- the ``opentelemetry`` SDK is imported lazily and any failure is swallowed (a single
  stderr note), never raised — telemetry export must never break a call.

The stderr dump is never removed; OTLP is purely additive.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

# Span/correlation identity attributes lifted to first-class OTel attributes when present
# on a recorded span (they arrive via the recorder's per-turn baggage, TASK-WEB-017).
_IDENTITY_KEYS = ("correlation_id", "conversation_id", "turn_index", "channel", "provider")

_DEFAULT_SERVICE_NAME = "voice-runtime"


def _truthy(value: str | None) -> bool:
    return bool(value) and value.strip().lower() in ("1", "true", "yes", "on")


def otlp_export_enabled(env: dict[str, str] | None = None) -> bool:
    """True when OTLP export is explicitly turned on via env; default off."""
    env = os.environ if env is None else env
    endpoint = env.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    return bool(endpoint) or _truthy(env.get("VOICE_OTEL_EXPORT"))


def _coerce_attr(value: Any) -> Any:
    """OTel attribute values must be primitives (or sequences of them)."""
    if isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _attributes(raw: dict[str, Any]) -> dict[str, Any]:
    return {key: _coerce_attr(val) for key, val in raw.items() if val is not None}


def export_recorder(
    recorder: Any,
    *,
    service_name: str = _DEFAULT_SERVICE_NAME,
    env: dict[str, str] | None = None,
    span_exporter: Any = None,
) -> bool:
    """Translate a ``TelemetryRecorder``'s spans/events/metrics into OTel spans and export.

    Returns ``True`` when spans were handed to an exporter, ``False`` when export is
    disabled or unavailable. When ``span_exporter`` is injected (tests), export runs
    regardless of the env gate so the translation can be validated offline with an
    in-memory exporter.
    """
    if span_exporter is None and not otlp_export_enabled(env):
        return False
    try:
        return _do_export(recorder, service_name=service_name, span_exporter=span_exporter)
    except Exception as exc:  # never let telemetry export break a call
        print(f"[otel-export] disabled after error: {exc}", file=sys.stderr, flush=True)
        return False


def _do_export(recorder: Any, *, service_name: str, span_exporter: Any) -> bool:
    # Lazy imports: only pulled when export is actually attempted, so the base runtime
    # and the test suite never require the OpenTelemetry SDK.
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.trace import SpanKind

    exporter = span_exporter if span_exporter is not None else _build_otlp_exporter()
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(service_name)

    spans = recorder.spans()
    events = recorder.events()
    metrics = recorder.metrics()

    root_attrs = _root_attributes(spans, events, metrics)
    end_ns = time.time_ns()
    total_ms = sum(getattr(s, "duration_ms", 0.0) for s in spans)
    root_start_ns = end_ns - int(max(total_ms, 0.0) * 1_000_000)

    root = tracer.start_span("voice.turn", start_time=root_start_ns, kind=SpanKind.SERVER)
    for key, value in root_attrs.items():
        root.set_attribute(key, value)
    for event in events:
        root.add_event(event.name, attributes=_attributes(event.attributes))
    for metric in metrics:
        root.set_attribute(f"metric.{metric.name}", _coerce_attr(metric.value))

    cursor_ns = root_start_ns
    for span in spans:
        span_end_ns = cursor_ns + int(max(getattr(span, "duration_ms", 0.0), 0.0) * 1_000_000)
        child = tracer.start_span(span.name, start_time=cursor_ns)
        for key, value in _attributes(span.attributes).items():
            child.set_attribute(key, value)
        child.end(end_time=span_end_ns)
        cursor_ns = span_end_ns

    root.end(end_time=end_ns)
    provider.force_flush()
    provider.shutdown()
    return True


def _root_attributes(spans: list[Any], events: list[Any], metrics: list[Any]) -> dict[str, Any]:
    """Hoist identity attributes (correlation_id, conversation_id, turn_index, …) onto the
    root span so a turn is filterable in the collector even if a child span lacks them."""
    merged: dict[str, Any] = {}
    for item in (*spans, *events, *metrics):
        attrs = getattr(item, "attributes", {}) or {}
        for key in _IDENTITY_KEYS:
            if key not in merged and attrs.get(key) is not None:
                merged[key] = _coerce_attr(attrs[key])
    return merged


def _build_otlp_exporter() -> Any:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter()
