"""Gradium STT — transcription via REST endpoint."""

import json

import httpx


async def transcribe_audio(
    audio_data: bytes,
    language: str,
    api_key: str,
) -> str | None:
    """Send audio to Gradium STT REST endpoint and return transcription."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.gradium.ai/api/post/speech/asr",
                headers={"x-api-key": api_key},
                params={
                    "model_name": "default",
                    "input_format": "pcm_16000",
                    "json_config": json.dumps({"language": language}),
                },
                content=audio_data,
            )

            if r.status_code != 200:
                print(f"[STT] HTTP {r.status_code}: {r.text[:200]}", flush=True)
                return None

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
            return result.strip() if result.strip() else None

    except Exception as e:
        print(f"[STT] Error: {e}", flush=True)
        return None
