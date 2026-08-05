# V1 Scope - Operator Invoice Explanation Assistant

> **Current delivery (refreshed 2026-08-05, `feat/sprint-11-remote-deployment`):**
> this document defines the **target** V1. What is **built** is the full **web
> Voice2Voice loop** with a **RAG-grounded answer engine**: web mic → Gradium STT
> (batch + streaming) → Java backend (RAG over pgvector, guardrails, three-band
> confidence, Redis-backed memory) → Gradium TTS (batch + streaming) → playback,
> over batch `POST /api/voice/turn` and streaming WebRTC with barge-in, plus the
> pilot deployment packaging (Docker/compose, HAProxy VIPs, CI, Ansible). The
> `time_to_first_audio` / mouth-to-ear latency slices are instrumented end-to-end
> (ADR-0029 pilot gate — currently **not met**, p95 ≈ 2142 ms).
>
> **NOT built yet (this whole "V1 Functional Scope" section is a target):**
> Billing/BSS access, invoice PDF extraction + deterministic comparison, customer
> identity, phone (Twilio) Voice2Voice, and Genesys/escalation handoff. Billing +
> identity are deferred to **Sprint 12+** (gated by OQ-001/003/004); telephony +
> Genesys to **Sprint 13** (gated by OQ-006). The runnable product is a
> **general-support RAG voice assistant on the web channel**, not yet the
> billing/invoice-explanation product described below. See
> `docs/architecture/reviews/full-adversarial-review-2026-08-05.md`,
> `docs/observability/voice-journey-timing.md`, and
> `product-backlog/backlog-index.md`.

## Product Hierarchy

This document is the canonical V1 value slice. It narrows the broader functional
specification in [`cahier-des-charges-fonctionnel.md`](cahier-des-charges-fonctionnel.md)
to the first business outcome: reliable invoice explanation based on BSS
evidence.

The broader support/RAG assistant is the product foundation and target vision.
Billing/BSS invoice explanation is the V1 value focus, as captured in
[ADR-0017](../architecture/adrs/ADR-0017-billing-v1-with-general-support-foundation.md).

The billing V1 scope is governed by:

- [ADR-0003](../architecture/adrs/ADR-0003-billing-v1-uses-read-only-bss-and-deterministic-comparison.md):
  BSS read-only evidence and deterministic comparison before LLM wording;
- [ADR-0004](../architecture/adrs/ADR-0004-bss-integration-through-typed-domain-ports.md):
  runtime BSS access through typed domain ports, not MCP;
- [ADR-0005](../architecture/adrs/ADR-0005-invoice-pdf-extraction-before-llm-explanation.md):
  invoice PDF extraction before explanation when no validated structured line
  endpoint is available;
- [ADR-0020](../architecture/adrs/ADR-0020-genesys-handoff-v1-full-audio-connector-optional.md):
  Genesys advisor handoff is V1 scope while full Genesys Audio Connector routing
  remains optional unless the pilot requires it;
- [Galaxion BSS integration plan](../integrations/galaxion/bss-integration-plan.md);
- [Invoice extraction JSON contract](../integrations/galaxion/invoice-extraction-json.md).

## Context

The application primarily targets the operator's end users and helps them
understand discrepancies in telecom billing.

It must be usable by phone or through a voice chat on a web page. The
Voice2Voice journey is mandatory in V1: the user must be able to ask their
question orally and receive an oral answer. This does not prevent also offering
written interaction when the channel allows it.

V1 will have read access to the operator's BSS data. The BSS is the source of
truth for invoices, contracts, offers, options, discounts, usage, billing events,
adjustments, payments, and changes in customer status.

## V1 Product Objective

Allow an end user to question the bot, primarily by voice, to understand why one
invoice or billing period differs from another.

The bot must rely on the identity and customer context provided by the activation
channel or by the BSS, retrieve the relevant data, compare the invoices or
periods involved, then return a reliable, detailed, and traceable explanation of
the price differences.

Target question:

> Why is the June invoice more expensive than the May invoice?

Expected answer:

> The invoice increases by EUR 18.40. This increase mainly comes from the
> expiration of a EUR 10 discount, EUR 6.90 of out-of-bundle data usage, and
> EUR 1.50 of prorated billing related to the activation of an option on June 14.

## Key Principle

The LLM must not guess the causes.

The system must first calculate discrepancies deterministically from BSS data,
then use AI to formulate a clear, educational, and contextualized explanation.

The knowledge base is used to explain business and pricing rules. It must not be
used to invent amounts or compensate for missing BSS data.

## V1 Functional Scope

> **Target — NOT IMPLEMENTED (2026-08-05).** Everything in this section (BSS
> access, invoice comparison, discrepancy explanation, phone journey, Genesys
> escalation) is the **target** V1 and is **not built** on the current stack
> (grep-verified: no billing/BSS/PDF/comparison/Genesys code in `backend/`). The
> shipped product answers from the knowledge base via RAG. Treat the "must"
> statements below as requirements for a future sprint, not delivered behavior.

### Access to BSS Data

For a given customer, the application must be able to retrieve:

- available invoices;
- detailed invoice lines, from deterministic invoice PDF extraction until a
  structured BSS line endpoint is validated behind `BssBillingPort`;
- active contracts and subscriptions during the compared periods;
- billed offers, options, and services;
- commercial discounts and their validity periods;
- billed or out-of-bundle usage;
- taxes, one-off fees, adjustments, and prorations;
- important billing events: offer change, option activation, cancellation,
  expired discount, goodwill gesture.

### Invoice Comparison

When no validated structured invoice-line endpoint exists, invoice PDFs must be
extracted into structured JSON before comparison, as defined by
[`ADR-0005`](../architecture/adrs/ADR-0005-invoice-pdf-extraction-before-llm-explanation.md)
and
[`invoice-extraction-json.md`](../integrations/galaxion/invoice-extraction-json.md).
Extraction status is part of the product behavior:

- `parseable`: comparison is allowed;
- `partial`: cautious comparison is allowed only on confirmed lines, with the
  unexplained remainder visible;
- `unusable`: comparison is forbidden and the bot must ask for clarification or
  escalate.

The application must compare two invoices or two periods and identify:

- lines that appeared;
- lines that disappeared;
- lines whose amount changed;
- usage variations;
- expired or modified discounts;
- one-off fees;
- adjustments;
- offer or option changes;
- tax or proration discrepancies.

The expected result is not only a technical diff. It must produce a
business-oriented causal analysis.

### Explanation of Discrepancies

The assistant must transform the detected discrepancies into an understandable
explanation.

The explanation must:

- start with the overall delta;
- list the main causes by decreasing impact;
- distinguish certain causes from probable causes;
- cite the BSS elements used as evidence;
- explain pricing rules if necessary;
- avoid any conclusion not justified by the available data.

### User Interaction

> **Partial (2026-08-05).** Built today: **web voice chat** oral Q&A (ask by voice,
> hear an oral answer) grounded in the knowledge base. NOT built: the **phone**
> channel, the invoice/discrepancy **summary + line-by-line + BSS-evidence** views
> (these depend on the unbuilt billing core), and writing-as-complementary-channel
> parity across all surfaces.

In V1, the end user must be able to:

- call the bot by phone;
- use voice chat from a web page;
- ask an oral question about an invoice or price discrepancy;
- receive a clear and explainable oral answer;
- use writing as a complementary channel when the interface allows it;
- view a summary of discrepancies on the web page;
- view line-by-line details when the web interface is available;
- obtain the BSS evidence associated with the explanation.

The core V1 value is invoice explanation based on BSS data, delivered in
Voice2Voice on phone and web voice channels.

### Escalation to a Human Agent

Escalation follows
[`ADR-0019`](../architecture/adrs/ADR-0019-escalation-rules-and-handoff-contract.md)
and
[`ADR-0020`](../architecture/adrs/ADR-0020-genesys-handoff-v1-full-audio-connector-optional.md).

The V1 target contact-center handoff is Genesys. The bot must be able to prepare
and trigger a Genesys advisor handoff in two cases:

- the customer explicitly asks to speak to an advisor;
- the bot cannot answer with a sufficient level of certainty, for example
  missing or inconsistent BSS data, or lack of evidence explaining the
  discrepancy.

In this case, the bot must clearly state the limitation encountered, summarize
the context already collected, and transmit useful elements to the human agent
so the customer does not have to repeat the entire request.

This requirement covers the Genesys escalation contract and advisor context. It
does not make the full Genesys Audio Connector bot path mandatory for V1: routing
the entire voice conversation through Genesys remains a pilot option or technical
spike unless the customer environment requires it.

The target contact-center pattern keeps Genesys Cloud CX as the system of record
for the call interaction. Genesys owns call ingestion, IVR/ANI-based context,
compliance recording, routing, queueing, supervision, agent desktop, and
contact-center reporting. The bot platform owns the AI conversation workflow,
RAG, guardrails, billing evidence retrieval, deterministic comparison, escalation
decision, and conversation memory.

If the pilot uses full Genesys voice routing, Genesys should route the call to a
virtual-agent flow or queue and stream audio to the voice runtime through
AudioHook or the selected Genesys media integration. The voice runtime handles
STT/TTS or speech-to-speech and barge-in, then calls the Java backend through the
normalized channel contract. If escalation is needed, the backend produces the
handoff context and the Genesys adapter attaches it to the existing interaction
before transfer to the normal advisor queue.

Customer identification should reuse Genesys IVR, ANI, or existing
contact-center lookup context when available. The AI layer must not duplicate
Genesys identity workflows, but the backend must still enforce its BSS access
rules from the received identity confidence and customer reference.

## Non-Functional Needs

### Reliability

Each explanation must be tied to precise BSS data.

If data is missing, the assistant must say so explicitly rather than producing
an unverifiable hypothesis.

### Traceability

Each cause of discrepancy must be linkable to:

- an invoice line;
- a BSS event;
- a pricing rule;
- usage;
- a discount;
- a contractual modification.

### Security

Access to the BSS involves sensitive data. V1 must provide for:

- a documented customer identification and access-control model for each pilot
  channel;
- a target path toward strong authentication and role-based access control before
  production exposure;
- logging of consultations;
- masking of unnecessary personal data;
- no sensitive personal data in application logs;
- read-only BSS access.

### Performance

The comparison must be fast enough for conversational use by an end user.

Recommended objective: initial comparison result in less than a few seconds on a
standard invoice.

Voice latency follows
[`ADR-0018`](../architecture/adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md):
the optimized voice journey aims for a first audible sentence around 700 ms, and
the measurable pilot acceptance criterion is `time_to_first_audio` p95 below
800 ms in a pre-warmed, co-located environment. This is not yet a contractual
production SLO.

The latency target must not lead to producing an unreliable explanation: if the
business analysis requires more time, the bot must be able to produce a fast oral
acknowledgement, then deliver the reliable explanation when the BSS evidence is
available.

Latency validation must be decomposed by brick before end-to-end acceptance. Each
brick should be measurable in isolation with a controlled fixture, then measured
again inside the complete voice journey using the same correlation id.

Recommended latency slices:

| Slice | Start | Stop | Primary test |
|---|---|---|---|
| Channel ingress | First customer audio frame accepted by channel | First audio frame received by voice runtime | WebRTC/Twilio/Genesys adapter integration test |
| Turn detection | User stops speaking | End-of-turn event accepted by voice runtime | Voice runtime test with recorded audio fixtures |
| STT | Audio chunk or utterance submitted to STT | Final transcript available | Provider adapter benchmark with short/long/noisy fixtures |
| Backend orchestration | Transcript submitted to backend | First backend token or first structured action | Backend integration test with fake LLM/BSS ports |
| BSS/PDF evidence | Evidence request started | Evidence object or extraction status available | Adapter/fixture test with nominal, partial, and unavailable cases |
| Deterministic comparison | Evidence object accepted | Invoice delta analysis available | Pure domain benchmark with fixed invoice fixtures |
| RAG/vector search | Retrieval query started | Top documents available | Vector adapter benchmark with warm and cold index |
| LLM wording | Prompt submitted | First token and final answer available | LLM adapter benchmark with streamed timing markers |
| TTS | Text chunk submitted | First playable audio frame available | TTS adapter benchmark with persistent and cold connections |
| Channel egress | First audio frame emitted by voice runtime | First audio frame playable by the customer channel | WebRTC/Twilio/Genesys adapter integration test |
| Genesys handoff | Escalation decision accepted | Interaction transferred or queued with context attached | Genesys sandbox/fake adapter contract test |

End-to-end reports must publish p50, p95, p99, min, max, mean, sample size,
channel, environment, provider configuration, warm/cold state, cache state, and
whether connections were already established. Genesys Analytics should be used
for contact-center KPIs such as queue time, transfer rate, handle time, and
abandonment. The AI layer should report containment, resolution without transfer,
evidence coverage, sentiment or satisfaction proxy, escalation reason, and all
per-step latency spans.

Barge-in and interruption handling must be tested as a cross-component behavior:
the channel media layer and the voice runtime must agree when user speech stops
assistant playback, cancels in-flight TTS, and decides whether the backend turn
should continue or be interrupted.

### Structuring V1 Technical Requirements

Some backlog items become direct prerequisites for the V1 scope because they
condition the Voice2Voice experience, omnichannel journeys, and operation in a
private cloud.

V1 must therefore provide for:

- real streaming STT and server-side turn-end detection to avoid depending only
  on browser VAD, especially on the phone channel;
- chunked streaming TTS and a persistent TTS connection to start the oral answer
  without waiting for complete audio generation;
- shared conversational state, for example Redis, to enable omnichannel journeys
  and backend scale-out;
- persistent conversational memory to resume a session and provide useful
  context in case of transfer to a human agent;
- a Genesys-compatible handoff contract for advisor escalation, including reason,
  summary, evidence, missing evidence and customer/session identifiers permitted
  by the pilot trust model;
- realistic BSS/PDF fixtures and invoice extraction status handling so the team
  can validate `parseable`, `partial`, and `unusable` cases before full BSS
  sandbox coverage is stable;
- span-based observability across the whole pipeline: STT, BSS retrieval,
  comparison, KB search, LLM first-token, TTS first-audio, and human agent
  transfer;
- co-location in a private cloud of the critical components on the voice path
  when the `time_to_first_audio` p95 below 800 ms pilot criterion must be met.

Generic knowledge-base connectors such as Confluence, generic PDF ingestion, or
database-backed KB sources are not V1 prerequisites. They remain post-MVP
enrichment work unless a missing billing rule blocks the first invoice
explanation slice. Invoice PDF extraction for billing evidence remains in V1 and
is distinct from generic KB PDF ingestion.

These requirements must remain linked to the backlog for splitting into epics
and user stories. The V1 scope explains why they are necessary; the backlog
carries the execution detail and priorities.

### AI and Voice Provider Agnosticism

The product core must remain agnostic to the providers and models used for the
LLM, STT, and TTS.

Business services must not depend directly on a specific provider or SDK. The
following capabilities must be exposed through application ports:

- generation or reformulation by LLM;
- speech-to-text transcription;
- text-to-speech synthesis;
- embeddings and vector search if necessary.

Concrete implementations may vary by environment: cloud solution, self-hosted
solution in a private cloud, local model, or managed provider. Changing provider
must not call into question the billing business model, the comparison engine, or
the bot's functional contract.

To start the POC/V1, the reference voice adapters will be based on Gradium for
STT/TTS capabilities and on Pipecat for real-time orchestration of the voice
pipeline. These choices serve as an operational starting point and benchmark
base, without closing the possibility of testing or replacing these solutions
later.

This agnosticism must also make it easy to test several LLM, STT, or TTS
solutions during the POC, benchmark, and industrialization phases. Choosing an
implementation must be possible by configuration or adapter replacement, without
modifying the business core or user journeys.

## Out of V1 Scope

- Modify an invoice.
- Automatically correct a billing error.
- Trigger a goodwill gesture.
- Issue a new invoice.
- Perform debt collection.
- Replace the BSS system.
- Give an answer without evidence when data is absent.

## V1 Success Criteria

V1 will be considered useful if it can correctly handle these cases:

- Phone call: the user orally asks why their invoice increased and receives an
  oral answer.
- Web voice chat: the user asks the same question from a web page and receives
  an oral answer, with a displayed summary.
- Why did my invoice increase this month?
- Which line explains the main difference?
- Is it due to an expired discount?
- Is it due to out-of-bundle usage?
- Was there an offer or option change?
- Can you summarize the explanation for a customer?
- Can you show me the evidence in the invoice or the BSS?
- I want to speak to an advisor.
- The bot transfers to a human agent when it cannot explain the discrepancy with
  enough certainty.
- If one invoice extraction is `partial`, the bot clearly separates confirmed
  causes from unexplained amounts.
- If one invoice extraction is `unusable`, the bot does not compare amounts and
  offers clarification or escalation.

## Synthetic Statement of Need

Build a voice assistant for operator billing analysis, targeting end users,
accessible by phone and by web voice chat, connected read-only to the BSS,
capable of comparing two customer invoices or periods, identifying the business
causes of price discrepancies, then producing a clear, reliable, and traceable
oral explanation based on BSS data and enriched by the pricing knowledge base.

## Expected Breakdown

Once this scope is validated, the breakdown can be organized around the
following epics:

- Read-only BSS connector.
- Billing domain model: invoice, contract, offer, usage.
- Invoice comparison engine.
- Explanation engine with BSS evidence.
- Invoice PDF extraction and BSS/PDF fixture validation.
- Phone Voice2Voice journey.
- Web Voice2Voice journey.
- Web interface for summary and evidence.
- Genesys advisor handoff and contact-center context transfer.
- Security, audit, and governance of BSS access.
- LLM / STT / TTS abstractions.
- OpenTelemetry-style observability, per-step latency measurement, and pilot
  performance reporting.
