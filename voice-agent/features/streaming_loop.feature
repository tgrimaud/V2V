Feature: End-to-end streaming voice loop
  As the low-latency streaming voice runtime
  I want one turn to flow from streamed partials to the first bot audio frame
  So that the pilot time_to_first_audio metric is derivable end to end over the
  composed streaming STT -> backend answer -> streaming TTS path (TASK-WEB-009, US-036)

  # TASK-WEB-009 / US-036 - partials stream while speaking, the answer is spoken back
  # incrementally, and time_to_first_audio is derivable under one correlation id.
  # The live WebRTC transport loop is validated manually (Chrome DevTools MCP) per the
  # ticket; this scenario locks the composed streaming pipeline as a regression net.
  Scenario: A streaming turn answers with partials then incremental first audio
    Given a customer speaking a question on the streaming voice loop
    When the streaming loop runs the turn end to end
    Then partial transcripts stream before the final transcript
    And the bot answer is spoken back as incremental audio
    And the whole turn shares one correlation id
    And time_to_first_audio is derivable from the turn telemetry
