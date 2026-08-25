"""Shared per-call telemetry dump for the streaming voice paths (WebRTC + WebSocket).

A streaming call returns no HTTP response per turn, so its only latency/QA evidence is
this end-of-call dump: the full span/event/metric snapshot serialized as one structured
line on stderr, plus an additive OTLP export. WebRTC (`webrtc_signaling`) and the interim
browser WebSocket path (`websocket_signaling`, TASK-WEB-028) share it so the evidence shape
is identical across transports (US-036).
"""

import json
import sys

from voice_common.otel_export import export_recorder
from voice_common.pipeline_timing import PipelineTimingReport
from voice_common.telemetry import TelemetryRecorder


def build_payload(telemetry: TelemetryRecorder) -> dict:
    """Assemble one call's evidence payload (spans/events/metrics + canonical per-slice timing).

    Extracted so the payload shape is unit-testable without capturing stderr (TASK-WEB-030 AC#2):
    the `pipeline_timing` block always carries every canonical journey slice with a measured
    true/false flag, so a slice with no span is marked `measured=false`, never silently omitted."""
    spans = telemetry.spans()
    return {
        "spans": [span.__dict__ for span in spans],
        "events": [event.__dict__ for event in telemetry.events()],
        "metrics": [metric.__dict__ for metric in telemetry.metrics()],
        # Canonical per-slice journey timing (US-036 / TASK-WEB-030 AC#2): every slice
        # (channel_ingress -> end_of_turn -> stt -> backend -> tts_first_audio ->
        # channel_egress) is ALWAYS present with measured true/false, so a slice with no
        # span shows up as measured=false + a reason, never silently omitted.
        "pipeline_timing": PipelineTimingReport.from_spans(spans).to_dict(),
    }


def log_telemetry(telemetry: TelemetryRecorder) -> None:
    """Dump one call's spans/events/metrics as a structured line, then OTLP-export."""
    payload = build_payload(telemetry)
    # flush=True: the per-call telemetry dump is the only latency/QA evidence for a
    # streaming call (no HTTP response per turn). When stderr is redirected to a file
    # it is block-buffered, so without an explicit flush the dump can sit unwritten
    # until the process exits — losing the evidence for TASK-WEB-009 measurement.
    print(json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)
    # Additive OTLP export (TASK-OBS-001): no-op unless OTEL_EXPORTER_OTLP_ENDPOINT /
    # VOICE_OTEL_EXPORT is set; never raises, so the stderr evidence above is authoritative.
    export_recorder(telemetry)
