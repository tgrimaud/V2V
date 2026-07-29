# ADR-0036: Communication style between the backend and the voice runtime

## Status

Proposed (2026-07-29)

## Context

The voice runtime (`voice-agent`, Python/Pipecat) and the answer backend (Java) are
two separate services. Today they communicate over a **synchronous request/response**
call: the runtime's `BackendAnswerPort.answer(request) -> AnswerResult` (HTTP adapter)
POSTs the transcript and blocks until the full answer is returned. One `correlation_id`
spans the turn.

Two questions have come up:

1. Should we introduce a message broker (RabbitMQ / Kafka) for **backend ↔ voice
   runtime** communication in general?
2. Should the **filler / acknowledgement phrase** (TASK-WEB-019 / US-020) be driven by
   an event over such a broker — in particular to tailor the phrase per detected intent
   (e.g. "pulling up your balance"), mirroring Pipecat's `on_function_calls_started`
   hook?

The dominant NFR on the live path is **latency** (ADR-0018 mouth-to-ear budget; Sprint 10
is explicitly a perceived-latency sprint). The live turn is also strictly **ordered**
(transcript → answer → TTS) and must correlate to the exact in-flight call.

It is useful to separate two very different communication concerns:

- **Flow A — live critical path** (transcript → answer → TTS, and any intra-turn signal
  such as the filler trigger): real-time, per-turn, correlated to one in-flight call,
  latency-bound.
- **Flow B — side/async events** (post-call summaries, audit transcripts, usage metering,
  KB-sync triggers, "call ended"/"escalation" fan-out, Genesys interaction records,
  asynchronous channels such as WhatsApp/email where the user is not waiting live):
  fire-and-forget, decoupled, potentially multi-consumer, latency-tolerant.

## Decision

1. **Flow A stays synchronous request/response.** Keep HTTP for `BackendAnswerPort`. When
   intra-turn streaming is needed (streaming tokens, or an early intra-turn signal), use
   the **backend's own SSE stream** (TASK-BE-007) over the *same in-flight request*, not a
   separate channel. If bidirectional real-time needs grow, the sanctioned evolution is
   **gRPC or WebSocket**, still point-to-point — **not** a broker.

2. **No message broker on Flow A.** A broker on the live path adds broker hops to a
   latency-reduction feature, and forces re-implementing request/response correlation on
   top of a bus (reply-to queues + correlation ids = RPC-over-broker anti-pattern), with
   at-least-once/ordering hazards that are unacceptable for a real-time turn.

3. **The filler-phrase trigger uses Flow A, never a broker.** Two designs, both broker-free:
   - **V1 — runtime-local timer (default):** the `AnswerProcessor` starts a timer around
     the backend call; if no answer/first-audio by a configurable perceived-wait threshold,
     it speaks **one generic** filler as a background task. No backend signal, no new
     channel; works with the current blocking port and stays deterministic in tests.
   - **Enhancement — tailored filler over the existing SSE stream:** to tailor the phrase
     to a detected intent, make the runtime adapter **stream-aware** and have the backend
     emit an **early intra-turn event** (e.g. `phase=retrieving` / `intent=...`) on its SSE
     stream **before** the first answer token. This is the split-architecture equivalent of
     Pipecat's `on_function_calls_started`; the SSE stream *is* the event channel. It reuses
     the in-flight request (trivial correlation, no ordering/wrong-turn risk, minimal
     latency).

4. **A broker is reserved for Flow B**, and only when a concrete async/fan-out/omnichannel
   need appears (targeted around Sprint 12 — telephony/Genesys and asynchronous channels).
   Because `BackendAnswerPort` (and any future event port) is a hexagonal **port**, the
   transport is an adapter detail: adopting a broker for Flow B later is an adapter change,
   not a rewrite. RabbitMQ vs Kafka is deferred to that decision (RabbitMQ for task
   queues / moderate volume / lower latency; Kafka for a high-throughput, replayable event
   log with independent consumers / audit / stream processing).

## Consequences

- The Sprint 10 latency theme is protected: no new infrastructure hop is added to the live
  turn, and the filler mechanism (TASK-WEB-019) ships with zero new infra in V1.
- Per-intent tailored fillers require the runtime adapter to consume the backend SSE stream
  and the backend to emit an early intra-turn event. Until that is built, the filler is a
  single generic phrase (with 2–3 random variants) driven by the runtime timer.
- No broker is introduced now; operational surface stays minimal for the pilot.
- A future Flow B eventing backbone remains open and low-cost to adopt thanks to the port
  abstraction; it must get its own ADR when chosen, including the RabbitMQ-vs-Kafka
  rationale and delivery/ordering/schema-versioning consequences.
- Cross-service trace correlation on the live path continues to rely on the shared
  `correlation_id` (ADR-0028 + the OTLP addendum, TASK-OBS-001), independent of transport.

## Alternatives Considered

- **Broker for backend ↔ runtime (Flow A):** rejected — adds latency to a latency feature,
  reintroduces RPC-over-broker correlation, and risks mis-ordered/late delivery on a
  real-time, per-turn path.
- **Broker specifically for the filler signal:** rejected — same live/correlated/latency
  nature as Flow A, plus the concrete failure mode of a filler arriving after the answer or
  for the previous turn, which is worse than no filler.
- **Separate WebSocket push channel for intra-turn signals:** deferred — a second channel to
  correlate to the in-flight call when the backend already has an SSE stream that can carry
  an early event; revisit only if SSE proves insufficient.
- **Do nothing (silence during long waits):** rejected — US-020 explicitly requires a spoken
  acknowledgement so the caller knows the turn is progressing.

## Related Documents

- TASK-WEB-019 (spoken filler / acknowledgement) and US-020 — `product-backlog/tasks/web-voice-tasks.md`, `product-backlog/stories/v1-user-stories.md`
- Sprint 10 — `product-backlog/sprints/sprint-10-pilot-latency.md`
- ADR-0013 / TASK-BE-007 (streaming-token answer over SSE)
- ADR-0018 (voice latency targets) and ADR-0029 (perceived-latency gate)
- ADR-0025 (barge-in / interruption) — the filler must remain interruptible
- ADR-0028 + TASK-OBS-001 (correlation id + observability, transport-independent)
- ADR-0009/0010/0011 (omnichannel contracts) — the future home of a Flow B eventing backbone
