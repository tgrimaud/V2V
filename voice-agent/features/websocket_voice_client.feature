Feature: Interim browser WebSocket voice client wiring
  As an external customer on a browser off the pilot subnet
  I want to hold a Voice2Voice conversation over one wss connection
  So that I can reach the bot without TURN, through the TLS edge
  (TASK-WEB-028, ADR-0043, ADR-0042)

  # AC #1 - the signaling builds the shared session over the socle transport and runs it
  Scenario: The interim WebSocket voice path builds a session over the socle transport
    Given the interim WebSocket voice signaling with a French server default
    When the WebSocket voice path starts
    Then it assembles a session through the shared session factory
    And it runs that session on the background loop
    And it records the call with the effective language "fr"

  # Interim deferral - the declared language is captured for correlation, not applied
  Scenario: A client's declared language is captured but the interim answers in the server language
    Given the interim WebSocket voice signaling with a French server default
    And the WebSocket voice path has started
    When a browser client connects declaring the language "en"
    Then the declared language "en" is captured for correlation
    And the effective conversation language stays "fr"

  # AC #2 - a second concurrent conversation is refused by the single-client socle
  Scenario: The socle serves one conversation at a time
    Given the voice bridge builds the WebSocket audio transport for the client path
    Then the transport is the single-client server variant that refuses a second client
