"""Gradium TTS provider (TASK-WEB-002, ST-3).

Symmetric mirror of stt_validation/gradium_provider.py for the voice-out side.
Implements the `TtsProvider` protocol so the runner, telemetry and QA harness stay
unchanged. The WebSocket transport is injectable so unit tests never hit the
network and no external dependency is imported on the default (non-live) path.
The API key is never placed in an exception message, log or telemetry attribute.

Contract locked by the ST-1 live spike, see docs/qa/gradium-tts-contract.md:
connect with `x-api-key` -> send `setup` -> expect `ready` -> send `text` +
`end_of_stream` -> collect `audio` (base64 PCM16) chunks until `end_of_stream`.
"""

import asyncio
import base64
import json
from typing import Any, Callable

from .providers import DEFAULT_AUDIO_FORMAT, EmptyTextError

GRADIUM_TTS_URL = "wss://api.gradium.ai/api/speech/tts"
DEFAULT_MODEL = "default"
DEFAULT_OUTPUT_FORMAT = DEFAULT_AUDIO_FORMAT  # pcm_16000 (PCM16 mono 16 kHz)
# `voice_id=default` is rejected by Gradium ("Embeddings not found"); a real
# catalog voice id is required. Elise (FR) is the project default (spike ST-1).
DEFAULT_VOICE_ID = "b35yykvVppLXyw_l"
DEFAULT_TIMEOUT_S = 30.0


class GradiumTtsError(RuntimeError):
    """Gradium TTS failed. The message is safe to surface (never carries the key)."""


# (url, headers, messages_to_send, timeout) -> server messages (JSON-parsed, in order)
Transport = Callable[[str, dict[str, str], list[dict[str, Any]], float], list[dict[str, Any]]]


class GradiumTtsProvider:
    name = "gradium-tts"

    def __init__(
        self,
        api_key: str,
        *,
        voice_id: str = DEFAULT_VOICE_ID,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        model_name: str = DEFAULT_MODEL,
        url: str = GRADIUM_TTS_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: Transport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Gradium API key is required")
        if not voice_id:
            raise ValueError("Gradium voice_id is required")
        self._api_key = api_key
        self._voice_id = voice_id
        self._output_format = output_format
        self._model_name = model_name
        self._url = url
        self._timeout_s = timeout_s
        self._transport = transport or _websocket_transport

    @property
    def audio_format(self) -> str:
        return self._output_format

    def synthesize(self, text: str) -> bytes:
        if not text or not text.strip():
            raise EmptyTextError("No text to synthesize")
        messages = self._transport(
            self._url,
            {"x-api-key": self._api_key},
            [
                {
                    "type": "setup",
                    "model_name": self._model_name,
                    "voice_id": self._voice_id,
                    "output_format": self._output_format,
                },
                {"type": "text", "text": text},
                {"type": "end_of_stream"},
            ],
            self._timeout_s,
        )
        return _collect_pcm(messages)


def _collect_pcm(messages: list[dict[str, Any]]) -> bytes:
    """Fold server messages into raw PCM bytes, mapping protocol errors to safe errors."""
    chunks: list[bytes] = []
    for message in messages:
        mtype = message.get("type")
        if mtype == "error":
            raise _protocol_error(message)
        if mtype == "audio":
            audio_b64 = message.get("audio")
            if audio_b64:
                chunks.append(base64.b64decode(audio_b64))
        elif mtype == "end_of_stream":
            break
    if not chunks:
        raise GradiumTtsError("Gradium TTS returned no audio for the given text")
    return b"".join(chunks)


def _protocol_error(message: dict[str, Any]) -> GradiumTtsError:
    code = message.get("code")
    text = str(message.get("message", "")).lower()
    if "credit" in text:
        return GradiumTtsError("Gradium TTS credits exhausted")
    if "embeddings not found" in text:
        return GradiumTtsError("Gradium TTS voice id is invalid")
    if code == 401 or "auth" in text:
        return GradiumTtsError("Gradium TTS authentication failed")
    return GradiumTtsError(f"Gradium TTS service error (code {code})")


def _websocket_transport(
    url: str,
    headers: dict[str, str],
    messages: list[dict[str, Any]],
    timeout: float,
) -> list[dict[str, Any]]:
    """Live path: run the WebSocket handshake and collect server messages."""
    return asyncio.run(_run_ws(url, headers, messages, timeout))


async def _run_ws(
    url: str,
    headers: dict[str, str],
    messages: list[dict[str, Any]],
    timeout: float,
) -> list[dict[str, Any]]:
    # `websockets` is imported lazily so the module (and every unit test using an
    # injected transport) never requires the dependency on the offline path.
    import websockets

    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            for message in messages:
                await ws.send(json.dumps(message))
            return await _recv_until_end(ws, timeout)
    except asyncio.TimeoutError as exc:
        raise TimeoutError("Gradium TTS request timed out") from exc
    except websockets.exceptions.WebSocketException as exc:
        # Handshake-level failures (e.g. HTTP 401 during the upgrade) — the real
        # auth path, distinct from an in-stream {"type":"error"} message. Mapped
        # to a safe message so the raw exception (and any header echo) never leaks.
        raise GradiumTtsError("Gradium TTS connection was rejected") from exc
    except OSError as exc:  # connection refused / DNS / TLS
        raise GradiumTtsError("Gradium TTS service is unreachable") from exc


async def _recv_until_end(ws: Any, timeout: float) -> list[dict[str, Any]]:
    received: list[dict[str, Any]] = []
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        data = json.loads(raw)
        received.append(data)
        if data.get("type") in ("end_of_stream", "error"):
            break
    return received
