"""Unified Pipecat voice bot (strategy B).

One bot definition, multiple transports — the Pipecat way of unifying channels:

  - Web:        WebRTC (SmallWebRTC) with the runner's prebuilt UI on :7860
  - Telephony:  Twilio Media Streams (TwilioFrameSerializer), 8 kHz mu-law

Both channels share the SAME pipeline:
  transport.input() -> Gradium STT (streaming) -> StreamingRAGProcessor -> Gradium TTS -> transport.output()

Server-side Silero VAD handles endpointing AND interruptions (barge-in) for free.
This is the alternative to the custom bridge (strategy A); it does not touch it
and runs on its own port (7860), so both can coexist.

Run:
  python -m agent.bot              # all transports; open http://localhost:7860 (WebRTC)
  python -m agent.bot -t webrtc    # WebRTC only
  python -m agent.bot -t twilio -x <public-host>   # telephony (needs a public proxy)
"""

import os
import uuid

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.gradium.stt import GradiumSTTService
from pipecat.services.gradium.tts import GradiumTTSService
from pipecat.transports.base_transport import TransportParams

from agent.backend_client import RAGBackendClient
from agent.streaming_rag_processor import StreamingRAGProcessor

load_dotenv()

GRADIUM_API_KEY = os.getenv("GRADIUM_API_KEY")
GRADIUM_VOICE_ID = os.getenv("GRADIUM_VOICE_ID", "default")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8081")

WELCOME_MESSAGE = (
    "Bonjour ! Je suis votre assistant virtuel du support télécom. "
    "Comment puis-je vous aider aujourd'hui ?"
)


def _transport_params() -> dict:
    """Audio I/O params for each supported transport.

    In Pipecat 1.4.0 VAD is no longer a TransportParams field; it is a
    dedicated ``VADProcessor`` placed in the pipeline (see ``bot()``). The
    transport only enables the audio in/out streams here.

    Telephony audio (8 kHz mu-law) is decoded by the Twilio serializer that
    `create_transport` wires up automatically, so the pipeline always sees PCM.
    """
    return {
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
        "twilio": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }


async def bot(runner_args: RunnerArguments):
    """Entry point discovered and invoked by the Pipecat development runner."""
    if not GRADIUM_API_KEY:
        logger.error("GRADIUM_API_KEY not set. Configure voice-agent/.env first.")
        return

    transport = await create_transport(runner_args, _transport_params())

    backend = RAGBackendClient(base_url=BACKEND_URL)
    conversation_id = f"pipecat-{uuid.uuid4().hex[:8]}"

    # stop_secs (silence before end-of-turn) is bumped from the 0.8s default to
    # 1.0s so brief mid-sentence pauses don't split one utterance into several
    # transcriptions. The StreamingRAGProcessor debounce coalesces the rest.
    vad = VADProcessor(
        vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=1.0))
    )
    stt = GradiumSTTService(api_key=GRADIUM_API_KEY, encoding="pcm")
    tts = GradiumTTSService(api_key=GRADIUM_API_KEY, voice_id=GRADIUM_VOICE_ID)
    rag = StreamingRAGProcessor(backend, conversation_id)

    pipeline = Pipeline([
        transport.input(),
        vad,
        stt,
        rag,
        tts,
        transport.output(),
    ])

    task = PipelineTask(
        pipeline,
        conversation_id=conversation_id,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        logger.info(f"Client connected (conversation {conversation_id})")
        # Send the welcome through the same LLM-response boundaries as RAG
        # answers so the RTVI observer emits botLlmStarted/botLlmText/
        # botLlmStopped uniformly. The WebRTC client (strategy B) then renders
        # every assistant turn as its own chat bubble.
        await task.queue_frames(
            [
                LLMFullResponseStartFrame(),
                LLMTextFrame(text=WELCOME_MESSAGE),
                LLMFullResponseEndFrame(),
            ]
        )

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    try:
        await runner.run(task)
    finally:
        await backend.close()


def main():
    from pipecat.runner.run import main as runner_main

    runner_main()


if __name__ == "__main__":
    main()
