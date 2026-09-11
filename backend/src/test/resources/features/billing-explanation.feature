Feature: Billing explanation behind the answer engine
  So that a customer understands why their bill changed without the assistant ever
  inventing a figure, the backend resolves the customer's identity, deterministically
  compares their two most recent invoices and hands the computed result to the LLM to
  rephrase (DEC-002). The bot escalates fail-closed when identity is unverified or the
  change cannot be explained, and redirects a non-billing question without any billing data.

  Scenario: A verified customer whose discount expired gets a grounded explanation
    Given a customer whose recent discount expired
    And the language model rephrases the explanation as "Votre facture a augmenté de 5.00 € en raison de la fin d'une remise."
    When the customer asks why their bill increased
    Then the assistant voices a grounded explanation
    And the explanation mentions "5.00 €"
    And the assistant does not escalate

  Scenario: The assistant never voices an amount that was not computed (DEC-002)
    Given a customer whose recent discount expired
    And the language model would fabricate "Vous devez 99,00 € au total."
    When the customer asks how much they must pay
    Then the assistant does not voice that answer
    And the assistant hands the customer to an advisor

  Scenario: An unknown customer reference reveals no billing data and escalates
    Given a customer reference that matches no account
    When the customer asks why their bill increased
    Then the assistant asks the customer to identify without revealing any billing amount
    And the assistant escalates the identity for a human advisor

  Scenario: An ambiguous customer reference never guesses the account
    Given a customer reference that matches several accounts
    When the customer asks why their bill increased
    Then the assistant asks the customer to identify without revealing any billing amount
    And the assistant escalates the identity for a human advisor

  Scenario: A customer with too little history is escalated rather than answered
    Given a customer with a single invoice on file
    When the customer asks why their bill increased
    Then the assistant does not voice that answer
    And the assistant escalates because the bill cannot be explained

  Scenario: An unusable pair of invoices is escalated instead of guessed
    Given a customer whose two invoices have no billable lines
    When the customer asks why their bill increased
    Then the assistant does not voice that answer
    And the assistant escalates because the bill cannot be explained

  Scenario: A verified customer whose bill is unchanged is told so
    Given a customer whose bill did not change
    And the language model rephrases the explanation as "Votre facture est identique au mois précédent."
    When the customer asks why their bill increased
    Then the assistant voices a grounded explanation
    And the explanation mentions "identique"
    And the assistant does not escalate

  Scenario: A non-billing question is redirected without touching billing data
    Given a customer whose recent discount expired
    When the customer asks a question unrelated to billing
    Then the assistant redirects to a billing question without calling the language model
