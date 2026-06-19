"""Bridge WebSocket server — translates the frontend's custom protocol to Pipecat frames.

Frontend protocol:
  - Client sends: binary audio chunks (PCM 16kHz 16-bit mono)
  - Client sends: text "END_OF_SPEECH" when done speaking
  - Server sends: JSON {"type":"transcription","text":"..."} after STT
  - Server sends: JSON {"type":"answer","text":"..."} after RAG
  - Server sends: binary audio (PCM 16kHz) for TTS playback

This server sits between the browser and the Gradium STT/TTS + RAG backend pipeline.
"""

import asyncio
import json
import os
import struct
import sys

import websockets
from dotenv import load_dotenv

from agent.backend_client import RAGBackendClient

load_dotenv()

GRADIUM_API_KEY = os.getenv("GRADIUM_API_KEY")
GRADIUM_VOICE_ID = os.getenv("GRADIUM_VOICE_ID", "default")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8081")
WS_HOST = os.getenv("VOICE_AGENT_HOST", "0.0.0.0")
WS_PORT = int(os.getenv("VOICE_AGENT_PORT", "8765"))

SAMPLE_RATE = 16000
TTS_SAMPLE_RATE = 16000

VOICE_MAP = {
    "fr": os.getenv("GRADIUM_VOICE_FR", "b35yykvVppLXyw_l"),  # Elise
    "en": os.getenv("GRADIUM_VOICE_EN", "YTpq7expH9539ERJ"),  # Emma
}
DEFAULT_LANGUAGE = "fr"


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


async def handle_client(websocket):
    """Handle one browser client session."""
    backend = RAGBackendClient(base_url=BACKEND_URL)
    print(f"[CLIENT] Connected from {websocket.remote_address}", flush=True)

    audio_buffer = bytearray()
    language = DEFAULT_LANGUAGE

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                audio_buffer.extend(message)
            elif isinstance(message, str):
                if message == "END_OF_SPEECH":
                    if not audio_buffer:
                        continue

                    audio_data = bytes(audio_buffer)
                    audio_buffer.clear()

                    print(f"[STT] Transcribing {len(audio_data)} bytes (lang={language})...", flush=True)
                    transcription = await transcribe_audio(audio_data, language)

                    if transcription:
                        print(f"[STT] Result: '{transcription}'", flush=True)
                        await websocket.send(json.dumps({
                            "type": "transcription",
                            "text": transcription,
                        }))

                        answer, audio_response = await process_question(
                            backend, transcription, language
                        )

                        await websocket.send(json.dumps({
                            "type": "answer",
                            "text": answer,
                        }))

                        if audio_response:
                            await websocket.send(audio_response)
                    else:
                        print("[STT] No transcription returned (silence?)", flush=True)
                        await websocket.send(json.dumps({
                            "type": "answer",
                            "text": "",
                        }))
                else:
                    try:
                        data = json.loads(message)
                        if data.get("type") == "set_language":
                            new_lang = data.get("language", DEFAULT_LANGUAGE)
                            if new_lang in VOICE_MAP:
                                language = new_lang
                                print(f"[CLIENT] Language set to '{language}'", flush=True)
                                await websocket.send(json.dumps({
                                    "type": "language_changed",
                                    "language": language,
                                }))
                    except (json.JSONDecodeError, KeyError):
                        pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        await backend.close()
        print(f"[CLIENT] Disconnected", flush=True)


async def transcribe_audio(audio_data: bytes, language: str = DEFAULT_LANGUAGE) -> str | None:
    """Send audio to Gradium STT REST endpoint and return transcription."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.gradium.ai/api/post/speech/asr",
                headers={"x-api-key": GRADIUM_API_KEY},
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


async def process_question(backend: RAGBackendClient, question: str, language: str = DEFAULT_LANGUAGE) -> tuple[str, bytes | None]:
    """Send question to RAG backend and synthesize answer via Gradium TTS."""
    try:
        result = await backend.ask(question)
        answer = result.get("answer", "Désolé, je n'ai pas compris.")
    except Exception as e:
        print(f"[RAG] Error: {e}")
        answer = "Désolé, une erreur est survenue. Veuillez réessayer."

    audio = await synthesize_speech(answer, language)
    return answer, audio


async def synthesize_speech(text: str, language: str = DEFAULT_LANGUAGE) -> bytes | None:
    """Send text to Gradium TTS via WebSocket and return WAV audio."""
    import base64

    voice_id = VOICE_MAP.get(language, VOICE_MAP[DEFAULT_LANGUAGE])

    try:
        async with websockets.connect(
            "wss://api.gradium.ai/api/speech/tts",
            additional_headers={"x-api-key": GRADIUM_API_KEY},
        ) as ws:
            setup_msg = json.dumps({
                "type": "setup",
                "model_name": "default",
                "voice_id": voice_id,
                "output_format": "pcm_16000",
            })
            await ws.send(setup_msg)

            ready = await ws.recv()
            ready_data = json.loads(ready)
            if ready_data.get("type") != "ready":
                print(f"[TTS] Unexpected setup response: {ready_data}", flush=True)

            await ws.send(json.dumps({
                "type": "text",
                "text": text,
            }))
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
                pcm_data = b"".join(audio_chunks)
                return pcm_to_wav(pcm_data, TTS_SAMPLE_RATE)
            return None

    except Exception as e:
        print(f"[TTS] Error: {e}")
        return None


async def main():
    if not GRADIUM_API_KEY:
        print("ERROR: GRADIUM_API_KEY not set.", flush=True)
        sys.exit(1)

    print(f"Voice agent bridge listening on ws://{WS_HOST}:{WS_PORT}", flush=True)
    print(f"  STT/TTS: Gradium (direct WebSocket API)", flush=True)
    print(f"  Backend: {BACKEND_URL}", flush=True)

    async with websockets.serve(handle_client, WS_HOST, WS_PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
