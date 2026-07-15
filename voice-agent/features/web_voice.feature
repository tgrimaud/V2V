Feature: Web voice STT ingress
  As a customer using the web voice chat
  I want my spoken question captured and transcribed by the voice runtime
  So that the page can show what I asked before the bot answers

  # TASK-WEB-001 / US-019 (STT half) - captured audio is transcribed and observable
  Scenario: Web voice input is transcribed and observable
    Given a web voice turn with captured PCM audio
    When the web voice ingress transcribes the turn
    Then the transcript is returned to the page
    And a real channel-ingress span records the received audio bytes
    And the STT slice latency and correlation id are observable

  # TASK-WEB-001 / US-019 (STT half) - provider failure stays safe and sanitized
  Scenario: Web voice STT failure stays safe and sanitized
    Given a web voice turn whose STT provider fails with a filesystem path
    When the web voice ingress transcribes the turn
    Then no transcript is invented on the page
    And a stable error code and sanitized reason are exposed
    And the sanitized reason contains no filesystem path

  # TASK-WEB-003-D / US-019 - the loop answers (backend) instead of echoing
  Scenario: The web voice loop answers instead of echoing
    Given a web voice turn processed by the pipecat runtime
    When the runtime runs the full voice turn
    Then the phrase is transcribed, answered by the backend and spoken back
    And the spoken reply is the backend answer, not the transcript
    And the pipeline slices are observable via telemetry

  # TASK-WEB-003-F / US-019 - safe spoken fallback when the backend cannot answer
  Scenario: Safe fallback when the backend cannot answer
    Given a web voice turn whose backend is unavailable
    When the runtime runs the full voice turn
    Then no billing content is invented in the reply
    And a safe spoken fallback is rendered to the customer
    And the degraded outcome is observable without leaking secrets

  # TASK-WEB-005 / TASK-WEB-003-D - both runtimes are behaviour-equivalent (identical output)
  Scenario: Both voice runtimes produce identical audio
    Given the same captured audio for both runtimes
    When the turn is processed by the stdlib and pipecat runtimes
    Then both runtimes produce identical WAV output
