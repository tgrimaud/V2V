"""Tests for the browser WebSocket audio framing serializer (TASK-WEB-026, ADR-0043).

The wire framing must deterministically demux a WebSocket connection into:
- binary message -> PCM16/16 kHz audio (``InputAudioRawFrame``)
- text message   -> JSON control frame ({"type": ...}), modelled on the Genesys
  AudioHook shape (JSON control + binary audio).
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipecat.frames.frames import (  # noqa: E402
    CancelFrame,
    EndFrame,
    InputAudioRawFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageUrgentFrame,
    StartFrame,
)

from web_voice.websocket_framing import ControlType, WebSocketAudioSerializer  # noqa: E402


def _serializer() -> WebSocketAudioSerializer:
    return WebSocketAudioSerializer()


class WebSocketFramingDemuxTest(unittest.IsolatedAsyncioTestCase):
    async def test_binary_message_is_deserialized_as_pcm16_audio(self):
        # GIVEN a raw PCM16 payload arriving as a binary WebSocket frame
        serializer = _serializer()
        pcm = b"\x01\x02\x03\x04" * 40
        # WHEN it is deserialized
        frame = await serializer.deserialize(pcm)
        # THEN it becomes a mono 16 kHz InputAudioRawFrame carrying the exact bytes
        self.assertIsInstance(frame, InputAudioRawFrame)
        self.assertEqual(frame.audio, pcm)
        self.assertEqual(frame.sample_rate, 16000)
        self.assertEqual(frame.num_channels, 1)

    async def test_text_message_is_deserialized_as_control_never_audio(self):
        # GIVEN a JSON control frame arriving as text
        serializer = _serializer()
        # WHEN it is deserialized
        frame = await serializer.deserialize(json.dumps({"type": ControlType.OPEN}))
        # THEN it is never treated as audio
        self.assertNotIsInstance(frame, InputAudioRawFrame)

    async def test_empty_binary_is_ignored(self):
        self.assertIsNone(await _serializer().deserialize(b""))

    async def test_invalid_json_text_is_ignored(self):
        self.assertIsNone(await _serializer().deserialize("not-json"))

    async def test_non_object_json_is_ignored(self):
        self.assertIsNone(await _serializer().deserialize(json.dumps([1, 2, 3])))


class WebSocketControlFramesTest(unittest.IsolatedAsyncioTestCase):
    async def test_open_opens_session_captures_language_and_acks_opened(self):
        serializer = _serializer()
        frame = await serializer.deserialize(json.dumps({"type": "open", "language": "fr"}))
        self.assertIsInstance(frame, OutputTransportMessageUrgentFrame)
        self.assertEqual(frame.message, {"type": ControlType.OPENED})
        self.assertTrue(serializer.is_open)
        self.assertEqual(serializer.selected_language, "fr")

    async def test_language_control_updates_selected_language_without_a_frame(self):
        serializer = _serializer()
        result = await serializer.deserialize(json.dumps({"type": "language", "language": "en"}))
        self.assertIsNone(result)
        self.assertEqual(serializer.selected_language, "en")

    async def test_barge_in_control_becomes_an_interruption_frame(self):
        frame = await _serializer().deserialize(json.dumps({"type": "barge_in"}))
        self.assertIsInstance(frame, InterruptionFrame)

    async def test_close_closes_session_and_acks_closed(self):
        serializer = _serializer()
        await serializer.deserialize(json.dumps({"type": "open"}))
        frame = await serializer.deserialize(json.dumps({"type": "close"}))
        self.assertIsInstance(frame, OutputTransportMessageUrgentFrame)
        self.assertEqual(frame.message, {"type": ControlType.CLOSED})
        self.assertFalse(serializer.is_open)

    async def test_ping_is_answered_with_pong(self):
        frame = await _serializer().deserialize(json.dumps({"type": "ping"}))
        self.assertEqual(frame.message, {"type": ControlType.PONG})

    async def test_unknown_control_type_is_ignored(self):
        self.assertIsNone(await _serializer().deserialize(json.dumps({"type": "nope"})))


class WebSocketSerializeTest(unittest.IsolatedAsyncioTestCase):
    async def test_bot_audio_is_serialized_to_raw_pcm16_bytes(self):
        serializer = _serializer()
        pcm = b"\x10\x20" * 100
        out = await serializer.serialize(
            OutputAudioRawFrame(audio=pcm, sample_rate=16000, num_channels=1)
        )
        self.assertEqual(out, pcm)

    async def test_interruption_frame_is_serialized_to_barge_in_json(self):
        out = await _serializer().serialize(InterruptionFrame())
        self.assertEqual(json.loads(out), {"type": ControlType.BARGE_IN})

    async def test_end_frame_is_serialized_to_call_end_json(self):
        out = await _serializer().serialize(EndFrame())
        self.assertEqual(json.loads(out), {"type": ControlType.CALL_END})

    async def test_cancel_frame_is_serialized_to_call_end_json(self):
        out = await _serializer().serialize(CancelFrame())
        self.assertEqual(json.loads(out), {"type": ControlType.CALL_END})

    async def test_transport_message_dict_passes_through_as_json(self):
        out = await _serializer().serialize(
            OutputTransportMessageUrgentFrame(message={"type": ControlType.OPENED})
        )
        self.assertEqual(json.loads(out), {"type": ControlType.OPENED})


class WebSocketSetupTest(unittest.IsolatedAsyncioTestCase):
    async def test_setup_adopts_pipeline_input_sample_rate_when_param_absent(self):
        serializer = WebSocketAudioSerializer(WebSocketAudioSerializer.InputParams(sample_rate=0))
        await serializer.setup(StartFrame(audio_in_sample_rate=16000, audio_out_sample_rate=16000))
        frame = await serializer.deserialize(b"\x00\x01" * 10)
        self.assertEqual(frame.sample_rate, 16000)


if __name__ == "__main__":
    unittest.main()
