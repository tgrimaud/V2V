Feature: End the call on a customer closing formula
  As a customer on the streaming voice loop
  I want the bot to end the call when I signal I am done
  So that I do not have to hang up manually
  (US-041, TASK-WEB-010, ADR-0035)

  # Happy path: a standalone closing -> confirmation turn -> spoken closing -> end of call
  Scenario: Customer says a closing formula and the call ends cleanly
    Given the streaming voice loop is active and the customer has their answer
    When the customer says a closing formula and then confirms they are done
    Then the bot asks whether they need anything else
    And the bot plays a short spoken closing
    And the closing turn is not sent to the backend as a question
    And the end-of-call reason is recorded as customer_farewell

  # False-positive guard: a closing word inside a longer request must not end the call
  Scenario: A closing word inside a longer request does not end the call
    Given the streaming voice loop is active and the customer has their answer
    When the customer uses a closing word as part of a longer request
    Then the call is not ended
    And the turn is answered normally by the backend
