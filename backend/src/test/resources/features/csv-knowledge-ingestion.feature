Feature: Operator CSV knowledge ingestion
  So that the assistant answers from the real operator support corpus, HTML support
  articles exported as CSV are ingested as clean, domain-classified knowledge through
  the same idempotent synchronization used by every other knowledge source.

  Scenario: An HTML support article is ingested as clean, domain-classified text
    Given an operator CSV article "196" classified as "billing" with HTML content:
      """
      <h1>Your bill</h1><p>Charges &amp; credits explained.</p>
      """
    When the operator knowledge base is synchronized
    Then the article is ingested under the "csv-article" source
    And the stored content is plain text without HTML tags
    And the stored operator content carries the "billing" domain

  Scenario: Re-synchronizing the unchanged CSV corpus processes nothing
    Given an operator CSV article "42" classified as "support" with HTML content:
      """
      <p>Reset your router to restore the connection.</p>
      """
    And the operator knowledge base has already been synchronized
    When the operator knowledge base is synchronized
    Then no operator article is ingested

  Scenario: Rows without an id or without content are skipped
    Given an operator CSV corpus with a blank-id row, an empty-content row and one valid row
    When the operator knowledge base is synchronized
    Then 1 operator article is ingested
