import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tts_synthesis import (  # noqa: E402
    DEFAULT_AUDIO_FORMAT,
    EmptyTextError,
    FixtureTtsProvider,
)


class FixtureTtsProviderTest(unittest.TestCase):
    def test_synthesize_returns_nonempty_pcm16_for_text(self) -> None:
        # GIVEN a fixture provider
        provider = FixtureTtsProvider()

        # WHEN a non-empty text is synthesized
        audio = provider.synthesize("Bonjour, ceci est un test.")

        # THEN it returns non-empty PCM16 (even number of bytes = 16-bit samples)
        self.assertGreater(len(audio), 0)
        self.assertEqual(len(audio) % 2, 0)
        self.assertEqual(provider.name, "fixture-tts")
        self.assertEqual(provider.audio_format, DEFAULT_AUDIO_FORMAT)

    def test_longer_text_yields_longer_audio(self) -> None:
        # GIVEN a fixture provider
        provider = FixtureTtsProvider()

        # WHEN a short and a long text are synthesized
        short = provider.synthesize("Oui.")
        long = provider.synthesize("Ceci est une phrase nettement plus longue que la premiere.")

        # THEN the longer text produces at least as much audio
        self.assertGreater(len(long), len(short))

    def test_duration_scales_with_sample_rate(self) -> None:
        # GIVEN a provider at 16 kHz and a known ms-per-char
        provider = FixtureTtsProvider(sample_rate_hz=16000, ms_per_char=100.0, min_ms=0.0)

        # WHEN a 10-char text is synthesized (~1000 ms -> 16000 samples -> 32000 bytes)
        audio = provider.synthesize("0123456789")

        # THEN the byte count matches the expected duration
        self.assertEqual(len(audio), 16000 * 2)

    def test_empty_text_raises_empty_text_error(self) -> None:
        # GIVEN a fixture provider
        provider = FixtureTtsProvider()

        # WHEN/THEN empty or whitespace text is rejected as "nothing to speak"
        for empty in ("", "   ", "\n\t"):
            with self.assertRaises(EmptyTextError):
                provider.synthesize(empty)


if __name__ == "__main__":
    unittest.main()
