"""Graceful 15-minute call-cap + hard-bounded drain for the Genesys adapter (TASK-WEB-041).

Extracted from `genesys_app.py` (review) so the handler module stays within the module
budget. Owns the cap timer and its teardown safety:

- At the cap the session is *drained* (trailing partial finalized, answer spoken) so
  Architect resumes and routes to the advisor queue — never a silent mid-call cut (R2).
- The drain is HARD-BOUNDED: if it wedges (a stuck STT/TTS provider), the session is
  force-stopped after a bounded grace so the concurrency slot + WS are ALWAYS freed at
  cap+grace (review Major #1).
- `DrainOnce` ensures the cap timer and the peer-disconnect handler never both drain the
  same session (review Minor: double-drain guard); the disconnect cancels a pending cap
  before draining itself.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from voice_common.telemetry import TelemetryRecorder

from .genesys_config import (
    GENESYS_AUDIO_CONNECTOR_CHANNEL,
    REASON_CAP_DRAIN_TIMEOUT,
    REASON_CAP_REACHED,
    SESSION_CAP_EVENT,
    SESSION_CAP_FORCED_EVENT,
)
from .websocket_app import _safe_stop

_logger = logging.getLogger(__name__)


class DrainOnce:
    """Drains the session at most once, whichever of the cap timer or the peer disconnect
    fires first (review Minor: no double `drain()`), and carries the cap task so the
    disconnect path can cancel a still-pending cap before draining itself.
    """

    def __init__(self) -> None:
        self._drained = False
        self.cap: asyncio.Task | None = None

    async def drain(self, session: Any) -> bool:
        if self._drained:
            return False
        self._drained = True
        await session.drain()
        return True


def wire_disconnect_drain(
    transport: Any,
    session: Any,
    drain: DrainOnce,
    on_disconnect: Callable[[], None] | None = None,
) -> None:
    """Drain the session when the peer disconnects so `session.run()` returns on its own.

    Cancels a still-pending cap first so the cap timer and the disconnect can never both
    drain the same session (double-drain guard). `on_disconnect` (TASK-WEB-042) records the
    call-end reason at the true trigger (the peer going away) before the drain; it is a plain
    sync callback so it never blocks the teardown.
    """

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(_transport, _client) -> None:  # noqa: ANN001 - pipecat callback
        if on_disconnect is not None:
            on_disconnect()
        cancel_cap(drain.cap)
        try:
            await drain.drain(session)
        except Exception:  # noqa: BLE001 - drain is best-effort; run() still returns on cancel
            _logger.debug("genesys drain on disconnect failed", exc_info=True)


def schedule_cap(
    session: Any,
    drain: DrainOnce,
    telemetry: TelemetryRecorder,
    cid: str,
    max_session_s: float,
    grace: float,
    on_cap: Callable[[], None] | None = None,
) -> asyncio.Task | None:
    """Arm the graceful 15-min cap timer, or None when disabled (max_session_s <= 0).

    `on_cap` (TASK-WEB-042) records the call-end reason when the cap is actually reached,
    before the graceful drain, so a cap-ended call is attributed as `cap_reached` and not as
    a generic client disconnect.
    """
    if max_session_s <= 0:
        return None
    return asyncio.ensure_future(
        _cap_after(session, drain, telemetry, cid, max_session_s, grace, on_cap)
    )


async def _cap_after(
    session: Any,
    drain: DrainOnce,
    telemetry: TelemetryRecorder,
    cid: str,
    delay: float,
    grace: float,
    on_cap: Callable[[], None] | None = None,
) -> None:
    """At the cap, record it and drain gracefully within a hard grace bound (never a cut)."""
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    if on_cap is not None:
        on_cap()
    telemetry.record(
        SESSION_CAP_EVENT,
        correlation_id=cid,
        channel=GENESYS_AUDIO_CONNECTOR_CHANNEL,
        reason=REASON_CAP_REACHED,
        max_session_s=delay,
    )
    await _drain_within_grace(session, drain, telemetry, cid, grace)


async def _drain_within_grace(
    session: Any, drain: DrainOnce, telemetry: TelemetryRecorder, cid: str, grace: float
) -> None:
    """Drain at the cap; force a hard stop if drain wedges so the slot is always freed."""
    try:
        await asyncio.wait_for(drain.drain(session), timeout=grace)
    except asyncio.TimeoutError:
        telemetry.record(
            SESSION_CAP_FORCED_EVENT,
            correlation_id=cid,
            channel=GENESYS_AUDIO_CONNECTOR_CHANNEL,
            reason=REASON_CAP_DRAIN_TIMEOUT,
            grace_s=grace,
        )
        await _safe_stop(session)
    except Exception:  # noqa: BLE001 - drain is best-effort; teardown still runs on stop
        _logger.debug("genesys cap drain failed", exc_info=True)


def cancel_cap(cap: asyncio.Task | None) -> None:
    if cap is not None and not cap.done():
        cap.cancel()
