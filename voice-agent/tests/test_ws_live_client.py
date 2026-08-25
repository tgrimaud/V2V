"""Tests for the headless WebSocket latency-evidence client helpers (TASK-WEB-031).

The asyncio socket loop needs a live server, but the wire-frame construction and the
audible-frame detection are pure and must be correct so a captured sample is trustworthy:
the `open` frame declares the language, the PCM is chunked into fixed 20 ms frames (short
tail padded), and only above-threshold binary frames count as the audible answer onset.
"""

import json
import struct
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))
sys.path.insert(0, str(VOICE_AGENT_ROOT / "scripts"))

from ws_live_client import (  # noqa: E402
    build_open_frame,
    frame_bytes,
    frame_rms,
    iter_pcm_frames,
    silence_frames,
)


class OpenFrameTest(unittest.TestCase):
    def test_open_frame_declares_language_when_present(self) -> None:
        self.assertEqual(json.loads(build_open_frame("fr")), {"type": "open", "language": "fr"})

    def test_open_frame_omits_language_when_none(self) -> None:
        self.assertEqual(json.loads(build_open_frame(None)), {"type": "open"})


class FramingTest(unittest.TestCase):
    def test_frame_bytes_is_two_bytes_per_sample(self) -> None:
        # 20 ms @ 16 kHz = 320 samples = 640 bytes (PCM16 mono)
        self.assertEqual(frame_bytes(16000, 20), 640)

    def test_pcm_is_chunked_and_the_short_tail_is_padded_with_silence(self) -> None:
        # GIVEN 1.5 frames of audio (all 0x01 bytes)
        chunk = 640
        pcm = b"\x01" * (chunk + chunk // 2)
        # WHEN chunked
        frames = list(iter_pcm_frames(pcm, chunk))
        # THEN two full-size frames, the last padded with trailing zeros (no truncation)
        self.assertEqual(len(frames), 2)
        self.assertTrue(all(len(f) == chunk for f in frames))
        self.assertEqual(frames[1][: chunk // 2], b"\x01" * (chunk // 2))
        self.assertEqual(frames[1][chunk // 2 :], b"\x00" * (chunk // 2))

    def test_silence_frames_are_zeroed_and_counted(self) -> None:
        frames = list(silence_frames(3, 640))
        self.assertEqual(len(frames), 3)
        self.assertTrue(all(f == b"\x00" * 640 for f in frames))


class FrameRmsTest(unittest.TestCase):
    def test_silence_is_zero_rms_and_loud_audio_is_above_threshold(self) -> None:
        silence = b"\x00" * 640
        loud = struct.pack("<320h", *([8000] * 320))
        self.assertEqual(frame_rms(silence), 0.0)
        self.assertGreater(frame_rms(loud), 200.0)

    def test_empty_frame_is_safe(self) -> None:
        self.assertEqual(frame_rms(b""), 0.0)


if __name__ == "__main__":
    unittest.main()
