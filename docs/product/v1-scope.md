# V1 Scope - Operator Invoice Explanation Assistant

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

### Access to BSS Data

For a given customer, the application must be able to retrieve:

- available invoices;
- detailed invoice lines;
- active contracts and subscriptions during the compared periods;
- billed offers, options, and services;
- commercial discounts and their validity periods;
- billed or out-of-bundle usage;
- taxes, one-off fees, adjustments, and prorations;
- important billing events: offer change, option activation, cancellation,
  expired discount, goodwill gesture.

### Invoice Comparison

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
[`ADR-0019`](../architecture/adrs/ADR-0019-escalation-rules-and-handoff-contract.md).

The bot must be able to transfer the conversation to a human agent in two cases:

- the customer explicitly asks to speak to an advisor;
- the bot cannot answer with a sufficient level of certainty, for example
  missing or inconsistent BSS data, or lack of evidence explaining the
  discrepancy.

In this case, the bot must clearly state the limitation encountered, summarize
the context already collected, and transmit useful elements to the human agent
so the customer does not have to repeat the entire request.

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

- strong authentication;
- role-based access control;
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
- semantic cache for frequent questions and recurring pricing explanations,
  without bypassing BSS evidence verification;
- span-based observability across the whole pipeline: STT, BSS retrieval,
  comparison, KB search, LLM first-token, TTS first-audio, and human agent
  transfer;
- co-location in a private cloud of the critical components on the voice path
  when the `time_to_first_audio` p95 below 800 ms pilot criterion must be met;
- additional KB connectors, especially PDF, Confluence, or database connectors,
  to enrich pricing rules and explanation content.

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
- Phone Voice2Voice journey.
- Web Voice2Voice journey.
- Web interface for summary and evidence.
- Security, audit, and governance of BSS access.
- LLM / STT / TTS abstractions and latency constraints.
