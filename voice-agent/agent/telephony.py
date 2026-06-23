"""Twilio Media Streams telephony transport for the bridge.

Handles the Twilio Media Streams WebSocket JSON protocol (8 kHz mu-law). Unlike
the browser path there is no client-side VAD, so end-of-turn is detected
server-side via TurnDetector. Once the caller stops speaking, the same
STT -> RAG -> TTS pipeline runs and mu-law audio is streamed back to the caller.

The frame parser and message builders are pure functions (unit-tested); the
session handler does the async I/O.
"""

import asyncio
import base64
import json
from dataclasses import dataclass

from agent.audio_codec import mulaw_to_pcm16
from agent.gradium_tts import synthesize_speech
from agent.sentence_splitter import find_sentence_boundary
from agent.stt_streaming import create_stt_session
from agent.turn_detector import TurnDetector, TurnDetectorConfig

TELEPHONY_INPUT_FORMAT = "ulaw_8000"
TELEPHONY_OUTPUT_FORMAT = "ulaw_8000"
TELEPHONY_SAMPLE_RATE = 8000


@dataclass
class MediaStreamEvent:
    kind: str  # connected | start | media | stop | mark | unknown
    stream_sid: str | None = None
    mulaw: bytes | None = None


def parse_twilio_message(raw: str) -> MediaStreamEvent:
    """Parse one inbound Twilio Media Streams JSON text frame."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return MediaStreamEvent("unknown")

    event = data.get("event", "unknown")

    if event == "start":
        start = data.get("start", {})
        return MediaStreamEvent("start", stream_sid=start.get("streamSid") or data.get("streamSid"))

    if event == "media":
        payload = data.get("media", {}).get("payload", "")
        mulaw = base64.b64decode(payload) if payload else b""
        return MediaStreamEvent("media", mulaw=mulaw)

    if event in ("connected", "stop", "mark"):
        return MediaStreamEvent(event)

    return MediaStreamEvent("unknown")


def build_media_message(stream_sid: str, mulaw_audio: bytes) -> str:
    """Build an outbound Twilio media frame carrying mu-law audio."""
    return json.dumps({
        "event": "media",
        "streamSid": stream_sid,
        "media": {"payload": base64.b64encode(mulaw_audio).decode("ascii")},
    })


def build_clear_message(stream_sid: str) -> str:
    """Build a Twilio `clear` frame to flush buffered audio (barge-in)."""
    return json.dumps({"event": "clear", "streamSid": stream_sid})


def telephony_turn_detector() -> TurnDetector:
    """TurnDetector tuned for 8 kHz telephony audio."""
    return TurnDetector(TurnDetectorConfig(
        sample_rate=TELEPHONY_SAMPLE_RATE,
        silence_ms=600,
        min_speech_ms=200,
    ))


async def handle_twilio_client(websocket, backend, api_key, voice_id, language="fr"):
    """Handle one Twilio Media Streams call session."""
    detector = telephony_turn_detector()
    utterance = bytearray()
    stream_sid: str | None = None
    response_task: asyncio.Task | None = None

    async def cancel_response():
        nonlocal response_task
        if response_task and not response_task.done():
            response_task.cancel()
            try:
                await response_task
            except asyncio.CancelledError:
                pass
        response_task = None

    try:
        async for raw in websocket:
            event = parse_twilio_message(raw)

            if event.kind == "start":
                stream_sid = event.stream_sid
                print(f"[TWILIO] Stream started: {stream_sid}", flush=True)

            elif event.kind == "media" and event.mulaw:
                utterance.extend(event.mulaw)
                if detector.process(mulaw_to_pcm16(event.mulaw)):
                    audio = bytes(utterance)
                    utterance = bytearray()
                    detector.reset()
                    await cancel_response()
                    response_task = asyncio.create_task(
                        _answer_call(websocket, backend, api_key, voice_id,
                                     language, stream_sid, audio)
                    )

            elif event.kind == "stop":
                print(f"[TWILIO] Stream stopped: {stream_sid}", flush=True)
                break
    finally:
        await cancel_response()


async def _answer_call(websocket, backend, api_key, voice_id, language, stream_sid, mulaw_audio):
    """STT (mu-law) -> RAG (SSE) -> TTS (mu-law) -> Twilio media frames."""
    stt_session = create_stt_session(language, api_key, TELEPHONY_INPUT_FORMAT)
    stt_session.feed(mulaw_audio)
    stt_result = await stt_session.finalize()

    if stt_result.error_code or not stt_result.text:
        return

    print(f"[TWILIO] Caller said: '{stt_result.text}'", flush=True)
    sentence_buffer = ""

    async for sse in backend.ask_stream(stt_result.text, f"twilio-{stream_sid}"):
        if sse.get("event") != "chunk":
            continue
        sentence_buffer += sse["data"].get("text", "")
        sentence, remainder = find_sentence_boundary(sentence_buffer)
        if sentence:
            sentence_buffer = remainder
            await _speak(websocket, api_key, voice_id, stream_sid, sentence)

    if sentence_buffer.strip():
        await _speak(websocket, api_key, voice_id, stream_sid, sentence_buffer.strip())


async def _speak(websocket, api_key, voice_id, stream_sid, text):
    audio = await synthesize_speech(text, voice_id, api_key, TELEPHONY_OUTPUT_FORMAT)
    if audio and stream_sid:
        await websocket.send(build_media_message(stream_sid, audio))
