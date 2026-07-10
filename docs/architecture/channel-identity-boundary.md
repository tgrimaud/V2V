# Channel And Identity Boundary

> **Branch state (`feat/restart-from-scratch`):** this document defines the
> **target** responsibility boundary. US-003 validated that boundary **as a design**,
> not as built software. On this branch, only the STT-in slice exists (web voice
> ingress → Gradium transcript + channel-ingress telemetry). TTS, turn detection,
> barge-in, the backend, guardrails, escalation and Genesys handoff are target,
> not implemented here.

## Objective

This document confirms the V1 product-visible boundary between channels, the
voice runtime, the Java backend, BSS evidence and Genesys handoff.

It satisfies `US-003` for the STT validation sprint by making clear that channels
provide trusted context and media transport, while the backend owns billing
reasoning, guardrails, escalation policy and handoff content.

## Governing Decisions

| Source | Decision Used Here |
|---|---|
| `ADR-0002` | Pipecat + Gradium is the target V1 voice path; the backend does not own real-time audio orchestration |
| `ADR-0009` | Channels are independent adapters that call the shared Java backend |
| `ADR-0020` | Genesys is the contact-center system of record; the backend owns AI conversation decisions and handoff content |
| `docs/product/v1-scope.md` | Voice2Voice is mandatory; customer identification should reuse channel, Genesys or BSS context when available |
| `docs/operations/development-workflow.md` | Runtime behavior must be observable through OpenTelemetry traces, metrics and structured logs |

## Responsibility Boundary

| Area | Owner | Responsibility |
|---|---|---|
| Web voice channel | Channel adapter / voice runtime | Capture customer audio, carry media, expose channel/session metadata, and surface the bot response to the customer |
| Phone channel | Channel adapter / voice runtime | Carry telephony audio, expose call/session metadata, and preserve channel-specific constraints |
| Genesys Cloud CX | Contact-center system of record | Call ingestion, IVR/ANI context when available, recording, routing, queueing, supervision, agent desktop and advisor handoff workflow |
| Voice runtime | Pipecat/Gradium target path | Real-time media orchestration, STT/TTS provider calls, turn detection, barge-in behavior and first voice latency markers |
| Java backend | Conversation intelligence owner | Billing reasoning, BSS evidence orchestration, deterministic comparison, guardrails, RAG, escalation decision, conversation memory and handoff content |
| BSS | Billing source of truth | Read-only invoices, periods, customer billing context, billing events and evidence used to justify invoice explanations |
| QA / observability | Delivery validation | Functional validation, STT evidence, latency by slice, OpenTelemetry evidence and bug tickets when defects are found |

## Identity Boundary

Channels may provide trusted identity context, but they do not decide whether
billing evidence may be exposed.

For V1:

- phone identity may come from Genesys IVR, ANI lookup, contact-center context or
  another accepted pilot identity source;
- web voice identity may come from the web session, pilot context, authenticated
  web context or another accepted identity source;
- BSS context confirms which customer account and billing periods can be used;
- the backend enforces whether the received identity confidence is sufficient for
  invoice access;
- if identity is incomplete, conflicting or not trusted enough, the backend must
  ask for clarification or start the appropriate escalation path;
- channels must not duplicate BSS access rules or expose invoice data on their
  own.

The exact identity confidence model remains governed by `OQ-001`.

## Conversation Boundary

Channels and the voice runtime transport customer turns. They do not own the
business conversation.

The backend owns:

- conversation state that affects billing explanation;
- business intent and routing;
- guardrails;
- whether evidence is sufficient;
- whether escalation is required;
- the summary and evidence passed to an advisor;
- audit-oriented outcome data.

The voice runtime owns:

- audio capture and playback;
- turn detection;
- STT and TTS provider interaction;
- interruption and barge-in mechanics;
- channel-specific voice timing markers.

## STT Sprint Boundary

For the STT validation sprint, the goal is not to deliver the full invoice
explanation journey. The goal is to validate the first voice input boundary:

1. controlled audio reaches the voice runtime;
2. the STT provider returns a transcript or a safe failure outcome;
3. the transcript can be associated with the channel/session/correlation context;
4. STT duration and outcome are observable separately from backend reasoning;
5. missing identity, provider failure or unusable audio do not lead to invented
   transcript or billing behavior.

The STT sprint may use controlled utterances before invoice comparison and BSS
reasoning are implemented.

## Minimum Channel Envelope Direction

Before production-grade channels, adapters should converge toward an envelope
containing:

| Field | Purpose |
|---|---|
| `channel` | Identifies the origin such as `web_voice`, `phone` or `genesys_voice` |
| `conversation_id` | Links all turns belonging to the same backend conversation |
| `external_session_id` | Links to the channel/provider session, such as web session, call id or Genesys conversation id |
| `message_id` | Supports duplicate detection and traceability for each inbound event |
| `idempotency_key` | Prevents duplicate processing on retries |
| `reply_mode` | States whether response is sync, streaming, async, voice or handoff |
| `customer_reference` | Carries a safe customer/account reference when the channel or BSS trust model permits it |
| `identity_confidence` | States whether the customer identity is strong enough for billing access |
| `correlation_id` | Connects channel, voice runtime, backend, STT, TTS, BSS and handoff observability |

This envelope is a direction for implementation tickets. `US-003` confirms the
ownership boundary; it does not require the final API contract to be implemented.

## Open Questions

| Question | Owner | Impact |
|---|---|---|
| Which identity source is accepted for the phone journey? | Product / BSS / Security / Contact Center | Determines whether phone callers can access invoice explanations without extra clarification |
| Which identity source is accepted for the web voice journey? | Product / BSS / Security | Determines whether web voice can expose billing data |
| What confidence levels map to "continue", "clarify", or "escalate"? | Product / BSS / Security | Controls safe billing data exposure |
| Is Genesys only the handoff target for the pilot, or also the phone entry point? | Product / Contact Center / Architecture | Determines whether full Genesys voice routing is in the pilot path |

## Acceptance Evidence For US-003

`US-003` is accepted as the baseline for the STT validation sprint. It validates
the **boundary design** (who owns what), not a built implementation of every
responsibility below — on this branch only STT-in + channel-ingress telemetry is
implemented; the rest is target ownership.

Validation:

- **Validated by:** User
- **Validation date:** 2026-07-09

Evidence (boundary design; ✅ = implemented on this branch, ◻ = target):

- ✅ channels provide trusted context and media transport (web voice ingress);
- the voice runtime owns real-time media (✅ STT + ingress telemetry; ◻ TTS, turn
  detection and barge-in are target);
- ◻ the backend owns billing reasoning, guardrails, escalation policy and handoff
  content (target — no backend on this branch);
- Genesys remains the contact-center system of record, not the owner of
  conversation intelligence;
- unresolved identity details are recorded as open questions rather than guessed.
