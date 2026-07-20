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

### Guarded emission (TASK-BE-007)

Streaming must not defeat the post-LLM output guardrail (ADR-0014 / DEC-002: the
assistant must never voice a currency amount that is not backed by evidence). Raw
token streaming would emit — and the voice runtime would speak — an ungrounded
amount before any check could run.

Decision: the backend emits **guarded, sentence-sized chunks**, not raw tokens.
The LLM tokens are buffered into sentences inside the domain; each completed
sentence is vetted by the output guardrail (amount-vs-evidence + non-answer
check) **before** it is emitted on the SSE stream. A sentence containing an
ungrounded amount is never emitted; the stream then emits the safe hand-off
message and terminates as a fallback. This preserves DEC-002 by construction
while still emitting the first sentence well before the full answer completes
(RF-021), because a TTS consumer needs at least a clause/sentence anyway, so the
practical latency cost versus raw tokens is largely absorbed by sentence grouping
that would otherwise happen in the runtime.

The concrete SSE contract is `POST /api/conversation/converse-stream` (mirrors the
ADR-0021 `/converse` request body: `transcript`, `conversation_id`,
`correlation_id`, `channel`), emitting:

- `chunk` events `{ "text": "<safe sentence>" }` as each vetted sentence is ready;
- one terminal `done` event `{ "text", "confidence?", "grounded" }`;
- a sanitized `error` event `{ error_code, message, correlation_id }` on failure.

The synchronous `/converse` endpoint stays available for non-streaming clients and
as the fallback path.

Latency is observable per ADR-0018/ADR-0028 with two new slices on the
`voice_support.slice` timer: `llm_first_token` (LLM start → first token) and
`backend_first_token` (request start → first emitted chunk), distinct from the
full-completion `llm_wording` / `backend_request` slices.

Known limitation: the guarded, buffered emission and the sentence boundary
heuristic (which never splits a decimal amount) are backend concerns here rather
than pure runtime concerns, a deliberate trade-off to keep DEC-002 enforceable on
the streamed path. The provider-side streaming call currently uses the SDK's
default WebClient (the ADR-0021/TASK-BE-012 read timeout applies to the sync
RestClient path); a streaming inter-chunk timeout is tracked as a follow-up.

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
