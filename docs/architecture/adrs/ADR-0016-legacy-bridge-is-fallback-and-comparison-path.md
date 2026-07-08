# ADR-0016: Legacy Bridge Is A Fallback And Comparison Path

## Status

Accepted

## Context

The project still contains a custom voice bridge with browser WebSocket and
Twilio Media Streams support. It includes useful implementation work:

- browser-side VAD and barge-in for the React POC;
- custom turn detection for telephony experiments;
- latency instrumentation;
- low-level audio codec and Twilio protocol handling;
- fallback access to the shared Java backend.

ADR-0002 made Pipecat + Gradium the target V1 voice path. Keeping the bridge
without a clear status would make new contributors treat it as the primary
architecture.

## Decision

Keep the custom bridge as a legacy fallback, comparison, and low-level testing
path until a separate retirement decision removes it.

The target V1 voice path is `voice-agent/agent/bot.py` with Pipecat. New
architecture diagrams, product decisions, and channel designs must describe the
Pipecat path first.

Bridge-specific files such as `bridge_server.py`, `ws_server.py`,
`twilio_server.py`, `rag_processor.py`, browser VAD, and custom telephony helpers
must be labeled as legacy, fallback, or comparison unless they are explicitly
reused by the Pipecat path.

## Consequences

- The project preserves a working fallback while the Pipecat path is benchmarked.
- Documentation must not present bridge internals as the V1 target runtime.
- The bridge carries maintenance cost until retired.
- A future ADR should decide the removal policy once Pipecat covers the required
  web, telephony, latency, observability, and fallback needs.

## Alternatives Considered

- **Delete the bridge immediately**: deferred because it remains useful for
  comparison, fallback, and low-level audio tests.
- **Keep the bridge as the main path**: rejected by ADR-0002 because Pipecat is
  the accepted V1 target.
- **Document both paths equally**: rejected because it makes the target runtime
  ambiguous.

## Related Documents

- `docs/architecture/adrs/ADR-0002-pipecat-gradium-target-voice-path.md`
- `docs/architecture/adrs/ADR-0010-industrialization-requires-contracts-slos-and-observability.md`
- `docs/architecture/architecture.md`
- `README.md`
