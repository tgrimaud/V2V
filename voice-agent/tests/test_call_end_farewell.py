"""Tests for the end-of-call farewell processor (TASK-WEB-010, ADR-0035).

On a customer closing formula the processor speaks a confirmation, suppresses the answer,
and ends the call on an explicit "done" confirmation OR a bounded silence — while a
follow-up request cancels the farewell and is answered normally. Ending is delegated to an
injected callback so the processor stays transport-agnostic and unit-testable.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipecat.frames.frames import TextFrame, TranscriptionFrame  # noqa: E402
from pipecat.tests.utils import SleepFrame, run_test  # noqa: E402

from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice.call_end_farewell import (  # noqa: E402
    DEFAULT_CLOSING_MESSAGE,
    DEFAULT_CONFIRM_PROMPT,
    SIGNAL_CONFIRMATION,
    SIGNAL_SILENCE,
    CallEndFarewellProcessor,
)
from web_voice.closing_intent import ClosingIntentDetector  # noqa: E402


def _envelope() -> SimpleNamespace:
    return SimpleNamespace(correlation_id="corr-1")


def _transcript(text: str) -> TranscriptionFrame:
    return TranscriptionFrame(text=text, user_id="u", timestamp="")


class _EndCallSpy:
    def __init__(self) -> None:
        self.signals: list[str] = []

    async def __call__(self, signal: str) -> None:
        self.signals.append(signal)


def _plain_texts(frames) -> list[str]:
    return [f.text for f in frames if type(f) is TextFrame]


def _transcripts(frames) -> list[str]:
    return [f.text for f in frames if isinstance(f, TranscriptionFrame)]


class ClosingDetectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_non_closing_turn_flows_through_to_the_answer_stage(self) -> None:
        # GIVEN a farewell processor and an ordinary question
        processor = CallEndFarewellProcessor(ClosingIntentDetector(), _envelope())
        # WHEN the question flows through
        down, _up = await run_test(processor, frames_to_send=[_transcript("pourquoi ma facture augmente")])
        # THEN the transcript is forwarded (to be answered) and nothing is spoken by us
        self.assertIn("pourquoi ma facture augmente", _transcripts(down))
        self.assertEqual([], _plain_texts(down))

    async def test_a_closing_speaks_the_confirmation_and_suppresses_the_answer(self) -> None:
        # GIVEN a farewell processor
        processor = CallEndFarewellProcessor(ClosingIntentDetector(), _envelope())
        # WHEN the customer says a standalone closing
        down, _up = await run_test(processor, frames_to_send=[_transcript("au revoir")])
        # THEN the confirmation is spoken and the closing transcript is NOT forwarded to answer
        self.assertIn(DEFAULT_CONFIRM_PROMPT, _plain_texts(down))
        self.assertEqual([], _transcripts(down))


class ConfirmationTurnTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_done_confirmation_speaks_the_closing_and_ends_the_call(self) -> None:
        # GIVEN a farewell processor with a teardown spy
        spy = _EndCallSpy()
        processor = CallEndFarewellProcessor(ClosingIntentDetector(), _envelope(), end_call=spy)
        # WHEN the customer says a closing then confirms they are done
        down, _up = await run_test(
            processor, frames_to_send=[_transcript("au revoir"), _transcript("non merci, c'est tout")]
        )
        # THEN the closing message is spoken and the call is ended with the confirmation signal
        self.assertIn(DEFAULT_CONFIRM_PROMPT, _plain_texts(down))
        self.assertIn(DEFAULT_CLOSING_MESSAGE, _plain_texts(down))
        self.assertEqual([SIGNAL_CONFIRMATION], spy.signals)
        self.assertEqual(SIGNAL_CONFIRMATION, processor.last_end_signal)

    async def test_a_follow_up_question_cancels_the_farewell_and_is_answered(self) -> None:
        # GIVEN a farewell processor with a teardown spy
        spy = _EndCallSpy()
        processor = CallEndFarewellProcessor(ClosingIntentDetector(), _envelope(), end_call=spy)
        # WHEN the customer says a closing but then asks something else
        down, _up = await run_test(
            processor,
            frames_to_send=[_transcript("au revoir"), _transcript("en fait, une question sur mon forfait")],
        )
        # THEN the call is NOT ended and the follow-up transcript is forwarded to be answered
        self.assertEqual([], spy.signals)
        self.assertIn("en fait, une question sur mon forfait", _transcripts(down))

    async def test_silence_after_the_confirmation_ends_the_call(self) -> None:
        # GIVEN a farewell processor with a very short confirmation window
        spy = _EndCallSpy()
        processor = CallEndFarewellProcessor(
            ClosingIntentDetector(), _envelope(), end_call=spy, confirm_timeout_s=0.05
        )
        # WHEN the customer says a closing then stays silent past the window
        down, _up = await run_test(
            processor, frames_to_send=[_transcript("au revoir"), SleepFrame(sleep=0.2)]
        )
        # THEN the closing is spoken and the call ends with the silence signal
        self.assertIn(DEFAULT_CLOSING_MESSAGE, _plain_texts(down))
        self.assertEqual([SIGNAL_SILENCE], spy.signals)


class FarewellTelemetryTest(unittest.IsolatedAsyncioTestCase):
    async def test_records_lifecycle_events_with_safe_attributes_only(self) -> None:
        # GIVEN a recorder and a standalone closing followed by a done confirmation
        telemetry = TelemetryRecorder()
        processor = CallEndFarewellProcessor(
            ClosingIntentDetector(), _envelope(), telemetry, end_call=_EndCallSpy()
        )
        # WHEN the farewell completes
        await run_test(
            processor, frames_to_send=[_transcript("Au revoir !"), _transcript("non c'est tout")]
        )
        # THEN the detection + end events are recorded under the correlation id
        names = {event.name for event in telemetry.events()}
        self.assertIn("voice.call_end.closing_detected", names)
        self.assertIn("voice.call_end.confirmed", names)
        confirmed = next(e for e in telemetry.events() if e.name == "voice.call_end.confirmed")
        self.assertEqual(SIGNAL_CONFIRMATION, confirmed.attributes["signal"])
        self.assertEqual("corr-1", confirmed.attributes["correlation_id"])
        # AND every recorded attribute is a safe key (no raw transcript field is recorded)
        allowed_keys = {"correlation_id", "matched_phrase", "signal"}
        for event in telemetry.events():
            self.assertTrue(set(event.attributes).issubset(allowed_keys), event.attributes)


if __name__ == "__main__":
    unittest.main()
