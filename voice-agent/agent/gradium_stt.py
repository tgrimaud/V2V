"""Gradium STT — transcription via REST endpoint."""

import json
import time
from dataclasses import dataclass

import httpx

_shared_client: httpx.AsyncClient | None = None


@dataclass
class SttResult:
    text: str | None = None
    error: str | None = None
    error_code: str | None = None


def get_stt_client() -> httpx.AsyncClient:
    """Return a shared httpx client (reuses TCP/TLS connections)."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=30.0)
    return _shared_client


async def close_stt_client():
    """Close the shared STT client (call on session end)."""
    global _shared_client
    if _shared_client and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None


async def transcribe_audio(
    audio_data: bytes,
    language: str,
    api_key: str,
    input_format: str = "pcm_16000",
) -> SttResult:
    """Send audio to Gradium STT REST endpoint and return transcription.

    `input_format` is the Gradium audio format: `pcm_16000` for browser/PCM
    clients, `ulaw_8000` for telephony (Twilio Media Streams / SIP).
    """
    start = time.perf_counter()
    try:
        client = get_stt_client()
        r = await client.post(
            "https://api.gradium.ai/api/post/speech/asr",
            headers={"x-api-key": api_key},
            params={
                "model_name": "default",
                "input_format": input_format,
                "json_config": json.dumps({"language": language}),
            },
            content=audio_data,
        )

        if r.status_code != 200:
            error_text = r.text[:200]
            print(f"[STT] HTTP {r.status_code}: {error_text}", flush=True)
            if "Insufficient credits" in error_text or "credits" in error_text.lower():
                return SttResult(error="Gradium STT credits exhausted", error_code="STT_CREDITS_EXHAUSTED")
            if r.status_code == 401:
                return SttResult(error="Gradium API key invalid", error_code="STT_AUTH_ERROR")
            return SttResult(error=f"STT service error (HTTP {r.status_code})", error_code="STT_ERROR")

        words = []
        for line in r.text.strip().split("\n"):
            if not line:
                continue
            data = json.loads(line)
            if data.get("type") == "text":
                word = data.get("text", "")
                if word:
                    words.append(word)

        result = " ".join(words)
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"[LATENCY] step=stt ms={elapsed_ms:.0f} bytes={len(audio_data)} fmt={input_format}", flush=True)
        return SttResult(text=result.strip() if result.strip() else None)

    except httpx.ConnectError:
        print("[STT] Connection error", flush=True)
        return SttResult(error="Cannot reach Gradium STT service", error_code="STT_UNREACHABLE")
    except Exception as e:
        print(f"[STT] Error: {e}", flush=True)
        return SttResult(error=f"STT error: {e}", error_code="STT_ERROR")
