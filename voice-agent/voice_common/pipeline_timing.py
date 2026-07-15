"""Voice-journey timing by pipeline slice (US-036).

Domain-neutral, read-only aggregator shared by both voice halves. It groups
recorded spans across a reviewed sample of turns and reports, per canonical
pipeline slice, a p50/p95/p99 latency distribution. Slices with no span in the
sample are reported explicitly as "not measured" with a reason, instead of being
silently omitted, so a reviewer can tell a missing measurement from a fast one.

It knows the span *names* emitted by both halves (as string literals, never
imports) so it stays free of any back-dependency on stt_validation, tts_synthesis
or the web_voice runtime — the emitter side owns the span-name constants.

Canonical slices follow US-036: channel ingress, end-of-turn, STT, backend first
token/action, TTS first audio, channel egress.
"""

from dataclasses import dataclass
from typing import Any, Iterable

from .telemetry import LatencyReport, Span

CHANNEL_INGRESS = "channel_ingress"
END_OF_TURN = "end_of_turn"
STT = "stt"
BACKEND_FIRST_TOKEN = "backend_first_token"
TTS_FIRST_AUDIO = "tts_first_audio"
CHANNEL_EGRESS = "channel_egress"

# Ordered as the audio flows through the voice journey.
PIPELINE_SLICES = (
    CHANNEL_INGRESS,
    END_OF_TURN,
    STT,
    BACKEND_FIRST_TOKEN,
    TTS_FIRST_AUDIO,
    CHANNEL_EGRESS,
)

# Canonical slice -> span names that measure it (first present name wins).
# String literals (not imports) so this module stays free of a back-dependency on
# the emitters; each emitter owns its own span-name constant.
_SLICE_SPAN_NAMES: dict[str, tuple[str, ...]] = {
    CHANNEL_INGRESS: ("web.voice.ingress", "stt.audio.accept"),
    END_OF_TURN: ("voice.end_of_turn",),
    STT: ("stt.request",),
    # backend.first_token wins when present (streaming backends); backend.request
    # (total answer duration) is the batch fallback. Both are emitted by
    # voice_pipeline/answer.py (TASK-WEB-003-D/E).
    BACKEND_FIRST_TOKEN: ("backend.first_token", "backend.request"),
    TTS_FIRST_AUDIO: ("voice.tts.first_audio",),
    CHANNEL_EGRESS: ("web.voice.egress",),
}

# Why a slice is not measured yet (only used when no span is present).
_UNMEASURED_NOTES: dict[str, str] = {
    CHANNEL_INGRESS: "no channel-ingress span in this sample",
    END_OF_TURN: "no end-of-turn span in this sample",
    STT: "no stt.request span in this sample",
    BACKEND_FIRST_TOKEN: "no backend.first_token span in this sample",
    TTS_FIRST_AUDIO: "no voice.tts.first_audio span in this sample",
    CHANNEL_EGRESS: "no web.voice.egress span in this sample",
}


@dataclass(frozen=True)
class SliceTiming:
    slice: str
    measured: bool
    report: LatencyReport | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "slice": self.slice,
            "measured": self.measured,
            "latency": self.report.to_dict() if self.report else None,
            "note": self.note,
        }


@dataclass(frozen=True)
class PipelineTimingReport:
    slices: list[SliceTiming]

    def measured_slices(self) -> list[SliceTiming]:
        return [s for s in self.slices if s.measured]

    def to_dict(self) -> dict[str, Any]:
        return {"slices": [s.to_dict() for s in self.slices]}

    @classmethod
    def from_spans(
        cls,
        spans: Iterable[Span],
        expected: tuple[str, ...] = PIPELINE_SLICES,
    ) -> "PipelineTimingReport":
        by_name = _durations_by_span_name(spans)
        slices = [_slice_timing(name, by_name) for name in expected]
        return cls(slices=slices)


def _durations_by_span_name(spans: Iterable[Span]) -> dict[str, list[float]]:
    durations: dict[str, list[float]] = {}
    for span in spans:
        durations.setdefault(span.name, []).append(span.duration_ms)
    return durations


def _slice_timing(slice_name: str, durations_by_name: dict[str, list[float]]) -> SliceTiming:
    # First present candidate span wins so a fixture-only run (stt.audio.accept)
    # and a web run (web.voice.ingress) never mix into the same distribution.
    for span_name in _SLICE_SPAN_NAMES.get(slice_name, ()):
        samples = durations_by_name.get(span_name)
        if samples:
            return SliceTiming(slice=slice_name, measured=True, report=LatencyReport.from_samples(samples))
    return SliceTiming(slice=slice_name, measured=False, note=_UNMEASURED_NOTES.get(slice_name))
