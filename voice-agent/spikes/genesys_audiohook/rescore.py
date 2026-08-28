"""ADR-0029 re-score with the Genesys leg included (TASK-WEB-025, R1).

ADR-0029 pilot gate: mouth-to-ear p95 <= 1500 ms. The Genesys round trip can only
*add* latency on top of the in-house path, whose last WS-live pilot sample is already
FAIL (2.76 s, TASK-WEB-039). This computes an honest re-score:

- the **measured Genesys transport overhead** (synthetic wss + transcode legs), and
- a **measured floor** = in-house base mouth-to-ear + that overhead.

If the measured floor already exceeds the gate, the outcome is a definitive **fail**
(the unmeasured cloud legs — Genesys ingress / Architect fork / egress — can only add
to it). Otherwise the outcome stays **not_measured** (never a silent pass), because a
PASS cannot be claimed while the cloud legs are unmeasured (they need the live org).
"""

from __future__ import annotations

from typing import Any

from voice_common.telemetry import LatencyReport

ADR_0029_MOUTH_TO_EAR_P95_MS = 1500.0
# Last WS-live pilot mouth-to-ear p95 (TASK-WEB-039, v0.6.0) — the in-house base the
# Genesys legs stack on top of. Overridable via the harness --base-mouth-to-ear-ms.
DEFAULT_BASE_MOUTH_TO_EAR_P95_MS = 2760.0


def rescore(
    overhead_samples: list[float],
    *,
    base_mouth_to_ear_p95_ms: float | None,
    gate_p95_ms: float = ADR_0029_MOUTH_TO_EAR_P95_MS,
) -> dict[str, Any]:
    overhead = LatencyReport.from_samples(overhead_samples) if overhead_samples else None
    overhead_p95 = overhead.p95_ms if overhead else None
    floor = _measured_floor(base_mouth_to_ear_p95_ms, overhead_p95)
    return {
        "gate_p95_ms": gate_p95_ms,
        "genesys_transport_overhead": overhead.to_dict() if overhead else None,
        "base_mouth_to_ear_p95_ms": base_mouth_to_ear_p95_ms,
        "measured_floor_p95_ms": floor,
        "status": _status(floor, gate_p95_ms),
        "reason": _reason(floor, gate_p95_ms),
    }


def _measured_floor(base: float | None, overhead_p95: float | None) -> float | None:
    if base is None or overhead_p95 is None:
        return None
    return round(base + overhead_p95, 3)


def _status(floor: float | None, gate_p95_ms: float) -> str:
    if floor is None:
        return "not_measured"
    return "fail" if floor > gate_p95_ms else "not_measured"


def _reason(floor: float | None, gate_p95_ms: float) -> str:
    if floor is None:
        return "cannot re-score: no Genesys transport overhead and/or no in-house base to stack it on"
    if floor > gate_p95_ms:
        return (
            f"measured floor {floor} ms already exceeds the {gate_p95_ms} ms gate; the "
            "unmeasured Genesys cloud legs (ingress/fork/egress) can only add — definitive FAIL"
        )
    return (
        "measured floor is under the gate, but PASS cannot be claimed while the Genesys "
        "cloud legs are unmeasured (live org required) — stays not_measured"
    )
