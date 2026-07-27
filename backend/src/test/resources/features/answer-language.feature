Feature: Answer language follows the customer's question language (TASK-BE-015)
  So that a French or English customer is always understood, the assistant answers each
  turn in the language of that turn's question — consistently across grounded answers,
  the insufficient-evidence fallback, the off-topic refusal and the human-escalation
  offer — and falls back to the deployment default (English for the Eir pilot) when the
  turn is too ambiguous to decide, keeping the current conversation language on ties.

  Scenario: English question gets an English answer (BR1)
    Given the knowledge base has relevant English support content
    When the customer's turn is "Why is my bill higher this month?"
    Then the assistant answers in English

  Scenario: French question gets a French answer (BR1)
    Given the knowledge base has relevant French support content
    When the customer's turn is "Pourquoi ma facture est plus élevée ce mois-ci ?"
    Then the assistant answers in French

  Scenario: Customer language wins over the content language (BR5)
    Given the knowledge base has relevant English support content
    When the customer's turn is "Pourquoi ma facture change-t-elle autant ce mois-ci ?"
    Then the assistant answers in French

  Scenario: Insufficient-evidence fallback and escalation are in the customer's language (BR4/BR7)
    Given the assistant cannot find enough evidence to answer
    When the customer's turn is "Is unlimited data roaming included in my current plan?"
    Then the assistant's spoken reply is in English
    And the assistant offers a human advisor

  Scenario: Insufficient-evidence fallback and escalation are in the customer's language, French (BR4/BR7)
    Given the assistant cannot find enough evidence to answer
    When the customer's turn is "Est-ce que l'itinérance data illimitée est incluse dans mon forfait ?"
    Then the assistant's spoken reply is in French
    And the assistant offers a human advisor

  Scenario: Off-topic refusal is in the customer's language, English (BR4/BR7)
    When the customer's turn is "What's the weather like today?"
    Then the assistant's spoken reply is in English

  Scenario: Off-topic refusal is in the customer's language, French (BR4/BR7)
    When the customer's turn is "Quel temps fera-t-il demain ?"
    Then the assistant's spoken reply is in French

  # BUG-005/ADR-0034: a vague/low-information turn ("ok", "vas-y") is now asked to clarify before
  # any retrieval, and the clarify wording still follows the decided language, so the default and
  # stickiness paths stay covered on a contentless turn.
  Scenario: A vague turn clarifies in the deployment default language (BR2/BUG-005)
    Given the knowledge base has relevant English support content
    When the customer's turn is "ok"
    Then the assistant's spoken reply is in English

  Scenario: A vague follow-up clarifies in the current conversation language (BR3/BUG-005)
    Given the knowledge base has relevant English support content
    And the conversation so far has been in French
    When the customer's turn is "ok"
    Then the assistant's spoken reply is in French

  Scenario: A vague follow-up clarifies (not a weak answer) and keeps the language (BUG-002/BUG-005)
    Given the assistant cannot find enough evidence to answer
    And the conversation so far has been in French
    When the customer's turn is "ok"
    Then the assistant's spoken reply is in French
    And the assistant asks the customer to clarify
