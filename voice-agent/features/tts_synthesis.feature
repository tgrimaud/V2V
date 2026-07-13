Feature: Voice response synthesis (voice-out)
  As a customer using the web voice chat
  I want the bot's response text spoken back to me
  So that the conversation is a full voice-in / voice-out loop

  # TASK-WEB-002 / US-019 (TTS half) - response text becomes observable audio
  Scenario: Reference response texts are synthesized to audio and observable
    Given the offline TTS provider and the reference response texts
    When the voice runtime synthesizes each reference text
    Then each reference text produces non-empty audio in the negotiated format
    And each synthesis emits a TTS first-audio span with its correlation id
    And the TTS request latency is observable per turn

  # TASK-WEB-002 - empty response text is not a failure and invents no audio
  Scenario: Empty response text yields no invented audio
    Given the offline TTS provider
    When the voice runtime synthesizes an empty response text
    Then the synthesis outcome is reported unavailable
    And no response audio is produced

  # TASK-WEB-002 - provider failure stays safe and sanitized (no secret leak)
  Scenario: Synthesis failure stays safe and sanitized
    Given a TTS provider that fails carrying a secret token
    When the voice runtime synthesizes a response text
    Then no response audio is invented
    And a stable TTS error code and sanitized reason are exposed
    And the sanitized TTS reason contains no secret token
