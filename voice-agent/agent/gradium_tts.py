"""Gradium TTS — speech synthesis via WebSocket + PCM-to-WAV conversion."""

import base64
import json
import struct
import time

import websockets

TTS_SAMPLE_RATE = 16000


def pcm_to_wav(pcm_data: bytes, sample_rate: int = TTS_SAMPLE_RATE) -> bytes:
    """Wrap raw PCM 16-bit mono data in a WAV header so the browser can decode it."""
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(pcm_data)
    file_size = 36 + data_size

    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', file_size, b'WAVE',
        b'fmt ', 16, 1, num_channels,
        sample_rate, byte_rate, block_align, bits_per_sample,
        b'data', data_size,
    )
    return header + pcm_data


async def synthesize_speech(
    text: str,
    voice_id: str,
    api_key: str,
    output_format: str = "pcm_16000",
) -> bytes | None:
    """Send text to Gradium TTS via WebSocket and return audio.

    For `pcm_16000` (web/browser) the PCM is wrapped in a WAV header so the
    browser can decode it. For `ulaw_8000` (telephony) the raw mu-law bytes are
    returned as-is (Twilio Media Streams expects raw mu-law payloads).
    """
    start = time.perf_counter()
    try:
        async with websockets.connect(
            "wss://api.gradium.ai/api/speech/tts",
            additional_headers={"x-api-key": api_key},
        ) as ws:
            setup_msg = json.dumps({
                "type": "setup",
                "model_name": "default",
                "voice_id": voice_id,
                "output_format": output_format,
            })
            await ws.send(setup_msg)

            ready = await ws.recv()
            ready_data = json.loads(ready)
            if ready_data.get("type") != "ready":
                print(f"[TTS] Setup failed: {ready_data}", flush=True)
                return None

            await ws.send(json.dumps({"type": "text", "text": text}))
            await ws.send(json.dumps({"type": "end_of_stream"}))

            audio_chunks = []
            async for msg in ws:
                data = json.loads(msg)
                if data.get("type") == "audio":
                    audio_b64 = data.get("audio", "")
                    if audio_b64:
                        audio_chunks.append(base64.b64decode(audio_b64))
                elif data.get("type") == "end_of_stream":
                    break

            if audio_chunks:
                audio_data = b"".join(audio_chunks)
                elapsed_ms = (time.perf_counter() - start) * 1000
                print(f"[LATENCY] step=tts ms={elapsed_ms:.0f} chars={len(text)} fmt={output_format}", flush=True)
                if output_format == "pcm_16000":
                    return pcm_to_wav(audio_data, TTS_SAMPLE_RATE)
                return audio_data
            return None

    except Exception as e:
        print(f"[TTS] Error: {e}", flush=True)
        return None
