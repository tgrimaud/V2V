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

Full Genesys Audio Connector routing of the complete bot conversation remains a
bounded feasibility spike or pilot option. It becomes V1 core only if the pilot
environment explicitly requires Genesys as the entry telephony layer.

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
  Genesys -> Pipecat -> Gradium STT -> backend -> Gradium TTS -> Genesys.

## Alternatives Considered

- **Make full Genesys Audio Connector mandatory in V1**: rejected because it adds
  avoidable integration and latency risk before billing value is proven.
- **Keep Genesys entirely post-MVP**: rejected because V1 escalation would not
  match the target contact-center environment.
- **Use only Twilio for V1 escalation**: rejected as a technical fallback, not a
  representative advisor handoff for the target organization.

## Related Documents

- `docs/architecture/adrs/ADR-0019-escalation-rules-and-handoff-contract.md`
- `docs/architecture/adrs/ADR-0017-billing-v1-with-general-support-foundation.md`
- `docs/architecture/adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md`
- `docs/product/v1-scope.md`
- `product-backlog/decisions/v1-decisions.md`
