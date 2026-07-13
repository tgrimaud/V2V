Feature: STT validation across controlled audio fixtures
  As QA validating the first speech-to-text slice
  I want repeatable evidence of transcript quality, coverage, latency and safe failure
  So that a go/no-go decision for broader Voice2Voice work is possible

  Background:
    Given the QA STT fixture manifest

  # TASK-STT-001 / TASK-STT-002 - transcript quality reviewed per category
  Scenario: Each declared fixture category produces a reviewed transcript outcome
    When QA runs the STT validation harness over the fixture set
    Then every usable fixture category is scored against its reference transcript
    And every usable fixture meets the configured quality threshold

  # TASK-STT-002 / TASK-STT-006 (RF-004) - silence is a distinct, safe outcome
  Scenario: Silence is reported as unavailable without an invented transcript
    When QA runs the STT validation harness over the fixture set
    Then the silence fixture is reported as unavailable
    And the silence fixture transcript is empty

  # TASK-STT-002 - missing fixture categories are explicit
  Scenario: Declared fixture coverage is reported explicitly
    When QA runs the STT validation harness over the fixture set
    Then no declared fixture category is missing
    And the overall fixture set is reported as ready

  # TASK-STT-003 / US-036 - STT latency is observable and percentile-ready
  Scenario: STT latency is isolated and percentile-ready
    When QA runs the STT validation harness over the fixture set
    Then a latency distribution with p50, p95 and p99 is available
    And each fixture reports its isolated STT slice duration

  # TASK-STT-003 - STT failure is observable without leaking sensitive data
  Scenario: STT failure is observable without leaking a filesystem path
    Given an audio fixture whose transcript sidecar is missing
    When QA runs the STT validation path on that fixture
    Then the outcome is failed
    And a correlation id is recorded for the run
    And the sanitized failure reason contains no filesystem path
