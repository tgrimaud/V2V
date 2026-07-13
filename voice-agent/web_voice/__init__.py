"""Web voice ingress for US-019 (STT half, TASK-WEB-001).

The web channel + voice runtime own audio capture, transport and the STT provider
call (see docs/architecture/channel-identity-boundary.md). This package turns the
STT validation scaffold into a real web ingress: it accepts browser-captured PCM
audio, builds a minimal channel envelope, and transcribes the turn through the
existing SttProvider protocol without forking the provider.
"""

from .end_of_turn import (
    END_OF_TURN_SPAN,
    SIGNAL_CLIENT_STOP,
    SIGNAL_SILENCE_WINDOW,
    EndOfTurnDetector,
    EndOfTurnResult,
)
from .envelope import ChannelEnvelope
from .ingress import WebVoiceIngress

__all__ = [
    "END_OF_TURN_SPAN",
    "SIGNAL_CLIENT_STOP",
    "SIGNAL_SILENCE_WINDOW",
    "ChannelEnvelope",
    "EndOfTurnDetector",
    "EndOfTurnResult",
    "WebVoiceIngress",
]
