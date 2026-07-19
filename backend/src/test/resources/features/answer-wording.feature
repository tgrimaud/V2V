Feature: Grounded answer wording
  So that the assistant speaks a helpful answer without ever inventing billing
  figures, the LLM wording step turns retrieved evidence into a concise reply, the
  output guardrail drops any amount not backed by evidence (DEC-002), and a blocked
  input is answered with a safe canned message without ever calling the LLM.

  Scenario: The assistant words a grounded answer from strong evidence
    Given retrieval returns strong billing evidence
    And the language model would reply "La hausse vient de la proration lors de votre changement d'offre."
    When the customer asks the assistant "Pourquoi ma facture a augmenté ?"
    Then the assistant voices the generated answer
    And the answer carries a confidence signal

  Scenario: The assistant never voices an amount that is not in the evidence
    Given retrieval returns strong billing evidence
    And the language model would reply "Votre facture est de 39,99 € ce mois-ci."
    When the customer asks the assistant "Combien vais-je payer ?"
    Then the assistant does not voice the generated answer
    And the assistant offers to reach a human advisor

  Scenario: A blocked input is answered without calling the language model
    Given the grounding pipeline blocks the input as off-topic
    When the customer asks the assistant "Quel temps fait-il demain ?"
    Then the assistant does not voice the generated answer
    And the language model is never called
