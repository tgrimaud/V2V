"""Tests for the HTTP conversation backend adapter (TASK-WEB-003-C).

A fake transport keeps the tests offline: they prove the adapter maps a real
endpoint response onto the conversation contract, degrades transport/timeout/HTTP
errors to a sanitized safe fallback, and never leaks the API key into any result,
error or telemetry attribute.
"""

import json
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from conversation_backend import (  # noqa: E402
    DEGRADED_FALLBACK_TEXT,
    AnswerOutcome,
    AnswerRequest,
    EmptyTranscriptError,
    HttpBackendAdapter,
    HttpResponse,
)
from conversation_backend.http_backend import HttpBackendError  # noqa: E402
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from voice_pipeline.answer import answer_with_telemetry  # noqa: E402

API_KEY = "sk-super-secret-123456"
ENDPOINT = "https://backend.internal/api/conversation/converse"


def _request(transcript: str = "pourquoi ma facture augmente") -> AnswerRequest:
    return AnswerRequest(
        transcript=transcript,
        correlation_id="corr-1",
        conversation_id="conv-1",
        channel="web_voice",
    )


class _CapturingTransport:
    """Records the call and returns a canned response (or raises a canned error)."""

    def __init__(self, response: HttpResponse | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    def __call__(self, url, headers, body, timeout) -> HttpResponse:
        self.calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        if self._error is not None:
            raise self._error
        return self._response


class HttpBackendMappingTest(unittest.TestCase):
    def test_maps_a_successful_response_to_the_contract(self) -> None:
        # GIVEN a transport returning a 200 answer with a confidence
        transport = _CapturingTransport(HttpResponse(200, json.dumps({"text": "voici la reponse", "confidence": 0.8})))
        adapter = HttpBackendAdapter(ENDPOINT, api_key=API_KEY, transport=transport)
        # WHEN a transcript is answered
        result = adapter.answer(_request())
        # THEN the response is mapped onto the conversation contract
        self.assertIs(result.outcome, AnswerOutcome.SUCCESS)
        self.assertEqual(result.text, "voici la reponse")
        self.assertEqual(result.provider, "http-backend")
        self.assertEqual(result.confidence, 0.8)
        self.assertEqual(result.correlation_id, "corr-1")

    def test_accepts_answer_as_an_alias_for_text(self) -> None:
        # GIVEN a transport returning the answer under the `answer` key
        transport = _CapturingTransport(HttpResponse(200, json.dumps({"answer": "reponse alias"})))
        adapter = HttpBackendAdapter(ENDPOINT, transport=transport)
        # WHEN a transcript is answered
        result = adapter.answer(_request())
        # THEN the alias is mapped to the answer text
        self.assertIs(result.outcome, AnswerOutcome.SUCCESS)
        self.assertEqual(result.text, "reponse alias")

    def test_sends_the_transcript_and_ids_and_api_key_header(self) -> None:
        # GIVEN a capturing transport
        transport = _CapturingTransport(HttpResponse(200, json.dumps({"text": "ok"})))
        adapter = HttpBackendAdapter(ENDPOINT, api_key=API_KEY, transport=transport)
        # WHEN a transcript is answered
        adapter.answer(_request(transcript="bonjour"))
        # THEN the request carries the transcript, ids and the key header
        call = transport.calls[0]
        self.assertEqual(call["url"], ENDPOINT)
        self.assertEqual(call["headers"]["x-api-key"], API_KEY)
        # The correlation id is propagated as a header too (one id end to end).
        self.assertEqual(call["headers"]["X-Correlation-Id"], "corr-1")
        sent = json.loads(call["body"])
        self.assertEqual(sent["transcript"], "bonjour")
        self.assertEqual(sent["conversation_id"], "conv-1")
        self.assertEqual(sent["correlation_id"], "corr-1")

    def test_empty_transcript_raises_without_calling_the_endpoint(self) -> None:
        # GIVEN a transport that would fail if called
        transport = _CapturingTransport(error=AssertionError("must not call the endpoint"))
        adapter = HttpBackendAdapter(ENDPOINT, transport=transport)
        # WHEN an empty transcript is answered
        # THEN it signals "nothing to answer" and never hits the transport
        with self.assertRaises(EmptyTranscriptError):
            adapter.answer(_request(transcript="   "))
        self.assertEqual(transport.calls, [])

    def test_requires_an_endpoint_url(self) -> None:
        # GIVEN no endpoint URL
        # WHEN the adapter is built
        # THEN it fails fast
        with self.assertRaises(ValueError):
            HttpBackendAdapter("")


class HttpBackendDegradedTest(unittest.TestCase):
    def _degraded(self, error=None, response=None):
        transport = _CapturingTransport(response=response, error=error)
        adapter = HttpBackendAdapter(ENDPOINT, api_key=API_KEY, transport=transport)
        return adapter.answer(_request())

    def test_transport_failure_degrades_to_the_safe_fallback(self) -> None:
        # GIVEN a transport that is unreachable
        result = self._degraded(error=HttpBackendError("conversation endpoint is unreachable"))
        # THEN a DEGRADED safe fallback is returned (never raised, never invented content)
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)
        self.assertEqual(result.text, DEGRADED_FALLBACK_TEXT)
        self.assertEqual(result.error_code, "backend_error")

    def test_timeout_maps_to_a_backend_timeout_code(self) -> None:
        # GIVEN a transport that times out
        result = self._degraded(error=TimeoutError("conversation endpoint request timed out"))
        # THEN the sanitized code marks it a timeout
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)
        self.assertEqual(result.error_code, "backend_timeout")

    def test_non_2xx_status_degrades(self) -> None:
        # GIVEN a transport returning a 503
        result = self._degraded(response=HttpResponse(503, "service unavailable"))
        # THEN the turn degrades safely
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)

    def test_unparsable_body_degrades(self) -> None:
        # GIVEN a 200 with a non-JSON body
        result = self._degraded(response=HttpResponse(200, "<html>not json</html>"))
        # THEN the turn degrades safely
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)

    def test_empty_answer_text_degrades(self) -> None:
        # GIVEN a 200 whose answer text is empty
        result = self._degraded(response=HttpResponse(200, json.dumps({"text": "   "})))
        # THEN the turn degrades safely (no empty spoken turn)
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)

    def test_no_api_key_leaks_into_the_result_on_error(self) -> None:
        # GIVEN a transport whose error message leaks the key as a token (worst case)
        result = self._degraded(error=RuntimeError(f"refused with credential {API_KEY}"))
        # THEN the sanitized reason and the whole result never contain the key
        self.assertNotIn(API_KEY, result.error_reason)
        self.assertNotIn(API_KEY, json.dumps(result.to_dict()))


class HttpBackendWithTelemetryTest(unittest.TestCase):
    def test_low_confidence_success_is_degraded_by_the_answer_step(self) -> None:
        # GIVEN an HTTP success with a low confidence, wrapped by the shared answer step
        transport = _CapturingTransport(HttpResponse(200, json.dumps({"text": "facture de 42 euros", "confidence": 0.1})))
        adapter = HttpBackendAdapter(ENDPOINT, transport=transport)
        telemetry = TelemetryRecorder()
        # WHEN it is answered through answer_with_telemetry (TASK-WEB-003-F policy)
        result = answer_with_telemetry(adapter, _request(), telemetry)
        # THEN the low-confidence content is never spoken; the safe fallback is
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)
        self.assertEqual(result.text, DEGRADED_FALLBACK_TEXT)
        self.assertEqual(result.degraded_reason, "low_confidence")

    def test_no_secret_reaches_telemetry_on_transport_failure(self) -> None:
        # GIVEN a transport that fails with a key-bearing message
        transport = _CapturingTransport(error=RuntimeError(f"boom credential {API_KEY}"))
        adapter = HttpBackendAdapter(ENDPOINT, api_key=API_KEY, transport=transport)
        telemetry = TelemetryRecorder()
        # WHEN answered through the telemetry helper
        answer_with_telemetry(adapter, _request(), telemetry)
        # THEN no span or event attribute leaks the key
        blob = str([s.attributes for s in telemetry.spans()]) + str([e.attributes for e in telemetry.events()])
        self.assertNotIn(API_KEY, blob)


if __name__ == "__main__":
    unittest.main()
