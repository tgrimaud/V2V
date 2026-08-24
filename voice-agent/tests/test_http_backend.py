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
        # TASK-OPS-007: a W3C traceparent derived from the correlation id links the voice
        # turn to its backend spans (same trace id, sampled flag so the backend keeps it).
        from voice_common.trace_context import derive_traceparent

        self.assertEqual(call["headers"]["traceparent"], derive_traceparent("corr-1"))
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


class HttpBackendWarmUpTest(unittest.TestCase):
    """TASK-BE-017 / lever 2: best-effort connect-time warm-up of the backend models."""

    def test_warm_up_posts_to_the_derived_endpoint_with_the_key(self) -> None:
        # GIVEN a converse endpoint URL and a capturing transport returning 200
        transport = _CapturingTransport(HttpResponse(200, json.dumps({"fullyWarmed": True})))
        adapter = HttpBackendAdapter(ENDPOINT, api_key=API_KEY, transport=transport)
        # WHEN warm-up is triggered
        warmed = adapter.warm_up()
        # THEN it POSTs to the /warm-up sibling of the converse URL with the key header
        self.assertTrue(warmed)
        call = transport.calls[0]
        self.assertEqual(call["url"], "https://backend.internal/api/conversation/warm-up")
        self.assertEqual(call["headers"]["x-api-key"], API_KEY)
        self.assertEqual(call["body"], b"")

    def test_warm_up_derives_from_a_converse_stream_url(self) -> None:
        # GIVEN a streaming converse URL
        transport = _CapturingTransport(HttpResponse(200, "{}"))
        adapter = HttpBackendAdapter(
            "https://backend.internal/api/conversation/converse-stream", transport=transport
        )
        # WHEN warm-up is triggered -> THEN it still targets the /warm-up sibling
        adapter.warm_up()
        self.assertEqual(transport.calls[0]["url"], "https://backend.internal/api/conversation/warm-up")

    def test_warm_up_url_handles_trailing_slash_and_query(self) -> None:
        # GIVEN converse URLs with a trailing slash or a query string
        for raw in (
            "https://backend.internal/api/conversation/converse/",
            "https://backend.internal/api/conversation/converse?trace=1",
        ):
            transport = _CapturingTransport(HttpResponse(200, "{}"))
            HttpBackendAdapter(raw, transport=transport).warm_up()
            # THEN the derived warm-up URL is clean (no trailing slash / query leak)
            self.assertEqual(
                transport.calls[0]["url"], "https://backend.internal/api/conversation/warm-up", raw
            )

    def test_warm_up_returns_false_on_non_2xx(self) -> None:
        # GIVEN the warm-up endpoint returns a 503
        adapter = HttpBackendAdapter(ENDPOINT, transport=_CapturingTransport(HttpResponse(503, "down")))
        # WHEN triggered -> THEN it reports "not warmed" (never raises)
        self.assertFalse(adapter.warm_up())

    def test_warm_up_swallows_transport_faults(self) -> None:
        # GIVEN a transport that raises (endpoint unreachable / timeout)
        adapter = HttpBackendAdapter(ENDPOINT, transport=_CapturingTransport(error=TimeoutError("timed out")))
        # WHEN triggered -> THEN it returns False and never raises (best-effort)
        self.assertFalse(adapter.warm_up())

    def test_warm_up_never_leaks_the_key_even_when_the_transport_raises(self) -> None:
        # GIVEN a transport whose fault message carries the key
        adapter = HttpBackendAdapter(
            ENDPOINT, api_key=API_KEY, transport=_CapturingTransport(error=RuntimeError(f"boom {API_KEY}"))
        )
        # WHEN triggered -> THEN no exception surfaces (so nothing to leak) and it returns False
        self.assertFalse(adapter.warm_up())


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


class _StreamTransport:
    """Fake SSE line transport: yields canned lines (or raises), and records the URL."""

    def __init__(self, lines: list[str] | None = None, error: Exception | None = None) -> None:
        self._lines = lines or []
        self._error = error
        self.calls: list[dict] = []
        self.closed = False

    def __call__(self, url, headers, body, timeout, control):
        self.calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        control.bind(self._close)
        if self._error is not None:
            raise self._error
        # Mirror urllib's `for raw in resp`: yield one physical line at a time (with its
        # trailing newline), not whole SSE blocks, so the parser sees real line framing.
        for block in self._lines:
            for line in block.splitlines(keepends=True):
                if control.stopped:
                    return
                yield line

    def _close(self) -> None:
        self.closed = True


def _chunk(text: str) -> str:
    return f'event:chunk\ndata:{{"text":"{text}"}}\n\n'


class HttpBackendStreamTest(unittest.TestCase):
    """TASK-WEB-020 / lever 1: consume the guarded SSE stream one vetted sentence at a time."""

    def test_stream_url_is_derived_from_the_converse_endpoint(self) -> None:
        # GIVEN converse endpoints (plain, trailing slash, query, already-streaming)
        cases = {
            "https://b.internal/api/conversation/converse": "https://b.internal/api/conversation/converse-stream",
            "https://b.internal/api/conversation/converse/": "https://b.internal/api/conversation/converse-stream",
            "https://b.internal/api/conversation/converse?x=1": "https://b.internal/api/conversation/converse-stream",
            "https://b.internal/api/conversation/converse-stream": "https://b.internal/api/conversation/converse-stream",
        }
        for raw, expected in cases.items():
            transport = _StreamTransport([_chunk("hi")])
            list(HttpBackendAdapter(raw, stream_transport=transport).answer_stream(_request()))
            # THEN the stream targets the converse-stream sibling
            self.assertEqual(transport.calls[0]["url"], expected, raw)

    def test_streams_chunks_then_done(self) -> None:
        # GIVEN a stream of two chunks then a grounded done
        lines = [
            _chunk("Bonjour."),
            _chunk("Votre facture a augmente."),
            'event:done\ndata:{"text":"Bonjour. Votre facture a augmente.","confidence":0.9,"grounded":true}\n\n',
        ]
        adapter = HttpBackendAdapter(ENDPOINT, stream_transport=_StreamTransport(lines))
        # WHEN consumed
        events = list(adapter.answer_stream(_request()))
        # THEN two chunk events (in order) then a done carrying confidence/grounded
        self.assertEqual([e.text for e in events if e.kind == "chunk"], ["Bonjour.", "Votre facture a augmente."])
        done = next(e for e in events if e.kind == "done")
        self.assertAlmostEqual(done.confidence, 0.9)
        self.assertIs(done.grounded, True)

    def test_connect_fault_yields_a_sanitized_error_event_not_a_raise(self) -> None:
        # GIVEN a stream transport that fails to connect with a key-bearing message
        transport = _StreamTransport(error=RuntimeError(f"unreachable {API_KEY}"))
        adapter = HttpBackendAdapter(ENDPOINT, api_key=API_KEY, stream_transport=transport)
        # WHEN consumed
        events = list(adapter.answer_stream(_request()))
        # THEN a single sanitized error event is produced (never raised, never leaks the key)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, "error")
        self.assertNotIn(API_KEY, f"{events[0].error_code} {events[0].error_reason}")

    def test_empty_transcript_raises_before_opening_the_stream(self) -> None:
        # GIVEN an empty transcript
        transport = _StreamTransport([_chunk("x")])
        adapter = HttpBackendAdapter(ENDPOINT, stream_transport=transport)
        # WHEN consumed -> THEN it stays UNAVAILABLE (no stream opened, never fabricates a turn)
        with self.assertRaises(EmptyTranscriptError):
            list(adapter.answer_stream(_request(transcript="   ")))
        self.assertEqual(transport.calls, [])

    def test_abort_stops_consuming_and_closes_the_stream(self) -> None:
        # GIVEN a control aborted after opening the stream
        from conversation_backend import StreamControl

        transport = _StreamTransport([_chunk("one"), _chunk("two"), _chunk("three")])
        adapter = HttpBackendAdapter(ENDPOINT, stream_transport=transport)
        control = StreamControl()
        gen = adapter.answer_stream(_request(), control)
        first = next(gen)
        # WHEN aborted (barge-in) after the first sentence
        control.abort()
        rest = list(gen)
        # THEN no further event is consumed and the underlying stream is closed
        self.assertEqual(first.text, "one")
        self.assertEqual(rest, [])
        self.assertTrue(transport.closed)


if __name__ == "__main__":
    unittest.main()
