"""Tests for the deterministic W3C trace context derivation (TASK-OPS-007).

The voice runtime injects a ``traceparent`` on the backend hop and, separately, builds
its exported ``voice.turn`` root span, both from the turn's correlation id. These prove
the two derivations agree (so the tiers share one trace), the header is well-formed W3C,
and a blank correlation id yields nothing (unchanged fresh-trace behaviour).
"""

import re
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from voice_common.trace_context import derive_traceparent, derive_trace_ids  # noqa: E402

_TRACEPARENT = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-0[01]$")


class DeriveTraceIdsTest(unittest.TestCase):
    def test_none_for_blank_correlation_id(self) -> None:
        # GIVEN no / blank correlation id
        # WHEN deriving ids
        # THEN nothing is derived (root span opens a fresh trace, header omitted)
        self.assertIsNone(derive_trace_ids(None))
        self.assertIsNone(derive_trace_ids("   "))
        self.assertIsNone(derive_traceparent(None))

    def test_deterministic_and_within_valid_ranges(self) -> None:
        # GIVEN a correlation id
        first = derive_trace_ids("corr-42")
        second = derive_trace_ids("  corr-42  ")
        # THEN derivation is stable (whitespace-trimmed) and ids are valid non-zero ranges
        self.assertIsNotNone(first)
        self.assertEqual(first, second)
        trace_id, span_id = first
        self.assertTrue(0 < trace_id < 2**128)
        self.assertTrue(0 < span_id < 2**64)

    def test_distinct_ids_per_correlation_id(self) -> None:
        # Different turns must not collapse into the same trace.
        self.assertNotEqual(derive_trace_ids("corr-a"), derive_trace_ids("corr-b"))

    def test_trace_and_span_ids_differ(self) -> None:
        # The span id is salted so it is not just a truncation of the trace id.
        trace_id, span_id = derive_trace_ids("corr-42")
        self.assertNotEqual(trace_id & ((1 << 64) - 1), span_id)


class DeriveTraceparentTest(unittest.TestCase):
    def test_well_formed_w3c_sampled_header(self) -> None:
        # GIVEN a correlation id
        header = derive_traceparent("corr-42")
        # THEN the header is a valid W3C traceparent with the sampled flag by default
        self.assertRegex(header, _TRACEPARENT)
        self.assertTrue(header.endswith("-01"))

    def test_unsampled_flag_when_requested(self) -> None:
        header = derive_traceparent("corr-42", sampled=False)
        self.assertTrue(header.endswith("-00"))

    def test_header_encodes_the_derived_ids(self) -> None:
        # The header hex must equal the ints the exporter uses, so both tiers agree.
        trace_id, span_id = derive_trace_ids("corr-42")
        header = derive_traceparent("corr-42")
        self.assertEqual(header, f"00-{trace_id:032x}-{span_id:016x}-01")


if __name__ == "__main__":
    unittest.main()
