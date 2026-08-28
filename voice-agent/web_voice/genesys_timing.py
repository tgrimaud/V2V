"""Genesys Audio Connector per-leg latency + capacity report (TASK-WEB-043, ADR-0049).

The Genesys counterpart of `scripts/streaming_latency_report.py`. It reuses the shared
per-slice machinery (`voice_common.pipeline_timing`) but supplies the **Genesys** leg
decomposition (ADR-0040/0049): Genesys cloud ingress -> Architect fork -> transcode in ->
end-of-turn -> STT -> backend -> TTS -> transcode out -> Genesys cloud egress. The
runtime-measurable legs (transcode in/out from `genesys_framing`, and the shared STT /
backend / TTS spans) are reported p50/p95; the legs that are NOT runtime-observable
(the Genesys-cloud ingress/egress and the Architect fork) are emitted `measured=false`
with a reason (US-036 rule), never silently omitted, so a gap is never read as a fast leg.

The Genesys `conversationId` is the turn's correlation id (see `envelope.for_genesys_turn`),
so every span/metric already carries it; the OTel exporter (`otel_export`) parents them
under the deterministic `conversationId -> traceparent` (one trace, voice + backend).

ADR-0029 re-score: the full mouth-to-ear round trip cannot be scored from runtime spans
alone (the Genesys cloud legs need the live org, DEC-015) and native end-of-turn is owned
by TASK-WEB-042, so the verdict is stated explicitly as gated rather than silently passed.
"""

from __future__ import annotations

from typing import Any, Iterable

from voice_common.pipeline_timing import (
    BACKEND_FIRST_TOKEN,
    END_OF_TURN,
    STT,
    TTS_FIRST_AUDIO,
    PipelineTimingReport,
    voice_to_first_audio_report,
)
from voice_common.telemetry import MetricSample, Span

from .envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL
from .genesys_config import ACTIVE_SESSIONS_METRIC, SESSION_REJECTED_METRIC
from .genesys_framing import TRANSCODE_IN_SPAN, TRANSCODE_OUT_SPAN

# Genesys-only legs (the shared STT/backend/TTS/end-of-turn labels are reused verbatim).
GENESYS_INGRESS = "genesys_ingress"
ARCHITECT_FORK = "architect_fork"
TRANSCODE_IN = "transcode_in"
TRANSCODE_OUT = "transcode_out"
GENESYS_EGRESS = "genesys_egress"

# Legs in audio-flow order (ADR-0040 leg decomposition).
GENESYS_PIPELINE_SLICES: tuple[str, ...] = (
    GENESYS_INGRESS,
    ARCHITECT_FORK,
    TRANSCODE_IN,
    END_OF_TURN,
    STT,
    BACKEND_FIRST_TOKEN,
    TTS_FIRST_AUDIO,
    TRANSCODE_OUT,
    GENESYS_EGRESS,
)

# Leg -> span names measuring it (first present wins, so no cross-name distribution mix).
GENESYS_SLICE_SPAN_NAMES: dict[str, tuple[str, ...]] = {
    GENESYS_INGRESS: (),
    ARCHITECT_FORK: (),
    TRANSCODE_IN: (TRANSCODE_IN_SPAN,),
    END_OF_TURN: ("voice.end_of_turn",),
    STT: ("stt.request",),
    BACKEND_FIRST_TOKEN: ("backend.first_token", "backend.request"),
    TTS_FIRST_AUDIO: ("voice.tts.first_audio",),
    TRANSCODE_OUT: (TRANSCODE_OUT_SPAN,),
    GENESYS_EGRESS: (),
}

_CLOUD_LEG_NOTE = (
    "Genesys-cloud leg, not runtime-observable; needs live-org measurement "
    "(R1 / DEC-015, docs/operations/genesys-live-measurement-runbook.md)"
)
GENESYS_UNMEASURED_NOTES: dict[str, str] = {
    GENESYS_INGRESS: f"caller -> Genesys edge -> runtime: {_CLOUD_LEG_NOTE}",
    ARCHITECT_FORK: f"Architect Call-Audio-Connector fork/pause: {_CLOUD_LEG_NOTE}",
    TRANSCODE_IN: "no genesys.transcode.in span in this sample",
    END_OF_TURN: "Genesys-path end-of-turn is owned by native Genesys events (TASK-WEB-042)",
    STT: "no stt.request span in this sample",
    BACKEND_FIRST_TOKEN: "no backend.first_token span in this sample",
    TTS_FIRST_AUDIO: "no voice.tts.first_audio span in this sample",
    TRANSCODE_OUT: "no genesys.transcode.out span in this sample",
    GENESYS_EGRESS: f"runtime -> Genesys edge -> caller: {_CLOUD_LEG_NOTE}",
}


def genesys_pipeline_timing(spans: Iterable[Span]) -> PipelineTimingReport:
    """Per-leg p50/p95 for the Genesys legs; cloud legs stay explicit measured=false gaps."""
    return PipelineTimingReport.from_spans(
        spans,
        expected=GENESYS_PIPELINE_SLICES,
        span_names=GENESYS_SLICE_SPAN_NAMES,
        notes=GENESYS_UNMEASURED_NOTES,
    )


def _channel_samples(metrics: Iterable[MetricSample], name: str) -> list[MetricSample]:
    return [
        m
        for m in metrics
        if m.name == name and m.attributes.get("channel") == GENESYS_AUDIO_CONNECTOR_CHANNEL
    ]


def genesys_concurrency(metrics: Iterable[MetricSample]) -> dict[str, Any]:
    """Ceiling + peak simultaneous Genesys sessions observed in the sample (gauge-derived)."""
    gauges = _channel_samples(metrics, ACTIVE_SESSIONS_METRIC)
    ceilings = {int(m.attributes["max_sessions"]) for m in gauges if "max_sessions" in m.attributes}
    return {
        "ceiling": max(ceilings) if ceilings else None,
        "peak_active_sessions": max((m.value for m in gauges), default=0.0),
        "gauge_samples": len(gauges),
    }


def genesys_backpressure(metrics: Iterable[MetricSample]) -> dict[str, Any]:
    """WS 1013 capacity refusals surfaced as an aggregatable counter (backpressure)."""
    refusals = _channel_samples(metrics, SESSION_REJECTED_METRIC)
    return {
        "metric": SESSION_REJECTED_METRIC,
        "refused_sessions": int(sum(m.value for m in refusals)),
    }


def genesys_adr_0029_verdict(spans: Iterable[Span]) -> dict[str, Any]:
    """Explicit ADR-0029 re-score verdict: gated (never a silent pass) while cloud legs
    and native end-of-turn (TASK-WEB-042) are un-instrumented in the runtime."""
    mouth_to_ear = voice_to_first_audio_report(spans)
    return {
        "status": "not_measured",
        "reason": (
            "full mouth-to-ear cannot be scored from runtime spans: the Genesys cloud "
            "ingress/egress + Architect fork are not runtime-observable (live-org only, "
            "DEC-015) and native end-of-turn is owned by TASK-WEB-042. The Genesys path "
            "stays a spike off the V1 critical path until the live-org re-score."
        ),
        "runtime_partial_mouth_to_ear": mouth_to_ear.to_dict(),
    }


def build_genesys_report(
    spans: list[Span],
    metrics: list[MetricSample],
    *,
    calls: int,
    channel: str = GENESYS_AUDIO_CONNECTOR_CHANNEL,
    provider: str = "gradium",
    warm: bool = True,
    note: str | None = None,
) -> dict[str, Any]:
    """Assemble the Genesys per-leg + capacity + ADR-0029 report over a reviewed sample."""
    return {
        "sample": {"calls": calls, "channel": channel, "provider": provider, "warm": warm, "note": note},
        "per_leg": genesys_pipeline_timing(spans).to_dict(),
        "concurrency": genesys_concurrency(metrics),
        "backpressure": genesys_backpressure(metrics),
        "adr_0029_gate": genesys_adr_0029_verdict(spans),
    }


def genesys_log_telemetry(telemetry: Any) -> None:
    """Per-call dump for a Genesys session: same stderr line + OTLP export as the shared
    path, but the `pipeline_timing` block carries the **Genesys** legs (not the web legs)."""
    from .session_telemetry import log_telemetry

    log_telemetry(telemetry, pipeline_timing=genesys_pipeline_timing)
