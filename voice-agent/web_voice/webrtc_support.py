"""WebRTC dependency guard (Sprint 6 / TASK-WEB-007, spike).

`SmallWebRTCTransport` hard-imports the optional WebRTC stack (`aiortc`, `av`,
`cv2`) at class-import time, so importing it without the extra raises `ImportError`.
The base voice-agent test suite (STT / TTS / backend bridge) must stay runnable
without those heavy C-extension wheels, so every WebRTC entry point goes through
this guard instead of importing the transport at module top level.

Install the extra to enable the real transport:

    pip install "pipecat-ai[webrtc]"

See `docs/qa/webrtc-transport-spike.md` for the dependency footprint and the
Python 3.14 / offline-index risks found during the spike.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WebRtcSupport:
    """Result of probing for the WebRTC transport dependencies."""

    available: bool
    missing: str | None = None

    @property
    def install_hint(self) -> str:
        return 'pip install "pipecat-ai[webrtc]"'


def probe_webrtc_support() -> WebRtcSupport:
    """Report whether `SmallWebRTCTransport` can be imported in this environment.

    Never raises: a missing extra is a supported (degraded) state, not an error.
    """
    try:
        from pipecat.transports.smallwebrtc.transport import (  # noqa: F401
            SmallWebRTCTransport,
        )
    except ImportError as exc:
        return WebRtcSupport(available=False, missing=str(exc))
    return WebRtcSupport(available=True)


def load_webrtc_transport():
    """Import and return `SmallWebRTCTransport`, or raise a clear error if missing."""
    support = probe_webrtc_support()
    if not support.available:
        raise RuntimeError(
            f"WebRTC transport unavailable ({support.missing}). "
            f"Install it with: {support.install_hint}"
        )
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

    return SmallWebRTCTransport
