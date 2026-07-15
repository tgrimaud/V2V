import json

from behave import given, then, when

from conversation_backend import (
    AnswerOutcome,
    AnswerRequest,
    DEGRADED_FALLBACK_TEXT,
    HttpBackendAdapter,
    HttpResponse,
)
from conversation_backend.http_backend import HttpBackendError
from voice_common.telemetry import TelemetryRecorder
from voice_pipeline.answer import answer_with_telemetry

API_KEY = "sk-conversation-secret-987654"
ENDPOINT = "https://backend.internal/api/conversation/ask"


def _request(transcript: str = "pourquoi ma facture augmente") -> AnswerRequest:
    return AnswerRequest(
        transcript=transcript,
        correlation_id="qa-http",
        conversation_id="conv-http",
        channel="web_voice",
    )


class _ScriptedTransport:
    def __init__(self, response=None, error=None) -> None:
        self._response = response
        self._error = error

    def __call__(self, url, headers, body, timeout) -> HttpResponse:
        if self._error is not None:
            raise self._error
        return self._response


@given("the http backend adapter with a fake transport")
def step_http_adapter(context):
    context.ok_transport = _ScriptedTransport(HttpResponse(200, json.dumps({"text": "voici votre reponse"})))
    context.fail_transport = _ScriptedTransport(error=HttpBackendError(f"unreachable with credential {API_KEY}"))
    context.timeout_transport = _ScriptedTransport(error=TimeoutError("conversation endpoint request timed out"))


@when("it answers a transcript")
def step_http_answer(context):
    context.ok_result = HttpBackendAdapter(ENDPOINT, api_key=API_KEY, transport=context.ok_transport).answer(_request())
    context.telemetry = TelemetryRecorder()
    fail_adapter = HttpBackendAdapter(ENDPOINT, api_key=API_KEY, transport=context.fail_transport)
    context.fail_result = answer_with_telemetry(fail_adapter, _request(), context.telemetry)
    timeout_adapter = HttpBackendAdapter(ENDPOINT, api_key=API_KEY, transport=context.timeout_transport)
    context.timeout_result = timeout_adapter.answer(_request())


@then("it maps the endpoint response to the conversation contract")
def step_http_mapped(context):
    assert context.ok_result.outcome is AnswerOutcome.SUCCESS, context.ok_result.outcome
    assert context.ok_result.text == "voici votre reponse"
    assert context.ok_result.provider == "http-backend"


@then("transport and timeout errors map to a sanitized degraded outcome")
def step_http_degraded(context):
    assert context.fail_result.outcome is AnswerOutcome.DEGRADED
    assert context.fail_result.text == DEGRADED_FALLBACK_TEXT
    assert context.fail_result.error_code == "backend_error"
    assert context.timeout_result.error_code == "backend_timeout"


@then("no secret appears in any error, log or telemetry")
def step_http_no_leak(context):
    blob = json.dumps(context.fail_result.to_dict()) + str([s.attributes for s in context.telemetry.spans()])
    blob += str([e.attributes for e in context.telemetry.events()])
    assert API_KEY not in blob, "the API key leaked into the sanitized output"
