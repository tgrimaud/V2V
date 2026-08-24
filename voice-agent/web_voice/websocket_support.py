"""WebSocket transport socle for the interim external-browser voice path (TASK-WEB-026).

ADR-0043 socle decision (spike output): use pipecat's **`SingleClientWebsocketServerTransport`**
(`pipecat.transports.websocket.server`), which is built on `websockets.asyncio.server.serve`
and pulls **no FastAPI** — FastAPI lives only in the sibling `websocket.fastapi` module we
never import. `websockets` is already a runtime dependency (Gradium TTS client), so no new
dependency is added. The transport is driven on the shared persistent asyncio loop
(`web_voice/async_loop.py`), like the WebRTC signaling path.

The frame framing (JSON control + binary PCM16/16 kHz) is injected via the pipecat
serializer seam (`WebSocketAudioSerializer`, `web_voice/websocket_framing.py`), which keeps
the socket/demux layer reusable by the Sprint 13 Genesys Audio Connector adapter.
"""

from dataclasses import dataclass

from web_voice.websocket_framing import WebSocketAudioSerializer

DEFAULT_SAMPLE_RATE = 16000


@dataclass(frozen=True)
class WebSocketSupport:
    """Result of probing for the WebSocket server transport (no FastAPI)."""

    available: bool
    missing: str | None = None

    @property
    def install_hint(self) -> str:
        return "pip install 'websockets>=13,<17'"


def probe_websocket_support() -> WebSocketSupport:
    """Report whether the websockets-based server transport can be imported.

    Never raises; a missing dependency is a supported (degraded) state. This path
    deliberately imports the `websocket.server` module (websockets-based), never
    `websocket.fastapi`, so no FastAPI/Starlette/uvicorn install is required.
    """
    try:
        from pipecat.transports.websocket.server import (  # noqa: F401
            SingleClientWebsocketServerTransport,
        )
    except ImportError as exc:
        return WebSocketSupport(available=False, missing=str(exc))
    return WebSocketSupport(available=True)


def load_websocket_transport_classes():
    """Import and return `(Transport, Params)`, or raise a clear error if missing."""
    support = probe_websocket_support()
    if not support.available:
        raise RuntimeError(
            f"WebSocket transport unavailable ({support.missing}). "
            f"Install it with: {support.install_hint}"
        )
    from pipecat.transports.websocket.server import (
        SingleClientWebsocketServerParams,
        SingleClientWebsocketServerTransport,
    )

    return SingleClientWebsocketServerTransport, SingleClientWebsocketServerParams


def build_websocket_audio_transport(
    host: str,
    port: int,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    serializer: WebSocketAudioSerializer | None = None,
    allowed_origins: list[str] | None = None,
):
    """Construct the browser WebSocket audio transport socle (no FastAPI).

    Bidirectional PCM16/16 kHz audio with the AudioHook-shaped framing serializer.
    Callers start/stop it by adding it to a pipeline that runs on the shared loop.

    `allowed_origins` is the Origin-header allowlist (anti-CSWSH). This socle exposes
    the seam; the effective external allowlist is set when the path is wired to the
    HAProxy edge (TASK-INFRA-010 / TASK-WEB-030). ``None`` keeps pipecat's default
    (``PIPECAT_ALLOWED_ORIGINS`` env, empty = allow all) so dev/loopback still works.
    """
    transport_cls, params_cls = load_websocket_transport_classes()
    kwargs = {
        "audio_in_enabled": True,
        "audio_out_enabled": True,
        "audio_in_sample_rate": sample_rate,
        "audio_out_sample_rate": sample_rate,
        "add_wav_header": False,
        "serializer": serializer or WebSocketAudioSerializer(),
    }
    if allowed_origins is not None:
        kwargs["allowed_origins"] = allowed_origins
    return transport_cls(params=params_cls(**kwargs), host=host, port=port)
