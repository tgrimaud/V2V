Feature: Streaming STT partial and final transcripts
  As the low-latency voice runtime
  I want transcripts to stream while the customer speaks
  So that the final transcript lands shortly after end-of-turn instead of paying the
  whole-clip batch cost (TASK-STT-010, closes RF-007)

  # TASK-STT-010 / US-036 - partials during speech, final after end-of-turn
  Scenario: Partial transcripts stream during speech and a final lands after end-of-turn
    Given a customer speaking on the web voice page with a streaming STT provider
    When the audio streams to the streaming STT processor
    Then partial transcripts are emitted before end-of-turn
    And a final transcript is produced after end-of-turn
    And time-to-first-partial and time-to-final are observable via OpenTelemetry

  # TASK-STT-010 / TASK-STT-009 - no invented boundary, no stream opened on silence
  Scenario: A silent stream produces no transcript and opens no provider connection
    Given a silent stream on the web voice page with a streaming STT provider
    When the audio streams to the streaming STT processor
    Then no final transcript is produced
    And the streaming provider is never opened

  # TASK-WEB-018 - a streaming STT finalize failure must be audible, never silent
  Scenario: A streaming STT finalize failure speaks the safe degraded fallback
    Given a customer speaking but the streaming STT provider fails to finalize
    When the audio streams to the streaming STT processor
    Then no final transcript is produced
    And the safe degraded fallback is spoken to the customer
    And the spoken fallback contains no digit or amount
    And a degraded-spoken outcome event is recorded via OpenTelemetry
