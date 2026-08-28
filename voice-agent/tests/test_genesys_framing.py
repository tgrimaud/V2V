"""TASK-WEB-041 / ADR-0049: the Genesys Audio Connector wire serializer.

`GenesysAudioConnectorSerializer` is the codec seam of the adapter: it keeps the whole
AudioHook-shaped control channel of its parent (`WebSocketAudioSerializer`) and overrides
only the audio path, transcoding PCMU/L16-8 kHz <-> the internal PCM16/16 kHz boundary
(ADR-0043: codec conversion lives in the transport, never in the shared core). Each
transcode emits a `genesys.transcode.in` / `.out` span stamped with codec + channel +
correlation id so a Genesys `conversationId` stitches into one trace.
"""

import array
import json
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from pipecat.frames.frames import (  # noqa: E402
    InputAudioRawFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
)

from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice import genesys_codec as gc  # noqa: E402
from web_voice.envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL  # noqa: E402
from web_voice.genesys_framing import (  # noqa: E402
    TRANSCODE_IN_SPAN,
    TRANSCODE_OUT_SPAN,
    GenesysAudioConnectorSerializer,
)
from web_voice.websocket_framing import ControlType  # noqa: E402


def _serializer(codec: str = gc.L16, telemetry=None, cid: str = "conv-1"):
    params = GenesysAudioConnectorSerializer.InputParams(sample_rate=16000, wire_codec=codec)
    return GenesysAudioConnectorSerializer(params, telemetry=telemetry, correlation_id=cid)


def _pcm16(num_samples: int) -> bytes:
    return array.array("h", [((i * 129) % 65536) - 32768 for i in range(num_samples)]).tobytes()


class GenesysSerializerAudioTest(unittest.IsolatedAsyncioTestCase):
    async def test_inbound_l16_binary_becomes_internal_16k_audio_frame(self) -> None:
        # GIVEN an 8 kHz L16 binary wire frame
        serializer = _serializer(gc.L16)
        wire = _pcm16(160)
        # WHEN it is deserialized
        frame = await serializer.deserialize(wire)
        # THEN it is an InputAudioRawFrame upsampled to the internal 16 kHz boundary
        self.assertIsInstance(frame, InputAudioRawFrame)
        self.assertEqual(frame.sample_rate, 16000)
        self.assertEqual(len(frame.audio), len(wire) * 2)

    async def test_inbound_pcmu_binary_is_decoded_and_upsampled(self) -> None:
        # GIVEN an 8 kHz PCMU (mu-law) binary wire frame (1 byte/sample)
        serializer = _serializer(gc.PCMU)
        ulaw = gc.pcm16_to_ulaw(_pcm16(160))
        # WHEN it is deserialized THEN it lands as 16 kHz PCM16 (2 bytes/sample, x2 rate)
        frame = await serializer.deserialize(ulaw)
        self.assertIsInstance(frame, InputAudioRawFrame)
        self.assertEqual(len(frame.audio), len(ulaw) * 2 * 2)

    async def test_outbound_bot_audio_is_downsampled_and_encoded_to_wire(self) -> None:
        # GIVEN a 16 kHz PCM16 bot audio frame
        serializer = _serializer(gc.L16)
        internal = _pcm16(320)
        # WHEN it is serialized THEN it is L16 wire bytes at half the sample count (8 kHz)
        wire = await serializer.serialize(
            OutputAudioRawFrame(audio=internal, sample_rate=16000, num_channels=1)
        )
        self.assertIsInstance(wire, (bytes, bytearray))
        self.assertEqual(len(wire), len(internal) // 2)

    async def test_empty_audio_serializes_and_deserializes_to_none(self) -> None:
        serializer = _serializer(gc.L16)
        self.assertIsNone(await serializer.deserialize(b""))
        empty = OutputAudioRawFrame(audio=b"", sample_rate=16000, num_channels=1)
        self.assertIsNone(await serializer.serialize(empty))


class GenesysSerializerControlTest(unittest.IsolatedAsyncioTestCase):
    async def test_barge_in_control_frame_surfaces_as_interruption(self) -> None:
        # GIVEN the native Genesys barge_in control frame (WEB-042 will drive this)
        serializer = _serializer()
        # WHEN it arrives as JSON text THEN the parent AudioHook vocabulary maps it 1:1
        frame = await serializer.deserialize(json.dumps({"type": ControlType.BARGE_IN}))
        self.assertIsInstance(frame, InterruptionFrame)

    async def test_open_control_frame_is_acked_with_opened(self) -> None:
        # GIVEN an AudioHook open handshake
        serializer = _serializer()
        # WHEN it is deserialized THEN the reused control channel acks with `opened`
        frame = await serializer.deserialize(json.dumps({"type": ControlType.OPEN}))
        self.assertEqual(frame.message["type"], ControlType.OPENED)
        self.assertTrue(serializer.is_open)


class GenesysSerializerTelemetryTest(unittest.IsolatedAsyncioTestCase):
    async def test_transcode_spans_carry_codec_channel_and_correlation_id(self) -> None:
        # GIVEN a serializer with a telemetry recorder and a known correlation id
        telemetry = TelemetryRecorder()
        serializer = _serializer(gc.PCMU, telemetry=telemetry, cid="conv-42")
        # WHEN one inbound and one outbound audio frame are transcoded
        await serializer.deserialize(gc.pcm16_to_ulaw(_pcm16(160)))
        await serializer.serialize(
            OutputAudioRawFrame(audio=_pcm16(320), sample_rate=16000, num_channels=1)
        )
        # THEN both per-leg transcode spans are emitted with the one-trace attributes
        spans = {span.name: span for span in telemetry.spans()}
        self.assertIn(TRANSCODE_IN_SPAN, spans)
        self.assertIn(TRANSCODE_OUT_SPAN, spans)
        for span in spans.values():
            self.assertEqual(span.attributes["codec"], gc.PCMU)
            self.assertEqual(span.attributes["channel"], GENESYS_AUDIO_CONNECTOR_CHANNEL)
            self.assertEqual(span.attributes["correlation_id"], "conv-42")

    async def test_no_telemetry_recorder_is_a_safe_no_op(self) -> None:
        # GIVEN a serializer with no telemetry (spans must simply not be recorded)
        serializer = _serializer(gc.L16, telemetry=None)
        # WHEN audio is transcoded THEN it still works and raises nothing
        frame = await serializer.deserialize(_pcm16(160))
        self.assertIsInstance(frame, InputAudioRawFrame)


class GenesysSerializerConstructionTest(unittest.TestCase):
    def test_defaults_to_l16_and_rejects_an_unsupported_codec(self) -> None:
        # GIVEN the spike recommendation: prefer L16 end to end
        self.assertEqual(_serializer().wire_codec, gc.L16)
        # WHEN an unsupported codec is requested THEN construction fails fast
        with self.assertRaises(ValueError):
            _serializer("OPUS")


if __name__ == "__main__":
    unittest.main()
