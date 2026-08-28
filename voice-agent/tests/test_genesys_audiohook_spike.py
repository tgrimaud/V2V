"""Tests for the THROWAWAY Genesys Audio Connector spike (TASK-WEB-025).

The spike is investigation-only and throwaway, but these tests keep it honest and keep
`unittest discover` green: they prove the transcode round trips, the prototype emits the
four synthetic transport legs, the per-leg report marks live/in-house legs unmeasured
(US-036 rule), the ADR-0029 re-score fails when the measured floor already exceeds the
gate, and the harness produces a report for both codecs + the concurrency probe.
"""

import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from voice_common.telemetry import TelemetryRecorder  # noqa: E402

from spikes.genesys_audiohook import transcode  # noqa: E402
from spikes.genesys_audiohook.audiohook_prototype import AudioHookSessionPrototype  # noqa: E402
from spikes.genesys_audiohook.genesys_legs import per_leg_report, transport_overhead_samples  # noqa: E402
from spikes.genesys_audiohook.rescore import rescore  # noqa: E402
from spikes.genesys_audiohook.synthetic_audio import synthetic_pcm16_16k, synthetic_wire_frames  # noqa: E402


class TranscodeTest(unittest.TestCase):
    def test_ulaw_round_trip_is_bounded(self) -> None:
        # GIVEN synthetic PCM16 samples
        pcm = synthetic_pcm16_16k(20, seed=3)
        # WHEN encoding to µ-law and back
        restored = transcode.ulaw_to_pcm16(transcode.pcm16_to_ulaw(pcm))
        # THEN length is preserved and µ-law quantization error stays bounded
        self.assertEqual(len(restored), len(pcm))

    def test_pcmu_path_upsamples_to_16k(self) -> None:
        # GIVEN one 20 ms 8 kHz PCMU frame (160 samples -> 160 bytes)
        frame = transcode.pcm16_to_ulaw(b"\x01\x00" * 160)
        # WHEN transcoding to the internal PCM16/16 kHz boundary
        internal = transcode.to_internal_pcm16(frame, "PCMU")
        # THEN it is upsampled 2x (320 samples -> 640 bytes)
        self.assertEqual(len(internal), 640)

    def test_l16_path_only_resamples(self) -> None:
        # GIVEN one 8 kHz L16 frame, WHEN going to the internal boundary and back
        frame = b"\x02\x00" * 160
        internal = transcode.to_internal_pcm16(frame, "L16")
        wire = transcode.from_internal_pcm16(internal, "L16")
        # THEN the round trip preserves the frame length (no companding)
        self.assertEqual(len(internal), 640)
        self.assertEqual(len(wire), len(frame))


class PrototypeTest(unittest.TestCase):
    def test_run_turn_emits_the_four_transport_legs(self) -> None:
        # GIVEN a throwaway session and synthetic caller frames
        telemetry = TelemetryRecorder()
        frames = synthetic_wire_frames(100, "PCMU", seed=1)
        session = AudioHookSessionPrototype(telemetry, codec="PCMU", conversation_id="c-1")
        # WHEN one round trip runs through an injected synthetic runtime (no backend code)
        session.run_turn(frames, lambda _pcm: synthetic_pcm16_16k(100, seed=2))
        # THEN it emits exactly the four synthetic transport/transcode legs, tagged with the id
        names = {span.name for span in telemetry.spans()}
        self.assertEqual(
            names,
            {"genesys.wss.inbound", "genesys.transcode.in", "genesys.transcode.out", "genesys.wss.outbound"},
        )
        self.assertTrue(all(s.attributes.get("correlation_id") == "c-1" for s in telemetry.spans()))


class LegReportTest(unittest.TestCase):
    def _sample(self, turns: int = 5) -> TelemetryRecorder:
        telemetry = TelemetryRecorder()
        for turn in range(turns):
            frames = synthetic_wire_frames(60, "PCMU", seed=turn + 1)
            AudioHookSessionPrototype(telemetry, codec="PCMU", conversation_id=f"c-{turn}").run_turn(
                frames, lambda _pcm: synthetic_pcm16_16k(60, seed=9)
            )
        return telemetry

    def test_live_and_in_house_legs_are_reported_unmeasured(self) -> None:
        # GIVEN a synthetic sample, WHEN building the per-leg report
        rows = {row["leg"]: row for row in per_leg_report(self._sample().spans())}
        # THEN cloud legs and in-house legs are explicit gaps, synthetic legs are measured
        self.assertFalse(rows["genesys_ingress"]["measured"])
        self.assertFalse(rows["backend"]["measured"])
        self.assertTrue(rows["transcode_in"]["measured"])
        self.assertIsNotNone(rows["genesys_ingress"]["note"])

    def test_transport_overhead_has_one_sample_per_turn(self) -> None:
        samples = transport_overhead_samples(self._sample(turns=4).spans())
        self.assertEqual(len(samples), 4)
        self.assertTrue(all(value > 0 for value in samples))


class RescoreTest(unittest.TestCase):
    def test_floor_over_gate_is_definitive_fail(self) -> None:
        # GIVEN a measured overhead stacked on an already-FAIL in-house base
        result = rescore([18.0, 19.0, 20.0], base_mouth_to_ear_p95_ms=2760.0)
        # THEN the re-score is a definitive fail (floor already exceeds the 1.5 s gate)
        self.assertEqual(result["status"], "fail")
        self.assertGreater(result["measured_floor_p95_ms"], result["gate_p95_ms"])

    def test_no_base_stays_not_measured(self) -> None:
        # WHEN there is no in-house base to stack the overhead on
        result = rescore([18.0], base_mouth_to_ear_p95_ms=None)
        # THEN a PASS is never silently claimed
        self.assertEqual(result["status"], "not_measured")

    def test_no_overhead_stays_not_measured(self) -> None:
        result = rescore([], base_mouth_to_ear_p95_ms=2760.0)
        self.assertEqual(result["status"], "not_measured")


class HarnessTest(unittest.TestCase):
    def test_build_report_covers_both_codecs_and_concurrency(self) -> None:
        from argparse import Namespace

        from spikes.genesys_audiohook.harness import build_report

        # GIVEN a small synthetic run
        args = Namespace(turns=3, caller_ms=100, answer_ms=100, concurrency=3, base_mouth_to_ear_ms=2760.0)
        # WHEN building the report
        report = build_report(args)
        # THEN both codecs are re-scored and the concurrency target is probed
        codecs = {c["codec"] for c in report["codecs"]}
        self.assertEqual(codecs, {"PCMU", "L16"})
        self.assertEqual(report["concurrency"]["target_sessions"], 3)
        self.assertTrue(all(c["adr_0029_rescore"]["status"] in {"fail", "not_measured"} for c in report["codecs"]))


if __name__ == "__main__":
    unittest.main()
