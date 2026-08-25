Feature: External browser WebSocket audio transport socle and framing
  As an external customer on a browser off the pilot subnet
  I want a WebSocket audio path that needs no TURN
  So that I can talk to the bot through the existing TLS edge
  (TASK-WEB-026, ADR-0043, ADR-0042)

  # AC #1 - the socle accepts the path without FastAPI, on the shared async loop
  Scenario: A wss audio transport is available without FastAPI
    Given the voice bridge builds the WebSocket audio transport
    Then the transport is the websockets-based server variant
    And building it requires no FastAPI import

  # AC #2 - the wire framing demultiplexes JSON control from binary audio
  Scenario: The wire framing separates JSON control from binary audio
    Given an open WebSocket voice connection
    When the client sends a binary PCM16 16 kHz audio frame
    Then the server treats it as customer audio
    When the client sends a JSON control frame
    Then the server treats it as a control message, never as audio

  # AC #2 - control vocabulary is modelled on the Genesys AudioHook shape (reuse)
  Scenario: A barge-in control frame stops the bot for reuse by Genesys later
    Given an open WebSocket voice connection
    When the client sends a barge-in control frame
    Then the server raises an interruption on the voice pipeline
