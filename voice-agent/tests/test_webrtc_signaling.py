"""Tests for the WebRTC signaling service (Sprint 6 / TASK-WEB-007).

Uses a real in-process `aiortc` peer as the "browser" and negotiates against the
`WebRtcSignalingService` running on its background loop — no external network, no
FastAPI. Proves the offer→answer handshake returns a valid SDP answer with a
correlation id and that the media plane actually reaches `connected`.

Requires the WebRTC extra; skipped cleanly when it is absent so the base suite stays
green without aiortc.
"""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from conversation_backend import AnswerOutcome, AnswerRequest, AnswerResult  # noqa: E402
from stt_validation.models import SttOutcome, TranscriptResult  # noqa: E402
from tts_synthesis.models import SynthesisResult, TtsOutcome  # noqa: E402
from web_voice.webrtc_support import probe_webrtc_support  # noqa: E402

WEBRTC = probe_webrtc_support().available


class _FakeIngress:
    def transcribe_turn(self, audio, envelope, telemetry=None, *, received_ms=None):
        return TranscriptResult(
            transcript="bonjour", provider="fake-stt", outcome=SttOutcome.SUCCESS,
            duration_ms=1.0, stt_request_ms=1.0, correlation_id="c",
        )


class _FakeEgress:
    def synthesize_turn(self, text, envelope, telemetry=None):
        result = SynthesisResult(
            audio=b"\x00\x00" * 160, provider="fake-tts", outcome=TtsOutcome.SUCCESS,
            duration_ms=1.0, tts_request_ms=1.0, correlation_id="c", audio_format="pcm_16000",
        )
        return SimpleNamespace(result=result, wav=b"WAV")

    def record_egress(self, response, envelope, telemetry, *, sent_ms=None):
        return None


class _FakeBackend:
    name = "fake-backend"

    def answer(self, request: AnswerRequest) -> AnswerResult:
        return AnswerResult(text="oui", provider=self.name, outcome=AnswerOutcome.SUCCESS,
                            correlation_id=request.correlation_id)


async def _wait_ice(peer) -> None:
    if peer.iceGatheringState == "complete":
        return
    done = asyncio.Event()
    peer.on("icegatheringstatechange", lambda: done.set() if peer.iceGatheringState == "complete" else None)
    await asyncio.wait_for(done.wait(), timeout=10)


@unittest.skipUnless(WEBRTC, "pipecat-ai[webrtc] not installed")
class WebRtcSignalingTest(unittest.IsolatedAsyncioTestCase):
    async def test_offer_returns_answer_and_media_connects(self) -> None:
        from aiortc import RTCPeerConnection, RTCSessionDescription
        from aiortc.mediastreams import AudioStreamTrack

        from web_voice.async_loop import BackgroundEventLoop
        from web_voice.webrtc_signaling import WebRtcSignalingService

        loop = BackgroundEventLoop()
        loop.start()
        service = WebRtcSignalingService(
            ingress=_FakeIngress(), egress=_FakeEgress(), backend=_FakeBackend(),
            loop=loop, log=lambda _t: None,
        )
        browser = RTCPeerConnection()
        try:
            # GIVEN a browser peer offering one audio track
            browser.addTrack(AudioStreamTrack())
            await browser.setLocalDescription(await browser.createOffer())
            await _wait_ice(browser)
            offer = {"sdp": browser.localDescription.sdp, "type": browser.localDescription.type}
            # WHEN the signaling service handles the offer (blocking, off the test loop)
            answer = await asyncio.to_thread(service.handle_offer, offer)
            # THEN a valid SDP answer with a correlation id comes back
            self.assertEqual(answer["type"], "answer")
            self.assertIn("m=audio", answer["sdp"])
            self.assertTrue(answer["correlation_id"])
            # AND the media plane actually establishes
            await browser.setRemoteDescription(
                RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
            )
            await self._wait_connected(browser)
            self.assertEqual(browser.connectionState, "connected")
        finally:
            await browser.close()
            await asyncio.to_thread(service.close)
            loop.stop()

    async def _wait_connected(self, peer) -> None:
        deadline = asyncio.get_event_loop().time() + 15
        while peer.connectionState != "connected":
            if asyncio.get_event_loop().time() > deadline:
                self.fail(f"WebRTC did not connect (state={peer.connectionState})")
            await asyncio.sleep(0.1)


if __name__ == "__main__":
    unittest.main()
