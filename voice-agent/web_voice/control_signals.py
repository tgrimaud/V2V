"""Pluggable control-signal seam for the streaming voice path (TASK-WEB-029, ADR-0043/0040).

Barge-in, end-of-turn, call-end and playback lifecycle are the **control plane** of a voice
turn. Today they are produced by the energy/amplitude detectors inside `StreamingSttProcessor`
(transport-agnostic) and by the WebSocket serializer (client control frames). This module adds
the seam that lets those same signals come from a **pluggable source** instead — e.g. the
Sprint 13 Genesys Audio Connector protocol events, or a browser client control channel — without
touching the session core. The vocabulary is named after Genesys AudioHook semantics so the
mapping is 1:1 later (ADR-0040).

The energy detectors stay authoritative on the browser path (no source injected → the processor
is a transparent pass-through). A source only *adds* another way to raise the same signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

from pipecat.frames.frames import ControlFrame


class ControlSignalType(str, Enum):
    """Control-plane vocabulary, named after Genesys AudioHook semantics (ADR-0040)."""

    BARGE_IN = "barge_in"
    END_OF_TURN = "end_of_turn"
    CALL_END = "call_end"
    PLAYBACK_STARTED = "playback_started"
    PLAYBACK_COMPLETED = "playback_completed"


@dataclass(frozen=True)
class ControlSignal:
    """One control-plane event from a source (energy detector, WS client, Genesys, tests)."""

    type: ControlSignalType
    attributes: dict[str, Any] = field(default_factory=dict)


class ControlSignalSource:
    """Port: an async stream of `ControlSignal`s from a non-energy source.

    Implementations must be cancellation-safe: the processor cancels the consumer task on
    `EndFrame`/`CancelFrame` and then calls `close()`.
    """

    def signals(self) -> AsyncIterator[ControlSignal]:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class EndOfTurnSignalFrame(ControlFrame):
    """Control-plane end-of-turn: finalize the current STT turn now, regardless of the energy
    detector's silence window (TASK-WEB-029). A `ControlFrame` so it flows in order downstream
    to `StreamingSttProcessor`, which owns the turn's streaming session."""
