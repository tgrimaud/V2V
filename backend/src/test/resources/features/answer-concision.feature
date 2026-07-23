Feature: Voice answers are kept concise without losing grounding (TASK-BE-018)
  So that long grounded answers stop dominating TTS synthesis time, the assistant is
  instructed to keep each spoken answer within a configured sentence budget, in the
  customer's own language. The budget only shortens a valid grounded answer: it never
  weakens grounding, never changes when the assistant hands off to a human, and can be
  disabled by configuration.

  Scenario: A configured budget instructs the model to stay within the sentence cap, in English
    Given the assistant is configured to keep answers within 3 sentences
    And the knowledge base has relevant support content
    When the customer asks the concise bot "Why is my bill higher this month?"
    Then the assistant still voices a grounded answer
    And the wording request caps the answer at 3 sentences
    And the concision instruction is written in English

  Scenario: A configured budget instructs the model to stay within the sentence cap, in French
    Given the assistant is configured to keep answers within 3 sentences
    And the knowledge base has relevant support content
    When the customer asks the concise bot "Pourquoi ma facture est-elle plus élevée ce mois-ci ?"
    Then the assistant still voices a grounded answer
    And the wording request caps the answer at 3 sentences
    And the concision instruction is written in French

  Scenario: Disabling the budget removes the concision instruction
    Given the assistant is configured with the answer budget disabled
    And the knowledge base has relevant support content
    When the customer asks the concise bot "Why is my bill higher this month?"
    Then the assistant still voices a grounded answer
    And the wording request carries no sentence cap

  Scenario: The budget does not change hand-off behavior when evidence is unusable
    Given the assistant is configured to keep answers within 3 sentences
    And the knowledge base has no usable evidence
    When the customer asks the concise bot "Is unlimited data roaming included in my current plan?"
    Then the assistant does not voice a grounded answer
    And a human advisor is offered
