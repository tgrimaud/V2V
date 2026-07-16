"""Tests for the streaming (frame-incremental) end-of-turn detector (TASK-STT-012).

Drives the detector with a frame sequence (speech -> silence -> fire) and asserts it
fires the `voice.end_of_turn` result **before** a full buffer exists, keeps the
TASK-STT-009 no-speech guarantee, and mirrors the batch `client_stop` fallback on
stream end.
"""

import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from web_voice.end_of_turn import (  # noqa: E402
    SIGNAL_CLIENT_STOP,
    SIGNAL_SILENCE_WINDOW,
    StreamingEndOfTurnDetector,
)

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = (SAMPLE_RATE * FRAME_MS // 1000) * 2  # 20 ms PCM16 mono


def _speech() -> bytes:
    return (5000).to_bytes(2, "little", signed=True) * (FRAME_BYTES // 2)


def _silence() -> bytes:
    return b"\x00" * FRAME_BYTES


def _detector(**kwargs) -> StreamingEndOfTurnDetector:
    params = dict(sample_rate_hz=SAMPLE_RATE, silence_window_ms=100, min_utterance_ms=40)
    params.update(kwargs)
    return StreamingEndOfTurnDetector(**params)


class StreamingEndOfTurnDetectorTest(unittest.TestCase):
    def test_fires_after_trailing_silence_window(self) -> None:
        # GIVEN 3 speech frames (60 ms) then silence
        detector = _detector()
        for _ in range(3):
            self.assertIsNone(detector.observe(_speech()).detection)
        # WHEN silence accumulates up to the 100 ms window (5 frames)
        decisions = [detector.observe(_silence()) for _ in range(5)]
        # THEN the turn fires on the frame that completes the window, before the full
        # utterance buffer is available, with the silence-window signal + attributes
        fired = [d for d in decisions if d.detection is not None]
        self.assertEqual(len(fired), 1)
        result = fired[0].detection
        self.assertEqual(result.signal, SIGNAL_SILENCE_WINDOW)
        self.assertEqual(result.slice_ms, 100)
        self.assertAlmostEqual(result.speech_end_ms, 60.0, places=3)
        self.assertGreaterEqual(result.trailing_silence_ms, 100.0)

    def test_no_speech_never_invents_a_turn(self) -> None:
        # GIVEN a stream that carries only silence
        detector = _detector()
        # WHEN observed frame by frame and then the stream ends
        for _ in range(20):
            self.assertIsNone(detector.observe(_silence()).detection)
        finish = detector.finish()
        # THEN no boundary is ever fired (TASK-STT-009 guarantee)
        self.assertIsNone(finish.detection)
        self.assertFalse(finish.discard)

    def test_finish_flushes_pending_speech_as_client_stop(self) -> None:
        # GIVEN speech followed by silence shorter than the window
        detector = _detector()
        for _ in range(3):
            detector.observe(_speech())
        for _ in range(2):  # 40 ms < 100 ms window
            self.assertIsNone(detector.observe(_silence()).detection)
        # WHEN the stream ends (EndFrame / call drop)
        result = detector.finish().detection
        # THEN pending speech is flushed with the client-stop signal
        self.assertIsNotNone(result)
        self.assertEqual(result.signal, SIGNAL_CLIENT_STOP)
        self.assertAlmostEqual(result.trailing_silence_ms, 40.0, places=3)
        self.assertAlmostEqual(result.slice_ms, 40.0, places=3)

    def test_sub_minimum_click_is_discarded_not_fired(self) -> None:
        # GIVEN a single 20 ms click below min_utterance_ms (40 ms)
        detector = _detector()
        detector.observe(_speech())
        # WHEN silence elapses past the window
        decisions = [detector.observe(_silence()) for _ in range(5)]
        # THEN the click is discarded (buffer drop), never fired as a turn
        self.assertTrue(any(d.discard for d in decisions))
        self.assertTrue(all(d.detection is None for d in decisions))

    def test_resets_between_consecutive_turns(self) -> None:
        # GIVEN one full turn already fired
        detector = _detector()
        for _ in range(3):
            detector.observe(_speech())
        first = [detector.observe(_silence()) for _ in range(5)]
        self.assertTrue(any(d.detection is not None for d in first))
        # WHEN a second turn streams in
        for _ in range(3):
            detector.observe(_speech())
        second = [detector.observe(_silence()) for _ in range(5)]
        # THEN it fires independently (speech_end_ms measured from the new turn start)
        fired = [d.detection for d in second if d.detection is not None]
        self.assertEqual(len(fired), 1)
        self.assertAlmostEqual(fired[0].speech_end_ms, 60.0, places=3)


if __name__ == "__main__":
    unittest.main()
