"""Web voice egress: response text -> TTS audio -> WAV bytes for the browser.

Symmetric mirror of WebVoiceIngress for the voice-out half. It delegates
synthesis to the TtsSynthesisRunner (so the TTS slice telemetry, sanitization and
outcome stay identical to the fixture/offline path), wraps the raw PCM16 into a
WAV container the browser can `decodeAudioData`, and adds a real channel-egress
span (`web.voice.egress`) measuring the audio bytes actually produced for the
wire. On any non-success outcome no audio is invented and no egress span is
emitted (the slice stays "not measured" for that turn).
"""

import struct
from dataclasses import dataclass

from tts_synthesis.models import SynthesisResult, TtsOutcome
from tts_synthesis.providers import DEFAULT_AUDIO_FORMAT, TtsProvider
from tts_synthesis.runner import TtsSynthesisRunner
from voice_common.telemetry import TelemetryRecorder, Timer

from .envelope import ChannelEnvelope

CHANNEL_EGRESS_SPAN = "web.voice.egress"
_WAV_HEADER_BYTES = 44


@dataclass(frozen=True)
class VoiceResponse:
    """Synthesis outcome plus the WAV bytes to send (only on success)."""

    result: SynthesisResult
    wav: bytes | None


class WebVoiceEgress:
    def __init__(
        self,
        provider: TtsProvider,
        *,
        providers_by_language: dict[str, TtsProvider] | None = None,
    ) -> None:
        self._provider = provider
        self._audio_format = getattr(provider, "audio_format", DEFAULT_AUDIO_FORMAT)
        # US-042: per-session TTS voices keyed by language ("fr"/"en"); Gradium selects the
        # spoken language through the voice. Empty on the fixture path -> single default voice.
        self._providers_by_language = {
            key.lower(): value for key, value in (providers_by_language or {}).items()
        }

    def _provider_for(self, envelope: ChannelEnvelope) -> TtsProvider:
        language = (getattr(envelope, "language", None) or "").lower()
        return self._providers_by_language.get(language, self._provider)

    def synthesize_turn(
        self,
        text: str,
        envelope: ChannelEnvelope,
        telemetry: TelemetryRecorder | None = None,
    ) -> VoiceResponse:
        telemetry = telemetry or TelemetryRecorder()
        runner = TtsSynthesisRunner(self._provider_for(envelope), telemetry)
        result = runner.synthesize(text, envelope.correlation_id)
        if result.outcome is not TtsOutcome.SUCCESS:
            return VoiceResponse(result=result, wav=None)
        wav = pcm_to_wav(result.audio, _sample_rate_from_format(result.audio_format))
        return VoiceResponse(result=result, wav=wav)

    def record_egress(
        self,
        response: VoiceResponse,
        envelope: ChannelEnvelope,
        telemetry: TelemetryRecorder,
        *,
        sent_ms: float | None = None,
    ) -> None:
        """Emit the channel-egress span for a successfully sent response.

        Called by the transport *after* the WAV bytes were written to the wire so
        `sent_ms` reflects the real send window. No-op on a non-success turn so no
        egress latency is fabricated. Falls back to a local window when no
        transport measurement is supplied (unit tests / Behave).
        """
        if response.wav is None:
            return
        egress_ms = sent_ms if sent_ms is not None else Timer().elapsed_ms()
        attrs = {
            **envelope.as_attributes(),
            "provider": self._provider_for(envelope).name,
            "audio_format": self._audio_format,
            "audio_bytes": len(response.wav),
        }
        telemetry.span(CHANNEL_EGRESS_SPAN, egress_ms, **attrs)
        telemetry.record("web.voice.egress.sent", audio_egress_ms=round(egress_ms, 3), **attrs)


def _sample_rate_from_format(audio_format: str) -> int:
    # e.g. "pcm_16000" -> 16000; fall back to 16 kHz for an unexpected token.
    tail = audio_format.rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else 16000


def pcm_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    """Wrap raw PCM16 mono little-endian samples in a 44-byte WAV header."""
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE",
        b"fmt ", 16, 1, 1,
        sample_rate, sample_rate * 2, 2, 16,
        b"data", len(pcm),
    )
    return header + pcm
