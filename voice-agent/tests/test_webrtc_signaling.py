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
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
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
            telemetry=TelemetryRecorder(),
            task=None,
        )
        service._sessions["pc-1"] = record
        # WHEN the call ends (closed/disconnected path)
        await service._drain_and_discard("pc-1")
        # THEN the session was drained (trailing partial flushed) then discarded + logged
        self.assertTrue(drained.is_set())
        self.assertNotIn("pc-1", service._sessions)
        self.assertEqual(logged, [record.telemetry])
        # AND the end-of-call reason (manual hangup) was recorded under the correlation id
        end = next(e for e in record.telemetry.events() if e.name == "voice.call_end")
        self.assertEqual(end.attributes["reason"], "client_stop")

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
            telemetry=TelemetryRecorder(),
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


class FarewellConfigTest(unittest.TestCase):
    """TASK-WEB-010: env-tunable farewell settings resolve like the barge-in config."""

    def setUp(self) -> None:
        self._vars = (
            "VOICE_FAREWELL_ENABLED",
            "VOICE_FAREWELL_CONFIRM_TIMEOUT_S",
            "VOICE_FAREWELL_PHRASES",
        )
        self._saved = {name: __import__("os").environ.pop(name, None) for name in self._vars}

    def tearDown(self) -> None:
        import os

        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_defaults_when_unset(self) -> None:
        from web_voice.webrtc_signaling import _farewell_config

        # GIVEN no overrides -> THEN the feature is enabled with default phrases/timeout
        config = _farewell_config()
        self.assertTrue(config["enabled"])
        self.assertGreater(config["timeout_s"], 0)
        self.assertIn("au revoir", config["closing_phrases"])

    def test_can_be_disabled(self) -> None:
        import os

        from web_voice.webrtc_signaling import _farewell_config

        # GIVEN the disable switch -> THEN the feature is off
        os.environ["VOICE_FAREWELL_ENABLED"] = "0"
        self.assertFalse(_farewell_config()["enabled"])

    def test_invalid_timeout_falls_back_to_default(self) -> None:
        import os

        from web_voice.call_end_farewell import DEFAULT_CONFIRM_TIMEOUT_S
        from web_voice.webrtc_signaling import _farewell_config

        # GIVEN a non-numeric / non-positive timeout -> THEN the default wins (no crash)
        os.environ["VOICE_FAREWELL_CONFIRM_TIMEOUT_S"] = "soon"
        self.assertEqual(_farewell_config()["timeout_s"], DEFAULT_CONFIRM_TIMEOUT_S)

    def test_phrase_list_override_is_parsed(self) -> None:
        import os

        from web_voice.webrtc_signaling import _farewell_config

        # GIVEN a comma-separated override -> THEN it replaces the default phrase set
        os.environ["VOICE_FAREWELL_PHRASES"] = " au revoir , ciao ,"
        self.assertEqual(_farewell_config()["closing_phrases"], ("au revoir", "ciao"))


class SilenceWindowConfigTest(unittest.TestCase):
    """TASK-WEB-015 lever 3: env-tunable end-of-turn hold, clamped to a safe floor."""

    def setUp(self) -> None:
        self._saved = __import__("os").environ.pop("VOICE_END_OF_TURN_SILENCE_MS", None)

    def tearDown(self) -> None:
        import os

        if self._saved is None:
            os.environ.pop("VOICE_END_OF_TURN_SILENCE_MS", None)
        else:
            os.environ["VOICE_END_OF_TURN_SILENCE_MS"] = self._saved

    def test_unset_yields_no_override(self) -> None:
        from web_voice.webrtc_signaling import _silence_window_config

        # GIVEN no override -> THEN the processor default applies (empty config)
        self.assertEqual(_silence_window_config(), {})

    def test_valid_override_above_floor_is_honoured(self) -> None:
        import os

        from web_voice.webrtc_signaling import _silence_window_config

        # GIVEN a value above the safe floor -> THEN it is used as-is
        os.environ["VOICE_END_OF_TURN_SILENCE_MS"] = "350"
        self.assertEqual(_silence_window_config(), {"silence_window_ms": 350.0})

    def test_below_floor_is_clamped_not_honoured(self) -> None:
        import os

        from web_voice.end_of_turn import MIN_SAFE_SILENCE_WINDOW_MS
        from web_voice.webrtc_signaling import _silence_window_config

        # GIVEN a reckless low value -> THEN it is clamped to the safe floor
        os.environ["VOICE_END_OF_TURN_SILENCE_MS"] = "50"
        self.assertEqual(_silence_window_config(), {"silence_window_ms": MIN_SAFE_SILENCE_WINDOW_MS})

    def test_invalid_or_non_positive_falls_back_to_default(self) -> None:
        import os

        from web_voice.webrtc_signaling import _silence_window_config

        # GIVEN a non-numeric / non-positive value -> THEN no override (default wins)
        os.environ["VOICE_END_OF_TURN_SILENCE_MS"] = "soon"
        self.assertEqual(_silence_window_config(), {})
        os.environ["VOICE_END_OF_TURN_SILENCE_MS"] = "0"
        self.assertEqual(_silence_window_config(), {})

    def test_below_floor_logs_a_clamp_warning_once(self) -> None:
        import os

        import web_voice.webrtc_signaling as signaling

        # GIVEN a reckless low value and no prior clamp warning this process
        signaling._silence_clamp_warned = False
        os.environ["VOICE_END_OF_TURN_SILENCE_MS"] = "50"
        # WHEN the config is read twice
        with self.assertLogs("web_voice.webrtc_signaling", level="WARNING") as captured:
            signaling._silence_window_config()
            signaling._silence_window_config()
        # THEN exactly one warning naming the clamp is emitted (no per-connection spam)
        clamp_lines = [m for m in captured.output if "below the safe floor" in m]
        self.assertEqual(len(clamp_lines), 1)

    def test_processor_applies_the_tuned_window_to_its_detector(self) -> None:
        from web_voice.streaming_stt_processor import StreamingSttProcessor

        # GIVEN a processor built with a tuned-down hold
        proc = StreamingSttProcessor(
            SimpleNamespace(name="stt"),
            SimpleNamespace(correlation_id="c", channel="web_voice", external_session_id="s"),
            silence_window_ms=350.0,
        )
        # THEN its end-of-turn detector fires on 350 ms of trailing silence, not 500 ms
        self.assertEqual(proc._detector.silence_window_ms, 350.0)

    def test_end_of_turn_telemetry_carries_the_configured_window(self) -> None:
        from web_voice.end_of_turn import SIGNAL_CLIENT_STOP, EndOfTurnResult
        from web_voice.streaming_stt_processor import StreamingSttProcessor

        # GIVEN a processor with a tuned hold and a client_stop detection (short silence)
        proc = StreamingSttProcessor(
            SimpleNamespace(name="stt"),
            SimpleNamespace(correlation_id="c", channel="web_voice", external_session_id="s"),
            silence_window_ms=350.0,
        )
        detection = EndOfTurnResult(True, SIGNAL_CLIENT_STOP, 120.0, 90.0, 90.0)
        # THEN the end_of_turn attrs expose the configured window, not just the short silence
        attrs = proc._end_of_turn_attrs(detection)
        self.assertEqual(attrs["silence_window_ms"], 350.0)
        self.assertEqual(attrs["trailing_silence_ms"], 90.0)


@unittest.skipUnless(WEBRTC, "pipecat-ai[webrtc] not installed")
class FarewellWiringTest(unittest.IsolatedAsyncioTestCase):
    def _service(self):
        from web_voice.webrtc_signaling import WebRtcSignalingService

        return WebRtcSignalingService(
            ingress=_FakeIngress(), egress=_FakeEgress(), backend=_FakeBackend(),
            loop=SimpleNamespace(), log=lambda _t: None,
            streaming_provider=SimpleNamespace(name="stt"),
            streaming_tts_provider=SimpleNamespace(name="tts"),
        )

    def test_end_of_call_reason_is_recorded_once_and_farewell_wins(self) -> None:
        # GIVEN a session record with a recorder
        from web_voice.webrtc_signaling import _Session

        service = self._service()
        record = _Session(
            connection=SimpleNamespace(pc_id="pc"),
            session=SimpleNamespace(),
            envelope=SimpleNamespace(correlation_id="corr-1"),
            telemetry=TelemetryRecorder(),
        )
        # WHEN a farewell reason is recorded, then a later closed event tries to overwrite it
        service._record_end_of_call(record, reason="customer_farewell", signal="confirmation")
        service._record_end_of_call(record, reason="client_stop")
        # THEN exactly one end-of-call event stands, and the farewell reason is kept
        ends = [e for e in record.telemetry.events() if e.name == "voice.call_end"]
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0].attributes["reason"], "customer_farewell")
        self.assertEqual(ends[0].attributes["signal"], "confirmation")

    async def test_on_farewell_records_reason_then_drains_and_disconnects(self) -> None:
        # GIVEN a session whose drain + disconnect are observable
        from web_voice.webrtc_signaling import _Session

        service = self._service()
        drained = asyncio.Event()
        disconnected = asyncio.Event()

        record = _Session(
            connection=SimpleNamespace(pc_id="pc", disconnect=lambda: _set(disconnected)),
            session=SimpleNamespace(drain=lambda: _set(drained)),
            envelope=SimpleNamespace(correlation_id="corr-1"),
            telemetry=TelemetryRecorder(),
            task=None,
        )
        # WHEN a farewell is confirmed
        await service._on_farewell(record, "silence")
        await asyncio.sleep(0.05)  # let the fire-and-forget teardown run
        # THEN the reason is recorded and the graceful drain + disconnect happened
        self.assertEqual(record.end_reason, "customer_farewell")
        self.assertTrue(drained.is_set())
        self.assertTrue(disconnected.is_set())

    def test_farewell_processor_absent_when_disabled(self) -> None:
        import os

        service = self._service()
        saved = os.environ.pop("VOICE_FAREWELL_ENABLED", None)
        os.environ["VOICE_FAREWELL_ENABLED"] = "false"
        try:
            # WHEN the feature is disabled -> THEN no farewell processor is built
            self.assertIsNone(
                service._build_farewell_processor(SimpleNamespace(correlation_id="c"), TelemetryRecorder())
            )
        finally:
            if saved is None:
                os.environ.pop("VOICE_FAREWELL_ENABLED", None)
            else:
                os.environ["VOICE_FAREWELL_ENABLED"] = saved


async def _set(event: asyncio.Event) -> None:
    event.set()


if __name__ == "__main__":
    unittest.main()
