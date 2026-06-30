# V1 User Stories

## US-001 - Identifier le client au debut de l'echange

**Parent:** EPIC-001  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want le bot to know which customer account my request concerns,  
So that the answer is based on my own billing context.

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
```

### Open Questions

- OQ-001 - Identification client par canal telephone et web.

---

## US-002 - Recuperer les factures disponibles

**Parent:** EPIC-001  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want the bot to find the invoices or billing periods that can be compared,  
So that I can understand the price difference without manually providing all details.

### Acceptance Criteria

```gherkin
Scenario: Comparable invoices are found
  Given the client is identified
  When the bot looks for recent billing periods
  Then the bot can identify the candidate invoices or periods for comparison
```

```gherkin
Scenario: Comparable invoices are missing
  Given the client is identified
  When no comparable billing period is available
  Then the bot explains that it cannot compare invoices yet
  And the bot offers a clarification or human handoff path
```

---

## US-003 - Detecter les donnees BSS insuffisantes

**Parent:** EPIC-001  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want the bot to detect when billing data is missing or inconsistent,  
So that it does not invent an explanation for my invoice.

### Acceptance Criteria

```gherkin
Scenario: Billing data is incomplete
  Given the bot is preparing an invoice explanation
  When required billing evidence is missing or inconsistent
  Then the bot states that the explanation cannot be confirmed
  And the bot offers a human handoff when appropriate
```

---

## US-004 - Selectionner deux factures ou periodes a comparer

**Parent:** EPIC-002  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want the bot to compare the relevant invoice with a previous invoice or period,  
So that I can understand what changed.

### Acceptance Criteria

```gherkin
Scenario: Client asks why the current invoice changed
  Given the client has at least two comparable billing periods
  When the client asks why the latest invoice is higher or lower
  Then the bot compares the relevant periods
```

```gherkin
Scenario: Client names a specific period
  Given the client asks about two specific periods
  When both periods are available
  Then the bot compares those periods
```

---

## US-005 - Identifier les lignes et montants qui changent

**Parent:** EPIC-002  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want the bot to identify which invoice lines changed, appeared or disappeared,  
So that I know where the price difference comes from.

### Acceptance Criteria

```gherkin
Scenario: Invoice lines changed
  Given two comparable invoices exist
  When the bot compares them
  Then it identifies the lines that appeared, disappeared or changed amount
  And it calculates the contribution of those lines to the total difference
```

---

## US-006 - Identifier les causes metier principales

**Parent:** EPIC-002  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want the bot to group invoice differences into understandable business causes,  
So that I can understand the reason rather than only seeing line changes.

### Acceptance Criteria

```gherkin
Scenario: Main causes are identified
  Given the invoice comparison found several differences
  When the bot prepares the explanation
  Then it groups differences into business causes such as discount expiry, usage overage, option change, prorata, tax, fee or adjustment
  And it presents the most impactful causes first
```

---

## US-007 - Recevoir une synthese des causes de hausse ou baisse

**Parent:** EPIC-003  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want a concise explanation of the main causes of my invoice difference,  
So that I can quickly understand the situation.

### Acceptance Criteria

```gherkin
Scenario: Clear synthesis is produced
  Given the bot found explainable invoice differences
  When it answers the client
  Then it starts with the total difference
  And it lists the main causes in understandable language
```

---

## US-008 - Obtenir les preuves associees a chaque cause

**Parent:** EPIC-003  
**Status:** Draft  
**Priority:** High

### User story

As a client utilisateur final,  
I want each explanation to be backed by evidence,  
So that I can trust the answer.

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

---

## US-009 - Expliquer une regle tarifaire associee a l'ecart

**Parent:** EPIC-003  
**Status:** Draft  
**Priority:** Medium

### User story

As a client utilisateur final,  
I want the bot to explain the billing rule behind the difference,  
So that I understand why the charge applies.

### Acceptance Criteria

```gherkin
Scenario: Relevant billing rule is found
  Given a billing cause is confirmed by BSS evidence
  When a matching billing rule is available in the knowledge base
  Then the bot explains the rule in plain language
  And the explanation remains consistent with the BSS evidence
```

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
