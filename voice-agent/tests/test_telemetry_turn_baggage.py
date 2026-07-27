"""Tests for the per-turn identity baggage on TelemetryRecorder (TASK-WEB-017).

On the streaming path one recorder lives for the whole call, so the per-turn id must
be stamped on every span/event/metric/log of the current turn while the stable
per-conversation correlation_id keeps being passed explicitly by the emitters. The
recorder merges a small "turn baggage" set (conversation_id/message_id/turn_index)
into each record until the next begin_turn.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_common.telemetry import TelemetryRecorder  # noqa: E402


class TelemetryTurnBaggageTest(unittest.TestCase):
    def test_no_begin_turn_leaves_attributes_untouched(self) -> None:
        # GIVEN a recorder on which no turn was started (batch path: fresh recorder/turn)
        telemetry = TelemetryRecorder()
        # WHEN a span/event/metric/log is recorded
        telemetry.span("stt.request", 5.0, correlation_id="corr-1")
        telemetry.record("stt.transcript.final", correlation_id="corr-1")
        telemetry.metric("stt.time_to_final_ms", 5.0, correlation_id="corr-1")
        telemetry.log("info", "done", correlation_id="corr-1")
        # THEN only the explicit attributes are present (no baggage keys injected)
        self.assertEqual(telemetry.spans()[0].attributes, {"correlation_id": "corr-1"})
        self.assertEqual(telemetry.events()[0].attributes, {"correlation_id": "corr-1"})
        self.assertEqual(telemetry.metrics()[0].attributes, {"correlation_id": "corr-1"})
        self.assertEqual(telemetry.logs()[0].attributes, {"correlation_id": "corr-1"})

    def test_begin_turn_stamps_baggage_on_every_record_type(self) -> None:
        # GIVEN a turn is begun with a per-turn identity
        telemetry = TelemetryRecorder()
        telemetry.begin_turn(conversation_id="conv-1", message_id="msg-1", turn_index=1)
        # WHEN records are emitted with only the explicit correlation id
        telemetry.span("stt.request", 5.0, correlation_id="corr-1")
        telemetry.record("stt.transcript.final", correlation_id="corr-1")
        telemetry.metric("stt.time_to_final_ms", 5.0, correlation_id="corr-1")
        telemetry.log("info", "done", correlation_id="corr-1")
        # THEN each record carries both the explicit correlation id and the turn baggage
        for attributes in (
            telemetry.spans()[0].attributes,
            telemetry.events()[0].attributes,
            telemetry.metrics()[0].attributes,
            telemetry.logs()[0].attributes,
        ):
            self.assertEqual(attributes["correlation_id"], "corr-1")
            self.assertEqual(attributes["conversation_id"], "conv-1")
            self.assertEqual(attributes["message_id"], "msg-1")
            self.assertEqual(attributes["turn_index"], 1)

    def test_explicit_attribute_wins_over_baggage_on_key_clash(self) -> None:
        # GIVEN a turn baggage that also carries a conversation_id
        telemetry = TelemetryRecorder()
        telemetry.begin_turn(conversation_id="baggage-conv", turn_index=1)
        # WHEN an emitter passes its own conversation_id explicitly
        telemetry.span("x", 1.0, conversation_id="explicit-conv")
        # THEN the explicit value wins (baggage never overrides an explicit attribute)
        self.assertEqual(telemetry.spans()[0].attributes["conversation_id"], "explicit-conv")

    def test_second_begin_turn_replaces_the_previous_baggage(self) -> None:
        # GIVEN a first turn's records
        telemetry = TelemetryRecorder()
        telemetry.begin_turn(conversation_id="conv-1", message_id="msg-1", turn_index=1)
        telemetry.span("a", 1.0)
        # WHEN the next turn begins and records again
        telemetry.begin_turn(conversation_id="conv-1", message_id="msg-2", turn_index=2)
        telemetry.span("b", 1.0)
        # THEN each span carries its own turn's identity, not the other's
        first = next(s for s in telemetry.spans() if s.name == "a")
        second = next(s for s in telemetry.spans() if s.name == "b")
        self.assertEqual(first.attributes["turn_index"], 1)
        self.assertEqual(first.attributes["message_id"], "msg-1")
        self.assertEqual(second.attributes["turn_index"], 2)
        self.assertEqual(second.attributes["message_id"], "msg-2")


if __name__ == "__main__":
    unittest.main()
