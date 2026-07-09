import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TelemetryEvent:
    name: str
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


class TelemetryRecorder:
    def __init__(self) -> None:
        self._events: list[TelemetryEvent] = []
        self._metrics: list[MetricSample] = []
        self._logs: list[StructuredLog] = []

    def record(self, name: str, **attributes: Any) -> None:
        self._events.append(TelemetryEvent(name, attributes))

    def metric(self, name: str, value: float, **attributes: Any) -> None:
        self._metrics.append(MetricSample(name, value, attributes))

    def log(self, level: str, message: str, **attributes: Any) -> None:
        self._logs.append(StructuredLog(level, message, attributes))

    def events(self) -> list[TelemetryEvent]:
        return list(self._events)

    def metrics(self) -> list[MetricSample]:
        return list(self._metrics)

    def logs(self) -> list[StructuredLog]:
        return list(self._logs)


class Timer:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000
