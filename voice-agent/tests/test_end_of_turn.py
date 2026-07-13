import array
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_voice.end_of_turn import (  # noqa: E402
    SIGNAL_CLIENT_STOP,
    SIGNAL_SILENCE_WINDOW,
    EndOfTurnDetector,
)

SAMPLE_RATE = 16000
SPEECH_LEVEL = 8000


def _pcm_le(samples: list[int]) -> bytes:
    """Serialize int16 samples as little-endian PCM16 on any host byte order."""
    data = array.array("h", samples)
    if sys.byteorder == "big":
        data.byteswap()
    return data.tobytes()


def _ms_to_samples(ms: float) -> int:
    return int(SAMPLE_RATE * ms / 1000)


def _speech_then_silence(speech_ms: float, silence_ms: float) -> bytes:
    return _pcm_le(
        [SPEECH_LEVEL] * _ms_to_samples(speech_ms) + [0] * _ms_to_samples(silence_ms)
    )


class EndOfTurnDetectorTest(unittest.TestCase):
    def test_long_trailing_silence_is_authoritative_silence_window(self) -> None:
        # GIVEN 200 ms of speech followed by 500 ms of trailing silence
        detector = EndOfTurnDetector()
        audio = _speech_then_silence(200, 500)

        # WHEN
        result = detector.detect(audio)

        # THEN the silence window is the authoritative end-of-turn signal
        self.assertTrue(result.detected)
        self.assertEqual(result.signal, SIGNAL_SILENCE_WINDOW)
        self.assertAlmostEqual(result.speech_end_ms, 200.0, delta=20.0)
        self.assertGreaterEqual(result.trailing_silence_ms, 500.0)
        self.assertEqual(result.slice_ms, 500.0)

    def test_short_trailing_silence_falls_back_to_client_stop(self) -> None:
        # GIVEN speech ending with only 100 ms of trailing silence (< window)
        detector = EndOfTurnDetector()
        audio = _speech_then_silence(200, 100)

        # WHEN
        result = detector.detect(audio)

        # THEN the explicit client stop is the fallback signal
        self.assertTrue(result.detected)
        self.assertEqual(result.signal, SIGNAL_CLIENT_STOP)
        self.assertAlmostEqual(result.trailing_silence_ms, 100.0, delta=20.0)
        self.assertAlmostEqual(result.slice_ms, result.trailing_silence_ms)

    def test_pure_silence_detects_no_turn_and_invents_no_boundary(self) -> None:
        # GIVEN a buffer of pure silence
        detector = EndOfTurnDetector()
        audio = _pcm_le([0] * _ms_to_samples(400))

        # WHEN
        result = detector.detect(audio)

        # THEN no turn boundary is invented
        self.assertFalse(result.detected)
        self.assertIsNone(result.slice_ms)
        self.assertIsNone(result.signal)

    def test_empty_audio_detects_no_turn(self) -> None:
        result = EndOfTurnDetector().detect(b"")
        self.assertFalse(result.detected)
        self.assertIsNone(result.slice_ms)

    def test_odd_length_buffer_is_handled_without_error(self) -> None:
        # GIVEN a buffer with a trailing odd byte (truncated frame)
        detector = EndOfTurnDetector()
        audio = _speech_then_silence(100, 500) + b"\x01"

        # WHEN / THEN it still classifies without raising
        result = detector.detect(audio)
        self.assertTrue(result.detected)

    def test_amplitude_threshold_below_speech_level_is_configurable(self) -> None:
        # GIVEN a detector whose threshold rejects the quiet "speech" level
        detector = EndOfTurnDetector(amplitude_threshold=SPEECH_LEVEL + 1)
        audio = _speech_then_silence(200, 500)

        # WHEN
        result = detector.detect(audio)

        # THEN the frames are treated as silence -> no turn
        self.assertFalse(result.detected)

    def test_invalid_configuration_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EndOfTurnDetector(sample_rate_hz=0)


if __name__ == "__main__":
    unittest.main()
