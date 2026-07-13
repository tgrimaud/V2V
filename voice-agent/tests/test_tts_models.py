import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tts_synthesis import SynthesisResult, TtsOutcome  # noqa: E402


class SynthesisResultTest(unittest.TestCase):
    def _result(self) -> SynthesisResult:
        return SynthesisResult(
            audio=b"\x01\x02\x03\x04",
            provider="fixture-tts",
            outcome=TtsOutcome.SUCCESS,
            duration_ms=12.3456,
            tts_request_ms=10.1234,
            correlation_id="cid-1",
            audio_format="pcm_16000",
        )

    def test_to_dict_never_leaks_raw_audio_bytes(self) -> None:
        # GIVEN a synthesis result carrying raw audio
        result = self._result()

        # WHEN it is serialized for telemetry/QA
        payload = result.to_dict()

        # THEN raw bytes are never exposed; only the byte count is
        self.assertNotIn("audio", payload)
        self.assertEqual(payload["audio_bytes"], 4)

    def test_to_dict_exposes_outcome_value_and_rounds_durations(self) -> None:
        # GIVEN a synthesis result
        result = self._result()

        # WHEN serialized
        payload = result.to_dict()

        # THEN the outcome is the enum value and durations are rounded to 3 decimals
        self.assertEqual(payload["outcome"], "success")
        self.assertEqual(payload["duration_ms"], 12.346)
        self.assertEqual(payload["tts_request_ms"], 10.123)
        self.assertEqual(payload["audio_format"], "pcm_16000")
        self.assertEqual(payload["correlation_id"], "cid-1")


if __name__ == "__main__":
    unittest.main()
