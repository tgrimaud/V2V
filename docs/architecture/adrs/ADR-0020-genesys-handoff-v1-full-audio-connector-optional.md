# ADR-0020: Genesys Handoff In V1, Full Audio Connector Optional

## Status

Accepted

## Context

V1 requires a credible human escalation path for billing explanations. The target
contact-center environment uses Genesys Cloud CX, so an escalation that only
simulates transfer outside Genesys would not validate the real advisor journey.

At the same time, routing the entire bidirectional bot conversation through
Genesys Audio Connector adds integration, network, security and latency risk. The
billing V1 still needs to prove the core value first: read-only BSS/PDF evidence,
deterministic invoice comparison, safe LLM wording and reliable escalation.

Genesys offers two relevant integration shapes:

- advisor handoff, where the bot triggers a transfer and sends context into the
  contact-center journey;
- full voice routing, where Genesys is the telephony entry point and streams the
  complete bot conversation to Pipecat/Gradium through Audio Connector.

Terminology (important, see ADR-0040): **AudioHook is the WebSocket/TLS protocol**;
it exposes two distinct features. The **Bot Transcription Connector** feature is
**listen-only** (monitoring, transcription, analytics) and cannot play audio back to
the caller. The **Audio Connector** feature is **bidirectional** (the service receives
customer audio and sends bot audio back, with `playback-*`, barge-in and
`BotTurnResponse` events) and is the only feature that fits a Voice2Voice bot that must
**speak**. Wherever this ADR previously said "Audio Connector or AudioHook" as if
interchangeable, the correct target is the **Audio Connector** feature — bare
AudioHook transcription is not a V2V media path.

The target enterprise pattern should keep Genesys as the system of record for the
contact-center interaction: call ingestion, IVR and ANI context, compliance
recording, routing, queueing, supervision, agent desktop, and contact-center
analytics. The bot platform should not duplicate those responsibilities. It
should own the AI conversation workflow, billing reasoning, RAG, guardrails,
tool/API calls, escalation decision, and conversation memory.

## Decision

Genesys advisor handoff is part of V1.

The bot must prepare a Genesys-compatible handoff context when escalation is
triggered by:

- explicit customer request for a human advisor;
- insufficient, inconsistent, partial or unusable billing evidence;
- unresolved invoice delta that cannot be explained safely.

The mandatory V1 handoff context includes, subject to the pilot trust model:

- escalation reason;
- conversation summary;
- compared invoice periods;
- known evidence;
- missing or uncertain evidence;
- unresolved points;
- customer/session identifiers permitted for Genesys transfer;
- recommended next advisor action.

Full Genesys **Audio Connector** routing of the complete bot conversation remains a
bounded feasibility spike or pilot option. In that shape, a Genesys Architect flow
invokes the **Call Audio Connector** action, which forks the call audio to the voice
runtime over the AudioHook WebSocket and pauses the flow, streams audio to the runtime
and receives the resulting bot audio back, then resumes the flow. The Java backend is
still called through the normalized channel envelope and remains the source of truth
for conversation decisions. See ADR-0040 for the media/control/context plane split and
the Audio Connector constraints.

Full Genesys voice routing becomes V1 core only if the pilot environment
explicitly requires Genesys as the entry telephony layer.

When handoff occurs, the Genesys adapter must attach the backend-provided context
to the existing Genesys interaction before transferring to the normal advisor
queue. The target context includes transcript summary, detected intent,
escalation reason, customer/session identifiers allowed by the trust model,
evidence already gathered, unresolved points, and recommended next advisor
action.

## Consequences

- V1 escalation validates the real contact-center target instead of a mock-only
  handoff.
- The core billing explanation journey remains deliverable without making the
  whole voice path depend on Genesys integration readiness.
- Backlog items must distinguish Genesys advisor handoff from full Genesys Audio
  Connector routing.
- The handoff payload must stay owned by the Java backend so billing evidence,
  escalation policy and audit rules remain centralized.
- Any Audio Connector spike must measure the full round trip:
  Genesys -> voice runtime -> STT -> backend -> TTS -> Genesys.
- Customer identification should reuse Genesys IVR, ANI, or existing
  contact-center lookup context when available. The backend still enforces BSS
  access from the identity confidence and customer reference it receives.
- KPI reporting must combine Genesys Analytics for contact-center metrics with
  AI-layer metrics for containment, resolution without transfer, evidence
  coverage, sentiment, and per-step latency.
- Barge-in and interruption handling must be validated as an integration concern
  between Genesys media handling and the selected voice runtime, not as a
  backend-only behavior.

## Alternatives Considered

- **Make full Genesys Audio Connector mandatory in V1**: rejected because it adds
  avoidable integration and latency risk before billing value is proven.
- **Keep Genesys entirely post-MVP**: rejected because V1 escalation would not
  match the target contact-center environment.
- **Use only Twilio for V1 escalation**: rejected as a technical fallback, not a
  representative advisor handoff for the target organization.

## Related Documents

- `docs/architecture/adrs/ADR-0040-genesys-audio-connector-v2v-media-plane.md`
- `docs/architecture/adrs/ADR-0019-escalation-rules-and-handoff-contract.md`
- `docs/architecture/adrs/ADR-0017-billing-v1-with-general-support-foundation.md`
- `docs/architecture/adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md`
- `docs/product/v1-scope.md`
- `product-backlog/decisions/v1-decisions.md`
