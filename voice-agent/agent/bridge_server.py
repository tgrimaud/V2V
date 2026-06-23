"""Bridge WebSocket server — translates the frontend's custom protocol to Gradium + RAG.

Frontend protocol:
  - Client sends: binary audio chunks (PCM 16kHz 16-bit mono)
  - Client sends: text "END_OF_SPEECH" when done speaking
  - Client sends: text "BARGE_IN" to interrupt current response
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
import time

import httpx
import websockets
from dotenv import load_dotenv

from agent.backend_client import RAGBackendClient
from agent.gradium_tts import synthesize_speech
from agent.sentence_splitter import find_sentence_boundary
from agent.stt_streaming import create_stt_session
from agent.telephony import handle_twilio_client

load_dotenv()

GRADIUM_API_KEY = os.getenv("GRADIUM_API_KEY")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8081")
WS_HOST = os.getenv("VOICE_AGENT_HOST", "0.0.0.0")
WS_PORT = int(os.getenv("VOICE_AGENT_PORT", "8765"))
TELEPHONY_WS_PORT = int(os.getenv("TWILIO_WS_PORT", "8766"))

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
    response_task: asyncio.Task | None = None

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                audio_buffer.extend(message)
            elif isinstance(message, str):
                if message == "END_OF_SPEECH":
                    if response_task and not response_task.done():
                        response_task.cancel()
                        try:
                            await response_task
                        except asyncio.CancelledError:
                            pass
                    response_task = asyncio.create_task(
                        _handle_end_of_speech(websocket, backend, audio_buffer, language)
                    )
                    audio_buffer = bytearray()
                elif message == "BARGE_IN":
                    if response_task and not response_task.done():
                        print("[BARGE-IN] Cancelling current response", flush=True)
                        response_task.cancel()
                        try:
                            await response_task
                        except asyncio.CancelledError:
                            pass
                        response_task = None
                        await websocket.send(json.dumps({
                            "type": "answer_done", "text": "[interrompu]"
                        }))
                else:
                    await _handle_json_message(websocket, message, language)
                    language = _extract_language(message, language)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if response_task and not response_task.done():
            response_task.cancel()
            try:
                await response_task
            except asyncio.CancelledError:
                pass
        await backend.close()
        print("[CLIENT] Disconnected", flush=True)


async def _handle_end_of_speech(websocket, backend, audio_buffer, language):
    """Process buffered audio: STT → streaming RAG → streaming TTS."""
    if not audio_buffer:
        await websocket.send(json.dumps({"type": "answer_done", "text": ""}))
        return

    turn_start = time.perf_counter()
    audio_data = bytes(audio_buffer)
    print(f"[STT] Transcribing {len(audio_data)} bytes (lang={language})...", flush=True)

    stt_session = create_stt_session(language, GRADIUM_API_KEY)
    stt_session.feed(audio_data)
    stt_result = await stt_session.finalize()

    if stt_result.error_code:
        print(f"[STT] Error: {stt_result.error} ({stt_result.error_code})", flush=True)
        await websocket.send(json.dumps({
            "type": "service_error",
            "code": stt_result.error_code,
            "message": stt_result.error,
        }))
        await websocket.send(json.dumps({"type": "answer_done", "text": ""}))
        return

    transcription = stt_result.text
    if not transcription:
        print("[STT] No transcription returned (silence?)", flush=True)
        await websocket.send(json.dumps({"type": "answer_done", "text": ""}))
        return

    print(f"[STT] Result: '{transcription}'", flush=True)
    await websocket.send(json.dumps({"type": "transcription", "text": transcription}))

    lang_hint = " (Please answer in English.)" if language == "en" else ""
    question = transcription + lang_hint

    try:
        await _stream_answer(websocket, backend, question, language, turn_start)
    except asyncio.CancelledError:
        print("[STREAM] Cancelled (barge-in)", flush=True)
        raise
    except Exception as e:
        print(f"[STREAM] SSE failed ({e}), falling back to POST", flush=True)
        await _fallback_non_streaming(websocket, backend, question, language)


async def _stream_answer(websocket, backend, question, language, turn_start=None):
    """Consume SSE from backend, split into sentences, TTS each concurrently."""
    voice_id = VOICE_MAP.get(language, VOICE_MAP[DEFAULT_LANGUAGE])
    sentence_buffer = ""
    full_answer = ""
    tts_queue = asyncio.Queue()
    first_audio_sent = False

    async def tts_worker():
        """Process TTS requests from queue and send audio to client."""
        nonlocal first_audio_sent
        while True:
            sentence = await tts_queue.get()
            if sentence is None:
                break
            audio = await synthesize_speech(sentence, voice_id, GRADIUM_API_KEY)
            if audio:
                await websocket.send(audio)
                if not first_audio_sent and turn_start is not None:
                    first_audio_sent = True
                    ttfa_ms = (time.perf_counter() - turn_start) * 1000
                    print(f"[LATENCY] step=time_to_first_audio ms={ttfa_ms:.0f}", flush=True)
            tts_queue.task_done()

    worker_task = asyncio.create_task(tts_worker())

    try:
        agent_id = None
        agent_name = None
        guardrail_blocked = False

        async for event in backend.ask_stream(question, "pipecat"):
            event_type = event.get("event", "")

            if event_type == "start":
                agent_id = event["data"].get("agentId")
                agent_name = event["data"].get("agentName")
                guardrail_blocked = event["data"].get("guardrailBlocked", False)
                await websocket.send(json.dumps({
                    "type": "answer_start",
                    "agentId": agent_id,
                    "agentName": agent_name,
                    "guardrailBlocked": guardrail_blocked,
                }))

            elif event_type == "chunk":
                token = event["data"].get("text", "")
                sentence_buffer += token
                full_answer += token

                sentence, remainder = find_sentence_boundary(sentence_buffer)
                if sentence:
                    sentence_buffer = remainder
                    await websocket.send(json.dumps({"type": "answer_chunk", "text": sentence}))
                    await tts_queue.put(sentence)

            elif event_type == "error":
                error_msg = event["data"].get("message", "Unknown error")
                print(f"[STREAM] Backend error: {error_msg}", flush=True)
                if not full_answer:
                    full_answer = "Désolé, une erreur est survenue."
                    await websocket.send(json.dumps({"type": "answer_chunk", "text": full_answer}))
                break

            elif event_type == "done":
                agent_id = event["data"].get("agentId")
                agent_name = event["data"].get("agentName")
                break

        if sentence_buffer.strip():
            remaining = sentence_buffer.strip()
            await websocket.send(json.dumps({"type": "answer_chunk", "text": remaining}))
            await tts_queue.put(remaining)

        await tts_queue.put(None)
        await worker_task

        done_msg = {"type": "answer_done", "text": full_answer}
        if agent_id:
            done_msg["agentId"] = agent_id
        if agent_name:
            done_msg["agentName"] = agent_name
        await websocket.send(json.dumps(done_msg))
        if turn_start is not None:
            total_ms = (time.perf_counter() - turn_start) * 1000
            print(f"[LATENCY] step=turn_total ms={total_ms:.0f} chars={len(full_answer)}", flush=True)
        print(f"[STREAM] Complete: {len(full_answer)} chars (agent={agent_name})", flush=True)

    except asyncio.CancelledError:
        await tts_queue.put(None)
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        raise


async def _fallback_non_streaming(websocket, backend, question, language):
    """Fallback to non-streaming POST /ask if SSE fails."""
    try:
        result = await backend.ask(question)
        answer = result.get("answer", "Désolé, je n'ai pas compris.")
    except httpx.ConnectError:
        await websocket.send(json.dumps({
            "type": "service_error",
            "code": "BACKEND_UNAVAILABLE",
            "message": "Backend service unavailable",
        }))
        answer = "Sorry, an error occurred." if language == "en" else "Désolé, une erreur est survenue."
    except Exception as e:
        error_str = str(e)
        print(f"[RAG] Fallback error: {e}", flush=True)
        if "401" in error_str or "Unauthorized" in error_str:
            await websocket.send(json.dumps({
                "type": "service_error",
                "code": "LLM_AUTH_ERROR",
                "message": "Mistral API key invalid or missing",
            }))
        else:
            await websocket.send(json.dumps({
                "type": "service_error",
                "code": "BACKEND_ERROR",
                "message": f"Backend error: {error_str[:100]}",
            }))
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


async def handle_telephony_client(websocket):
    """Handle one telephony (Twilio Media Streams) call session."""
    backend = RAGBackendClient(base_url=BACKEND_URL)
    voice_id = VOICE_MAP[DEFAULT_LANGUAGE]
    print(f"[TELEPHONY] Call connected from {websocket.remote_address}", flush=True)
    try:
        await handle_twilio_client(websocket, backend, GRADIUM_API_KEY, voice_id, DEFAULT_LANGUAGE)
    finally:
        await backend.close()
        print("[TELEPHONY] Call disconnected", flush=True)


async def main():
    if not GRADIUM_API_KEY:
        print("ERROR: GRADIUM_API_KEY not set.", flush=True)
        sys.exit(1)

    print(f"Voice agent bridge listening on ws://{WS_HOST}:{WS_PORT} (browser)", flush=True)
    print(f"Telephony listening on ws://{WS_HOST}:{TELEPHONY_WS_PORT} (Twilio Media Streams, ulaw_8000)", flush=True)
    print(f"  STT/TTS: Gradium (direct WebSocket API)", flush=True)
    print(f"  Backend: {BACKEND_URL} (SSE streaming)", flush=True)

    async with websockets.serve(handle_client, WS_HOST, WS_PORT), \
            websockets.serve(handle_telephony_client, WS_HOST, TELEPHONY_WS_PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
