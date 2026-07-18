Feature: Knowledge base ingestion
  So that the assistant answers from grounded, up-to-date content, the knowledge
  base is kept in sync with its source articles without re-processing content that
  has not changed, and stale content is removed.

  Background:
    Given an empty knowledge base

  Scenario: First synchronization ingests every source article
    Given the source provides 3 articles
    When the knowledge base is synchronized
    Then 3 articles are ingested
    And 0 articles are skipped

  Scenario: Re-synchronizing unchanged articles processes nothing
    Given the source provides 3 articles
    And the knowledge base has already been synchronized
    When the knowledge base is synchronized
    Then 0 articles are ingested
    And 3 articles are skipped

  Scenario: Editing an article re-ingests only that article
    Given the source provides 3 articles
    And the knowledge base has already been synchronized
    When article "a.md" is edited and the knowledge base is synchronized
    Then 1 article is ingested
    And the previous content of "a.md" is removed before re-ingestion

  Scenario: Removing a source article purges it from the knowledge base
    Given the source provides 3 articles
    And the knowledge base has already been synchronized
    When article "b.md" is removed from the source and the knowledge base is synchronized
    Then 1 article is deleted
    And "b.md" is no longer present in the knowledge base

  Scenario: An article with no domain tag is stored under the general domain
    Given the source provides an article with no domain tag
    When the knowledge base is synchronized
    Then the stored content carries the "general" domain
