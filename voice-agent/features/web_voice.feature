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
