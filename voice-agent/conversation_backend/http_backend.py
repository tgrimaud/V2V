"""HTTP conversation backend adapter (TASK-WEB-003-C).

Calls a real conversation endpoint (the Java answer engine) over HTTP and maps its
response onto the neutral conversation contract (`AnswerResult`). The transport is
injectable so unit tests never hit the network and the default stdlib path needs no
external dependency.

Failure policy (mirrors TASK-WEB-003-F degraded mode): a transport fault, timeout,
non-2xx status or unparsable body never raises out of `answer` and never leaks a
secret — it maps to a sanitized DEGRADED result (safe fallback text + a stable
`error_code` + a redacted `error_reason`). The API key lives only in the request
header; it is never placed in an exception, log or telemetry attribute.

This module stays neutral: it imports only stdlib, the shared `voice_common`
sanitizer and the in-package contract; never `stt_validation`, `tts_synthesis` or
`web_voice` (enforced by tests/test_architecture_separation.py).
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from voice_common.sanitization import sanitize_error

from .degraded import BACKEND_UNAVAILABLE_REASON, degraded_answer
from .models import AnswerOutcome, AnswerRequest, AnswerResult
from .port import EmptyTranscriptError

DEFAULT_TIMEOUT_S = 8.0
# Provisional conversation contract (formalized by the TASK-WEB-003-G ADR): the
# request carries the transcript + traceability ids; the response carries the answer
# text and an optional confidence. `answer` is accepted as an alias for `text`.
_ANSWER_KEYS = ("text", "answer")


class HttpBackendError(RuntimeError):
    """HTTP backend call failed. The message is safe to surface (never the API key)."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str


# (url, headers, body, timeout) -> HttpResponse
Transport = Callable[[str, dict[str, str], bytes, float], HttpResponse]


class HttpBackendAdapter:
    """`BackendAnswerPort` calling a real conversation endpoint over HTTP."""

    name = "http-backend"

    def __init__(
        self,
        endpoint_url: str,
        *,
        api_key: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: Transport | None = None,
    ) -> None:
        if not endpoint_url:
            raise ValueError("HTTP backend endpoint URL is required")
        self._url = endpoint_url
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._transport = transport or _urllib_transport

    def answer(self, request: AnswerRequest) -> AnswerResult:
        if not request.transcript or not request.transcript.strip():
            # Nothing to answer: stays UNAVAILABLE upstream, never a fabricated turn.
            raise EmptyTranscriptError("No transcript to answer")
        try:
            response = self._transport(self._url, self._headers(request), self._payload(request), self._timeout_s)
        except Exception as exc:  # noqa: BLE001 - any transport fault degrades to a safe reply
            return self._degraded(request, exc)
        return self._map_response(request, response)

    def _headers(self, request: AnswerRequest) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        # Propagate the turn's correlation id as a header too (not a secret), so the backend's
        # request filter logs the same id from the very first line — one id end to end even
        # before the controller reads it from the body (the body value stays authoritative).
        if request.correlation_id:
            headers["X-Correlation-Id"] = request.correlation_id
        return headers

    def _payload(self, request: AnswerRequest) -> bytes:
        body = {
            "transcript": request.transcript,
            "conversation_id": request.conversation_id,
            "correlation_id": request.correlation_id,
            "channel": request.channel,
        }
        return json.dumps(body).encode("utf-8")

    def _map_response(self, request: AnswerRequest, response: HttpResponse) -> AnswerResult:
        if response.status < 200 or response.status >= 300:
            return self._degraded(request, HttpBackendError(f"conversation endpoint HTTP {response.status}"))
        try:
            data = json.loads(response.body)
        except json.JSONDecodeError:
            return self._degraded(request, HttpBackendError("conversation endpoint returned an unparsable body"))
        text = _first_text(data)
        if not text:
            return self._degraded(request, HttpBackendError("conversation endpoint returned no answer text"))
        return AnswerResult(
            text=text,
            provider=self.name,
            outcome=AnswerOutcome.SUCCESS,
            correlation_id=request.correlation_id,
            confidence=_confidence(data),
        )

    def _degraded(self, request: AnswerRequest, exc: Exception) -> AnswerResult:
        sanitized = sanitize_error(exc, domain="backend")
        return degraded_answer(
            request,
            provider=self.name,
            degraded_reason=BACKEND_UNAVAILABLE_REASON,
            error_code=sanitized.reason_code,
            error_reason=sanitized.reason,
        )


def _first_text(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in _ANSWER_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _confidence(data: Any) -> float | None:
    value = data.get("confidence") if isinstance(data, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def _urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> HttpResponse:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310 - operator-configured endpoint
            return HttpResponse(status=resp.status, body=resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        return HttpResponse(status=exc.code, body=body_text)
    except TimeoutError as exc:  # socket timeout -> backend_timeout via sanitizer
        raise TimeoutError("conversation endpoint request timed out") from exc
    except urllib.error.URLError as exc:
        raise HttpBackendError("conversation endpoint is unreachable") from exc
