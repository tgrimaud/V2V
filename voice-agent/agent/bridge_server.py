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


async def handle_client(websocket):
    """Handle one browser client session."""
    backend = RAGBackendClient(base_url=BACKEND_URL)
    print(f"[CLIENT] Connected from {websocket.remote_address}", flush=True)

    audio_buffer = bytearray()

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

                    print(f"[STT] Transcribing {len(audio_data)} bytes...", flush=True)
                    transcription = await transcribe_audio(audio_data)

                    if transcription:
                        print(f"[STT] Result: '{transcription}'", flush=True)
                        await websocket.send(json.dumps({
                            "type": "transcription",
                            "text": transcription,
                        }))

                        answer, audio_response = await process_question(
                            backend, transcription
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
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        await backend.close()
        print(f"[CLIENT] Disconnected", flush=True)


async def transcribe_audio(audio_data: bytes) -> str | None:
    """Send audio to Gradium STT via WebSocket and return transcription."""
    import base64

    try:
        async with websockets.connect(
            "wss://api.gradium.ai/api/speech/asr",
            additional_headers={"x-api-key": GRADIUM_API_KEY},
        ) as ws:
            setup_msg = json.dumps({
                "type": "setup",
                "model_name": "default",
                "input_format": "pcm_16000",
            })
            await ws.send(setup_msg)

            ready = await ws.recv()
            ready_data = json.loads(ready)
            if ready_data.get("type") != "ready":
                print(f"[STT] Unexpected setup response: {ready_data}")

            chunk_size = 3200  # 100ms of PCM 16kHz 16-bit mono
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                audio_b64 = base64.b64encode(chunk).decode()
                await ws.send(json.dumps({
                    "type": "audio",
                    "audio": audio_b64,
                }))

            await ws.send(json.dumps({"type": "end_of_stream"}))

            full_text = ""
            async for msg in ws:
                data = json.loads(msg)
                if data.get("type") == "text":
                    full_text += data.get("text", "")
                elif data.get("type") == "end_text":
                    full_text += data.get("text", "")
                elif data.get("type") == "end_of_stream":
                    break

            return full_text.strip() if full_text.strip() else None

    except Exception as e:
        print(f"[STT] Error: {e}")
        return None


async def process_question(backend: RAGBackendClient, question: str) -> tuple[str, bytes | None]:
    """Send question to RAG backend and synthesize answer via Gradium TTS."""
    try:
        result = await backend.ask(question)
        answer = result.get("answer", "Désolé, je n'ai pas compris.")
    except Exception as e:
        print(f"[RAG] Error: {e}")
        answer = "Désolé, une erreur est survenue. Veuillez réessayer."

    audio = await synthesize_speech(answer)
    return answer, audio


async def synthesize_speech(text: str) -> bytes | None:
    """Send text to Gradium TTS via WebSocket and return PCM audio."""
    import base64

    try:
        async with websockets.connect(
            "wss://api.gradium.ai/api/speech/tts",
            additional_headers={"x-api-key": GRADIUM_API_KEY},
        ) as ws:
            setup_msg = json.dumps({
                "type": "setup",
                "model_name": "default",
                "voice_id": GRADIUM_VOICE_ID,
                "output_format": "pcm_16000",
            })
            await ws.send(setup_msg)

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
                return b"".join(audio_chunks)
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
