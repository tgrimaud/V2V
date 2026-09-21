Feature: Knowledge base sync resilience (BUG-022)
  So that a slow or failing embedding on one article can neither stall the whole
  corpus synchronization nor silently drop an article from the assistant's
  knowledge, synchronization keeps going when one article's embedding fails and
  marks an article as available only once it is fully stored — otherwise the
  article is retried on the next run instead of being silently lost.

  Scenario: One article's failed embedding does not abort the whole sync
    Given a knowledge article "welcome" that can be fully embedded
    And a knowledge article "billing-faq" whose embedding partially fails
    When the corpus is synchronized
    Then the synchronization completes without aborting
    And article "welcome" is available to the assistant

  Scenario: A partially embedded article is reported and retried, not silently lost
    Given a knowledge article "billing-faq" whose embedding partially fails
    When the corpus is synchronized
    Then article "billing-faq" is not yet available to the assistant
    And the partial ingestion of article "billing-faq" is reported for operators
    When article "billing-faq" can be fully embedded again
    And the corpus is synchronized
    Then article "billing-faq" is available to the assistant
