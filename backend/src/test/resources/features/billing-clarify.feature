Feature: Bounded billing clarifying dialogue (US-043 increment C)
  As a customer who reports a billing problem by voice or text,
  I want the assistant to ask a few short questions to understand what is wrong,
  So that I get a relevant answer (or a well-prepared transfer) instead of a generic enumeration.

  Background:
    Given the billing clarifying budget is 2 questions

  Scenario: An under-specified billing problem is clarified before answering
    When the customer sends "J'ai un problème avec ma facture"
    Then the assistant asks a clarifying billing question
    And it does not answer from the knowledge base yet
    # BR1, BR2, BR4

  Scenario: The clarifying dialogue is bounded
    Given the customer has already been asked 2 clarifying billing questions
    When the customer sends "J'ai un problème avec ma facture"
    Then the assistant offers to transfer the customer to a human advisor
    And it does not ask another clarifying question
    # BR3

  Scenario: A specific, answerable billing question is answered directly
    When the customer sends "J'ai un problème : ma facture a augmenté de 10 euros"
    Then the assistant answers from the knowledge base
    # BR5

  Scenario: A request for a human is not intercepted
    When the customer sends "J'ai un problème avec ma facture, je veux parler à un conseiller"
    Then the clarifying flow does not intercept the turn
    # BR5

  Scenario: Clarifying wording follows the session language
    When the customer sends "J'ai un problème avec ma facture"
    Then the clarifying question is in French
    # BR6

  Scenario: No invented amounts in a clarifying question
    Given the language model would propose a clarifying question mentioning an amount
    When the customer sends "J'ai un problème avec ma facture"
    Then the assistant offers to transfer the customer to a human advisor
    And the response contains no amount
    # BR4, DEC-002
