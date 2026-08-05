"""Tests for `build_ice_servers` (TASK-INFRA-006): env STUN/TURN -> ICE server list.

STUN-only stays a plain `list[str]` (unchanged behaviour); any TURN promotes every
entry to a credentialed `IceServer`, matching `SmallWebRTCConnection`'s homogeneous-list
contract. The IceServer cases need the WebRTC extra and skip cleanly without it.
"""

import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from web_voice.server import build_ice_servers  # noqa: E402
from web_voice.webrtc_support import probe_webrtc_support  # noqa: E402

WEBRTC = probe_webrtc_support().available


class BuildIceServersTest(unittest.TestCase):
    def test_no_config_returns_empty_list(self):
        # GIVEN no STUN and no TURN
        # WHEN building the ICE servers
        result = build_ice_servers()
        # THEN the list is empty (WebRTC uses host candidates only)
        self.assertEqual(result, [])

    def test_stun_only_returns_plain_url_strings(self):
        # GIVEN two STUN URLs (comma-separated, with stray whitespace)
        # WHEN building the ICE servers with no TURN
        result = build_ice_servers(stun="stun:a.example:3478, stun:b.example:3478")
        # THEN the homogeneous str form is kept unchanged (backward compatible)
        self.assertEqual(result, ["stun:a.example:3478", "stun:b.example:3478"])

    @unittest.skipUnless(WEBRTC, "WebRTC extra (aiortc) not installed")
    def test_turn_with_credentials_promotes_all_entries_to_ice_servers(self):
        from pipecat.transports.smallwebrtc.connection import IceServer

        # GIVEN one STUN and one TURN URL with credentials
        result = build_ice_servers(
            stun="stun:s.example:3478",
            turn="turn:t.example:3478",
            turn_username="user",
            turn_credential="secret",
        )
        # THEN every entry is an IceServer (homogeneous list, as the connection requires)
        self.assertTrue(all(isinstance(s, IceServer) for s in result))
        self.assertEqual(len(result), 2)
        turn = result[-1]
        self.assertEqual(turn.urls, "turn:t.example:3478")
        self.assertEqual(turn.username, "user")
        self.assertEqual(turn.credential, "secret")

    @unittest.skipUnless(WEBRTC, "WebRTC extra (aiortc) not installed")
    def test_turn_without_credentials_is_dropped(self):
        from pipecat.transports.smallwebrtc.connection import IceServer

        # GIVEN a TURN URL but NO username/credential (misconfiguration)
        result = build_ice_servers(stun="stun:s.example:3478", turn="turn:t.example:3478")
        # THEN the unauthenticable TURN relay is dropped (no silent fake success),
        #      only the STUN server survives (promoted to IceServer form)
        self.assertEqual(len(result), 1)
        self.assertTrue(isinstance(result[0], IceServer))
        self.assertEqual(result[0].urls, "stun:s.example:3478")


if __name__ == "__main__":
    unittest.main()
