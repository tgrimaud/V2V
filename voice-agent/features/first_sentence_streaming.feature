Feature: Stream the backend answer to TTS on the first vetted sentence (TASK-WEB-020, lever 1)
  As a caller on the streaming voice path
  I want the bot to start speaking the first vetted sentence as soon as it is ready
  So that perceived time-to-first-audio drops without ever voicing unsafe content

  Background:
    Given a voice turn with the backend answer streaming enabled

  Scenario: Each vetted sentence is spoken as its own frame, in order
    Given the backend streams the sentences "Bonjour." then "Votre facture a augmente."
    When the streamed turn runs end to end
    Then the sentences are spoken one frame each in order "Bonjour.|Votre facture a augmente."
    And the streamed turn outcome is success

  Scenario: A blocked sentence speaks the safe hand-off and degrades
    Given the backend blocks a sentence and streams only the safe hand-off "Un conseiller pourra vous aider."
    When the streamed turn runs end to end
    Then the sentences are spoken one frame each in order "Un conseiller pourra vous aider."
    And the streamed turn outcome is degraded

  Scenario: A backend error mid-answer speaks the safe fallback
    Given the backend fails to stream any sentence
    When the streamed turn runs end to end
    Then the safe degraded fallback is spoken
    And the streamed turn outcome is degraded
