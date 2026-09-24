"""Tests for `web_voice.ws_common` (TASK-WEB-048 / ADR-0053).

`ws_language_config` + the shared WS telemetry/config constants were extracted here from the
retired interim `websocket_signaling.py`. These tests preserve the coverage the deleted
`test_websocket_signaling.py::WebSocketConfigTest` gave `ws_language_config`, and lock the
telemetry names/values so the cross-transport pilot chart (US-036) stays stable.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_voice.ws_common import (  # noqa: E402
    ACTIVE_SESSIONS_METRIC,
    CLIENT_CONNECTED_EVENT,
    CLIENT_DISCONNECTED_EVENT,
    SESSION_REJECTED_EVENT,
    SESSION_STARTED_EVENT,
    WS_LANGUAGE_ENV_VAR,
    WS_MAX_SESSIONS_ENV_VAR,
    ws_language_config,
)


class WsLanguageConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.get(WS_LANGUAGE_ENV_VAR)
        os.environ.pop(WS_LANGUAGE_ENV_VAR, None)

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(WS_LANGUAGE_ENV_VAR, None)
        else:
            os.environ[WS_LANGUAGE_ENV_VAR] = self._saved

    def test_unset_env_keeps_backend_auto_detection(self) -> None:
        # GIVEN no VOICE_WS_LANGUAGE set
        # WHEN resolving the server-default language
        # THEN None is returned (backend auto-detects the answer language)
        self.assertIsNone(ws_language_config())

    def test_blank_env_is_treated_as_unset(self) -> None:
        os.environ[WS_LANGUAGE_ENV_VAR] = "   "
        self.assertIsNone(ws_language_config())

    def test_value_is_stripped_and_lowercased(self) -> None:
        os.environ[WS_LANGUAGE_ENV_VAR] = "  FR  "
        self.assertEqual(ws_language_config(), "fr")


class WsTelemetryNamesTest(unittest.TestCase):
    def test_telemetry_names_are_stable_across_transports(self) -> None:
        # These names are shared by the aiohttp `/ws` path (US-036) — a rename would break
        # the cross-transport pilot chart, so lock them.
        self.assertEqual(SESSION_STARTED_EVENT, "voice.ws.session_started")
        self.assertEqual(CLIENT_CONNECTED_EVENT, "voice.ws.client_connected")
        self.assertEqual(CLIENT_DISCONNECTED_EVENT, "voice.ws.client_disconnected")
        self.assertEqual(ACTIVE_SESSIONS_METRIC, "voice.ws.active_sessions")
        self.assertEqual(SESSION_REJECTED_EVENT, "voice.ws.session_rejected")

    def test_env_var_names_are_preserved(self) -> None:
        self.assertEqual(WS_MAX_SESSIONS_ENV_VAR, "VOICE_MAX_WS_SESSIONS")
        self.assertEqual(WS_LANGUAGE_ENV_VAR, "VOICE_WS_LANGUAGE")


if __name__ == "__main__":
    unittest.main()
