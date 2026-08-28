Feature: Genesys AudioHook connection authentication
  As the pilot runtime operator exposing the Genesys Audio Connector endpoint
  I want each AudioHook connection verified (API key + HMAC signature) before a session builds
  So that only the legitimate Genesys tenant can stream audio and the endpoint never opens unguarded
  (TASK-INFRA-012, ADR-0049, ADR-0001)

  # A correctly signed Genesys handshake is admitted
  Scenario: A correctly signed AudioHook connection is accepted
    Given a configured Genesys AudioHook authenticator
    When the official Genesys signed connection is verified
    Then the connection auth outcome is "accepted"

  # A forged/altered signature is refused (constant-time compare path)
  Scenario: A tampered signature is rejected
    Given a configured Genesys AudioHook authenticator
    When a connection with a tampered signature is verified
    Then the connection auth outcome is "rejected_bad_signature"

  # A connection presenting no API key is refused before the signature is even checked
  Scenario: A connection with no API key is rejected
    Given a configured Genesys AudioHook authenticator
    When a connection with no API key is verified
    Then the connection auth outcome is "rejected_missing_key"

  # Enabled-but-unconfigured must fail closed, never open
  Scenario: An enabled but unconfigured endpoint fails closed
    Given a Genesys AudioHook authenticator with no key or secret configured
    When the official Genesys signed connection is verified
    Then the connection auth outcome is "rejected_not_configured"

  # Every attempt is observable, and no secret material leaks into telemetry
  Scenario: Auth outcome telemetry is emitted without leaking the secret
    Given a configured Genesys AudioHook authenticator
    When the official Genesys signed connection is verified
    Then an auth-outcome event and metric are recorded on the Genesys channel
    And no secret, API key, or signature appears in the telemetry
