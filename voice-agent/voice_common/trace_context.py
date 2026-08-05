"""Deterministic W3C trace context derived from a turn's correlation id (TASK-OPS-007).

The voice runtime records telemetry into an in-memory ``TelemetryRecorder`` and exports
it to the collector *after* the turn (see ``voice_common.otel_export``), while the HTTP
call to the backend happens *during* the turn — there is no live OpenTelemetry context to
inject at call time. To still stitch a voice turn to its backend spans into **one trace**,
we derive a stable W3C ``traceparent`` from the turn's ``correlation_id`` (the join key
already carried end to end):

- the backend receives ``traceparent`` on the HTTP hop and, because it ships
  ``micrometer-tracing-bridge-otel`` with the default W3C propagation + a ParentBased
  sampler, continues that same trace id (the ``01`` sampled flag keeps it even under a
  low probability);
- the voice-side exporter builds the ``voice.turn`` root span under the *same* derived
  trace id + parent span id, so both tiers share one trace id in the collector.

Derivation is a pure function of the correlation id (BLAKE2b), so the id computed at
HTTP-call time and the id computed at export time always match without shared state.
IDs of all-zero are invalid per the spec, so they are nudged to 1 (astronomically
unlikely with a real correlation id, but guarded anyway).
"""

from __future__ import annotations

import hashlib

_TRACE_ID_BYTES = 16
_SPAN_ID_BYTES = 8
_SPAN_SALT = b"voice-turn-span"
_SAMPLED_FLAG = "01"
_UNSAMPLED_FLAG = "00"


def _digest(correlation_id: str, size: int, salt: bytes = b"") -> int:
    raw = hashlib.blake2b(correlation_id.encode("utf-8"), digest_size=size, salt=salt[:16]).digest()
    value = int.from_bytes(raw, "big")
    return value or 1  # 0 is not a valid trace/span id


def derive_trace_ids(correlation_id: str | None) -> tuple[int, int] | None:
    """(trace_id, span_id) as ints derived from the correlation id, or None if blank."""
    if not correlation_id or not correlation_id.strip():
        return None
    key = correlation_id.strip()
    return _digest(key, _TRACE_ID_BYTES), _digest(key, _SPAN_ID_BYTES, _SPAN_SALT)


def derive_traceparent(correlation_id: str | None, *, sampled: bool = True) -> str | None:
    """W3C ``traceparent`` header value for the turn, or None when no correlation id.

    Format: ``00-<32 hex trace id>-<16 hex span id>-<flags>``. ``sampled`` sets the
    trace-flags byte (``01`` = record + export), which the backend's ParentBased sampler
    honours so a voice-initiated call is always captured end to end.
    """
    ids = derive_trace_ids(correlation_id)
    if ids is None:
        return None
    trace_id, span_id = ids
    flags = _SAMPLED_FLAG if sampled else _UNSAMPLED_FLAG
    return f"00-{trace_id:032x}-{span_id:016x}-{flags}"
