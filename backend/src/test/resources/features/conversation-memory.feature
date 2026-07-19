Feature: Stateful conversation memory
  So that the voice assistant sustains a natural multi-turn exchange, the conversation
  endpoint keeps a short memory per conversation: a follow-up question is answered with the
  earlier turns as context (the current turn excluded), the first turn is treated as a fresh
  start while later turns are treated as ongoing, and separate conversations never share
  context.

  Scenario: A follow-up question is answered with the earlier turn as context
    Given a fresh conversation memory
    And retrieval returns answerable evidence
    When the customer says "Pourquoi ma facture change ?" in conversation "c1"
    And the customer then says "Et le mois prochain ?" in conversation "c1"
    Then the language model received the previous turn as context
    And the follow-up is treated as an ongoing conversation

  Scenario: The very first turn of a conversation is treated as a fresh start
    Given a fresh conversation memory
    And retrieval returns answerable evidence
    When the customer says "Bonjour" in conversation "c1"
    Then the turn is treated as the start of the conversation
    And the language model received no prior context

  Scenario: Separate conversations never share context
    Given a fresh conversation memory
    And retrieval returns answerable evidence
    When the customer says "Question A" in conversation "c1"
    And the customer says "Question B" in conversation "c2"
    Then the language model received no prior context
    And conversation "c2" is treated as a fresh start
