"""Tests for the conversation backend selection factory (TASK-WEB-003-C)."""

import os
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from conversation_backend import HttpBackendAdapter, StubBackendAdapter, build_backend  # noqa: E402
from conversation_backend.backend_factory import (  # noqa: E402
    API_KEY_ENV_VAR,
    ENDPOINT_ENV_VAR,
    TIMEOUT_ENV_VAR,
)


class BuildBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {k: os.environ.get(k) for k in (ENDPOINT_ENV_VAR, API_KEY_ENV_VAR, TIMEOUT_ENV_VAR)}
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_stub_is_the_default(self) -> None:
        # GIVEN no name
        # WHEN a backend is built
        # THEN the deterministic stub is returned
        self.assertIsInstance(build_backend(), StubBackendAdapter)
        self.assertIsInstance(build_backend("stub"), StubBackendAdapter)

    def test_http_is_built_from_environment(self) -> None:
        # GIVEN the backend *server base* URL + key + timeout in the environment
        os.environ[ENDPOINT_ENV_VAR] = "https://backend.internal:8080"
        os.environ[API_KEY_ENV_VAR] = "sk-key"
        os.environ[TIMEOUT_ENV_VAR] = "3.5"
        # WHEN the http backend is built
        backend = build_backend("http")
        # THEN the adapter targets the converse endpoint appended to the server base
        self.assertIsInstance(backend, HttpBackendAdapter)
        self.assertEqual(backend._url, "https://backend.internal:8080/api/conversation/converse")
        self.assertEqual(backend._timeout_s, 3.5)

    def test_http_appends_converse_path_and_trims_trailing_slash(self) -> None:
        # GIVEN a server base URL with a trailing slash
        os.environ[ENDPOINT_ENV_VAR] = "http://192.168.0.11/"
        # WHEN the http backend is built
        backend = build_backend("http")
        # THEN the trailing slash is dropped before the converse path is appended
        self.assertEqual(backend._url, "http://192.168.0.11/api/conversation/converse")

    def test_http_keeps_a_full_converse_url_unchanged(self) -> None:
        # GIVEN a legacy full converse URL (backward compatibility)
        os.environ[ENDPOINT_ENV_VAR] = "http://192.168.0.11/api/conversation/converse"
        # WHEN the http backend is built
        backend = build_backend("http")
        # THEN it is kept as-is (idempotent), never doubled
        self.assertEqual(backend._url, "http://192.168.0.11/api/conversation/converse")

    def test_http_requires_the_endpoint_url(self) -> None:
        # GIVEN no endpoint URL in the environment
        # WHEN the http backend is built
        # THEN it fails fast with a clear error
        with self.assertRaises(ValueError):
            build_backend("http")

    def test_rejects_an_unknown_backend(self) -> None:
        # GIVEN an unknown backend name
        # WHEN a backend is built
        # THEN it fails fast
        with self.assertRaises(ValueError):
            build_backend("bogus")


if __name__ == "__main__":
    unittest.main()
