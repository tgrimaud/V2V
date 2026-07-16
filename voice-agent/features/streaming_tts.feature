Feature: Streaming TTS incremental playback
  As the low-latency voice runtime
  I want the bot response audio to start on the first synthesized chunk
  So that the customer hears the answer before the whole clip is synthesized
  (TASK-WEB-004)

  # TASK-WEB-004 / US-036 - playback starts on the first audio chunk
  Scenario: The bot response audio starts before full synthesis
    Given a response text ready for the customer with a streaming TTS provider
    When the answer streams to the streaming TTS processor
    Then audio chunks are emitted incrementally before synthesis completes
    And time-to-first-audio is observable via OpenTelemetry

  # TASK-WEB-004 - never invent audio on a non-success outcome
  Scenario: An empty answer produces no audio and stays observable
    Given an empty response for the customer with a streaming TTS provider
    When the answer streams to the streaming TTS processor
    Then no audio is produced
    And an unavailable TTS outcome is observable via OpenTelemetry
