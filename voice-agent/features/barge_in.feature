Feature: Barge-in during a spoken answer
  As a customer on the streaming voice loop
  I want to interrupt the bot while it is speaking
  So that the assistant stops playback promptly and hears my new question
  (US-021, TASK-WEB-008)

  # TASK-WEB-008 / US-021 - onset while the bot speaks cuts the answer end to end
  Scenario: The customer interrupts the bot mid-answer
    Given the bot is speaking an answer on the streaming voice loop
    When the customer starts speaking while the bot is speaking
    Then the spoken answer is interrupted
    And an interruption is broadcast to the voice pipeline
    And the barge-in is observable via OpenTelemetry
    And the customer's new utterance is transcribed as the next turn

  # TASK-WEB-008 - no interruption when the bot is not speaking (normal turn)
  Scenario: A normal turn is not treated as a barge-in
    Given the bot is idle on the streaming voice loop
    When the customer speaks a normal turn
    Then no interruption is broadcast to the voice pipeline
    And no barge-in is recorded
    And the customer's utterance is transcribed
