"""Tests for the WebRTC dependency guard (Sprint 6 / TASK-WEB-007, spike).

The guard must never raise on a missing extra (a supported degraded state) and must
give an actionable install hint. These assertions hold whether or not
`pipecat-ai[webrtc]` is installed, so the base suite stays green without the heavy
C-extension wheels.
"""

import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from web_voice.webrtc_support import (  # noqa: E402
    load_webrtc_transport,
    probe_webrtc_support,
)


class WebRtcSupportTest(unittest.TestCase):
    def test_probe_never_raises_and_reports_a_boolean(self) -> None:
        # GIVEN any environment (extra installed or not)
        # WHEN probing WebRTC support
        support = probe_webrtc_support()
        # THEN it reports a boolean and always exposes an actionable install hint
        self.assertIsInstance(support.available, bool)
        self.assertIn("pipecat-ai[webrtc]", support.install_hint)

    def test_probe_reports_missing_dep_when_unavailable(self) -> None:
        # GIVEN a probe result
        support = probe_webrtc_support()
        if support.available:
            # Extra installed: no missing dep, and the transport loads.
            self.assertIsNone(support.missing)
            self.assertIsNotNone(load_webrtc_transport())
        else:
            # Extra absent (this offline env): the missing module is named, and the
            # loader raises a clear, actionable error rather than a bare ImportError.
            self.assertIsNotNone(support.missing)
            with self.assertRaises(RuntimeError) as ctx:
                load_webrtc_transport()
            self.assertIn("pipecat-ai[webrtc]", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
