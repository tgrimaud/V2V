"""Tests for the headless Genesys AudioHook client (TASK-WEB-047).

The point of the client is to test the `/genesys/audiohook` endpoint WITHOUT a live
Genesys org, so its two load-bearing properties must be locked:

1. the connection-auth handshake it builds is accepted by the REAL
   `GenesysConnectionAuthenticator` — byte-for-byte, or it drifts and stops testing the
   real endpoint (a wrong secret / expired signature must be refused);
2. driving the REAL `make_genesys_handler` over an in-process socket, a client-signed
   handshake opens a session while a tampered one is refused BEFORE the WS upgrade.

The codec + signature scheme are the production ones (`web_voice/genesys_codec.py`,
`web_voice/genesys_signature.py`), so this is a faithful stand-in for Genesys.
"""

import os
import sys
import time
import unittest
import uuid
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))
sys.path.insert(0, str(VOICE_AGENT_ROOT / "scripts"))

import aiohttp  # noqa: E402
from aiohttp.test_utils import make_mocked_request  # noqa: E402

from types import SimpleNamespace  # noqa: E402

from genesys_local_client import (  # noqa: E402
    _connect_targets,
    _resolve_credentials,
    build_signed_headers,
    decode_secret,
    frame_rms,
    synthetic_pcm16_16k,
)
from web_voice import genesys_codec  # noqa: E402
from web_voice.genesys_auth import (  # noqa: E402
    OUTCOME_BAD_SIGNATURE,
    GenesysAuthConfig,
    GenesysConnectionAuthenticator,
)

# Import the real-handler test plumbing (fake factory + blocking session + serve mixin)
# so the e2e exercises the SAME handler path the tests already trust for the lifecycle.
from tests.test_genesys_app import (  # noqa: E402
    GenesysHandlerServeMixin,
    _FakeFactory,
    _wait_for,
)
from web_voice.genesys_app import make_genesys_handler  # noqa: E402

_KEY = "local-dev-key"
_SECRET_B64 = "c2VjcmV0LXNoYXJlZC1rZXktZm9yLXRoZS1sb2NhbC10ZXN0cw=="
_SECRET = decode_secret(_SECRET_B64)
_AUTHORITY = "genesys-local-test"


def _headers(path: str, *, correlation_id: str, secret: bytes = _SECRET, expires_delta: int = 300):
    now = int(time.time())
    return build_signed_headers(
        request_target=path,
        authority=_AUTHORITY,
        api_key=_KEY,
        secret=secret,
        org_id="org-1",
        session_id=f"sess-{uuid.uuid4().hex[:6]}",
        correlation_id=correlation_id,
        created=now,
        expires=now + expires_delta,
        nonce=uuid.uuid4().hex,
        key_id="pilot",
    )


def _authenticator(secret: bytes = _SECRET) -> GenesysConnectionAuthenticator:
    return GenesysConnectionAuthenticator(
        GenesysAuthConfig(api_key=_KEY, secret=secret, authority_override=_AUTHORITY)
    )


class BuildSignedHeadersTest(unittest.TestCase):
    def test_signed_handshake_is_accepted_by_the_real_authenticator(self) -> None:
        # GIVEN the client-built signed headers for a request
        path = "/genesys/audiohook?conversationId=conv-1"
        headers = _headers(path, correlation_id="conv-1")
        request = make_mocked_request("GET", path, headers=headers)
        # WHEN the real connection-auth policy verifies them (same key + secret)
        result = _authenticator().authenticate(request)
        # THEN the connection is accepted (byte-for-byte signature match, fresh, non-replayed)
        self.assertTrue(result.ok)

    def test_wrong_secret_is_rejected_as_bad_signature(self) -> None:
        # GIVEN headers the client signed with the shared secret
        path = "/genesys/audiohook?conversationId=conv-2"
        headers = _headers(path, correlation_id="conv-2")
        request = make_mocked_request("GET", path, headers=headers)
        # WHEN the authenticator is configured with a DIFFERENT secret
        other = _authenticator(secret=decode_secret("b3RoZXItc2VjcmV0LXZhbHVlLW5vdC1tYXRjaGluZw=="))
        # THEN the signature does not match and the connection is refused
        result = other.authenticate(request)
        self.assertFalse(result.ok)
        self.assertEqual(result.outcome, OUTCOME_BAD_SIGNATURE)

    def test_expired_signature_is_rejected(self) -> None:
        # GIVEN a signature whose expires is already in the past
        path = "/genesys/audiohook?conversationId=conv-3"
        headers = _headers(path, correlation_id="conv-3", expires_delta=-3600)
        request = make_mocked_request("GET", path, headers=headers)
        # WHEN verified THEN it fails freshness (rejected as a bad signature)
        result = _authenticator().authenticate(request)
        self.assertFalse(result.ok)
        self.assertEqual(result.outcome, OUTCOME_BAD_SIGNATURE)


class CodecAndAudioHelpersTest(unittest.TestCase):
    def test_synthetic_audio_is_low_amplitude_and_deterministic(self) -> None:
        # GIVEN deterministic synthetic non-PII audio (DEC-014)
        first = synthetic_pcm16_16k(200, seed=7)
        second = synthetic_pcm16_16k(200, seed=7)
        # THEN it is reproducible and well below the STT onset / audible threshold
        self.assertEqual(first, second)
        self.assertLess(frame_rms(first), 200.0)

    def test_wire_codec_round_trip_preserves_length_ratio(self) -> None:
        # GIVEN one 20 ms internal frame (640 bytes PCM16/16k)
        frame = synthetic_pcm16_16k(20, seed=1)
        for codec in genesys_codec.SUPPORTED_CODECS:
            # WHEN encoded to the wire codec and decoded back
            wire = genesys_codec.from_internal_pcm16(frame, codec)
            restored = genesys_codec.to_internal_pcm16(wire, codec)
            # THEN it returns to the internal 16 kHz length (8k wire is half-rate)
            self.assertEqual(len(wire), 160 if codec == "PCMU" else 320)
            self.assertEqual(len(restored), len(frame))


class CredentialAndTargetResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {k: os.environ.pop(k, None) for k in ("GENESYS_AUDIOHOOK_API_KEY", "GENESYS_AUDIOHOOK_SECRET")}

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_credentials_prefer_env_so_the_secret_stays_off_argv(self) -> None:
        # GIVEN the server's own env vars set (no --api-key/--secret on the command line)
        os.environ["GENESYS_AUDIOHOOK_API_KEY"] = _KEY
        os.environ["GENESYS_AUDIOHOOK_SECRET"] = _SECRET_B64
        api_key, secret = _resolve_credentials(SimpleNamespace(api_key=None, secret=None))
        # THEN they are resolved from the env (argv would leak via `ps`)
        self.assertEqual(api_key, _KEY)
        self.assertEqual(secret, _SECRET)

    def test_missing_credentials_exit_cleanly(self) -> None:
        # GIVEN neither env nor flags THEN a clear SystemExit, not a traceback
        with self.assertRaises(SystemExit):
            _resolve_credentials(SimpleNamespace(api_key=None, secret=None))

    def test_connect_targets_owns_the_query_so_request_target_matches_raw_path(self) -> None:
        # GIVEN a --url carrying a stray query and a conversation id
        args = SimpleNamespace(
            url="ws://host:8090/genesys/audiohook?ignored=1",
            conversation_id="conv-x",
            request_target=None,
            authority=None,
        )
        full_url, request_target, authority = _connect_targets(args)
        # THEN the client owns the query (conversationId) and the signed target == the path it dials
        self.assertEqual(full_url, "ws://host:8090/genesys/audiohook?conversationId=conv-x")
        self.assertEqual(request_target, "/genesys/audiohook?conversationId=conv-x")
        self.assertEqual(authority, "host:8090")


class GenesysLocalClientE2ETest(GenesysHandlerServeMixin):
    async def test_client_signed_handshake_opens_a_session_over_a_real_socket(self) -> None:
        # GIVEN the REAL handler guarded by the REAL authenticator (configured key + secret)
        factory = _FakeFactory()
        handler = make_genesys_handler(factory, authenticator=_authenticator(), log=lambda _r: None)
        client = await self._serve(handler)
        path = "/genesys/audiohook?conversationId=conv-e2e"
        # WHEN the client connects with its signed handshake headers
        websocket = await client.ws_connect(path, headers=_headers(path, correlation_id="conv-e2e"))
        await _wait_for(lambda: bool(factory.sessions) and factory.sessions[0].ran)
        # THEN the auth passes and a session is built (no live Genesys needed)
        self.assertEqual(len(factory.sessions), 1)
        factory.sessions[0].release()
        await websocket.close()

    async def test_tampered_signature_is_refused_before_the_ws_upgrade(self) -> None:
        # GIVEN the handler guarded by an authenticator with a DIFFERENT secret
        factory = _FakeFactory()
        other = _authenticator(secret=decode_secret("ZGlmZmVyZW50LXNlY3JldC1mb3ItdGhlLWhhbmRsZXI="))
        handler = make_genesys_handler(factory, authenticator=other, log=lambda _r: None)
        client = await self._serve(handler)
        path = "/genesys/audiohook?conversationId=conv-bad"
        # WHEN the client presents headers signed with the ORIGINAL secret
        # THEN the WS upgrade is refused (401) and no session is ever built
        with self.assertRaises(aiohttp.WSServerHandshakeError):
            await client.ws_connect(path, headers=_headers(path, correlation_id="conv-bad"))
        self.assertEqual(len(factory.sessions), 0)


if __name__ == "__main__":
    unittest.main()
