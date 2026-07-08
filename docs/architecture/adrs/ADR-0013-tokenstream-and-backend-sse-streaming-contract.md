# ADR-0013: Backend Streaming Uses TokenStream And SSE

## Status

Accepted

## Context

Voice and text clients need partial answers before the full LLM response is
complete. The voice path especially benefits from early text chunks because
Pipecat can send sentence-sized text to TTS while the backend is still
generating the rest of the response.

Earlier documentation exposed Reactor `Flux<String>` as the domain streaming
contract. That leaked a framework type into the domain model.

## Decision

The domain streaming contract is `TokenStream`.

The Java backend exposes streaming answers through the shared conversation API,
currently as SSE on `/api/conversation/ask-stream`. Infrastructure adapters may
use Reactor, Spring AI streaming, or provider-specific streams internally, but
they must convert those technical streams to `TokenStream` before returning to
the domain.

Pipecat consumes the backend SSE stream and groups tokens into text suitable for
TTS. Text clients can consume the same backend streaming contract without going
through Pipecat.

## Consequences

- The domain remains pure Java and independent from Reactor.
- Voice and text channels share one backend streaming contract.
- Provider-specific streaming APIs are isolated inside adapters.
- Sentence grouping and audio playback remain voice-runtime concerns, not
  backend business rules.
- Voice latency targets and measurement conditions are governed by ADR-0018.
  Production SLO acceptance remains gated by ADR-0010.

## Alternatives Considered

- **Expose Reactor `Flux<String>` from the domain port**: rejected because it
  leaks a framework abstraction into the domain layer.
- **Use only blocking backend responses**: rejected because it delays voice TTS
  and worsens perceived latency.

## Related Documents

- `docs/architecture/adrs/ADR-0001-java-backend-owns-conversation-domain.md`
- `docs/architecture/adrs/ADR-0010-industrialization-requires-contracts-slos-and-observability.md`
- `docs/architecture/adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md`
- `docs/architecture/architecture.md`
- `docs/engineering/development-guide.md`
