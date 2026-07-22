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
    provider_name = "fake-stt"

    def transcribe_turn(self, audio, envelope, telemetry=None, *, received_ms=None, detect_end_of_turn=True):
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


@unittest.skipUnless(WEBRTC, "pipecat-ai[webrtc] not installed")
class WebRtcSignalingCleanupTest(unittest.IsolatedAsyncioTestCase):
    async def test_call_end_drains_session_before_discarding(self) -> None:
        # GIVEN a signaling service holding one live session record
        from web_voice.webrtc_signaling import WebRtcSignalingService, _Session

        drained = asyncio.Event()
        logged: list = []

        class _FakeSession:
            async def drain(self) -> None:
                drained.set()

        service = WebRtcSignalingService(
            ingress=_FakeIngress(), egress=_FakeEgress(), backend=_FakeBackend(),
            loop=SimpleNamespace(), log=logged.append,
        )
        record = _Session(
            connection=SimpleNamespace(pc_id="pc-1"),
            session=_FakeSession(),
            envelope=SimpleNamespace(correlation_id="c"),
            telemetry=SimpleNamespace(),
            task=None,
        )
        service._sessions["pc-1"] = record
        # WHEN the call ends (closed/disconnected path)
        await service._drain_and_discard("pc-1")
        # THEN the session was drained (trailing partial flushed) then discarded + logged
        self.assertTrue(drained.is_set())
        self.assertNotIn("pc-1", service._sessions)
        self.assertEqual(logged, [record.telemetry])

    async def test_drain_failure_still_discards_the_session(self) -> None:
        # GIVEN a session whose drain() raises (e.g. abrupt drop mid-flush)
        from web_voice.webrtc_signaling import WebRtcSignalingService, _Session

        class _ExplodingSession:
            async def drain(self) -> None:
                raise RuntimeError("socket already gone")

        service = WebRtcSignalingService(
            ingress=_FakeIngress(), egress=_FakeEgress(), backend=_FakeBackend(),
            loop=SimpleNamespace(), log=lambda _t: None,
        )
        record = _Session(
            connection=SimpleNamespace(pc_id="pc-2"),
            session=_ExplodingSession(),
            envelope=SimpleNamespace(correlation_id="c"),
            telemetry=SimpleNamespace(),
            task=None,
        )
        service._sessions["pc-2"] = record
        # WHEN the call ends and draining fails
        await service._drain_and_discard("pc-2")
        # THEN teardown still proceeds (best-effort flush never blocks discard)
        self.assertNotIn("pc-2", service._sessions)

    async def test_hanging_drain_is_bounded_and_still_logs_telemetry(self) -> None:
        # GIVEN a session whose drain() never completes: on a closed/disconnected
        # connection the transport is dead, so the EndFrame queued by drain() can never
        # reach the output and the coroutine hangs in an uncancellable await. This is the
        # exact TASK-WEB-009 teardown hang that silently lost every streaming-call
        # telemetry dump (the only latency evidence for a streaming call).
        from web_voice.webrtc_signaling import WebRtcSignalingService, _Session

        started = asyncio.Event()
        run_task_cancelled = asyncio.Event()

        class _HangingSession:
            async def drain(self) -> None:
                started.set()
                await asyncio.Event().wait()  # never returns (dead transport)

        async def _never_ending() -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                run_task_cancelled.set()
                raise

        logged: list = []
        service = WebRtcSignalingService(
            ingress=_FakeIngress(), egress=_FakeEgress(), backend=_FakeBackend(),
            loop=SimpleNamespace(), log=logged.append,
        )
        run_task = asyncio.ensure_future(_never_ending())
        record = _Session(
            connection=SimpleNamespace(pc_id="pc-3"),
            session=_HangingSession(),
            envelope=SimpleNamespace(correlation_id="c"),
            telemetry=SimpleNamespace(),
            task=run_task,
        )
        service._sessions["pc-3"] = record
        # WHEN teardown drains with a short bound then discards
        await service._drain(record, timeout=0.05)
        service._discard("pc-3")
        # THEN drain started, the wait was bounded (did not hang the teardown), the stuck
        # run() task was cancelled to avoid a leak, and telemetry was still logged
        self.assertTrue(started.is_set())
        await asyncio.sleep(0.01)  # let the fire-and-forget cancellation propagate
        self.assertTrue(run_task.cancelled() or run_task_cancelled.is_set())
        self.assertEqual(logged, [record.telemetry])


@unittest.skipUnless(WEBRTC, "pipecat-ai[webrtc] not installed")
class WebRtcLanguageSelectionTest(unittest.TestCase):
    """US-042: the per-session streaming STT/TTS providers are selected from the offer
    language carried by the session envelope (fr/en), falling back to the default."""

    def _service(self):
        from web_voice.webrtc_signaling import WebRtcSignalingService

        return WebRtcSignalingService(
            ingress=_FakeIngress(), egress=_FakeEgress(), backend=_FakeBackend(),
            loop=SimpleNamespace(), log=lambda _t: None,
            streaming_provider=SimpleNamespace(name="stt-default"),
            streaming_tts_provider=SimpleNamespace(name="tts-default"),
            streaming_providers_by_language={
                "fr": SimpleNamespace(name="stt-fr"), "en": SimpleNamespace(name="stt-en"),
            },
            streaming_tts_providers_by_language={
                "fr": SimpleNamespace(name="tts-fr"), "en": SimpleNamespace(name="tts-en"),
            },
        )

    def test_streaming_providers_selected_by_envelope_language(self) -> None:
        from web_voice.envelope import ChannelEnvelope

        service = self._service()
        en = ChannelEnvelope.for_web_turn(language="en")
        fr = ChannelEnvelope.for_web_turn(language="fr")
        none = ChannelEnvelope.for_web_turn()
        # THEN each half picks the language-specific provider, and the default when unset
        self.assertEqual(service._streaming_provider_for(en).name, "stt-en")
        self.assertEqual(service._streaming_provider_for(fr).name, "stt-fr")
        self.assertEqual(service._streaming_provider_for(none).name, "stt-default")
        self.assertEqual(service._streaming_tts_provider_for(en).name, "tts-en")
        self.assertEqual(service._streaming_tts_provider_for(fr).name, "tts-fr")
        self.assertEqual(service._streaming_tts_provider_for(none).name, "tts-default")


if __name__ == "__main__":
    unittest.main()
