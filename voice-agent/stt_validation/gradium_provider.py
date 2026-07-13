"""Fresh Gradium STT provider (TASK-STT-008).

Implements the `SttProvider` protocol so the validation harness, manifest,
telemetry and Behave scenarios stay unchanged. The HTTP transport is injectable
so unit tests never hit the network and no external dependency is required for
the default stdlib path. The API key is never placed in an exception message,
log or telemetry attribute.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .providers import NoSpeechDetectedError

GRADIUM_ASR_URL = "https://api.gradium.ai/api/post/speech/asr"
DEFAULT_MODEL = "default"
DEFAULT_LANGUAGE = "fr"
DEFAULT_INPUT_FORMAT = "pcm_16000"
DEFAULT_TIMEOUT_S = 30.0
# Gradium validates Content-Type against an allowlist and rejects the urllib
# default (application/x-www-form-urlencoded). Verified accepted values:
# `audio/pcm` for PCM input, `audio/basic` for G.711 u-law telephony.
PCM_CONTENT_TYPE = "audio/pcm"
ULAW_CONTENT_TYPE = "audio/basic"


def _content_type_for(input_format: str) -> str:
    return ULAW_CONTENT_TYPE if input_format.startswith("ulaw") else PCM_CONTENT_TYPE


class GradiumSttError(RuntimeError):
    """Gradium STT failed. The message is safe to surface (never carries the key)."""


@dataclass(frozen=True)
class GradiumResponse:
    status: int
    body: str


# (url, headers, params, content, timeout) -> GradiumResponse
Transport = Callable[[str, dict[str, str], dict[str, str], bytes, float], GradiumResponse]


class GradiumSttProvider:
    name = "gradium-stt"

    def __init__(
        self,
        api_key: str,
        *,
        language: str = DEFAULT_LANGUAGE,
        input_format: str = DEFAULT_INPUT_FORMAT,
        model_name: str = DEFAULT_MODEL,
        url: str = GRADIUM_ASR_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        content_type: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Gradium API key is required")
        self._api_key = api_key
        self._language = language
        self._input_format = input_format
        self._model_name = model_name
        self._url = url
        self._timeout_s = timeout_s
        self._content_type = content_type or _content_type_for(input_format)
        self._transport = transport or _urllib_transport

    def transcribe(self, audio_path: Path) -> str:
        audio = audio_path.read_bytes()  # FileNotFoundError -> fixture_missing (path redacted)
        response = self._transport(
            self._url,
            {"x-api-key": self._api_key, "Content-Type": self._content_type},
            {
                "model_name": self._model_name,
                "input_format": self._input_format,
                "json_config": json.dumps({"language": self._language}),
            },
            audio,
            self._timeout_s,
        )
        if response.status != 200:
            raise _http_error(response)
        transcript = _parse_transcript(response.body)
        if not transcript:
            raise NoSpeechDetectedError("Gradium STT recognized no speech in the audio")
        return transcript


def _http_error(response: GradiumResponse) -> GradiumSttError:
    if "credit" in response.body.lower():
        return GradiumSttError("Gradium STT credits exhausted")
    if response.status == 401:
        return GradiumSttError("Gradium STT authentication failed (HTTP 401)")
    return GradiumSttError(f"Gradium STT service error (HTTP {response.status})")


def _parse_transcript(body: str) -> str:
    """Join line-delimited Gradium `type: text` tokens into a single transcript."""
    words: list[str] = []
    for line in body.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GradiumSttError("Gradium STT returned an unparsable response") from exc
        if data.get("type") == "text":
            word = str(data.get("text", "")).strip()
            if word:
                words.append(word)
    return " ".join(words).strip()


def _urllib_transport(
    url: str,
    headers: dict[str, str],
    params: dict[str, str],
    content: bytes,
    timeout: float,
) -> GradiumResponse:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(full_url, data=content, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310 - fixed https host
            return GradiumResponse(status=resp.status, body=resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return GradiumResponse(status=exc.code, body=body)
    except TimeoutError as exc:  # socket timeout -> stt_timeout via sanitizer
        raise TimeoutError("Gradium STT request timed out") from exc
    except urllib.error.URLError as exc:
        raise GradiumSttError("Gradium STT service is unreachable") from exc
