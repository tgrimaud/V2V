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
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Callable

from voice_common.sanitization import sanitize_error
from voice_common.trace_context import derive_traceparent

from .degraded import BACKEND_UNAVAILABLE_REASON, degraded_answer
from .models import AnswerOutcome, AnswerRequest, AnswerResult
from .port import EmptyTranscriptError
from .streaming import ERROR, AnswerStreamEvent, StreamControl, parse_sse_events

DEFAULT_TIMEOUT_S = 8.0
# Warm-up (TASK-BE-017 / lever 2) runs a cold LLM + embedding call, which can take
# several seconds on the very first hit — give it a more generous ceiling than a turn,
# since it runs off the per-turn critical path and a timeout just means "not warmed".
WARM_UP_TIMEOUT_S = 30.0
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
# (url, headers, body, timeout, control) -> raw SSE line iterator (TASK-WEB-020, lever 1).
# Separate from Transport so the blocking `answer` path is untouched; the streaming
# transport yields lines lazily so the first sentence reaches the caller as it arrives.
StreamTransport = Callable[[str, dict[str, str], bytes, float, StreamControl], Iterator[str]]


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
        stream_transport: StreamTransport | None = None,
    ) -> None:
        if not endpoint_url:
            raise ValueError("HTTP backend endpoint URL is required")
        self._url = endpoint_url
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._transport = transport or _urllib_transport
        self._stream_transport = stream_transport or _urllib_stream_transport

    def answer(self, request: AnswerRequest) -> AnswerResult:
        if not request.transcript or not request.transcript.strip():
            # Nothing to answer: stays UNAVAILABLE upstream, never a fabricated turn.
            raise EmptyTranscriptError("No transcript to answer")
        try:
            response = self._transport(self._url, self._headers(request), self._payload(request), self._timeout_s)
        except Exception as exc:  # noqa: BLE001 - any transport fault degrades to a safe reply
            return self._degraded(request, exc)
        return self._map_response(request, response)

    def answer_stream(
        self, request: AnswerRequest, control: StreamControl | None = None
    ) -> Iterator[AnswerStreamEvent]:
        """Stream vetted sentences from the guarded SSE endpoint (TASK-WEB-020 / lever 1).

        Yields `chunk` events (each already a grounded, guardrail-vetted sentence — the
        backend `GuardedSentenceEmitter` enforces DEC-002 per sentence), a terminal
        `done` (confidence + grounded), or a sanitized `error`. Mirrors `answer`'s
        failure policy: a connect or mid-stream fault never raises out and never leaks a
        secret — it surfaces as one `error` event so the caller degrades safely. An
        empty transcript stays UNAVAILABLE (never a fabricated turn), exactly like
        `answer`. `control` lets a barge-in abort a blocked read cleanly.
        """
        if not request.transcript or not request.transcript.strip():
            raise EmptyTranscriptError("No transcript to answer")
        control = control or StreamControl()
        try:
            lines = self._stream_transport(
                self._stream_url(), self._headers(request), self._payload(request), self._timeout_s, control
            )
            yield from parse_sse_events(lines)
        except EmptyTranscriptError:
            raise
        except Exception as exc:  # noqa: BLE001 - any stream fault degrades to a safe error event
            if control.stopped:
                return  # aborted by barge-in: not a fault, just stop consuming
            sanitized = sanitize_error(exc, domain="backend")
            yield AnswerStreamEvent(kind=ERROR, error_code=sanitized.reason_code, error_reason=sanitized.reason)

    def _stream_url(self) -> str:
        # Derive the guarded-stream sibling of the converse endpoint: ".../converse" ->
        # ".../converse-stream"; an already-streaming URL is kept; any other endpoint gets
        # a "converse-stream" sibling. Query/fragment/trailing slash are dropped first so
        # ".../converse/", ".../converse?x=1" map correctly (mirror of `_warm_up_url`).
        parts = urllib.parse.urlsplit(self._url)
        path = parts.path.rstrip("/")
        last = path.rsplit("/", 1)[-1] if "/" in path else path
        if last == "converse-stream":
            new_path = path
        elif last == "converse":
            new_path = f"{path[: -len('converse')]}converse-stream"
        else:
            base = path.rsplit("/", 1)[0] if "/" in path else ""
            new_path = f"{base}/converse-stream"
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, new_path, "", ""))

    def warm_up(self) -> bool:
        """Best-effort connect-time warm-up of the backend models (TASK-BE-017 / lever 2).

        POSTs to the warm-up endpoint derived from the converse URL so the first real
        turn does not pay the cold LLM + embedding cost. Runs off the per-turn critical
        path; never raises and never leaks the key — any fault returns False (not warmed).
        """
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        try:
            response = self._transport(self._warm_up_url(), headers, b"", WARM_UP_TIMEOUT_S)
        except Exception:  # noqa: BLE001 - warm-up is best-effort; a fault must never surface
            return False
        return 200 <= response.status < 300

    def _warm_up_url(self) -> str:
        # Derive the /warm-up sibling of the converse endpoint robustly: drop any query /
        # fragment and a trailing slash before replacing the last path segment, so
        # ".../converse", ".../converse-stream", ".../converse/" and ".../converse?x=1"
        # all map to ".../warm-up".
        parts = urllib.parse.urlsplit(self._url)
        path = parts.path.rstrip("/")
        base = path.rsplit("/", 1)[0] if "/" in path else path
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, f"{base}/warm-up", "", ""))

    def _headers(self, request: AnswerRequest) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        # Propagate the turn's correlation id as a header too (not a secret), so the backend's
        # request filter logs the same id from the very first line — one id end to end even
        # before the controller reads it from the body (the body value stays authoritative).
        if request.correlation_id:
            headers["X-Correlation-Id"] = request.correlation_id
            # W3C trace context (TASK-OPS-007): a deterministic traceparent derived from the
            # correlation id so the backend continues the SAME trace id — a voice turn and its
            # backend spans land in one trace in the collector. Sampled flag = 01 so a
            # voice-initiated call is kept even under a low backend sampling probability.
            traceparent = derive_traceparent(request.correlation_id)
            if traceparent:
                headers["traceparent"] = traceparent
        return headers

    def _payload(self, request: AnswerRequest) -> bytes:
        body = {
            "transcript": request.transcript,
            "conversation_id": request.conversation_id,
            "correlation_id": request.correlation_id,
            "channel": request.channel,
        }
        # US-042: only send the language when the UI forced one, so the backend keeps
        # auto-detecting otherwise (a null/blank field is ignored by the backend anyway).
        if request.language:
            body["language"] = request.language
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


def _urllib_stream_transport(
    url: str, headers: dict[str, str], body: bytes, timeout: float, control: StreamControl
) -> Iterator[str]:
    """Default SSE line transport: POST and yield decoded response lines lazily.

    Binds the response `close` to the `control` so a barge-in can unblock a read that is
    waiting mid-line, and always closes the socket in `finally` so an aborted or failed
    stream never leaks the connection.
    """
    request = urllib.request.Request(url, data=body, headers={**headers, "Accept": "text/event-stream"}, method="POST")
    resp = urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - operator-configured endpoint
    control.bind(resp.close)
    try:
        for raw in resp:
            if control.stopped:
                break
            yield raw.decode("utf-8", errors="replace")
    finally:
        try:
            resp.close()
        except Exception:  # noqa: BLE001 - best-effort close
            pass
