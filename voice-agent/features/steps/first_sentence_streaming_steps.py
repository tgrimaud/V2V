import asyncio
from types import SimpleNamespace

from behave import given, then, when
from pipecat.frames.frames import TextFrame, TranscriptionFrame
from pipecat.tests.utils import run_test

from conversation_backend import (
    CHUNK,
    DONE,
    ERROR,
    AnswerOutcome,
    AnswerStreamEvent,
    DEGRADED_FALLBACK_TEXT,
    EmptyTranscriptError,
)
from voice_pipeline.answer import AnswerProcessor


def _envelope() -> SimpleNamespace:
    return SimpleNamespace(channel="web_voice", conversation_id="conv-stream", correlation_id="corr-stream")


class _ScriptedStreamBackend:
    name = "scripted-stream"

    def __init__(self, events: list[AnswerStreamEvent]) -> None:
        self._events = events

    def answer_stream(self, request, control=None):
        if not request.transcript or not request.transcript.strip():
            raise EmptyTranscriptError("nothing to answer")
        yield from self._events


def _spoken(down) -> list[str]:
    return [f.text for f in down if type(f) is TextFrame]


@given("a voice turn with the backend answer streaming enabled")
def step_streaming_enabled(context):
    context.events = None


@given('the backend streams the sentences "{first}" then "{second}"')
def step_two_sentences(context, first, second):
    context.events = [
        AnswerStreamEvent(kind=CHUNK, text=first),
        AnswerStreamEvent(kind=CHUNK, text=second),
        AnswerStreamEvent(kind=DONE, text=f"{first} {second}", confidence=0.9, grounded=True),
    ]


@given('the backend blocks a sentence and streams only the safe hand-off "{handoff}"')
def step_blocked_handoff(context, handoff):
    context.events = [
        AnswerStreamEvent(kind=CHUNK, text=handoff),
        AnswerStreamEvent(kind=DONE, text=handoff, grounded=False),
    ]


@given("the backend fails to stream any sentence")
def step_stream_error(context):
    context.events = [AnswerStreamEvent(kind=ERROR, error_code="ERR_UPSTREAM", error_reason="unavailable")]


@when("the streamed turn runs end to end")
def step_run_streamed(context):
    processor = AnswerProcessor(
        _ScriptedStreamBackend(context.events), _envelope(), backend_stream=True, filler_enabled_flag=False
    )
    down, _up = asyncio.run(
        run_test(
            processor,
            frames_to_send=[TranscriptionFrame(text="pourquoi ma facture augmente", user_id="u", timestamp="")],
        )
    )
    context.spoken = _spoken(down)
    context.result = processor.result


@then('the sentences are spoken one frame each in order "{expected}"')
def step_sentences_in_order(context, expected):
    assert context.spoken == expected.split("|"), context.spoken


@then("the safe degraded fallback is spoken")
def step_safe_fallback(context):
    assert context.spoken == [DEGRADED_FALLBACK_TEXT], context.spoken


@then("the streamed turn outcome is success")
def step_outcome_success(context):
    assert context.result.outcome is AnswerOutcome.SUCCESS, context.result.outcome


@then("the streamed turn outcome is degraded")
def step_outcome_degraded(context):
    assert context.result.outcome is AnswerOutcome.DEGRADED, context.result.outcome
