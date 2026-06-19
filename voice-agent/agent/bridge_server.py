"""Bridge WebSocket server — translates the frontend's custom protocol to Gradium + RAG.

Frontend protocol:
  - Client sends: binary audio chunks (PCM 16kHz 16-bit mono)
  - Client sends: text "END_OF_SPEECH" when done speaking
  - Client sends: JSON {"type":"set_language","language":"fr|en"}
  - Server sends: JSON {"type":"transcription","text":"..."} after STT
  - Server sends: JSON {"type":"answer","text":"..."} after RAG
  - Server sends: binary audio (WAV 16kHz) for TTS playback
"""

import asyncio
import json
import os
import sys

import websockets
from dotenv import load_dotenv

from agent.backend_client import RAGBackendClient
from agent.gradium_stt import transcribe_audio
from agent.gradium_tts import synthesize_speech

load_dotenv()

GRADIUM_API_KEY = os.getenv("GRADIUM_API_KEY")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8081")
WS_HOST = os.getenv("VOICE_AGENT_HOST", "0.0.0.0")
WS_PORT = int(os.getenv("VOICE_AGENT_PORT", "8765"))

VOICE_MAP = {
    "fr": os.getenv("GRADIUM_VOICE_FR", "b35yykvVppLXyw_l"),
    "en": os.getenv("GRADIUM_VOICE_EN", "YTpq7expH9539ERJ"),
}
DEFAULT_LANGUAGE = "fr"


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
                    await _handle_end_of_speech(websocket, backend, audio_buffer, language)
                    audio_buffer.clear()
                else:
                    await _handle_json_message(websocket, message, language)
                    language = _extract_language(message, language)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        await backend.close()
        print("[CLIENT] Disconnected", flush=True)


async def _handle_end_of_speech(websocket, backend, audio_buffer, language):
    """Process buffered audio: STT → RAG → TTS → send responses."""
    if not audio_buffer:
        await websocket.send(json.dumps({"type": "answer", "text": ""}))
        return

    audio_data = bytes(audio_buffer)
    print(f"[STT] Transcribing {len(audio_data)} bytes (lang={language})...", flush=True)

    transcription = await transcribe_audio(audio_data, language, GRADIUM_API_KEY)

    if not transcription:
        print("[STT] No transcription returned (silence?)", flush=True)
        await websocket.send(json.dumps({"type": "answer", "text": ""}))
        return

    print(f"[STT] Result: '{transcription}'", flush=True)
    await websocket.send(json.dumps({"type": "transcription", "text": transcription}))

    answer, audio_response = await _process_question(backend, transcription, language)
    await websocket.send(json.dumps({"type": "answer", "text": answer}))

    if audio_response:
        await websocket.send(audio_response)


async def _handle_json_message(websocket, message, language):
    """Handle JSON control messages (e.g. set_language)."""
    try:
        data = json.loads(message)
        if data.get("type") == "set_language":
            new_lang = data.get("language", DEFAULT_LANGUAGE)
            if new_lang in VOICE_MAP:
                print(f"[CLIENT] Language set to '{new_lang}'", flush=True)
                await websocket.send(json.dumps({
                    "type": "language_changed",
                    "language": new_lang,
                }))
    except (json.JSONDecodeError, KeyError):
        pass


def _extract_language(message: str, current: str) -> str:
    """Extract language from a set_language message, or return current."""
    try:
        data = json.loads(message)
        if data.get("type") == "set_language":
            new_lang = data.get("language", current)
            return new_lang if new_lang in VOICE_MAP else current
    except (json.JSONDecodeError, KeyError):
        pass
    return current


async def _process_question(backend, question, language):
    """Send question to RAG backend and synthesize answer via TTS."""
    try:
        lang_hint = " (Please answer in English.)" if language == "en" else ""
        result = await backend.ask(question + lang_hint)
        answer = result.get("answer", "Désolé, je n'ai pas compris.")
    except Exception as e:
        print(f"[RAG] Error: {e}", flush=True)
        answer = "Sorry, an error occurred." if language == "en" else "Désolé, une erreur est survenue."

    voice_id = VOICE_MAP.get(language, VOICE_MAP[DEFAULT_LANGUAGE])
    audio = await synthesize_speech(answer, voice_id, GRADIUM_API_KEY)
    return answer, audio


async def main():
    if not GRADIUM_API_KEY:
        print("ERROR: GRADIUM_API_KEY not set.", flush=True)
        sys.exit(1)

    print(f"Voice agent bridge listening on ws://{WS_HOST}:{WS_PORT}", flush=True)
    print(f"  STT/TTS: Gradium (direct WebSocket API)", flush=True)
    print(f"  Backend: {BACKEND_URL}", flush=True)

    async with websockets.serve(handle_client, WS_HOST, WS_PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
