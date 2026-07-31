Feature: Spoken filler / acknowledgement during a slow answer
  As a caller waiting for the bot to analyse my request
  I want a short spoken acknowledgement when the answer takes time
  So that the wait feels responsive and I know the turn is still progressing
  # TASK-WEB-019 / US-020 - runtime-local timer, generic phrase, no billing content,
  # interruptible. Trigger transport rationale: ADR-0036 (Flow A, no broker).

  Scenario: A slow answer is preceded by a short holding phrase
    Given a voice turn whose backend answer is slower than the filler threshold
    When the turn runs end to end
    Then a short holding phrase is spoken before the answer
    And the holding phrase carries no digit or amount
    And the filler is observable with the correlation id and the wait it triggered on

  Scenario: A fast answer is spoken without any filler
    Given a voice turn whose backend answers before the filler threshold
    When the turn runs end to end
    Then only the answer is spoken with no holding phrase
