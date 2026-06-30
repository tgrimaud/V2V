# V1 User Stories

## US-001 - Identifier le client au debut de l'echange

**Parent:** EPIC-001  
**Status:** Ready for review  
**Priority:** High

### User story

As a client utilisateur final,
I want the bot to know which customer account my request concerns,
So that the invoice explanation is based only on my own billing context.

### MVP Assumptions

- The channel or pilot journey can provide a customer context before the explanation starts.
- If the context is not trusted enough, the bot must not access or expose detailed billing information.
- The exact target mechanism for phone and web identification remains covered by OQ-001.

### Acceptance Criteria

```gherkin
Scenario: Client identity is known with enough confidence
  Given a client starts a billing explanation conversation
  When the channel provides enough customer context
  Then the bot continues the invoice explanation journey for that client
  And the bot does not ask the client to repeat known information
```

```gherkin
Scenario: Client identity is not reliable enough
  Given a client starts a billing explanation conversation
  When the bot cannot determine the customer account with enough confidence
  Then the bot asks for clarification or starts the escalation path
  And the bot does not expose detailed invoice data
```

```gherkin
Scenario: Client identity conflicts with requested invoice context
  Given a client starts a billing explanation conversation
  When the available identity context does not match the requested invoice or account
  Then the bot refuses to explain that invoice
  And the bot offers clarification or handoff
```

### Ready Notes

- Product must define what "enough confidence" means for the MVP pilot.
- Security must validate what can be spoken or displayed before strong identification.

### Open Questions

- OQ-001 - Identification client par canal telephone et web.

---

## US-002 - Recuperer les factures disponibles

**Parent:** EPIC-001  
**Status:** Ready for review  
**Priority:** High

### User story

As a client utilisateur final,
I want the bot to find the invoices or billing periods that can be compared,
So that I can understand the price difference without manually providing all details.

### MVP Assumptions

- At least the recent billing periods needed for a month-to-month comparison are available for pilot clients.
- A billing period is comparable only if its total amount and detailed billing evidence are available enough for EPIC-002.
- BSS availability and granularity remain covered by OQ-003.

### Acceptance Criteria

```gherkin
Scenario: Comparable invoices are found
  Given the client is identified
  When the bot looks for recent billing periods
  Then the bot can identify the candidate invoices or periods for comparison
  And the bot can distinguish the latest period from previous comparable periods
```

```gherkin
Scenario: Comparable invoices are missing
  Given the client is identified
  When no comparable billing period is available
  Then the bot explains that it cannot compare invoices yet
  And the bot offers a clarification or human handoff path
```

```gherkin
Scenario: Client names a period that exists
  Given the client is identified
  When the client asks about a specific available billing period
  Then that period can be used as a comparison candidate
```

```gherkin
Scenario: Client names a period that is unavailable
  Given the client is identified
  When the client asks about a missing or inaccessible billing period
  Then the bot explains that the period is not available for comparison
  And the bot does not invent missing invoice data
```

### Ready Notes

- The MVP needs a clear list of minimum billing fields required to compare periods safely.
- The user-facing wording for missing periods should stay short on voice channels.

---

## US-003 - Detecter les donnees BSS insuffisantes

**Parent:** EPIC-001  
**Status:** Ready for review  
**Priority:** High

### User story

As a client utilisateur final,
I want the bot to detect when billing data is missing or inconsistent,  
So that it does not invent an explanation for my invoice.

### MVP Assumptions

- The bot can distinguish unavailable data, incomplete data and contradictory data.
- Missing evidence should be visible to the explanation and escalation journey.
- The minimal proof threshold remains covered by OQ-002.

### Acceptance Criteria

```gherkin
Scenario: Billing data is incomplete
  Given the bot is preparing an invoice explanation
  When required billing evidence is missing or inconsistent
  Then the bot states that the explanation cannot be confirmed
  And the bot offers a human handoff when appropriate
```

```gherkin
Scenario: Billing data is contradictory
  Given the bot is preparing an invoice explanation
  When billing totals, line amounts or events contradict each other
  Then the bot marks the analysis as unreliable
  And the bot does not present a definitive cause
```

```gherkin
Scenario: Some causes are confirmed and others are uncertain
  Given the bot is preparing an invoice explanation
  When part of the invoice difference is supported by evidence and part is not
  Then the bot can explain the confirmed causes
  And clearly identifies the unexplained or uncertain remainder
```

### Ready Notes

- This story protects the non-invention rule and should be tested with negative examples.
- It is a prerequisite for safe completion of US-007, US-008 and US-017.

---

## US-004 - Selectionner deux factures ou periodes a comparer

**Parent:** EPIC-002  
**Status:** Ready for delivery split  
**Priority:** High

### User story

As a client utilisateur final,
I want the bot to compare the relevant invoice with a previous invoice or period,  
So that I can understand what changed.

### MVP Assumptions

- If the client asks "why is this invoice higher/lower", the default comparison is latest period versus immediately previous comparable period.
- If the client names two periods, those periods take precedence when both are available.
- If the requested comparison is ambiguous, the bot asks one clarification instead of guessing.

### Acceptance Criteria

```gherkin
Scenario: Client asks why the current invoice changed
  Given the client has at least two comparable billing periods
  When the client asks why the latest invoice is higher or lower
  Then the bot compares the relevant periods
  And it states which two periods are being compared
```

```gherkin
Scenario: Client names a specific period
  Given the client asks about two specific periods
  When both periods are available
  Then the bot compares those periods
```

```gherkin
Scenario: Requested comparison is ambiguous
  Given the client has several possible billing periods
  When the client request does not identify enough context
  Then the bot asks a clarification question
  And does not choose an arbitrary period silently
```

```gherkin
Scenario: Requested periods are not comparable
  Given the client asks to compare two periods
  When one period is missing or does not contain enough billing evidence
  Then the bot explains that the comparison cannot be completed reliably
  And offers clarification or handoff
```

### Ready Notes

- This story defines period selection only; the detailed difference calculation belongs to US-005 and US-006.

---

## US-005 - Identifier les lignes et montants qui changent

**Parent:** EPIC-002  
**Status:** Ready for delivery split  
**Priority:** High

### User story

As a client utilisateur final,
I want the bot to identify which invoice lines changed, appeared or disappeared,  
So that I know where the price difference comes from.

### MVP Assumptions

- The compared periods provide a total amount and enough line detail to calculate contributions.
- The comparison result must reconcile line-level changes with the total delta or explicitly expose the unexplained remainder.
- Amounts are presented from BSS evidence, not calculated by the LLM.

### Acceptance Criteria

```gherkin
Scenario: Invoice lines changed
  Given two comparable invoices exist
  When the bot compares them
  Then it identifies the lines that appeared, disappeared or changed amount
  And it calculates the contribution of those lines to the total difference
```

```gherkin
Scenario: Invoice line appeared
  Given two comparable invoices exist
  When a charged line exists only in the newer period
  Then the bot identifies the line as an added charge
  And includes its amount in the positive delta
```

```gherkin
Scenario: Invoice line disappeared
  Given two comparable invoices exist
  When a charged line exists only in the older period
  Then the bot identifies the line as a removed charge
  And includes its amount in the negative delta
```

```gherkin
Scenario: Invoice line amount changed
  Given two comparable invoices exist
  When the same billing line has a different amount across periods
  Then the bot identifies the amount change
  And includes only the difference in the delta explanation
```

```gherkin
Scenario: Total delta is not fully reconciled
  Given two comparable invoices exist
  When known line changes do not explain the full invoice difference
  Then the bot exposes the unexplained remainder
  And the final explanation stays cautious
```

### Ready Notes

- This is the first core implementation story for the deterministic comparison engine.
- The product wording must distinguish increases, decreases and neutral changes.

---

## US-006 - Identifier les causes metier principales

**Parent:** EPIC-002  
**Status:** Ready for delivery split  
**Priority:** High

### User story

As a client utilisateur final,
I want the bot to group invoice differences into understandable business causes,  
So that I can understand the reason rather than only seeing line changes.

### MVP Assumptions

- V1 categories are limited to discount expiry, usage overage, option or service change, prorata, tax, one-off fee, adjustment and other.
- A cause can be confirmed only when it is supported by billing evidence.
- Causes are ordered by financial impact when amounts are available.

### Acceptance Criteria

```gherkin
Scenario: Main causes are identified
  Given the invoice comparison found several differences
  When the bot prepares the explanation
  Then it groups differences into business causes such as discount expiry, usage overage, option change, prorata, tax, fee or adjustment
  And it presents the most impactful causes first
```

```gherkin
Scenario: Discount expiry explains an increase
  Given the invoice comparison found that a previous discount no longer applies
  When the bot prepares the explanation
  Then it identifies discount expiry as a cause
  And uses the lost discount amount as the cause impact
```

```gherkin
Scenario: Usage overage explains an increase
  Given the invoice comparison found charged consumption outside the included allowance
  When the bot prepares the explanation
  Then it identifies usage overage as a cause
  And connects it to the relevant consumption evidence
```

```gherkin
Scenario: Cause category is unknown
  Given the invoice comparison found a monetary difference
  When the difference cannot be mapped to a known business category
  Then the bot classifies it as other or unexplained
  And does not invent a business reason
```

### Ready Notes

- The first delivery split can support a subset of categories if the unsupported categories are explicitly marked out of scope.
- Product should validate the category labels with billing experts before customer-facing release.

---

## US-007 - Recevoir une synthese des causes de hausse ou baisse

**Parent:** EPIC-003  
**Status:** Ready for review  
**Priority:** High

### User story

As a client utilisateur final,
I want a concise explanation of the main causes of my invoice difference,  
So that I can quickly understand the situation.

### MVP Assumptions

- The synthesis is generated only after deterministic comparison results are available.
- The first sentence states the total delta and whether the invoice increased or decreased.
- The answer should be understandable when delivered by voice without looking at the screen.

### Acceptance Criteria

```gherkin
Scenario: Clear synthesis is produced
  Given the bot found explainable invoice differences
  When it answers the client
  Then it starts with the total difference
  And it lists the main causes in understandable language
```

```gherkin
Scenario: Causes are ordered by impact
  Given the bot found several confirmed causes
  When it answers the client
  Then it presents the largest impact first
  And keeps minor causes secondary
```

```gherkin
Scenario: Explanation contains confirmed and uncertain parts
  Given the bot found confirmed causes and an unexplained remainder
  When it answers the client
  Then it explains the confirmed causes
  And explicitly says what remains uncertain
```

```gherkin
Scenario: No reliable explanation can be produced
  Given the bot cannot confirm enough causes for the invoice difference
  When it answers the client
  Then it explains that the difference cannot be confirmed from available data
  And offers or starts the appropriate handoff path
```

### Ready Notes

- The synthesis must never introduce a cause or amount that is absent from the comparison result.
- Voice phrasing should be short enough to avoid a long spoken monologue.

---

## US-008 - Obtenir les preuves associees a chaque cause

**Parent:** EPIC-003  
**Status:** Ready for review  
**Priority:** High

### User story

As a client utilisateur final,
I want each explanation to be backed by evidence,  
So that I can trust the answer.

### MVP Assumptions

- Evidence can be an invoice line, billing event, discount, consumption record, tax, fee, regularisation or contract change.
- Evidence may be cited orally in summary form and displayed with more detail on web when available.
- Evidence must not expose unnecessary personal data.

### Acceptance Criteria

```gherkin
Scenario: Evidence is available
  Given the bot explains a cause of invoice difference
  When evidence exists in the billing context
  Then the bot can point to the relevant invoice line, billing event, discount, consumption, tax, fee or contract change
```

```gherkin
Scenario: Evidence is missing
  Given the bot cannot find enough evidence for a possible cause
  When the client asks for the explanation
  Then the bot does not present the cause as confirmed
```

```gherkin
Scenario: Evidence supports the spoken synthesis
  Given the bot gives a spoken explanation
  When the corresponding evidence is shown or summarized
  Then it supports the same causes and amounts as the spoken answer
```

```gherkin
Scenario: Evidence contains sensitive details
  Given supporting evidence includes personal or sensitive billing data
  When the bot prepares the customer-facing explanation
  Then it exposes only the minimum necessary information
```

### Ready Notes

- This story links EPIC-003 with EPIC-008 security expectations.
- The exact proof threshold remains open until OQ-002 is decided.

---

## US-009 - Expliquer une regle tarifaire associee a l'ecart

**Parent:** EPIC-003  
**Status:** Ready for review  
**Priority:** Medium

### User story

As a client utilisateur final,
I want the bot to explain the billing rule behind the difference,  
So that I understand why the charge applies.

### MVP Assumptions

- The rule explanation is secondary to BSS evidence.
- The knowledge base can explain product, tariff or billing rules only when a relevant entry exists.
- Missing knowledge base content must not prevent the bot from presenting confirmed BSS facts.

### Acceptance Criteria

```gherkin
Scenario: Relevant billing rule is found
  Given a billing cause is confirmed by BSS evidence
  When a matching billing rule is available in the knowledge base
  Then the bot explains the rule in plain language
  And the explanation remains consistent with the BSS evidence
```

```gherkin
Scenario: No matching billing rule is found
  Given a billing cause is confirmed by BSS evidence
  When no matching billing rule is available in the knowledge base
  Then the bot explains the confirmed fact without inventing a rule
  And may say that no additional tariff explanation is available
```

```gherkin
Scenario: Knowledge base conflicts with BSS evidence
  Given a billing cause is confirmed by BSS evidence
  When a knowledge base rule appears inconsistent with the BSS evidence
  Then the bot prioritizes the BSS evidence
  And avoids presenting the conflicting rule as fact
```

### Ready Notes

- This story can follow US-007 and US-008; it enriches explanations but is not required to calculate the invoice delta.

---

## US-010 - Appeler le bot pour demander une explication de facture

**Parent:** EPIC-004  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want to call the bot by phone and ask why my invoice changed,  
So that I can get help without using a screen.

### Acceptance Criteria

```gherkin
Scenario: Phone Voice2Voice journey
  Given a client calls the bot
  When the client asks why their invoice changed
  Then the bot conducts the interaction by voice
  And provides a spoken billing explanation or an escalation path
```

---

## US-011 - Recevoir un accuse de reception vocal lorsque l'analyse prend du temps

**Parent:** EPIC-004  
**Status:** Draft  
**Priority:** Medium

### User story

As a client utilisateur final,  
I want the bot to acknowledge my request quickly when analysis takes time,  
So that I know the conversation is still progressing.

### Acceptance Criteria

```gherkin
Scenario: Analysis needs more time
  Given the bot needs more time to verify billing evidence
  When the client is waiting on a voice channel
  Then the bot gives a short spoken acknowledgement
  And later provides the reliable explanation or escalates
```

---

## US-012 - Demander oralement un transfert vers conseiller

**Parent:** EPIC-004, EPIC-006  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want to ask for a human advisor by voice,  
So that I can leave the automated journey when I need human help.

### Acceptance Criteria

```gherkin
Scenario: Client asks for human advisor
  Given the client is speaking with the bot
  When the client asks to talk to a human advisor
  Then the bot starts the human handoff journey
```

---

## US-013 - Poser une question par chat vocal web

**Parent:** EPIC-005  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want to use a web page to speak with the bot,  
So that I can get a voice explanation while also seeing useful information.

### Acceptance Criteria

```gherkin
Scenario: Web Voice2Voice journey
  Given the client opens the web voice chat
  When the client asks a billing question by voice
  Then the bot responds by voice
  And the page can display the relevant synthesis when available
```

---

## US-014 - Lire la synthese de l'explication sur la page web

**Parent:** EPIC-005, EPIC-007  
**Status:** Draft  
**Priority:** Medium

### User story

As a client utilisateur final,  
I want to see a written synthesis of the spoken explanation,  
So that I can review the key points after listening.

### Acceptance Criteria

```gherkin
Scenario: Written synthesis mirrors spoken answer
  Given the bot has delivered a spoken explanation on the web channel
  When the synthesis is displayed
  Then it reflects the same main causes and evidence as the spoken answer
```

---

## US-015 - Utiliser l'ecrit pour completer une question vocale

**Parent:** EPIC-005  
**Status:** Draft  
**Priority:** Low

### User story

As a client utilisateur final,  
I want to type complementary information when needed,  
So that I can help the bot clarify my request without leaving the web journey.

### Acceptance Criteria

```gherkin
Scenario: Written clarification complements voice
  Given the client is using the web voice journey
  When the client provides clarification in writing
  Then the bot uses it as part of the same conversation context
```

---

## US-016 - Etre transfere sur demande explicite

**Parent:** EPIC-006  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want to be transferred to a human advisor when I ask for it,  
So that I remain in control of the support journey.

### Acceptance Criteria

```gherkin
Scenario: Explicit handoff request
  Given the client is interacting with the bot
  When the client asks to speak with a human advisor
  Then the bot confirms the transfer
  And starts the human handoff path
```

---

## US-017 - Etre transfere quand le bot n'a pas assez de certitude

**Parent:** EPIC-006  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want the bot to transfer me when it cannot answer safely,  
So that I do not receive an unreliable explanation.

### Acceptance Criteria

```gherkin
Scenario: Bot lacks enough certainty
  Given the bot cannot explain the invoice difference with enough evidence
  When the conversation should continue
  Then the bot explains the limitation
  And starts or offers the human handoff path
```

---

## US-018 - Fournir a l'agent humain un resume exploitable

**Parent:** EPIC-006  
**Status:** Draft  
**Priority:** High

### User story

As a human billing advisor,  
I want to receive the context already collected by the bot,  
So that the client does not need to repeat the whole story.

### Acceptance Criteria

```gherkin
Scenario: Advisor receives context
  Given the bot transfers a client to a human advisor
  When the transfer happens
  Then the advisor receives a summary of the question, compared periods, known evidence, missing evidence and reason for handoff
```

---

## US-019 - Consulter le delta global

**Parent:** EPIC-007  
**Status:** Draft  
**Priority:** Medium

### User story

As a client utilisateur final,  
I want to see the total difference between the compared invoices,  
So that I immediately understand the size of the change.

### Acceptance Criteria

```gherkin
Scenario: Delta is displayed
  Given two invoices have been compared
  When the web synthesis is shown
  Then the total difference is visible
```

---

## US-020 - Consulter le detail des causes

**Parent:** EPIC-007  
**Status:** Draft  
**Priority:** Medium

### User story

As a client utilisateur final,  
I want to see the main causes and their contribution,  
So that I understand what explains the total difference.

### Acceptance Criteria

```gherkin
Scenario: Causes are displayed by impact
  Given several causes explain the invoice difference
  When the web synthesis is shown
  Then the causes are listed in a clear order
  And each cause shows its impact when available
```

---

## US-021 - Voir les preuves et limites de l'analyse

**Parent:** EPIC-007  
**Status:** Draft  
**Priority:** Medium

### User story

As a client utilisateur final,  
I want to know what evidence supports the explanation and what is uncertain,  
So that I can trust the result or understand why a human is needed.

### Acceptance Criteria

```gherkin
Scenario: Evidence and limits are visible
  Given the bot produced an explanation
  When the detailed view is available
  Then the client can see the supporting evidence
  And any unresolved or uncertain points are clearly identified
```

---

## US-022 - Proteger les donnees personnelles exposees au client

**Parent:** EPIC-008  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want only necessary personal and billing information to be exposed,  
So that my sensitive data remains protected.

### Acceptance Criteria

```gherkin
Scenario: Only necessary data is shown or spoken
  Given the bot prepares an explanation
  When the explanation is delivered
  Then it avoids exposing unnecessary personal data
```

---

## US-023 - Journaliser les consultations sensibles

**Parent:** EPIC-008  
**Status:** Draft  
**Priority:** High

### User story

As an operator compliance stakeholder,  
I want sensitive billing consultations to be auditable,  
So that the operator can investigate misuse or disputes.

### Acceptance Criteria

```gherkin
Scenario: Sensitive consultation is auditable
  Given a client billing explanation is requested
  When the journey completes or escalates
  Then an audit trail exists for the consultation outcome
```

---

## US-024 - Signaler les limites de l'analyse

**Parent:** EPIC-008  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want the bot to clearly state when it cannot confirm an explanation,  
So that I am not misled.

### Acceptance Criteria

```gherkin
Scenario: Analysis limit is disclosed
  Given the bot lacks enough evidence for a reliable answer
  When the client asks for an explanation
  Then the bot clearly states the limitation
  And does not present an unconfirmed explanation as fact
```

---

## US-025 - Mesurer les temps cles du parcours vocal

**Parent:** EPIC-009  
**Status:** Draft  
**Priority:** Medium

### User story

As a product owner,  
I want to measure key moments in the voice journey,  
So that we can verify whether the experience is acceptable.

### Acceptance Criteria

```gherkin
Scenario: Voice journey timing is measurable
  Given a client completes a voice billing explanation journey
  When the journey is reviewed
  Then key timing points such as first acknowledgement and first meaningful answer can be assessed
```

---

## US-026 - Suivre les escalades et leurs raisons

**Parent:** EPIC-009  
**Status:** Draft  
**Priority:** Medium

### User story

As a product owner,  
I want to understand why clients are escalated to human advisors,  
So that we can improve the bot and the support journey.

### Acceptance Criteria

```gherkin
Scenario: Handoff reason is known
  Given a conversation is escalated
  When the escalation is reviewed
  Then the reason is available as explicit client request, insufficient evidence, missing data, incoherent data or another product-visible category
```

---

## US-027 - Suivre les questions non resolues

**Parent:** EPIC-009  
**Status:** Draft  
**Priority:** Medium

### User story

As a product owner,  
I want to know which questions the bot cannot resolve,  
So that future improvements target real client needs.

### Acceptance Criteria

```gherkin
Scenario: Unresolved question is visible for product review
  Given the bot cannot resolve a client question
  When the conversation outcome is reviewed
  Then the unresolved question can be categorized for future improvement
```
