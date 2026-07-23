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


# --- time_to_first_audio composite (ADR-0018 pilot acceptance criterion) ---------
#
# ADR-0018 defines `time_to_first_audio` as the latency from the moment the voice
# runtime accepts the end of the user's turn to the first playable audio frame
# emitted back to the same channel. On the streaming WebRTC path the end-of-turn
# span (`voice.end_of_turn`) *ends* at that acceptance point, so the composite is
# the sum of the sequential post-EOT slices that lead to the first audio frame:
# STT finalize tail + backend answer + TTS time-to-first-audio.
#
# `web.voice.egress` (the channel-egress add-on) is NOT part of this sum: it is
# only emitted on the batch HTTP path, never on the streaming WebRTC transport,
# so including it would silently drop every streaming turn. The residual egress
# add-on is reported as an explicit gap in the QA report, not folded in here.
TIME_TO_FIRST_AUDIO = "time_to_first_audio"
TIME_TO_FIRST_AUDIO_SLICES: tuple[str, ...] = (STT, BACKEND_FIRST_TOKEN, TTS_FIRST_AUDIO)


@dataclass(frozen=True)
class CompositeTiming:
    name: str
    measured: bool
    component_slices: tuple[str, ...]
    report: LatencyReport | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "measured": self.measured,
            "component_slices": list(self.component_slices),
            "latency": self.report.to_dict() if self.report else None,
            "note": self.note,
        }


def _ordered_slice_durations(slice_name: str, spans: list[Span]) -> list[float]:
    """Durations of the first-present candidate span for a slice, in recorded order."""
    by_name = _durations_by_span_name(spans)
    for span_name in _SLICE_SPAN_NAMES.get(slice_name, ()):
        samples = by_name.get(span_name)
        if samples:
            return samples
    return []


def _group_spans_by_correlation(spans: Iterable[Span]) -> list[list[Span]]:
    """Group spans by correlation id so turns from different calls never mix.

    Spans keep their recorded order within a group (a call runs one turn to
    completion before the next), which lets us reconstruct per-turn composites by
    positional zip even when a single call answered several turns.
    """
    groups: dict[Any, list[Span]] = {}
    for span in spans:
        cid = span.attributes.get("correlation_id")
        groups.setdefault(cid, []).append(span)
    return list(groups.values())


def time_to_first_audio_samples(spans: Iterable[Span]) -> list[float]:
    """Per-turn EOT->first-audio composites (ms) across the sample.

    Within each correlation group the component slices are positional-zipped: the
    k-th STT tail + k-th backend answer + k-th TTS first-audio = turn k. A turn is
    skipped when any component slice is missing (e.g. a barge-in turn with no final
    answer), so an incomplete turn never contributes a truncated composite.
    """
    samples: list[float] = []
    for group in _group_spans_by_correlation(spans):
        per_slice = [_ordered_slice_durations(s, group) for s in TIME_TO_FIRST_AUDIO_SLICES]
        if any(not durations for durations in per_slice):
            continue
        turns = min(len(durations) for durations in per_slice)
        for k in range(turns):
            samples.append(round(sum(durations[k] for durations in per_slice), 3))
    return samples


def time_to_first_audio_report(spans: Iterable[Span]) -> CompositeTiming:
    materialized = list(spans)
    samples = time_to_first_audio_samples(materialized)
    if not samples:
        return CompositeTiming(
            name=TIME_TO_FIRST_AUDIO,
            measured=False,
            component_slices=TIME_TO_FIRST_AUDIO_SLICES,
            note="no complete end-of-turn->first-audio turn in this sample",
        )
    return CompositeTiming(
        name=TIME_TO_FIRST_AUDIO,
        measured=True,
        component_slices=TIME_TO_FIRST_AUDIO_SLICES,
        report=LatencyReport.from_samples(samples),
    )


# --- voice_to_first_audio composite (mouth-to-ear, ADR-0029, TASK-WEB-014) --------
#
# ADR-0018's `time_to_first_audio` starts at end-of-turn *acceptance*; the market
# measures **mouth-to-ear** (ADR-0029): from the instant the customer stops speaking
# to the first agent audio the customer *hears*. This composite folds back in the two
# slices `time_to_first_audio` excludes:
#   - END_OF_TURN: the trailing-silence hold *before* acceptance (server-measured as
#     the `voice.end_of_turn` span), and
#   - CHANNEL_EGRESS: the runtime egress add-on on the audio path (measured on the
#     WebRTC streaming path by the ChannelEgressProbe, TASK-WEB-014).
# END_OF_TURN + the post-EOT path (STT + backend + TTS) are the **required**
# components; CHANNEL_EGRESS is folded **per turn when present** and reported as an
# explicit residual gap otherwise, so a missing egress span is never silently treated
# as zero. The browser-audible add-on *beyond* runtime egress (RTP encode/packetize +
# network + jitter buffer + playout) is not server-observable and stays a documented
# residual gap (see docs/observability/voice-journey-timing.md).
VOICE_TO_FIRST_AUDIO = "voice_to_first_audio"
VOICE_TO_FIRST_AUDIO_REQUIRED_SLICES: tuple[str, ...] = (
    END_OF_TURN,
    STT,
    BACKEND_FIRST_TOKEN,
    TTS_FIRST_AUDIO,
)
VOICE_TO_FIRST_AUDIO_SLICES: tuple[str, ...] = (
    *VOICE_TO_FIRST_AUDIO_REQUIRED_SLICES,
    CHANNEL_EGRESS,
)


@dataclass(frozen=True)
class _MouthToEar:
    samples: list[float]
    turns: int
    turns_with_egress: int


def _voice_to_first_audio(spans: Iterable[Span]) -> _MouthToEar:
    """Per-turn mouth-to-ear composites, folding channel egress when the turn has it.

    Required slices are positional-zipped per correlation group (as for
    `time_to_first_audio`); a turn missing any required slice is skipped so no
    truncated composite is produced. Channel egress is added to turn k only when the
    group carries a k-th egress sample, and the egress coverage is tracked so the
    report can state honestly whether egress was folded for all / some / no turns.
    """
    samples: list[float] = []
    turns = 0
    turns_with_egress = 0
    for group in _group_spans_by_correlation(spans):
        required = [_ordered_slice_durations(s, group) for s in VOICE_TO_FIRST_AUDIO_REQUIRED_SLICES]
        if any(not durations for durations in required):
            continue
        egress = _ordered_slice_durations(CHANNEL_EGRESS, group)
        group_turns = min(len(durations) for durations in required)
        for k in range(group_turns):
            total = sum(durations[k] for durations in required)
            if k < len(egress):
                total += egress[k]
                turns_with_egress += 1
            samples.append(round(total, 3))
        turns += group_turns
    return _MouthToEar(samples=samples, turns=turns, turns_with_egress=turns_with_egress)


def voice_to_first_audio_samples(spans: Iterable[Span]) -> list[float]:
    """Per-turn mouth-to-ear composites (ms): EOT hold + STT + backend + TTS + egress."""
    return _voice_to_first_audio(spans).samples


def _egress_coverage_note(turns: int, turns_with_egress: int) -> str | None:
    if turns_with_egress == 0:
        return (
            "channel_egress not folded (no egress span in this sample); mouth-to-ear "
            "excludes the audio egress add-on — stated residual gap"
        )
    if turns_with_egress < turns:
        return (
            f"channel_egress folded for {turns_with_egress}/{turns} turns; the rest "
            "exclude the egress add-on (stated residual gap)"
        )
    return (
        "channel_egress folded as runtime egress (frame -> WebRTC transport); the "
        "browser-audible add-on beyond runtime egress stays a stated residual gap"
    )


def voice_to_first_audio_report(spans: Iterable[Span]) -> CompositeTiming:
    result = _voice_to_first_audio(list(spans))
    if not result.samples:
        return CompositeTiming(
            name=VOICE_TO_FIRST_AUDIO,
            measured=False,
            component_slices=VOICE_TO_FIRST_AUDIO_SLICES,
            note="no complete end-of-turn->first-audio turn (with end_of_turn hold) in this sample",
        )
    return CompositeTiming(
        name=VOICE_TO_FIRST_AUDIO,
        measured=True,
        component_slices=VOICE_TO_FIRST_AUDIO_SLICES,
        report=LatencyReport.from_samples(result.samples),
        note=_egress_coverage_note(result.turns, result.turns_with_egress),
    )
