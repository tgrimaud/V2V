Feature: WebSocket capacity ceiling and per-slice observability
  As the voice runtime operator on small shared LB VMs
  I want the WebSocket path to refuse extra sessions cleanly and emit per-slice evidence
  So that the pilot never crashes under load and QA can chart latency per journey slice
  (TASK-WEB-030, ADR-0043, ADR-0028, TASK-WEB-024)

  # AC #1 - an extra concurrent client is refused cleanly, and the refusal is observable
  Scenario: A WebSocket session past the ceiling is refused cleanly
    Given a started WebSocket signaling service with one connected client
    When an extra browser opens a wss voice connection
    Then it is refused with the single-client capacity reason and no crash
    And an active-session gauge and a refusal event are recorded

  # AC #2 - the end-of-call dump carries every canonical journey slice
  Scenario: A completed WebSocket call dumps the canonical per-slice spans
    Given a completed wss voice turn with only some slices measured
    When the per-call telemetry is dumped
    Then every canonical journey slice is present under one correlation id
    And a slice with no span is marked measured false, never omitted
