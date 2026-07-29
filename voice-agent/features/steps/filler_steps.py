import asyncio
import time
from types import SimpleNamespace

from behave import given, then, when
from pipecat.frames.frames import TextFrame, TranscriptionFrame
from pipecat.tests.utils import run_test

from conversation_backend import AnswerOutcome, AnswerRequest, AnswerResult
from voice_common.telemetry import TelemetryRecorder
from voice_pipeline.answer import AnswerProcessor
from voice_pipeline.filler import FILLER_SPOKEN_EVENT, FILLER_SPOKEN_METRIC

FILLER_PHRASE = "Un instant, je vérifie."
ANSWER_TEXT = "voici la reponse a votre question"


def _envelope() -> SimpleNamespace:
    return SimpleNamespace(channel="web_voice", conversation_id="conv-filler", correlation_id="corr-filler")


class _TimedBackend:
    name = "fake-backend"

    def __init__(self, delay_s: float) -> None:
        self._delay_s = delay_s

    def answer(self, request: AnswerRequest) -> AnswerResult:
        if self._delay_s:
            time.sleep(self._delay_s)
        return AnswerResult(
            text=ANSWER_TEXT,
            provider=self.name,
            outcome=AnswerOutcome.SUCCESS,
            correlation_id=request.correlation_id,
        )


def _spoken_texts(down) -> list[str]:
    return [f.text for f in down if isinstance(f, TextFrame) and not isinstance(f, TranscriptionFrame)]


def _run(processor: AnswerProcessor) -> list[str]:
    down, _up = asyncio.run(
        run_test(
            processor,
            frames_to_send=[TranscriptionFrame(text="pourquoi ma facture augmente", user_id="u", timestamp="")],
        )
    )
    return _spoken_texts(down)


@given("a voice turn whose backend answer is slower than the filler threshold")
def step_slow_turn(context):
    context.telemetry = TelemetryRecorder()
    context.processor = AnswerProcessor(
        _TimedBackend(delay_s=0.08),
        _envelope(),
        context.telemetry,
        filler_threshold_ms=10,
        filler_phrases=[FILLER_PHRASE],
    )


@given("a voice turn whose backend answers before the filler threshold")
def step_fast_turn(context):
    context.telemetry = TelemetryRecorder()
    context.processor = AnswerProcessor(
        _TimedBackend(delay_s=0.0),
        _envelope(),
        context.telemetry,
        filler_threshold_ms=10_000,
        filler_phrases=[FILLER_PHRASE],
    )


@when("the turn runs end to end")
def step_run_turn(context):
    context.spoken = _run(context.processor)


@then("a short holding phrase is spoken before the answer")
def step_filler_before_answer(context):
    assert context.spoken == [FILLER_PHRASE, ANSWER_TEXT], context.spoken


@then("the holding phrase carries no digit or amount")
def step_filler_no_digit(context):
    assert not any(ch.isdigit() for ch in context.spoken[0]), context.spoken[0]


@then("the filler is observable with the correlation id and the wait it triggered on")
def step_filler_observable(context):
    event = next(e for e in context.telemetry.events() if e.name == FILLER_SPOKEN_EVENT)
    assert event.attributes["correlation_id"] == "corr-filler", event.attributes
    assert event.attributes["channel"] == "web_voice", event.attributes
    assert event.attributes["wait_ms"] == 10.0, event.attributes
    metric = next(m for m in context.telemetry.metrics() if m.name == FILLER_SPOKEN_METRIC)
    assert metric.value == 1, metric.value


@then("only the answer is spoken with no holding phrase")
def step_only_answer(context):
    assert context.spoken == [ANSWER_TEXT], context.spoken
    assert not any(e.name == FILLER_SPOKEN_EVENT for e in context.telemetry.events())
