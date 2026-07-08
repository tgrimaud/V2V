# V1 User Stories

## US-001 - Identify The Customer At The Start Of The Exchange

**Parent:** EPIC-001  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** High

### User Story

As an end customer, I want the bot to know which customer account my request
concerns, so that the invoice explanation uses only my own billing context.

### Acceptance Criteria

```gherkin
Scenario: Customer identity is reliable enough
  Given a customer starts a billing explanation conversation
  When the channel or pilot context identifies the customer with enough confidence
  Then the bot continues the invoice explanation journey for that customer
  And the bot does not ask the customer to repeat known information
```

```gherkin
Scenario: Customer identity is not reliable enough
  Given a customer starts a billing explanation conversation
  When the bot cannot determine the customer account with enough confidence
  Then the bot asks for clarification or starts the escalation path
  And the bot does not expose detailed invoice data
```

### Open Questions

- OQ-001 - Customer identification by phone and web voice channel.

---

## US-002 - Retrieve Available Invoices And Billing Periods

**Parent:** EPIC-001  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** High

### User Story

As an end customer, I want the bot to find the invoices or billing periods that
can be compared, so that I do not have to manually provide all details.

### Acceptance Criteria

```gherkin
Scenario: Comparable invoices are found
  Given the customer is identified
  When the bot looks for recent billing periods
  Then the bot identifies candidate invoices or periods for comparison
  And the bot can distinguish the latest period from previous comparable periods
```

```gherkin
Scenario: Comparable invoices are missing
  Given the customer is identified
  When no comparable billing period is available
  Then the bot explains that it cannot compare invoices yet
  And it offers clarification or human handoff
```

### Open Questions

- OQ-003 - BSS data availability and granularity.

---

## US-003 - Detect Insufficient BSS Evidence

**Parent:** EPIC-001  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** High

### User Story

As an end customer, I want the bot to detect when billing evidence is missing,
partial or inconsistent, so that it does not invent an explanation.

### Acceptance Criteria

```gherkin
Scenario: Billing evidence is incomplete
  Given the bot is preparing an invoice explanation
  When required billing evidence is missing or inconsistent
  Then the bot states that the explanation cannot be confirmed
  And the bot offers a human handoff when appropriate
```

```gherkin
Scenario: Some causes are confirmed and others are uncertain
  Given the bot is preparing an invoice explanation
  When part of the invoice difference is supported by evidence and part is not
  Then the bot explains the confirmed causes
  And clearly identifies the unexplained or uncertain remainder
```

---

## US-004 - Select Two Invoices Or Billing Periods To Compare

**Parent:** EPIC-002  
**Classification:** V1 core  
**Status:** Ready for delivery split  
**Priority:** High

### User Story

As an end customer, I want the bot to compare the relevant invoice with a previous
invoice or period, so that I can understand what changed.

### Acceptance Criteria

```gherkin
Scenario: Customer asks why the current invoice changed
  Given the customer has at least two comparable billing periods
  When the customer asks why the latest invoice is higher or lower
  Then the bot compares the relevant periods
  And it states which two periods are being compared
```

```gherkin
Scenario: Requested comparison is ambiguous
  Given the customer has several possible billing periods
  When the request does not identify enough context
  Then the bot asks one clarification question
  And does not choose an arbitrary period silently
```

---

## US-005 - Identify Changed Invoice Lines And Amounts

**Parent:** EPIC-002  
**Classification:** V1 core  
**Status:** Ready for delivery split  
**Priority:** High

### User Story

As an end customer, I want the bot to identify which invoice lines changed,
appeared or disappeared, so that I know where the price difference comes from.

### Acceptance Criteria

```gherkin
Scenario: Invoice lines changed
  Given two comparable invoices exist
  When the bot compares them
  Then it identifies the lines that appeared, disappeared or changed amount
  And it calculates their contribution to the total difference
```

```gherkin
Scenario: Total delta is not fully reconciled
  Given two comparable invoices exist
  When known line changes do not explain the full invoice difference
  Then the bot exposes the unexplained remainder
  And the final explanation stays cautious
```

---

## US-006 - Identify The Main Business Causes

**Parent:** EPIC-002  
**Classification:** V1 core  
**Status:** Ready for delivery split  
**Priority:** High

### User Story

As an end customer, I want the bot to group invoice differences into understandable
business causes, so that I understand why the invoice changed.

### Acceptance Criteria

```gherkin
Scenario: Main causes are identified
  Given the invoice comparison found several differences
  When the bot prepares the explanation
  Then it groups differences into business causes such as discount expiry, usage overage, option change, proration, tax, fee or adjustment
  And it presents the most impactful causes first
```

```gherkin
Scenario: Cause category is unknown
  Given the invoice comparison found a monetary difference
  When the difference cannot be mapped to a known business category
  Then the bot classifies it as other or unexplained
  And does not invent a business reason
```

---

## US-007 - Receive A Synthesis Of Increase Or Decrease Causes

**Parent:** EPIC-003  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** High

### User Story

As an end customer, I want a concise explanation of the main causes of my invoice
difference, so that I can quickly understand the situation.

### Acceptance Criteria

```gherkin
Scenario: Clear synthesis is produced
  Given the bot found explainable invoice differences
  When it answers the customer
  Then it starts with the total difference
  And it lists the main causes in understandable language
```

```gherkin
Scenario: No reliable explanation can be produced
  Given the bot cannot confirm enough causes for the invoice difference
  When it answers the customer
  Then it explains that the difference cannot be confirmed from available data
  And offers or starts the appropriate handoff path
```

---

## US-008 - Obtain Evidence For Each Cause

**Parent:** EPIC-003  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** High

### User Story

As an end customer, I want each explanation to be backed by evidence, so that I
can trust the answer.

### Acceptance Criteria

```gherkin
Scenario: Evidence is available
  Given the bot explains a cause of invoice difference
  When evidence exists in the billing context
  Then the bot points to the relevant invoice line, billing event, discount, usage, tax, fee or contract change
```

```gherkin
Scenario: Evidence contains sensitive details
  Given supporting evidence includes personal or sensitive billing data
  When the bot prepares the customer-facing explanation
  Then it exposes only the minimum necessary information
```

---

## US-009 - Explain The Billing Rule Behind A Delta

**Parent:** EPIC-003  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** Medium

### User Story

As an end customer, I want the bot to explain the billing rule behind the
difference, so that I understand why the charge applies.

### Acceptance Criteria

```gherkin
Scenario: Relevant billing rule is found
  Given a billing cause is confirmed by BSS evidence
  When a matching billing rule is available in the knowledge base
  Then the bot explains the rule in plain language
  And the explanation remains consistent with the BSS evidence
```

```gherkin
Scenario: Knowledge base conflicts with BSS evidence
  Given a billing cause is confirmed by BSS evidence
  When a knowledge base rule appears inconsistent with the BSS evidence
  Then the bot prioritizes the BSS evidence
  And avoids presenting the conflicting rule as fact
```

---

## US-010 - Handle Invoice Extraction Status

**Parent:** EPIC-010, EPIC-002, EPIC-003  
**Classification:** V1 enabler  
**Status:** Draft  
**Priority:** High

### User Story

As an end customer, I want the bot to handle parseable, partial and unusable
invoice extraction states safely, so that I receive only reliable explanations.

### Acceptance Criteria

```gherkin
Scenario: Invoice extraction is parseable
  Given two invoice extractions are parseable
  When the bot compares the invoices
  Then the comparison can use the confirmed extracted lines
```

```gherkin
Scenario: Invoice extraction is partial
  Given one invoice extraction is partial
  When the bot prepares the explanation
  Then it separates confirmed causes from unexplained amounts
  And it does not present uncertain lines as confirmed evidence
```

```gherkin
Scenario: Invoice extraction is unusable
  Given one invoice extraction is unusable
  When the customer asks for a comparison
  Then the bot does not compare amounts
  And it offers clarification or escalation
```

---

## US-011 - Use Realistic BSS/PDF Fixtures For V1 Validation

**Parent:** EPIC-010  
**Classification:** V1 enabler  
**Status:** Draft  
**Priority:** High

### User Story

As a product and QA stakeholder, I want realistic billing fixtures for the V1
journeys, so that the team can validate explanation behavior before full BSS
sandbox access is stable.

### Acceptance Criteria

```gherkin
Scenario: Nominal fixture reconciles the delta
  Given a fixture contains two comparable invoices
  When the bot explains the invoice difference
  Then the global delta reconciles with confirmed causes
  And evidence is available for each main cause
```

```gherkin
Scenario: Fixture covers unsafe data
  Given a fixture contains missing, inconsistent or unreliable extraction data
  When the bot prepares the explanation
  Then the expected behavior is limitation, clarification or escalation
  And no unsupported amount is confirmed
```

---

## US-012 - Call The Bot For A Spoken Invoice Explanation

**Parent:** EPIC-004  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** High

### User Story

As an end customer, I want to call the bot by phone and ask why my invoice
changed, so that I can get help without using a screen.

### Acceptance Criteria

```gherkin
Scenario: Phone Voice2Voice journey
  Given a customer calls the bot
  When the customer asks why their invoice changed
  Then the bot conducts the interaction by voice
  And provides a spoken billing explanation or an escalation path
```

---

## US-013 - Receive A Quick Spoken Acknowledgement During Long Analysis

**Parent:** EPIC-004  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** Medium

### User Story

As an end customer, I want the bot to acknowledge my request quickly when
analysis takes time, so that I know the conversation is still progressing.

### Acceptance Criteria

```gherkin
Scenario: Analysis needs more time
  Given the bot needs more time to verify billing evidence
  When the customer is waiting on a voice channel
  Then the bot gives a short spoken acknowledgement
  And later provides the reliable explanation or escalates
```

---

## US-014 - Ask Orally For Transfer To An Advisor

**Parent:** EPIC-004, EPIC-006  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** High

### User Story

As an end customer, I want to ask for a human advisor by voice, so that I can
leave the automated journey when I need human help.

### Acceptance Criteria

```gherkin
Scenario: Customer asks for human advisor
  Given the customer is speaking with the bot
  When the customer asks to talk to a human advisor
  Then the bot starts the human handoff journey
```

---

## US-015 - Ask From A Web Voice Chat

**Parent:** EPIC-005  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** High

### User Story

As an end customer, I want to use a web page to speak with the bot, so that I can
get a voice explanation while also seeing useful information.

### Acceptance Criteria

```gherkin
Scenario: Web Voice2Voice journey
  Given the customer opens the web voice chat
  When the customer asks a billing question by voice
  Then the bot responds by voice
  And the page can display the relevant synthesis when available
```

---

## US-016 - Read The Synthesis On The Web Page

**Parent:** EPIC-005, EPIC-007  
**Classification:** V1 enabler  
**Status:** Ready for review  
**Priority:** Medium

### User Story

As an end customer, I want to see a written synthesis of the spoken explanation,
so that I can review the key points after listening.

### Acceptance Criteria

```gherkin
Scenario: Written synthesis mirrors spoken answer
  Given the bot has delivered a spoken explanation on the web channel
  When the synthesis is displayed
  Then it reflects the same main causes and evidence as the spoken answer
```

---

## US-017 - Use Text To Complement A Voice Question

**Parent:** EPIC-005  
**Classification:** V1 enabler  
**Status:** Ready for review  
**Priority:** Low

### User Story

As an end customer, I want to type complementary information when needed, so that
I can clarify my request without leaving the web journey.

### Acceptance Criteria

```gherkin
Scenario: Written clarification complements voice
  Given the customer is using the web voice journey
  When the customer provides clarification in writing
  Then the bot uses it as part of the same conversation context
```

---

## US-018 - Be Transferred On Explicit Request

**Parent:** EPIC-006  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** High

### User Story

As an end customer, I want to be transferred to a human advisor when I ask for
it, so that I remain in control of the support journey.

### Acceptance Criteria

```gherkin
Scenario: Explicit handoff request
  Given the customer is interacting with the bot
  When the customer asks to speak with a human advisor
  Then the bot confirms the transfer
  And starts the human handoff path
```

---

## US-019 - Be Transferred When The Bot Lacks Enough Certainty

**Parent:** EPIC-006  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** High

### User Story

As an end customer, I want the bot to transfer me when it cannot answer safely,
so that I do not receive an unreliable explanation.

### Acceptance Criteria

```gherkin
Scenario: Bot lacks enough certainty
  Given the bot cannot explain the invoice difference with enough evidence
  When the conversation should continue
  Then the bot explains the limitation
  And starts or offers the human handoff path
```

---

## US-020 - Provide The Advisor With Usable Context

**Parent:** EPIC-006  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** High

### User Story

As a human billing advisor, I want to receive the context already collected by
the bot, so that the customer does not need to repeat the whole story.

### Acceptance Criteria

```gherkin
Scenario: Advisor receives context
  Given the bot transfers a customer to a human advisor
  When the transfer happens
  Then the advisor receives a summary of the question, compared periods, known evidence, missing evidence and reason for handoff
```

---

## US-033 - Hand Off To Genesys With Advisor Context

**Parent:** EPIC-006  
**Classification:** V1 core  
**Status:** Draft  
**Priority:** High

### User Story

As a contact-center advisor, I want escalated billing conversations to arrive
through Genesys with the bot context, so that I can continue the support journey
without asking the customer to repeat everything.

### Acceptance Criteria

```gherkin
Scenario: Explicit advisor request reaches Genesys
  Given the customer asks to speak with a human advisor
  When the bot starts the handoff
  Then Genesys receives a handoff request with the conversation summary, reason and permitted customer/session identifiers
```

```gherkin
Scenario: Insufficient evidence reaches Genesys
  Given the bot cannot explain the invoice delta with enough evidence
  When the bot escalates
  Then Genesys receives the known evidence, missing evidence and unresolved points
  And the customer is told that the advisor will receive the available context
```

---

## US-021 - Consult The Global Delta

**Parent:** EPIC-007  
**Classification:** V1 enabler  
**Status:** Ready for review  
**Priority:** Medium

### User Story

As an end customer, I want to see the total difference between the compared
invoices, so that I immediately understand the size of the change.

### Acceptance Criteria

```gherkin
Scenario: Delta is displayed
  Given two invoices have been compared
  When the web synthesis is shown
  Then the total difference is visible
```

---

## US-022 - Consult Cause Details

**Parent:** EPIC-007  
**Classification:** V1 enabler  
**Status:** Ready for review  
**Priority:** Medium

### User Story

As an end customer, I want to see the main causes and their contribution, so that
I understand what explains the total difference.

### Acceptance Criteria

```gherkin
Scenario: Causes are displayed by impact
  Given several causes explain the invoice difference
  When the web synthesis is shown
  Then the causes are listed in a clear order
  And each cause shows its impact when available
```

---

## US-023 - See Evidence And Analysis Limits

**Parent:** EPIC-007  
**Classification:** V1 enabler  
**Status:** Ready for review  
**Priority:** Medium

### User Story

As an end customer, I want to know what evidence supports the explanation and
what is uncertain, so that I can trust the result or understand why a human is
needed.

### Acceptance Criteria

```gherkin
Scenario: Evidence and limits are visible
  Given the bot produced an explanation
  When the detailed view is available
  Then the customer can see the supporting evidence
  And unresolved or uncertain points are clearly identified
```

---

## US-024 - Protect Personal Data Exposed To The Customer

**Parent:** EPIC-008  
**Classification:** V1 enabler  
**Status:** Ready for review  
**Priority:** High

### User Story

As an end customer, I want only necessary personal and billing information to be
exposed, so that my sensitive data remains protected.

### Acceptance Criteria

```gherkin
Scenario: Only necessary data is shown or spoken
  Given the bot prepares an explanation
  When the explanation is delivered
  Then it avoids exposing unnecessary personal data
```

---

## US-025 - Audit Sensitive Consultations

**Parent:** EPIC-008  
**Classification:** V1 enabler  
**Status:** Ready for review  
**Priority:** High

### User Story

As an operator compliance stakeholder, I want sensitive billing consultations to
be auditable, so that the operator can investigate misuse or disputes.

### Acceptance Criteria

```gherkin
Scenario: Sensitive consultation is auditable
  Given a customer billing explanation is requested
  When the journey completes or escalates
  Then an audit trail exists for the consultation outcome
```

---

## US-026 - Disclose Analysis Limits

**Parent:** EPIC-008  
**Classification:** V1 core  
**Status:** Ready for review  
**Priority:** High

### User Story

As an end customer, I want the bot to clearly state when it cannot confirm an
explanation, so that I am not misled.

### Acceptance Criteria

```gherkin
Scenario: Analysis limit is disclosed
  Given the bot lacks enough evidence for a reliable answer
  When the customer asks for an explanation
  Then the bot clearly states the limitation
  And does not present an unconfirmed explanation as fact
```

---

## US-027 - Measure Key Voice Journey Timings

**Parent:** EPIC-009  
**Classification:** V1 pilot gate  
**Status:** Ready for review  
**Priority:** High

### User Story

As a product owner, I want to measure key moments in the voice journey, so that
we can verify whether the experience is acceptable.

### Acceptance Criteria

```gherkin
Scenario: Voice journey timing is measurable
  Given a customer completes a voice billing explanation journey
  When the journey is reviewed
  Then key timing points such as first acknowledgement and first meaningful answer can be assessed
```

---

## US-028 - Track Escalations And Their Reasons

**Parent:** EPIC-009  
**Classification:** V1 pilot gate  
**Status:** Ready for review  
**Priority:** Medium

### User Story

As a product owner, I want to understand why customers are escalated to human
advisors, so that we can improve the bot and the support journey.

### Acceptance Criteria

```gherkin
Scenario: Handoff reason is known
  Given a conversation is escalated
  When the escalation is reviewed
  Then the reason is available as explicit customer request, insufficient evidence, missing data, inconsistent data or another product-visible category
```

---

## US-029 - Track Unresolved Questions

**Parent:** EPIC-009  
**Classification:** V1 pilot gate  
**Status:** Ready for review  
**Priority:** Medium

### User Story

As a product owner, I want to know which questions the bot cannot resolve, so
that future improvements target real customer needs.

### Acceptance Criteria

```gherkin
Scenario: Unresolved question is visible for product review
  Given the bot cannot resolve a customer question
  When the conversation outcome is reviewed
  Then the unresolved question can be categorized for future improvement
```

---

## US-030 - Consult Line-By-Line Invoice Differences

**Parent:** EPIC-007  
**Classification:** V1 enabler  
**Status:** Draft  
**Priority:** Medium

### User Story

As an end customer using the web journey, I want to inspect the invoice lines
behind the explanation, so that I can understand which concrete charges changed.

### Acceptance Criteria

```gherkin
Scenario: Line differences are visible
  Given two invoices have been compared
  When the detailed web view is available
  Then the customer can see lines that appeared, disappeared or changed amount
  And those line differences remain consistent with the spoken explanation
```

```gherkin
Scenario: Line detail is not safe to display
  Given a line contains sensitive or uncertain information
  When the web detail is prepared
  Then the detail is masked, limited or marked uncertain
  And the bot does not expose unsupported evidence
```

---

## US-031 - Validate Billing And Pricing KB Content For V1

**Parent:** EPIC-010, EPIC-003  
**Classification:** V1 enabler  
**Status:** Draft  
**Priority:** Medium

### User Story

As a billing business contributor, I want the V1 billing rules to be present in
the knowledge base, so that confirmed BSS causes can be explained in plain
language.

### Acceptance Criteria

```gherkin
Scenario: Required billing rule is present
  Given a V1 fixture contains a confirmed billing cause
  When the bot needs to explain the associated tariff or business rule
  Then a reviewed KB entry exists for that rule
  And the wording remains consistent with the BSS evidence
```

```gherkin
Scenario: Billing rule is missing
  Given a confirmed BSS cause has no matching KB rule
  When the bot prepares the explanation
  Then the bot explains the confirmed fact without inventing the missing rule
  And the missing rule is visible for backlog review
```

---

## US-032 - Measure Invoice Comparison Response Time

**Parent:** EPIC-009, EPIC-002  
**Classification:** V1 pilot gate  
**Status:** Draft  
**Priority:** Medium

### User Story

As a product owner, I want to measure how long invoice comparison takes, so that
we can keep the billing explanation journey conversational without sacrificing
evidence quality.

### Acceptance Criteria

```gherkin
Scenario: Comparison duration is measurable
  Given a customer asks for an invoice explanation
  When the system retrieves evidence and compares invoices
  Then the comparison duration can be reviewed separately from voice latency
```

```gherkin
Scenario: Comparison takes longer than expected
  Given invoice evidence analysis takes longer than the conversational target
  When the customer is waiting on a voice channel
  Then the bot can provide a short acknowledgement
  And waits for reliable evidence before giving the explanation
```
