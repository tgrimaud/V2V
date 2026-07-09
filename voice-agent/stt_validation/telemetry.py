import math
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TelemetryEvent:
    name: str
    attributes: dict[str, Any]


@dataclass(frozen=True)
class Span:
    """OpenTelemetry-compatible timing span isolating one pipeline slice."""

    name: str
    duration_ms: float
    attributes: dict[str, Any]


@dataclass(frozen=True)
class MetricSample:
    name: str
    value: float
    attributes: dict[str, Any]


@dataclass(frozen=True)
class StructuredLog:
    level: str
    message: str
    attributes: dict[str, Any]


@dataclass(frozen=True)
class LatencyReport:
    """Percentile summary so individual samples contribute to p50/p95/p99."""

    count: int
    min_ms: float | None = None
    max_ms: float | None = None
    p50_ms: float | None = None
    p95_ms: float | None = None
    p99_ms: float | None = None

    @classmethod
    def from_samples(cls, samples: list[float]) -> "LatencyReport":
        ordered = sorted(samples)
        if not ordered:
            return cls(count=0)
        return cls(
            count=len(ordered),
            min_ms=round(ordered[0], 3),
            max_ms=round(ordered[-1], 3),
            p50_ms=_percentile(ordered, 50),
            p95_ms=_percentile(ordered, 95),
            p99_ms=_percentile(ordered, 99),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
        }


def _percentile(ordered: list[float], percentile: float) -> float:
    """Nearest-rank percentile over a pre-sorted list."""
    rank = math.ceil(percentile / 100 * len(ordered))
    index = min(max(rank, 1), len(ordered)) - 1
    return round(ordered[index], 3)


@dataclass
class TelemetryRecorder:
    _events: list[TelemetryEvent] = field(default_factory=list)
    _spans: list[Span] = field(default_factory=list)
    _metrics: list[MetricSample] = field(default_factory=list)
    _logs: list[StructuredLog] = field(default_factory=list)

    def record(self, name: str, **attributes: Any) -> None:
        self._events.append(TelemetryEvent(name, attributes))

    def span(self, name: str, duration_ms: float, **attributes: Any) -> None:
        self._spans.append(Span(name, round(duration_ms, 3), attributes))

    def metric(self, name: str, value: float, **attributes: Any) -> None:
        self._metrics.append(MetricSample(name, round(value, 3), attributes))

    def log(self, level: str, message: str, **attributes: Any) -> None:
        self._logs.append(StructuredLog(level, message, attributes))

    def events(self) -> list[TelemetryEvent]:
        return list(self._events)

    def spans(self) -> list[Span]:
        return list(self._spans)

    def metrics(self) -> list[MetricSample]:
        return list(self._metrics)

    def logs(self) -> list[StructuredLog]:
        return list(self._logs)


class Timer:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000
