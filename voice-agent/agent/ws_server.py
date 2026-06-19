"""WebSocket transport for browser-based voice chat.

Runs a local WebSocket server that the React frontend connects to.
Audio flows in PCM 16kHz from the browser microphone, and generated audio flows back.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from pipecat.frames.frames import TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.gradium.stt import GradiumSTTService
from pipecat.services.gradium.tts import GradiumTTSService
from pipecat.transports.websocket.server import (
    WebsocketServerParams,
    WebsocketServerTransport,
)

from agent.backend_client import RAGBackendClient
from agent.rag_processor import RAGProcessor

load_dotenv()

WELCOME_MESSAGE = (
    "Bonjour ! Je suis votre assistant virtuel du support télécom. "
    "Comment puis-je vous aider aujourd'hui ?"
)


async def run_websocket_agent():
    """Run a voice agent accessible via WebSocket from the browser frontend."""

    gradium_api_key = os.getenv("GRADIUM_API_KEY")
    gradium_voice_id = os.getenv("GRADIUM_VOICE_ID", "default")
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8081")
    ws_host = os.getenv("VOICE_AGENT_HOST", "0.0.0.0")
    ws_port = int(os.getenv("VOICE_AGENT_PORT", "8765"))

    if not gradium_api_key:
        print("ERROR: GRADIUM_API_KEY not set.")
        sys.exit(1)

    backend = RAGBackendClient(base_url=backend_url)

    transport = WebsocketServerTransport(
        params=WebsocketServerParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=16000,
        ),
        host=ws_host,
        port=ws_port,
    )

    stt = GradiumSTTService(
        api_key=gradium_api_key,
        encoding="pcm",
        sample_rate=16000,
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
            audio_in_sample_rate=16000,
            audio_out_sample_rate=16000,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        await task.queue_frames([TextFrame(text=WELCOME_MESSAGE)])

    runner = PipelineRunner()
    print(f"WebSocket voice agent listening on ws://{ws_host}:{ws_port}")
    print(f"  STT/TTS: Gradium | Backend: {backend_url}")
    await runner.run(task)
    await backend.close()


def main():
    asyncio.run(run_websocket_agent())


if __name__ == "__main__":
    main()
