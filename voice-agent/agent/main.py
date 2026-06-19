"""Main Pipecat voice agent using Gradium for STT/TTS and Java backend for RAG."""

import asyncio
import os
import sys

from dotenv import load_dotenv
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.gradium.stt import GradiumSTTService
from pipecat.services.gradium.tts import GradiumTTSService
from pipecat.transports.services.daily import DailyParams, DailyTransport

from agent.backend_client import RAGBackendClient
from agent.rag_processor import RAGProcessor

load_dotenv()


async def run_agent():
    """Start the Pipecat voice agent with Gradium STT/TTS and RAG backend."""

    gradium_api_key = os.getenv("GRADIUM_API_KEY")
    gradium_voice_id = os.getenv("GRADIUM_VOICE_ID", "default")
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8081")

    if not gradium_api_key:
        print("ERROR: GRADIUM_API_KEY not set. Copy .env.example to .env and configure it.")
        sys.exit(1)

    backend = RAGBackendClient(base_url=backend_url)
    if not await backend.health():
        print(f"WARNING: Java backend not reachable at {backend_url}")

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
            stt,
            rag_processor,
            tts,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=16000,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    runner = PipelineRunner()

    print(f"Voice agent started — Gradium STT/TTS, backend: {backend_url}")
    print("Waiting for audio input...")

    await runner.run(task)
    await backend.close()


def main():
    asyncio.run(run_agent())


if __name__ == "__main__":
    main()
