"""Behave steps for the Genesys AudioHook connection authentication (TASK-INFRA-012).

Drives the `GenesysConnectionAuthenticator` directly with fake requests built from the
OFFICIAL Genesys worked example, covering the accepted / bad-signature / missing-key /
fail-closed paths and the no-secret-leak telemetry contract.
"""

import base64

from behave import given, then, when
from multidict import CIMultiDict

from voice_common.telemetry import TelemetryRecorder
from web_voice.envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL
from web_voice.genesys_auth import (
    AUTH_EVENT,
    AUTH_OUTCOME_METRIC,
    GenesysAuthConfig,
    GenesysConnectionAuthenticator,
)

_API_KEY = "SGVsbG8sIEkgYW0gdGhlIEFQSSBrZXkh"
_SECRET_B64 = "TXlTdXBlclNlY3JldEtleVRlbGxOby0xITJAMyM0JDU="
_SIGNATURE = "sig1=:NZBwyBHRRyRoeLqy1IzOa9VYBuI8TgMFt2GRDkDuJh4=:"
_TARGET = "/api/v1/voicebiometrics/ws"
_INPUT = (
    'sig1=("@request-target" "@authority" "audiohook-organization-id" '
    '"audiohook-session-id" "audiohook-correlation-id" "x-api-key");'
    'keyid="SGVsbG8sIEkgYW0gdGhlIEFQSSBrZXkh";nonce="VGhpc0lzQVVuaXF1ZU5vbmNl";'
    'alg="hmac-sha256";created=1641013200;expires=3282026430'
)


class _FakeRequest:
    def __init__(self, headers: dict, raw_path: str = _TARGET):
        self.headers = CIMultiDict(headers)
        self.raw_path = raw_path
        self.query: dict = {}


def _golden_headers(**overrides) -> dict:
    headers = {
        "X-API-KEY": _API_KEY,
        "Audiohook-Organization-Id": "d7934305-0972-4844-938e-9060eef73d05",
        "Audiohook-Session-Id": "30b0e395-84d3-4570-ac13-9a62d8f514c0",
        "Audiohook-Correlation-Id": "e160e428-53e2-487c-977d-96989bf5c99d",
        "Host": "audiohook.example.com",
        "Signature-Input": _INPUT,
        "Signature": _SIGNATURE,
    }
    headers.update(overrides)
    return headers


# Freshness (Major B) age-bounds the golden `created=1641013200`, so the accepted/telemetry
# scenarios run the clock 60s after it (inside the 300s window); canonicalization is unchanged.
_GOLDEN_NOW = 1641013200.0 + 60


def _authenticator(context, config: GenesysAuthConfig) -> GenesysConnectionAuthenticator:
    context.recorder = TelemetryRecorder()
    return GenesysConnectionAuthenticator(
        config, telemetry_factory=lambda: context.recorder, now=lambda: _GOLDEN_NOW
    )


@given("a configured Genesys AudioHook authenticator")
def step_configured_authenticator(context):
    config = GenesysAuthConfig(api_key=_API_KEY, secret=base64.b64decode(_SECRET_B64))
    context.authenticator = _authenticator(context, config)


@given("a Genesys AudioHook authenticator with no key or secret configured")
def step_unconfigured_authenticator(context):
    context.authenticator = _authenticator(context, GenesysAuthConfig())


@when("the official Genesys signed connection is verified")
def step_verify_golden(context):
    context.result = context.authenticator.authenticate(_FakeRequest(_golden_headers()))


@when("a connection with a tampered signature is verified")
def step_verify_tampered(context):
    tampered = "sig1=:XZBwyBHRRyRoeLqy1IzOa9VYBuI8TgMFt2GRDkDuJh4=:"
    context.result = context.authenticator.authenticate(
        _FakeRequest(_golden_headers(Signature=tampered))
    )


@when("a connection with no API key is verified")
def step_verify_no_key(context):
    headers = _golden_headers()
    headers.pop("X-API-KEY")
    context.result = context.authenticator.authenticate(_FakeRequest(headers))


@then('the connection auth outcome is "{outcome}"')
def step_assert_outcome(context, outcome):
    assert context.result.outcome == outcome, f"expected {outcome}, got {context.result.outcome}"


@then("an auth-outcome event and metric are recorded on the Genesys channel")
def step_assert_telemetry_recorded(context):
    event = next(e for e in context.recorder.events() if e.name == AUTH_EVENT)
    assert event.attributes["channel"] == GENESYS_AUDIO_CONNECTOR_CHANNEL
    metric = next(m for m in context.recorder.metrics() if m.name == AUTH_OUTCOME_METRIC)
    assert metric.attributes["channel"] == GENESYS_AUDIO_CONNECTOR_CHANNEL
    assert metric.value == 1.0


@then("no secret, API key, or signature appears in the telemetry")
def step_assert_no_leak(context):
    forbidden = (_SECRET_B64, _API_KEY, "NZBwyBHRRyRoeLqy1IzOa9VYBuI8TgMFt2GRDkDuJh4=")
    blobs = [str(e.attributes) for e in context.recorder.events()]
    blobs += [str(m.attributes) for m in context.recorder.metrics()]
    for blob in blobs:
        for secret in forbidden:
            assert secret not in blob, f"secret material leaked into telemetry: {secret}"
