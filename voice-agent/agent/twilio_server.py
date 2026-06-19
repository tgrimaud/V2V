"""Twilio Media Streams transport — handles phone calls via Pipecat + Gradium.

Twilio sends 8kHz μ-law audio over WebSocket; Gradium supports ulaw_8000 natively.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.gradium.stt import GradiumSTTService
from pipecat.services.gradium.tts import GradiumTTSService
from pipecat.transports.network.websocket_server import (
    WebSocketServerParams,
    WebSocketServerTransport,
)

from agent.backend_client import RAGBackendClient
from agent.rag_processor import RAGProcessor

load_dotenv()

WELCOME_MESSAGE = (
    "Bonjour, bienvenue au support technique. "
    "Comment puis-je vous aider ?"
)


async def run_twilio_agent():
    """Run a voice agent for Twilio Media Streams (telephony)."""

    gradium_api_key = os.getenv("GRADIUM_API_KEY")
    gradium_voice_id = os.getenv("GRADIUM_VOICE_ID", "default")
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8081")
    twilio_ws_port = int(os.getenv("TWILIO_WS_PORT", "8766"))

    if not gradium_api_key:
        print("ERROR: GRADIUM_API_KEY not set.")
        sys.exit(1)

    backend = RAGBackendClient(base_url=backend_url)

    transport = WebSocketServerTransport(
        params=WebSocketServerParams(
            host="0.0.0.0",
            port=twilio_ws_port,
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
        )
    )

    stt = GradiumSTTService(
        api_key=gradium_api_key,
        encoding="ulaw",
        sample_rate=8000,
    )

    tts = GradiumTTSService(
        api_key=gradium_api_key,
        voice_id=gradium_voice_id,
    )

    rag_processor = RAGProcessor(backend)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            rag_processor,
            tts,
            transport.output(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        await task.queue_frames([TextFrame(text=WELCOME_MESSAGE)])

    runner = PipelineRunner()
    print(f"Twilio voice agent listening on ws://0.0.0.0:{twilio_ws_port}")
    print(f"  STT/TTS: Gradium (ulaw_8000) | Backend: {backend_url}")
    await runner.run(task)
    await backend.close()


def main():
    asyncio.run(run_twilio_agent())


if __name__ == "__main__":
    main()
