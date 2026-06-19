"""Bridge WebSocket server — translates the frontend's custom protocol to Gradium + RAG.

Frontend protocol:
  - Client sends: binary audio chunks (PCM 16kHz 16-bit mono)
  - Client sends: text "END_OF_SPEECH" when done speaking
  - Client sends: JSON {"type":"set_language","language":"fr|en"}
  - Server sends: JSON {"type":"transcription","text":"..."} after STT
  - Server sends: JSON {"type":"answer_chunk","text":"..."} per sentence (streaming)
  - Server sends: binary audio (WAV 16kHz) per sentence (streaming)
  - Server sends: JSON {"type":"answer_done","text":"..."} when generation complete
  - Server sends: JSON {"type":"answer","text":"..."} fallback (non-streaming)
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
from agent.sentence_splitter import find_sentence_boundary

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
    """Process buffered audio: STT → streaming RAG → streaming TTS."""
    if not audio_buffer:
        await websocket.send(json.dumps({"type": "answer_done", "text": ""}))
        return

    audio_data = bytes(audio_buffer)
    print(f"[STT] Transcribing {len(audio_data)} bytes (lang={language})...", flush=True)

    transcription = await transcribe_audio(audio_data, language, GRADIUM_API_KEY)

    if not transcription:
        print("[STT] No transcription returned (silence?)", flush=True)
        await websocket.send(json.dumps({"type": "answer_done", "text": ""}))
        return

    print(f"[STT] Result: '{transcription}'", flush=True)
    await websocket.send(json.dumps({"type": "transcription", "text": transcription}))

    lang_hint = " (Please answer in English.)" if language == "en" else ""
    question = transcription + lang_hint

    try:
        await _stream_answer(websocket, backend, question, language)
    except Exception as e:
        print(f"[STREAM] SSE failed ({e}), falling back to POST", flush=True)
        await _fallback_non_streaming(websocket, backend, question, language)


async def _stream_answer(websocket, backend, question, language):
    """Consume SSE from backend, split into sentences, TTS each concurrently."""
    voice_id = VOICE_MAP.get(language, VOICE_MAP[DEFAULT_LANGUAGE])
    sentence_buffer = ""
    full_answer = ""
    tts_queue = asyncio.Queue()

    async def tts_worker():
        """Process TTS requests from queue and send audio to client."""
        while True:
            sentence = await tts_queue.get()
            if sentence is None:
                break
            audio = await synthesize_speech(sentence, voice_id, GRADIUM_API_KEY)
            if audio:
                await websocket.send(audio)
            tts_queue.task_done()

    worker_task = asyncio.create_task(tts_worker())

    async for event in backend.ask_stream(question, "pipecat"):
        event_type = event.get("event", "")

        if event_type == "chunk":
            token = event["data"].get("text", "")
            sentence_buffer += token
            full_answer += token

            sentence, remainder = find_sentence_boundary(sentence_buffer)
            if sentence:
                sentence_buffer = remainder
                await websocket.send(json.dumps({"type": "answer_chunk", "text": sentence}))
                await tts_queue.put(sentence)

        elif event_type == "done":
            break

    # Flush any remaining text in buffer
    if sentence_buffer.strip():
        remaining = sentence_buffer.strip()
        await websocket.send(json.dumps({"type": "answer_chunk", "text": remaining}))
        await tts_queue.put(remaining)

    # Signal TTS worker to stop and wait for completion
    await tts_queue.put(None)
    await worker_task

    await websocket.send(json.dumps({"type": "answer_done", "text": full_answer}))
    print(f"[STREAM] Complete: {len(full_answer)} chars", flush=True)


async def _fallback_non_streaming(websocket, backend, question, language):
    """Fallback to non-streaming POST /ask if SSE fails."""
    try:
        result = await backend.ask(question)
        answer = result.get("answer", "Désolé, je n'ai pas compris.")
    except Exception as e:
        print(f"[RAG] Fallback error: {e}", flush=True)
        answer = "Sorry, an error occurred." if language == "en" else "Désolé, une erreur est survenue."

    voice_id = VOICE_MAP.get(language, VOICE_MAP[DEFAULT_LANGUAGE])
    await websocket.send(json.dumps({"type": "answer_chunk", "text": answer}))

    audio = await synthesize_speech(answer, voice_id, GRADIUM_API_KEY)
    if audio:
        await websocket.send(audio)

    await websocket.send(json.dumps({"type": "answer_done", "text": answer}))


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


async def main():
    if not GRADIUM_API_KEY:
        print("ERROR: GRADIUM_API_KEY not set.", flush=True)
        sys.exit(1)

    print(f"Voice agent bridge listening on ws://{WS_HOST}:{WS_PORT}", flush=True)
    print(f"  STT/TTS: Gradium (direct WebSocket API)", flush=True)
    print(f"  Backend: {BACKEND_URL} (SSE streaming)", flush=True)

    async with websockets.serve(handle_client, WS_HOST, WS_PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
