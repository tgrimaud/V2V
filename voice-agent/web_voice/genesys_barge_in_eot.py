"""Barge-in / end-of-turn / end-of-call ownership for the Genesys Audio Connector path
(TASK-WEB-042, ADR-0049 point 4 / ADR-0040 / ADR-0025 / ADR-0035).

Per-path ownership, **reusing the shared streaming machinery** — never a bespoke parallel path
(ADR-0043/0047). The Genesys transport builds the same `StreamingSttProcessor` +
`CallEndFarewellProcessor` through the shared `SessionFactory`:

- **Barge-in** is the SAME Pipecat-native `broadcast_interruption()` + bot-speaking gate +
  amplitude/N-frame sustained-onset discriminator (ADR-0025), env-tunable via the shared
  `VOICE_BARGE_IN_THRESHOLD` / `VOICE_BARGE_IN_FRAMES`. **End-of-turn** uses the SAME
  `StreamingEndOfTurnDetector` + silence-window seam (`_silence_window_config()`). Both emit
  `voice.barge_in.*` / `voice.end_of_turn.*` with `channel=genesys_audio_connector` from the
  envelope, so per-channel observability is automatic.
- **End-of-call** reuses the `CallEndFarewellProcessor` confirmation turn + the Genesys
  `DrainOnce` teardown; this module wires the injected `end_call(signal)` to that drain and
  records the `voice.call_end` reason on the Genesys channel.

Genesys-specific pieces that live here: (1) a per-transport control-signal SOURCE seam so the
native AudioHook control events (barge-in / end-of-turn / call-end signalled by Genesys rather
than detected on our PCM) can become authoritative later, disabling the in-house detectors on
this path (ADR-0049 point 4) — EMPTY by default (`detector` mode), so the detectors stay
authoritative and the path works with NO native events today; (2) the end-of-call teardown
wiring + `voice.call_end` reason recording.

TODO(TASK-WEB-042: live-measurement): the native AudioHook control event names/shapes are NOT
yet confirmed — they need the live Genesys Architect flow (DEC-015,
`docs/operations/genesys-live-measurement-runbook.md`). Until then `native` mode yields no
signals (idle seam) and `detector` mode is the default. When the live events land: populate
`GenesysControlSignalSource._EVENT_TYPE_MAP` with the confirmed names AND disable the in-house
detectors on this path so the two do not both fire (ADR-0049 point 4).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncIterator, Callable

from voice_common.telemetry import TelemetryRecorder

from .control_signals import ControlSignal, ControlSignalSource, ControlSignalType
from .genesys_cap import DrainOnce, wire_disconnect_drain
from .genesys_config import (
    CALL_END_EVENT,
    GENESYS_AUDIO_CONNECTOR_CHANNEL,
    REASON_CAP_REACHED,
    REASON_CLIENT_DISCONNECT,
    REASON_CUSTOMER_FAREWELL,
)

_logger = logging.getLogger(__name__)

CONTROL_MODE_ENV_VAR = "VOICE_GENESYS_CONTROL_MODE"
CONTROL_MODE_DETECTOR = "detector"
CONTROL_MODE_NATIVE = "native"


def genesys_control_mode_config() -> str:
    """Resolve the Genesys barge-in/EOT ownership mode (default `detector`).

    `detector` (default): the in-house energy/amplitude detectors own barge-in + end-of-turn
    (the working interim path — native AudioHook events are not confirmed yet). `native`: wire
    the native-event control-signal source (idle until the event map is confirmed live). An
    unknown value falls back to `detector` rather than crashing a call.
    """
    raw = (os.environ.get(CONTROL_MODE_ENV_VAR) or "").strip().lower()
    return raw if raw in (CONTROL_MODE_DETECTOR, CONTROL_MODE_NATIVE) else CONTROL_MODE_DETECTOR


class GenesysControlSignalSource(ControlSignalSource):
    """Maps Genesys native AudioHook control events -> `ControlSignal`s (ADR-0049 point 4).

    PREPARATION seam: with no live AudioHook control stream wired (`events is None`),
    `signals()` yields nothing, so the in-house energy detectors stay authoritative and the
    Genesys path works with NO native events. Injecting an async `events` stream (future,
    once the live event names are confirmed) makes Genesys the barge-in / end-of-turn /
    call-end authority on this path.
    """

    # TODO(TASK-WEB-042: live-measurement): fill with the CONFIRMED native AudioHook control
    # event names (candidates from ADR-0040/0049: "barge-in", "playback-started"/
    # "playback-completed", "BotTurnResponse"/end-of-turn). Empty today -> the seam is a no-op.
    # TODO(TASK-WEB-042: R4 - populate map AND disable in-house detectors together): populating
    # this map without disabling the in-house energy/amplitude detectors on the Genesys path would
    # let BOTH fire (double barge-in/EOT, ADR-0049 point 4). Do the two edits in one change.
    _EVENT_TYPE_MAP: dict[str, ControlSignalType] = {}

    def __init__(
        self,
        envelope: Any,
        telemetry: TelemetryRecorder | None = None,
        *,
        events: AsyncIterator[Any] | None = None,
    ) -> None:
        self._envelope = envelope
        self._telemetry = telemetry
        self._events = events

    async def signals(self) -> AsyncIterator[ControlSignal]:
        if self._events is None:
            return  # idle seam: the in-house detectors own barge-in/EOT on this path
        async for raw in self._events:
            signal = self._to_signal(raw)
            if signal is not None:
                yield signal

    def _to_signal(self, raw: Any) -> ControlSignal | None:
        name = raw.get("type") if isinstance(raw, dict) else getattr(raw, "type", None)
        signal_type = self._EVENT_TYPE_MAP.get(name)
        if signal_type is None:
            return None
        return ControlSignal(signal_type, attributes={"source": "genesys_native"})


def genesys_control_source_factory(
    mode: str,
) -> Callable[[Any], ControlSignalSource | None] | None:
    """Return the `(envelope -> ControlSignalSource | None)` factory for the Genesys path.

    `detector` mode -> None: the `ControlSignalProcessor` is a transparent pass-through and
    the in-house detectors own barge-in/EOT. `native` mode -> a `GenesysControlSignalSource`
    per call (idle until a live event stream is wired, TODO live-measurement).
    """
    if mode != CONTROL_MODE_NATIVE:
        return None
    _warn_if_native_seam_idle()

    def _factory(envelope: Any) -> ControlSignalSource:
        return GenesysControlSignalSource(envelope)

    return _factory


def _warn_if_native_seam_idle() -> None:
    """Startup WARN when `native` mode resolves to an EMPTY event map (ADR-0049 R4).

    The native AudioHook control seam is selected but `_EVENT_TYPE_MAP` is not populated yet, so
    it emits no signals: the in-house energy/amplitude detectors remain the barge-in/end-of-turn
    authority on the Genesys path. Static operational warning only - no PII, no per-call state.
    """
    if GenesysControlSignalSource._EVENT_TYPE_MAP:
        return
    _logger.warning(
        "genesys control mode=native but the native AudioHook event map is empty: "
        "native control seam is idle, in-house detectors remain authoritative "
        "(TASK-WEB-042 / ADR-0049 R4)"
    )


class GenesysCallControl:
    """Owns the Genesys `DrainOnce` teardown + single `voice.call_end` reason emission.

    Mirrors the WebRTC `_record_end_of_call` guard: whichever termination path fires first
    (customer farewell / 15-min cap / peer disconnect) records the reason exactly once, on the
    `genesys_audio_connector` channel, so a bot farewell is never overwritten by the later
    disconnect the drain itself triggers. No PII is recorded — reason + correlation id only.
    """

    def __init__(self, telemetry: TelemetryRecorder, cid: str, drain: DrainOnce) -> None:
        self._telemetry = telemetry
        self._cid = cid
        self.drain = drain
        self._reason: str | None = None

    def record(self, reason: str, signal: str | None = None) -> None:
        if self._reason is not None:
            return
        self._reason = reason
        attributes: dict[str, Any] = {
            "correlation_id": self._cid,
            "channel": GENESYS_AUDIO_CONNECTOR_CHANNEL,
            "reason": reason,
        }
        if signal is not None:
            attributes["signal"] = signal
        self._telemetry.record(CALL_END_EVENT, **attributes)

    def on_cap(self) -> None:
        self.record(REASON_CAP_REACHED)

    def record_default(self) -> None:
        """Teardown net: no farewell/cap = peer disconnect (idempotent, never overrides)."""
        self.record(REASON_CLIENT_DISCONNECT)


def wire_genesys_call_control(
    transport: Any, session: Any, farewell: Any, telemetry: TelemetryRecorder, cid: str
) -> GenesysCallControl:
    """Wire the Genesys end-of-call paths onto the shared drain teardown (TASK-WEB-042).

    Creates the `DrainOnce` guard, records `client_disconnect` at peer disconnect, and wires
    the farewell processor's `end_call(signal)` to record `customer_farewell` + drain (the
    ADR-0035 confirmation turn). Returns the `GenesysCallControl` the handler drives.
    """
    control = GenesysCallControl(telemetry, cid, DrainOnce())
    wire_disconnect_drain(transport, session, control.drain, on_disconnect=control.record_default)
    _wire_farewell(farewell, session, control)
    return control


def _wire_farewell(farewell: Any, session: Any, control: GenesysCallControl) -> None:
    if farewell is None:
        return

    async def _end_call(signal: str) -> None:
        control.record(REASON_CUSTOMER_FAREWELL, signal=signal)
        # Schedule the drain OFF the pipeline task: the farewell runs inside session.run(),
        # so we must not await our own run() from within it (mirrors the WebRTC path).
        asyncio.ensure_future(_drain_after_farewell(session, control.drain))

    farewell.set_end_call(_end_call)


async def _drain_after_farewell(session: Any, drain: DrainOnce) -> None:
    """Drain the ADR-0035 closing message via the TASK-WEB-008 path (best-effort)."""
    try:
        await drain.drain(session)
    except Exception:  # noqa: BLE001 - teardown is best-effort, never blocks/raises
        _logger.debug("genesys farewell drain failed", exc_info=True)
