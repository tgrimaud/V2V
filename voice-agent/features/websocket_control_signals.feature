Feature: Pluggable control-signal seam for barge-in and end-of-turn
  As the voice runtime owner preparing the Genesys Audio Connector
  I want barge-in and end-of-turn to be drivable from a pluggable control source
  So that browser control frames or Genesys protocol events can replace the energy
  detectors without touching the session core
  (TASK-WEB-029, ADR-0043, ADR-0040)

  # AC #2 - a pluggable source finalizes the turn without the energy detector
  Scenario: A pluggable control source ends the turn
    Given a streaming voice loop fed by a pluggable control source
    And the customer is speaking with no trailing silence
    When the control source emits an end-of-turn signal
    Then the current turn is finalized and transcribed
    And the end-of-turn came from the control source, not the energy detector

  # AC #1 - a pluggable source cuts the bot mid-answer (barge-in) over the seam
  Scenario: A pluggable control source barges in on the bot
    Given the bot is speaking an answer on the streaming voice loop with a control source
    When the control source emits a barge-in signal
    Then the spoken answer is cut and an interruption is broadcast
    And the barge-in is observable as a Genesys-named control signal
