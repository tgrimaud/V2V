Feature: Streaming VAD-based end-of-turn detection
  As the streaming voice runtime
  I want the end of a customer turn detected while audio streams
  So that the loop can react before the whole utterance buffer exists (TASK-STT-012)

  # TASK-STT-012 / US-036 - end-of-turn fires incrementally from streamed frames
  Scenario: End-of-turn fires from streamed audio frames
    Given a stream of speech frames followed by a trailing-silence window
    When the frames are streamed to the utterance aggregator
    Then an end-of-turn is fired before the full buffer is available
    And a voice.end_of_turn span with the turn correlation id is recorded

  # TASK-STT-012 / TASK-STT-009 - no invented boundary on a silent stream
  Scenario: No turn boundary is invented on a silent stream
    Given a stream that carries only silence
    When the frames are streamed to the utterance aggregator
    Then no end-of-turn is fired
    And no voice.end_of_turn span is recorded
