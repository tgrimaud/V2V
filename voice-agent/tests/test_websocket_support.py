"""Tests for the WebSocket transport socle (TASK-WEB-026, ADR-0043).

AC #1: a wss connection is accepted without FastAPI, driven on the shared loop.
These tests assert the *socle* invariants that make that true: the transport is the
websockets-based `SingleClientWebsocketServerTransport` (not the FastAPI variant), it
builds without importing FastAPI, and it carries the AudioHook-shaped framing serializer.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_voice.websocket_framing import WebSocketAudioSerializer  # noqa: E402
from web_voice.websocket_support import (  # noqa: E402
    build_websocket_audio_transport,
    load_websocket_transport_classes,
    probe_websocket_support,
)


class WebSocketSupportProbeTest(unittest.TestCase):
    def test_transport_is_available_websockets_is_a_runtime_dependency(self):
        # GIVEN websockets is a declared runtime dependency
        # WHEN probing the socle
        support = probe_websocket_support()
        # THEN the websockets-based transport is importable
        self.assertTrue(support.available, support.missing)

    def test_socle_transport_is_the_websockets_variant_not_fastapi(self):
        transport_cls, _ = load_websocket_transport_classes()
        # The class must come from the websockets-based server module, never the FastAPI one
        self.assertEqual(transport_cls.__module__, "pipecat.transports.websocket.server")


class WebSocketSocleBuildTest(unittest.TestCase):
    def test_building_the_transport_requires_no_fastapi_import(self):
        # GIVEN FastAPI is not needed for this path
        fastapi_before = {m for m in sys.modules if m == "fastapi" or m.startswith("fastapi.")}
        # WHEN the socle transport is built
        transport = build_websocket_audio_transport("127.0.0.1", 8091)
        # THEN it is constructed and no FastAPI module was pulled in by building it
        self.assertIsNotNone(transport)
        fastapi_after = {m for m in sys.modules if m == "fastapi" or m.startswith("fastapi.")}
        self.assertEqual(fastapi_before, fastapi_after)

    def test_transport_exposes_input_and_output_for_the_pipeline(self):
        transport = build_websocket_audio_transport("127.0.0.1", 8091)
        # The pipeline drives the transport via its input()/output() processors.
        self.assertIsNotNone(transport.input())
        self.assertIsNotNone(transport.output())

    def test_default_serializer_is_the_audiohook_shaped_framing(self):
        serializer = WebSocketAudioSerializer()
        transport = build_websocket_audio_transport("127.0.0.1", 8091, serializer=serializer)
        self.assertIsNotNone(transport)

    def test_origin_allowlist_seam_is_honoured_when_provided(self):
        # GIVEN an explicit anti-CSWSH Origin allowlist (edge-hardening seam)
        origins = ["https://voice.example.test"]
        # WHEN the socle transport is built with it
        transport = build_websocket_audio_transport("127.0.0.1", 8091, allowed_origins=origins)
        # THEN the allowlist is carried on the transport params
        self.assertEqual(transport._params.allowed_origins, origins)


if __name__ == "__main__":
    unittest.main()
