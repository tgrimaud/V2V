"""TASK-INFRA-012: Genesys AudioHook connection authentication (API key + HMAC signature).

Verifies the connection-auth verifier that gates the `GET /genesys/audiohook` endpoint
BEFORE a session is built. The canonicalization is locked against the OFFICIAL Genesys
golden vector (session-walkthrough / security docs) so a byte-drift breaks the test, then
the policy + telemetry + fail-closed posture + handler wiring are exercised with fakes.

GIVEN/WHEN/THEN throughout; manual fakes, no mocking library.
"""

import asyncio
import base64
import hashlib
import hmac
import os
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from multidict import CIMultiDict  # noqa: E402

from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice.envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL  # noqa: E402
from web_voice.genesys_app import make_genesys_handler  # noqa: E402
from web_voice.genesys_auth import (  # noqa: E402
    AUTH_EVENT,
    AUTH_OUTCOME_METRIC,
    OUTCOME_ACCEPTED,
    OUTCOME_BAD_SIGNATURE,
    OUTCOME_MISSING_KEY,
    OUTCOME_NOT_CONFIGURED,
    GenesysAuthConfig,
    GenesysConnectionAuthenticator,
    resolve_auth_config_from_env,
)
from web_voice.genesys_signature import (  # noqa: E402
    SignatureInput,
    build_signature_base,
    parse_signature_headers,
)

# Official Genesys AudioHook worked example (developer.genesys.cloud/devapps/audiohook/security).
GOLDEN_API_KEY = "SGVsbG8sIEkgYW0gdGhlIEFQSSBrZXkh"
GOLDEN_SECRET_B64 = "TXlTdXBlclNlY3JldEtleVRlbGxOby0xITJAMyM0JDU="
GOLDEN_SIGNATURE = "sig1=:NZBwyBHRRyRoeLqy1IzOa9VYBuI8TgMFt2GRDkDuJh4=:"
GOLDEN_TARGET = "/api/v1/voicebiometrics/ws"
# `created` carried by the golden Signature-Input. Freshness (Major B) age-bounds `created`,
# so the tests that must ACCEPT the golden vector run the clock near it (60s later, inside
# the default 300s window) — the signature base / recomputed digest is untouched.
GOLDEN_CREATED = 1641013200
GOLDEN_NOW = float(GOLDEN_CREATED + 60)
GOLDEN_INPUT = (
    'sig1=("@request-target" "@authority" "audiohook-organization-id" '
    '"audiohook-session-id" "audiohook-correlation-id" "x-api-key");'
    'keyid="SGVsbG8sIEkgYW0gdGhlIEFQSSBrZXkh";nonce="VGhpc0lzQVVuaXF1ZU5vbmNl";'
    'alg="hmac-sha256";created=1641013200;expires=3282026430'
)


class _FakeRequest:
    def __init__(self, headers: dict, raw_path: str = GOLDEN_TARGET, query: dict | None = None):
        self.headers = CIMultiDict(headers)
        self.raw_path = raw_path
        self.query = query or {}


def _golden_headers(**overrides) -> dict:
    headers = {
        "X-API-KEY": GOLDEN_API_KEY,
        "Audiohook-Organization-Id": "d7934305-0972-4844-938e-9060eef73d05",
        "Audiohook-Session-Id": "30b0e395-84d3-4570-ac13-9a62d8f514c0",
        "Audiohook-Correlation-Id": "e160e428-53e2-487c-977d-96989bf5c99d",
        "Host": "audiohook.example.com",
        "Signature-Input": GOLDEN_INPUT,
        "Signature": GOLDEN_SIGNATURE,
    }
    headers.update(overrides)
    return headers


def _golden_config() -> GenesysAuthConfig:
    return GenesysAuthConfig(api_key=GOLDEN_API_KEY, secret=base64.b64decode(GOLDEN_SECRET_B64))


def _authenticator(config: GenesysAuthConfig, recorder: TelemetryRecorder | None = None,
                   now: float = GOLDEN_NOW) -> GenesysConnectionAuthenticator:
    shared = recorder or TelemetryRecorder()
    return GenesysConnectionAuthenticator(config, telemetry_factory=lambda: shared, now=lambda: now)


# --- Freshness / replay signing helper (Major B) --------------------------------------
# Signs a request over a fixed component set with a configurable created/expires/nonce so
# the freshness + nonce policy can be exercised with real, valid HMAC signatures. Uses an
# authority_override so `@authority` resolves deterministically without a Host header.
_FRESH_COMPONENTS = [
    "@request-target", "@authority", "audiohook-organization-id",
    "audiohook-session-id", "x-api-key",
]


def _signing_config() -> GenesysAuthConfig:
    return GenesysAuthConfig(
        api_key=GOLDEN_API_KEY,
        secret=base64.b64decode(GOLDEN_SECRET_B64),
        authority_override="test-authority",
    )


def _signed_request(config: GenesysAuthConfig, *, created=None, expires=9999999999,
                    nonce=None, raw_path: str = "/genesys/audiohook") -> "_FakeRequest":
    params = f'keyid="{config.api_key}";alg="hmac-sha256"'
    if created is not None:
        params += f";created={int(created)}"
    if expires is not None:
        params += f";expires={int(expires)}"
    if nonce is not None:
        params += f';nonce="{nonce}"'
    raw_params = "(" + " ".join(f'"{c}"' for c in _FRESH_COMPONENTS) + ");" + params
    headers = {
        "X-API-KEY": config.api_key,
        "Audiohook-Organization-Id": "org-1",
        "Audiohook-Session-Id": "sess-1",
    }
    sig_input = SignatureInput("sig1", _FRESH_COMPONENTS, raw_params, {}, b"")
    base = build_signature_base(_FakeRequest(headers, raw_path=raw_path), sig_input,
                                config.authority_override)
    digest = hmac.new(config.secret, base.encode(), hashlib.sha256).digest()
    headers["Signature-Input"] = f"sig1={raw_params}"
    headers["Signature"] = f"sig1=:{base64.b64encode(digest).decode()}:"
    return _FakeRequest(headers, raw_path=raw_path)


class GenesysGoldenVectorTest(unittest.TestCase):
    def test_official_genesys_example_is_accepted(self) -> None:
        # GIVEN the official Genesys worked example (api key + HMAC signature + secret)
        auth = _authenticator(_golden_config())
        # WHEN the connection auth is verified
        result = auth.authenticate(_FakeRequest(_golden_headers()))
        # THEN it is accepted (our canonicalization matches Genesys byte for byte)
        self.assertTrue(result.ok)
        self.assertEqual(result.outcome, OUTCOME_ACCEPTED)

    def test_canonical_base_matches_the_published_signature(self) -> None:
        # GIVEN the golden request THEN rebuilding the base + HMAC reproduces the doc signature
        request = _FakeRequest(_golden_headers())
        parsed = parse_signature_headers(request.headers)
        base = build_signature_base(request, parsed, None)
        digest = hmac.new(base64.b64decode(GOLDEN_SECRET_B64), base.encode(), hashlib.sha256).digest()
        self.assertEqual(base64.b64encode(digest).decode(), "NZBwyBHRRyRoeLqy1IzOa9VYBuI8TgMFt2GRDkDuJh4=")

    def test_tampered_signature_byte_is_rejected(self) -> None:
        # GIVEN the golden request with one flipped signature byte (constant-time compare path)
        tampered = "sig1=:XZBwyBHRRyRoeLqy1IzOa9VYBuI8TgMFt2GRDkDuJh4=:"
        auth = _authenticator(_golden_config())
        # WHEN verified THEN it is a bad-signature rejection, not accepted
        result = auth.authenticate(_FakeRequest(_golden_headers(Signature=tampered)))
        self.assertFalse(result.ok)
        self.assertEqual(result.outcome, OUTCOME_BAD_SIGNATURE)

    def test_tampered_covered_component_is_rejected(self) -> None:
        # GIVEN a request whose signed org-id header was altered after signing
        auth = _authenticator(_golden_config())
        headers = _golden_headers(**{"Audiohook-Organization-Id": "00000000-0000-0000-0000-000000000000"})
        # WHEN verified THEN the rebuilt base no longer matches -> bad signature
        result = auth.authenticate(_FakeRequest(headers))
        self.assertEqual(result.outcome, OUTCOME_BAD_SIGNATURE)


class GenesysAuthPolicyTest(unittest.TestCase):
    def test_unconfigured_config_fails_closed(self) -> None:
        # GIVEN an enabled endpoint with NO api key + secret configured
        auth = _authenticator(GenesysAuthConfig())
        # WHEN any connection arrives THEN it is refused as not-configured (fail closed, 503)
        result = auth.authenticate(_FakeRequest(_golden_headers()))
        self.assertEqual(result.outcome, OUTCOME_NOT_CONFIGURED)
        self.assertFalse(result.ok)
        self.assertEqual(result.http_status, 503)

    def test_missing_api_key_is_rejected(self) -> None:
        # GIVEN a configured verifier and a request with no X-API-KEY header
        headers = _golden_headers()
        headers.pop("X-API-KEY")
        auth = _authenticator(_golden_config())
        # WHEN verified THEN it is rejected as missing key (401), before touching the signature
        result = auth.authenticate(_FakeRequest(headers))
        self.assertEqual(result.outcome, OUTCOME_MISSING_KEY)
        self.assertEqual(result.http_status, 401)

    def test_wrong_api_key_is_rejected_as_missing_key(self) -> None:
        auth = _authenticator(_golden_config())
        result = auth.authenticate(_FakeRequest(_golden_headers(**{"X-API-KEY": "not-the-key"})))
        self.assertEqual(result.outcome, OUTCOME_MISSING_KEY)

    def test_missing_signature_headers_is_rejected(self) -> None:
        # GIVEN a valid api key but no Signature / Signature-Input headers
        headers = _golden_headers()
        headers.pop("Signature")
        headers.pop("Signature-Input")
        auth = _authenticator(_golden_config())
        # WHEN verified THEN it is a bad-signature rejection
        self.assertEqual(auth.authenticate(_FakeRequest(headers)).outcome, OUTCOME_BAD_SIGNATURE)

    def test_expired_signature_is_rejected(self) -> None:
        # GIVEN a clock well past the signature's `expires` + skew slop
        auth = _authenticator(_golden_config(), now=4_000_000_000.0)
        # WHEN verified THEN the (otherwise valid) signature is rejected as expired
        self.assertEqual(auth.authenticate(_FakeRequest(_golden_headers())).outcome, OUTCOME_BAD_SIGNATURE)

    def test_non_ascii_api_key_degrades_to_a_clean_rejection_not_500(self) -> None:
        # GIVEN a request whose X-API-KEY is non-ASCII (str compare_digest would raise, Minor 2)
        auth = _authenticator(_golden_config())
        # WHEN verified THEN it is a clean missing-key rejection (401), never an unhandled 500
        result = auth.authenticate(_FakeRequest(_golden_headers(**{"X-API-KEY": "clé-secrète"})))
        self.assertEqual(result.outcome, OUTCOME_MISSING_KEY)
        self.assertEqual(result.http_status, 401)


class GenesysAuthTelemetryTest(unittest.TestCase):
    def _secrets_absent(self, recorder: TelemetryRecorder) -> None:
        forbidden = (GOLDEN_SECRET_B64, GOLDEN_API_KEY, "NZBwyBHRRyRoeLqy1IzOa9VYBuI8TgMFt2GRDkDuJh4=")
        blobs = [str(e.attributes) for e in recorder.events()] + [str(m.attributes) for m in recorder.metrics()]
        for blob in blobs:
            for secret in forbidden:
                self.assertNotIn(secret, blob)

    def test_accepted_emits_outcome_event_and_metric_without_secret_leak(self) -> None:
        # GIVEN a shared recorder and the golden accepted connection
        shared = TelemetryRecorder()
        logged: list[TelemetryRecorder] = []
        auth = GenesysConnectionAuthenticator(
            _golden_config(), telemetry_factory=lambda: shared, log=logged.append, now=lambda: GOLDEN_NOW
        )
        # WHEN it authenticates
        auth.authenticate(_FakeRequest(_golden_headers(), query={"conversationId": "conv-1"}))
        # THEN a bounded auth-outcome event + metric fire on the Genesys channel, secrets absent
        event = next(e for e in shared.events() if e.name == AUTH_EVENT)
        self.assertEqual(event.attributes["outcome"], OUTCOME_ACCEPTED)
        self.assertEqual(event.attributes["channel"], GENESYS_AUDIO_CONNECTOR_CHANNEL)
        self.assertEqual(event.attributes["auth_scope"], "conversation")
        metric = next(m for m in shared.metrics() if m.name == AUTH_OUTCOME_METRIC)
        self.assertEqual((metric.value, metric.attributes["outcome"]), (1.0, OUTCOME_ACCEPTED))
        # Major C: the metric label set is EXACTLY the bounded pair {channel, outcome} —
        # correlation_id (per-connection, unbounded) must NOT appear as a metric attribute.
        self.assertEqual(set(metric.attributes.keys()), {"channel", "outcome"})
        self.assertEqual(logged, [shared])
        self._secrets_absent(shared)

    def test_rejection_emits_bounded_outcome_and_no_secret_leak(self) -> None:
        # GIVEN a tampered signature THEN telemetry records rejected_bad_signature, no leak
        shared = TelemetryRecorder()
        auth = _authenticator(_golden_config(), recorder=shared)
        auth.authenticate(_FakeRequest(_golden_headers(Signature="sig1=:AAAA:")))
        metric = next(m for m in shared.metrics() if m.name == AUTH_OUTCOME_METRIC)
        self.assertEqual(metric.attributes["outcome"], OUTCOME_BAD_SIGNATURE)
        self._secrets_absent(shared)

    def test_connection_scope_uses_session_id_when_no_conversation_id(self) -> None:
        # GIVEN no conversationId query (pre-session auth) but a Genesys session id header
        shared = TelemetryRecorder()
        auth = _authenticator(GenesysAuthConfig(), recorder=shared)
        auth.authenticate(_FakeRequest(_golden_headers()))
        event = next(e for e in shared.events() if e.name == AUTH_EVENT)
        # THEN the event is connection-scoped and correlated on the session id
        self.assertEqual(event.attributes["auth_scope"], "connection")
        self.assertEqual(event.attributes["correlation_id"], "30b0e395-84d3-4570-ac13-9a62d8f514c0")


class GenesysAuthExporterFlushTest(unittest.TestCase):
    """Major A: the per-attempt telemetry must be FLUSHED through the exporter in prod, not
    merely recorded into a recorder the default no-op then drops."""

    @staticmethod
    def _outcomes(recorder: TelemetryRecorder) -> tuple[str, str]:
        event = next(e for e in recorder.events() if e.name == AUTH_EVENT)
        metric = next(m for m in recorder.metrics() if m.name == AUTH_OUTCOME_METRIC)
        return event.attributes["outcome"], metric.attributes["outcome"]

    def test_exporter_receives_outcome_event_and_metric_on_accept_and_reject(self) -> None:
        # GIVEN an authenticator whose flush hook is a capturing exporter (prod wires the
        # real stderr + OTLP export; the field default is a no-op that would discard it)
        exported: list[TelemetryRecorder] = []
        auth = GenesysConnectionAuthenticator(
            _golden_config(), log=exported.append, now=lambda: GOLDEN_NOW
        )
        # WHEN one accepted then one rejected connection authenticate
        auth.authenticate(_FakeRequest(_golden_headers()))
        auth.authenticate(_FakeRequest(_golden_headers(Signature="sig1=:AAAA:")))
        # THEN the exporter RECEIVED an auth-outcome event + metric for each (not just recorded)
        self.assertEqual(len(exported), 2)
        self.assertEqual(
            [self._outcomes(rec) for rec in exported],
            [(OUTCOME_ACCEPTED, OUTCOME_ACCEPTED), (OUTCOME_BAD_SIGNATURE, OUTCOME_BAD_SIGNATURE)],
        )


class GenesysFreshnessReplayTest(unittest.TestCase):
    """Major B: `expires` mandatory, `created` age-bounded, `nonce` replay-protected."""

    def _auth(self) -> GenesysConnectionAuthenticator:
        return _authenticator(_signing_config())  # default clock is GOLDEN_NOW

    def test_signature_without_expires_is_rejected(self) -> None:
        # GIVEN a validly signed request that carries NO `expires` param
        request = _signed_request(_signing_config(), created=GOLDEN_CREATED, expires=None)
        # WHEN verified THEN it is rejected (expires mandatory) via the bad-signature outcome
        self.assertEqual(self._auth().authenticate(request).outcome, OUTCOME_BAD_SIGNATURE)

    def test_stale_created_beyond_max_age_is_rejected(self) -> None:
        # GIVEN a signed request whose `created` is an hour older than the clock (>300s)
        request = _signed_request(_signing_config(), created=GOLDEN_NOW - 3600)
        # WHEN verified THEN the stale signature is rejected
        self.assertEqual(self._auth().authenticate(request).outcome, OUTCOME_BAD_SIGNATURE)

    def test_future_created_beyond_skew_is_rejected(self) -> None:
        # GIVEN a signed request whose `created` is an hour in the future
        request = _signed_request(_signing_config(), created=GOLDEN_NOW + 3600)
        # WHEN verified THEN it is rejected (future beyond the allowed skew)
        self.assertEqual(self._auth().authenticate(request).outcome, OUTCOME_BAD_SIGNATURE)

    def test_fresh_unique_nonce_is_accepted(self) -> None:
        # GIVEN a fresh, validly signed request carrying an unseen nonce
        request = _signed_request(_signing_config(), created=GOLDEN_CREATED, nonce="unique-1")
        # WHEN verified THEN it is accepted
        self.assertEqual(self._auth().authenticate(request).outcome, OUTCOME_ACCEPTED)

    def test_created_absent_with_expires_present_is_accepted(self) -> None:
        # GIVEN a signed request with `expires` present but NO `created` (created optional)
        request = _signed_request(_signing_config(), created=None, expires=9999999999)
        # WHEN verified THEN it is accepted (matches the far-expires golden posture)
        self.assertEqual(self._auth().authenticate(request).outcome, OUTCOME_ACCEPTED)

    def test_replayed_nonce_is_rejected_on_second_use(self) -> None:
        # GIVEN one authenticator and a signed request carrying a nonce
        auth = self._auth()
        request = _signed_request(_signing_config(), created=GOLDEN_CREATED, nonce="replay-me")
        # WHEN the identical nonce is presented twice
        first = auth.authenticate(request)
        second = auth.authenticate(request)
        # THEN the first is accepted and the replay is rejected as a bad signature
        self.assertEqual(first.outcome, OUTCOME_ACCEPTED)
        self.assertEqual(second.outcome, OUTCOME_BAD_SIGNATURE)


class GenesysAuthConfigEnvTest(unittest.TestCase):
    _KEYS = (
        "GENESYS_AUDIOHOOK_API_KEY",
        "GENESYS_AUDIOHOOK_SECRET",
        "GENESYS_AUDIOHOOK_API_KEY_HEADER",
        "GENESYS_AUDIOHOOK_MAX_SIGNATURE_AGE_S",
        "GENESYS_AUDIOHOOK_NONCE_CACHE_SIZE",
        "GENESYS_AUDIOHOOK_AUTHORITY",
    )

    def setUp(self) -> None:
        self._saved = {key: os.environ.get(key) for key in self._KEYS}
        for key in self._KEYS:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_unset_env_yields_unconfigured_fail_closed(self) -> None:
        self.assertFalse(resolve_auth_config_from_env().configured)

    def test_set_env_decodes_secret_and_is_configured(self) -> None:
        os.environ["GENESYS_AUDIOHOOK_API_KEY"] = GOLDEN_API_KEY
        os.environ["GENESYS_AUDIOHOOK_SECRET"] = GOLDEN_SECRET_B64
        config = resolve_auth_config_from_env()
        self.assertTrue(config.configured)
        self.assertEqual(config.secret, base64.b64decode(GOLDEN_SECRET_B64))
        self.assertEqual(config.api_key, GOLDEN_API_KEY)


async def _wait_for(predicate, *, timeout: float = 10.0) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("timed out waiting for condition")
        await asyncio.sleep(0.02)


class _FakeSession:
    def __init__(self) -> None:
        self.ran = False
        self._release = asyncio.Event()

    async def run(self) -> None:
        self.ran = True
        await self._release.wait()

    async def drain(self) -> None:
        self._release.set()

    async def stop(self) -> None:
        self._release.set()

    def release(self) -> None:
        self._release.set()


class _FakeFactory:
    def __init__(self) -> None:
        self.sessions: list[_FakeSession] = []

    def build_session(self, transport, envelope, telemetry):
        session = _FakeSession()
        self.sessions.append(session)
        return session, None


_HANDLER_COMPONENTS = [
    "@request-target",
    "@authority",
    "audiohook-organization-id",
    "audiohook-session-id",
    "x-api-key",
]
# created anchored to GOLDEN_CREATED so it is fresh under the handler tests' GOLDEN_NOW clock
# (Major B age bound); no nonce here, so the replay cache does not apply on this path.
_HANDLER_PARAMS = f'keyid="{GOLDEN_API_KEY}";alg="hmac-sha256";created={GOLDEN_CREATED};expires=9999999999'


def _sign_headers(config: GenesysAuthConfig, base_headers: dict, raw_path: str) -> dict:
    raw_params = "(" + " ".join(f'"{c}"' for c in _HANDLER_COMPONENTS) + ");" + _HANDLER_PARAMS
    sig_input = SignatureInput("sig1", _HANDLER_COMPONENTS, raw_params, {}, b"")
    base = build_signature_base(_FakeRequest(base_headers, raw_path=raw_path), sig_input,
                               config.authority_override)
    digest = hmac.new(config.secret, base.encode(), hashlib.sha256).digest()
    signed = dict(base_headers)
    signed["Signature-Input"] = f"sig1={raw_params}"
    signed["Signature"] = f"sig1=:{base64.b64encode(digest).decode()}:"
    return signed


class GenesysAuthHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def _serve(self, handler) -> TestClient:
        app = web.Application()
        app.router.add_get("/genesys/audiohook", handler)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    async def test_bad_auth_returns_401_and_never_builds_a_session(self) -> None:
        # GIVEN a configured, auth-guarded handler
        factory = _FakeFactory()
        handler = make_genesys_handler(
            factory, authenticator=_authenticator(_golden_config()), log=lambda _r: None
        )
        client = await self._serve(handler)
        # WHEN a request arrives with the wrong API key (no valid signature)
        response = await client.get("/genesys/audiohook", headers={"X-API-KEY": "nope"})
        # THEN it is refused with 401 before the WS upgrade and no session is built
        self.assertEqual(response.status, 401)
        self.assertEqual(len(factory.sessions), 0)

    async def test_unconfigured_endpoint_fails_closed_with_503(self) -> None:
        # GIVEN the endpoint is enabled but auth is unconfigured (fail-closed)
        factory = _FakeFactory()
        handler = make_genesys_handler(
            factory, authenticator=_authenticator(GenesysAuthConfig()), log=lambda _r: None
        )
        client = await self._serve(handler)
        # WHEN any connection arrives THEN it is refused 503 and builds nothing
        response = await client.get("/genesys/audiohook")
        self.assertEqual(response.status, 503)
        self.assertEqual(len(factory.sessions), 0)

    async def test_valid_signature_upgrades_and_builds_a_session(self) -> None:
        # GIVEN a configured handler and a correctly signed AudioHook handshake
        config = GenesysAuthConfig(
            api_key=GOLDEN_API_KEY,
            secret=base64.b64decode(GOLDEN_SECRET_B64),
            authority_override="test-authority",
        )
        factory = _FakeFactory()
        handler = make_genesys_handler(
            factory, authenticator=_authenticator(config), log=lambda _r: None
        )
        client = await self._serve(handler)
        headers = _sign_headers(config, {
            "X-API-KEY": GOLDEN_API_KEY,
            "Audiohook-Organization-Id": "d7934305-0972-4844-938e-9060eef73d05",
            "Audiohook-Session-Id": "30b0e395-84d3-4570-ac13-9a62d8f514c0",
        }, "/genesys/audiohook")
        # WHEN the signed connection opens THEN it upgrades and the session is built
        websocket = await client.ws_connect("/genesys/audiohook", headers=headers)
        await _wait_for(lambda: bool(factory.sessions) and factory.sessions[0].ran)
        self.assertEqual(len(factory.sessions), 1)
        factory.sessions[0].release()
        await websocket.close()


if __name__ == "__main__":
    unittest.main()
