"""Genesys Audio Connector per-leg latency model + ADR-0029 re-score (TASK-WEB-025).

The Genesys round trip adds legs the WS/WebRTC paths do not have (sprint-13 doc):

  Genesys ingress -> Architect Call-Audio-Connector fork -> our wss inbound ->
  transcode in -> [ STT -> backend -> TTS ] -> transcode out -> wss outbound ->
  Genesys egress

Each leg is one slice, reported p50/p95. Following the US-036 rule, a leg with no
span in the sample is emitted ``measured=false`` with a reason + owning source, never
omitted, so a reviewer can tell a missing measurement from a fast one. Under DEC-014
(synthetic-first) only the ``wss`` transport + transcode legs are measurable in this
spike; the Genesys cloud legs need the live org, and STT/backend/TTS reuse the
existing ADR-0029 WS pilot base rather than being re-measured here.
"""

from __future__ import annotations

from typing import Any, Iterable

from voice_common.telemetry import LatencyReport, Span

SYNTHETIC = "synthetic-prototype"
LIVE_ORG = "live-genesys-org"
IN_HOUSE = "in-house-reuse"

# Ordered as the audio flows through the Genesys round trip.
GENESYS_LEGS: tuple[str, ...] = (
    "genesys_ingress",
    "architect_fork",
    "wss_inbound",
    "transcode_in",
    "stt",
    "backend",
    "tts",
    "transcode_out",
    "wss_outbound",
    "genesys_egress",
)

# Synthetic legs the throwaway prototype emits (one span per leg per turn).
LEG_SPAN_NAME: dict[str, str] = {
    "wss_inbound": "genesys.wss.inbound",
    "transcode_in": "genesys.transcode.in",
    "transcode_out": "genesys.transcode.out",
    "wss_outbound": "genesys.wss.outbound",
}

LEG_SOURCE: dict[str, str] = {
    "genesys_ingress": LIVE_ORG,
    "architect_fork": LIVE_ORG,
    "wss_inbound": SYNTHETIC,
    "transcode_in": SYNTHETIC,
    "stt": IN_HOUSE,
    "backend": IN_HOUSE,
    "tts": IN_HOUSE,
    "transcode_out": SYNTHETIC,
    "wss_outbound": SYNTHETIC,
    "genesys_egress": LIVE_ORG,
}

_UNMEASURED_NOTE: dict[str, str] = {
    LIVE_ORG: "requires the live Genesys org (Architect Call-Audio-Connector flow) — TASK-INFRA-012",
    IN_HOUSE: "reuse the existing ADR-0029 WS pilot base (not re-measured in this spike) — TASK-WEB-043",
}

# The Genesys transport overhead the spike can actually measure = the four synthetic
# legs added on top of the existing in-house mouth-to-ear (R1 isolated Genesys leg).
_TRANSPORT_LEGS: tuple[str, ...] = ("wss_inbound", "transcode_in", "transcode_out", "wss_outbound")


def _durations(spans: Iterable[Span], span_name: str) -> list[float]:
    return [s.duration_ms for s in spans if s.name == span_name]


def per_leg_report(spans: Iterable[Span]) -> list[dict[str, Any]]:
    materialized = list(spans)
    return [_leg_row(leg, materialized) for leg in GENESYS_LEGS]


def _leg_row(leg: str, spans: list[Span]) -> dict[str, Any]:
    source = LEG_SOURCE[leg]
    samples = _durations(spans, LEG_SPAN_NAME[leg]) if leg in LEG_SPAN_NAME else []
    if samples:
        return {"leg": leg, "source": source, "measured": True, "latency": LatencyReport.from_samples(samples).to_dict(), "note": None}
    return {"leg": leg, "source": source, "measured": False, "latency": None, "note": _UNMEASURED_NOTE.get(source)}


def transport_overhead_samples(spans: Iterable[Span]) -> list[float]:
    """Per-turn sum of the four synthetic transport+transcode legs (ms)."""
    per_leg = [_durations(spans, LEG_SPAN_NAME[leg]) for leg in _TRANSPORT_LEGS]
    if any(not d for d in per_leg):
        return []
    turns = min(len(d) for d in per_leg)
    return [round(sum(d[k] for d in per_leg), 3) for k in range(turns)]
