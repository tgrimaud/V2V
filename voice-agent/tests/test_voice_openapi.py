"""Tests for the hand-written voice-runtime OpenAPI spec (TASK-WEB-016).

Covers: the committed spec is a structurally valid OpenAPI document; it does not
drift from the server's actual routes; and the server serves it at
`GET /api/voice/openapi.yaml`.
"""

import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_voice.server import (  # noqa: E402
    OPENAPI_PATH,
    OPENAPI_ROUTE,
    STT_ROUTE,
    TTS_ROUTE,
    TURN_ROUTE,
    WEBRTC_OFFER_ROUTE,
    WebVoiceHTTPServer,
    build_handler,
)


def _load_spec() -> dict:
    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


class VoiceOpenApiSpecTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = _load_spec()

    def test_spec_is_a_structurally_valid_openapi_3_document(self) -> None:
        # GIVEN the committed spec
        # THEN it declares OpenAPI 3, an info block and at least one server
        self.assertTrue(str(self.spec.get("openapi", "")).startswith("3."))
        self.assertIn("Voice Support Bot", self.spec["info"]["title"])
        self.assertTrue(self.spec["info"]["version"])
        self.assertTrue(self.spec.get("servers"))

    def test_spec_describes_the_error_and_payload_schemas(self) -> None:
        # GIVEN the spec components
        schemas = self.spec["components"]["schemas"]
        # THEN both error shapes and the key payloads are described
        for name in ("VoiceErrorBody", "GuardError", "SttSuccess", "WebRtcOffer", "WebRtcAnswer"):
            self.assertIn(name, schemas, f"missing schema {name}")
        # AND the client-safe error body carries the stable contract fields
        self.assertEqual(
            set(schemas["VoiceErrorBody"]["required"]),
            {"outcome", "error_code", "correlation_id", "message"},
        )

    def test_every_operation_documents_at_least_one_response(self) -> None:
        # GIVEN each documented operation
        for path, item in self.spec["paths"].items():
            for method, op in item.items():
                # THEN at least one response is described (the contract is never open-ended)
                self.assertTrue(op.get("responses"), f"{method.upper()} {path} has no responses")
                # AND a 200 success is always present
                self.assertIn("200", op["responses"], f"{method.upper()} {path} missing 200")

    def test_spec_does_not_drift_from_the_servers_actual_routes(self) -> None:
        # GIVEN the paths documented in the spec
        documented = set(self.spec["paths"].keys())
        # AND the routes the server actually exposes (the single source of truth in code)
        actual = {STT_ROUTE, TTS_ROUTE, TURN_ROUTE, WEBRTC_OFFER_ROUTE, OPENAPI_ROUTE}
        # THEN they match exactly — a new/removed route must update the spec (drift guard)
        self.assertEqual(documented, actual)


class VoiceOpenApiServeTest(unittest.TestCase):
    def _serve(self) -> int:
        server = WebVoiceHTTPServer(("127.0.0.1", 0), build_handler(processor=None))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def test_server_serves_the_spec_as_yaml(self) -> None:
        # GIVEN the running server
        port = self._serve()
        conn = HTTPConnection("127.0.0.1", port, timeout=10)
        # WHEN the spec route is fetched
        conn.request("GET", OPENAPI_ROUTE)
        response = conn.getresponse()
        payload = response.read()
        content_type = response.getheader("Content-Type")
        conn.close()
        # THEN it is served as YAML and parses back to the same OpenAPI document
        self.assertEqual(response.status, 200)
        self.assertIn("application/yaml", content_type)
        served = yaml.safe_load(payload.decode("utf-8"))
        self.assertEqual(served["info"]["title"], _load_spec()["info"]["title"])
        self.assertIn(STT_ROUTE, served["paths"])


if __name__ == "__main__":
    unittest.main()
