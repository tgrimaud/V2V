Feature: HTTP conversation backend adapter
  As the voice runtime
  I want to call a real conversation endpoint over HTTP
  So that the loop can answer with the operator's answer engine, safely

  # TASK-WEB-003-C / US-019 - map a real endpoint onto the conversation contract
  Scenario: The runtime can target a real conversation endpoint
    Given the http backend adapter with a fake transport
    When it answers a transcript
    Then it maps the endpoint response to the conversation contract
    And transport and timeout errors map to a sanitized degraded outcome
    And no secret appears in any error, log or telemetry
