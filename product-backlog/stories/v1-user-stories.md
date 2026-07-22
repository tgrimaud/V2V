# V1 User Stories - From-Scratch Restart

## Restart Note

All stories below assume a fresh implementation branch. The previous
implementation remains available on `main` as backup/reference, but these stories
do not depend on existing code.

---

## US-001 - Reconfirm The V1 Restart Baseline

**Parent:** EPIC-001
**Classification:** V1 foundation
**Status:** Draft
**Priority:** High

### User Story

As a product owner, I want the team to agree on the restart baseline, so that new
delivery work starts from the validated V1 outcome rather than from legacy code.

### Acceptance Criteria

```gherkin
Scenario: Restart baseline is explicit
  Given the project restarts from an empty implementation branch
  When the V1 scope is reviewed
  Then the team confirms that invoice delta explanation remains the V1 outcome
  And the previous implementation is treated as backup and reference only
```

---

## US-002 - Define The Delivery Sequence For The Empty Codebase

**Parent:** EPIC-001
**Classification:** V1 foundation
**Status:** Draft
**Priority:** High

### User Story

As a delivery lead, I want a clear first-build sequence, so that the team can
avoid rebuilding everything at once.

### Acceptance Criteria

```gherkin
Scenario: Delivery order is reviewable
  Given the V1 epics are reviewed
  When the first implementation sprint is planned
  Then each story is ordered behind the minimum evidence, comparison, voice, handoff and observability prerequisites it needs
```

---

## US-003 - Confirm The Channel And Identity Boundary

**Parent:** EPIC-001
**Classification:** V1 foundation
**Status:** Done
**Priority:** High

### User Story

As an architect, I want the product-visible boundary between channels and the
backend confirmed, so that identity, conversation and handoff responsibilities
are not duplicated.

### Acceptance Criteria

```gherkin
Scenario: Channel boundary is confirmed
  Given the V1 target supports phone, web voice and Genesys handoff
  When the architecture baseline is reviewed
  Then channels provide trusted context and media transport
  And the backend owns billing reasoning, guardrails, escalation policy and handoff content
```

### Review Evidence

- `docs/architecture/channel-identity-boundary.md`
- Validated by the user on 2026-07-09.

---

## US-004 - Identify The Customer At The Start Of The Exchange

**Parent:** EPIC-002
**Classification:** V1 core
**Status:** Draft
**Priority:** High

### User Story

As an end customer, I want the bot to know which customer account my request
concerns, so that the invoice explanation uses only my own billing context.

### Acceptance Criteria

```gherkin
Scenario: Customer identity is reliable enough
  Given a customer starts a billing explanation conversation
  When the channel, Genesys context, pilot context or BSS context identifies the customer with enough confidence
  Then the bot continues the invoice explanation journey for that customer
  And it does not ask the customer to repeat known information
```

```gherkin
Scenario: Customer identity is not reliable enough
  Given a customer starts a billing explanation conversation
  When the bot cannot determine the customer account with enough confidence
  Then the bot asks for clarification or starts the escalation path
  And it does not expose detailed invoice data
```

---

## US-005 - Retrieve Available Invoices And Billing Periods

**Parent:** EPIC-002
**Classification:** V1 core
**Status:** Draft
**Priority:** High

### User Story

As an end customer, I want the bot to find the invoices or periods that can be
compared, so that I do not have to manually provide all details.

### Acceptance Criteria

```gherkin
Scenario: Comparable periods are found
  Given the customer is identified
  When the bot looks for recent billing periods
  Then candidate invoices or periods are available for comparison
  And the bot can distinguish the latest period from previous comparable periods
```

---

## US-006 - Detect Insufficient BSS Evidence

**Parent:** EPIC-002
**Classification:** V1 core
**Status:** Draft
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
  And it offers a human handoff when appropriate
```

---

## US-007 - Use Realistic BSS/PDF Fixtures For V1 Validation

**Parent:** EPIC-003
**Classification:** V1 enabler
**Status:** Draft
**Priority:** High

### User Story

As a product and QA stakeholder, I want realistic billing fixtures, so that the
team can validate explanation behavior before full BSS sandbox access is stable.

### Acceptance Criteria

```gherkin
Scenario: Fixture set covers V1 cases
  Given the fixture set is reviewed
  Then it covers nominal, discount expiry, overage, proration, insufficient data and unreliable extraction journeys
  And each fixture has an expected product behavior
```

---

## US-008 - Handle Invoice Extraction Status

**Parent:** EPIC-003
**Classification:** V1 enabler
**Status:** Draft
**Priority:** High

### User Story

As an end customer, I want the bot to handle parseable, partial and unusable
invoice extraction safely, so that I receive only reliable explanations.

### Acceptance Criteria

```gherkin
Scenario: Extraction is partial or unusable
  Given invoice extraction is partial or unusable
  When the customer asks for a comparison
  Then confirmed information is separated from uncertain information
  And unsupported amounts are not presented as confirmed facts
```

---

## US-009 - Validate Billing And Pricing Knowledge For V1

**Parent:** EPIC-003, EPIC-005
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
  And the wording remains consistent with BSS evidence
```

---

## US-010 - Select Two Invoices Or Billing Periods To Compare

**Parent:** EPIC-004
**Classification:** V1 core
**Status:** Draft
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
  And states which two periods are being compared
```

---

## US-011 - Identify Changed Invoice Lines And Amounts

**Parent:** EPIC-004
**Classification:** V1 core
**Status:** Draft
**Priority:** High

### User Story

As an end customer, I want the bot to identify which invoice lines changed,
appeared or disappeared, so that I know where the price difference comes from.

### Acceptance Criteria

```gherkin
Scenario: Invoice lines changed
  Given two comparable invoices exist
  When the bot compares them
  Then it identifies lines that appeared, disappeared or changed amount
  And it calculates their contribution to the total difference
```

---

## US-012 - Identify The Main Business Causes

**Parent:** EPIC-004
**Classification:** V1 core
**Status:** Draft
**Priority:** High

### User Story

As an end customer, I want the bot to group invoice differences into business
causes, so that I understand why the invoice changed.

### Acceptance Criteria

```gherkin
Scenario: Main causes are identified
  Given invoice comparison found several differences
  When the explanation is prepared
  Then differences are grouped into business causes such as discount expiry, usage overage, option change, proration, tax, fee or adjustment
  And the most impactful causes are presented first
```

---

## US-013 - Expose Unresolved Or Unreconciled Amounts

**Parent:** EPIC-004, EPIC-005
**Classification:** V1 core
**Status:** Draft
**Priority:** High

### User Story

As an end customer, I want unexplained invoice amounts to be visible, so that I
am not misled by a partial explanation.

### Acceptance Criteria

```gherkin
Scenario: Total delta is not fully reconciled
  Given known causes do not explain the full invoice difference
  When the bot prepares the explanation
  Then the unexplained remainder is visible
  And the final explanation stays cautious
```

---

## US-014 - Receive A Synthesis Of Increase Or Decrease Causes

**Parent:** EPIC-005
**Classification:** V1 core
**Status:** Draft
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

---

## US-015 - Obtain Evidence For Each Cause

**Parent:** EPIC-005
**Classification:** V1 core
**Status:** Draft
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

---

## US-016 - Explain The Billing Rule Behind A Delta

**Parent:** EPIC-005
**Classification:** V1 core
**Status:** Draft
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

---

## US-017 - Disclose When No Reliable Explanation Can Be Produced

**Parent:** EPIC-005, EPIC-009
**Classification:** V1 core
**Status:** Draft
**Priority:** High

### User Story

As an end customer, I want the bot to clearly state when it cannot confirm an
explanation, so that I am not misled.

### Acceptance Criteria

```gherkin
Scenario: No reliable explanation can be produced
  Given the bot cannot confirm enough causes for the invoice difference
  When it answers the customer
  Then it explains that the difference cannot be confirmed from available data
  And offers or starts the appropriate handoff path
```

---

## US-018 - Call The Bot For A Spoken Invoice Explanation

**Parent:** EPIC-006
**Classification:** V1 core
**Status:** Draft
**Priority:** High

### User Story

As an end customer, I want to call the bot by phone and ask why my invoice
changed, so that I can get help without using a screen.

### Acceptance Criteria

```gherkin
Scenario: Phone Voice2Voice journey
  Given a customer calls the bot
  When the customer asks why their invoice changed
  Then the interaction is conducted by voice
  And the customer receives a spoken billing explanation or an escalation path
```

---

## US-019 - Ask From A Web Voice Chat

**Parent:** EPIC-006
**Classification:** V1 core
**Status:** Draft
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

## US-020 - Receive A Quick Spoken Acknowledgement During Long Analysis

**Parent:** EPIC-006
**Classification:** V1 core
**Status:** Draft
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

## US-021 - Interrupt The Bot During A Spoken Answer

**Parent:** EPIC-006, EPIC-010
**Classification:** V1 core
**Status:** Draft
**Priority:** Medium

### User Story

As an end customer, I want to interrupt the bot while it is speaking, so that the
conversation feels natural.

### Acceptance Criteria

```gherkin
Scenario: Customer interrupts the assistant
  Given the assistant is playing a spoken answer
  When the customer starts speaking
  Then the assistant stops playback
  And the interruption outcome is observable for pilot review
```

---

## US-022 - Use Text To Complement A Voice Question

**Parent:** EPIC-006
**Classification:** V1 enabler
**Status:** Draft
**Priority:** Low

### User Story

As an end customer, I want to type complementary information when needed, so that
I can clarify my request without leaving the web journey.

### Acceptance Criteria

```gherkin
Scenario: Written clarification complements voice
  Given the customer is using the web voice journey
  When they provide clarification in writing
  Then the bot uses it as part of the same conversation context
```

---

## US-023 - Be Transferred On Explicit Request

**Parent:** EPIC-007
**Classification:** V1 core
**Status:** Draft
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

## US-024 - Be Transferred When The Bot Lacks Enough Certainty

**Parent:** EPIC-007
**Classification:** V1 core
**Status:** Draft
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

## US-025 - Provide The Advisor With Usable Context

**Parent:** EPIC-007
**Classification:** V1 core
**Status:** Draft
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

## US-026 - Hand Off To Genesys With Advisor Context

**Parent:** EPIC-007
**Classification:** V1 core
**Status:** Draft
**Priority:** High

### User Story

As a contact-center advisor, I want escalated billing conversations to arrive
through Genesys with the bot context, so that I can continue the support journey
without asking the customer to repeat everything.

### Acceptance Criteria

```gherkin
Scenario: Escalation reaches Genesys
  Given a conversation is escalated
  When the bot starts the handoff
  Then Genesys receives the conversation summary, escalation reason, permitted identifiers, known evidence and unresolved points
```

```gherkin
Scenario: Genesys handoff outcome is observable
  Given a conversation is escalated to Genesys
  When the handoff completes or fails
  Then the handoff outcome, target queue, latency and error reason are available for pilot review
```

---

## US-027 - Validate Whether Full Genesys Voice Routing Is Required For The Pilot

**Parent:** EPIC-007, EPIC-010
**Classification:** V1 pilot gate
**Status:** Draft
**Priority:** Medium

### User Story

As a contact-center stakeholder, I want to decide whether pilot calls must enter
through Genesys, so that the team can separate mandatory handoff from optional
full voice routing.

### Acceptance Criteria

```gherkin
Scenario: Genesys voice entry decision is visible
  Given the pilot contact-center environment is reviewed
  When Genesys requirements are assessed
  Then the team knows whether Genesys is only the advisor handoff target or also the phone entry point
```

---

## US-028 - Read The Synthesis On The Web Page

**Parent:** EPIC-008
**Classification:** V1 enabler
**Status:** Draft
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

## US-029 - Consult The Global Delta

**Parent:** EPIC-008
**Classification:** V1 enabler
**Status:** Draft
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

## US-030 - Consult Cause Details

**Parent:** EPIC-008
**Classification:** V1 enabler
**Status:** Draft
**Priority:** Medium

### User Story

As an end customer, I want to see the main causes and their contribution, so that
I understand what explains the total difference.

### Acceptance Criteria

```gherkin
Scenario: Causes are displayed by impact
  Given several causes explain the invoice difference
  When the web synthesis is shown
  Then causes are listed clearly
  And each cause shows its impact when available
```

---

## US-031 - See Evidence And Analysis Limits

**Parent:** EPIC-008
**Classification:** V1 enabler
**Status:** Draft
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

## US-032 - Consult Line-By-Line Invoice Differences

**Parent:** EPIC-008
**Classification:** V1 enabler
**Status:** Draft
**Priority:** Medium

### User Story

As an end customer using the web journey, I want to inspect invoice lines behind
the explanation, so that I can understand which concrete charges changed.

### Acceptance Criteria

```gherkin
Scenario: Line differences are visible
  Given two invoices have been compared
  When the detailed web view is available
  Then the customer can see lines that appeared, disappeared or changed amount
  And those line differences remain consistent with the spoken explanation
```

---

## US-033 - Protect Personal Data Exposed To The Customer

**Parent:** EPIC-009
**Classification:** V1 enabler
**Status:** Draft
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

## US-034 - Audit Sensitive Consultations

**Parent:** EPIC-009
**Classification:** V1 enabler
**Status:** Draft
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

## US-035 - Disclose Analysis Limits

**Parent:** EPIC-009
**Classification:** V1 core
**Status:** Draft
**Priority:** High

### User Story

As an end customer, I want the bot to clearly state what it could not verify, so
that I understand the limits of the answer.

### Acceptance Criteria

```gherkin
Scenario: Analysis limit is disclosed
  Given the bot lacks enough evidence for a reliable answer
  When the customer asks for an explanation
  Then the bot clearly states the limitation
  And does not present an unconfirmed explanation as fact
```

---

## US-036 - Measure Key Voice Journey Timings By Pipeline Slice

**Parent:** EPIC-010
**Classification:** V1 pilot gate
**Status:** Done (STT sprint scope) — see `docs/observability/voice-journey-timing.md`
**Priority:** High

### User Story

As a product owner, I want to measure the voice journey by pipeline slice, so
that the team can identify where latency is introduced.

### Acceptance Criteria

```gherkin
Scenario: Voice journey timing is measurable by slice
  Given a customer completes a voice billing explanation journey
  When the journey is reviewed
  Then channel ingress, end-of-turn, STT, backend first token or action, TTS first audio and channel egress timings can be assessed separately
  And the journey exposes p50, p95 and p99 measurements for the reviewed sample
```

---

## US-037 - Measure Invoice Comparison Response Time

**Parent:** EPIC-010, EPIC-004
**Classification:** V1 pilot gate
**Status:** Draft
**Priority:** Medium

### User Story

As a product owner, I want to measure how long invoice comparison takes, so that
the billing explanation journey remains conversational without sacrificing
evidence quality.

### Acceptance Criteria

```gherkin
Scenario: Comparison duration is measurable
  Given a customer asks for an invoice explanation
  When the system retrieves evidence and compares invoices
  Then BSS/PDF evidence retrieval and deterministic comparison durations can be reviewed separately from voice latency
```

---

## US-038 - Track Escalations And Their Reasons

**Parent:** EPIC-010
**Classification:** V1 pilot gate
**Status:** Draft
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

## US-039 - Track Unresolved Questions

**Parent:** EPIC-010
**Classification:** V1 pilot gate
**Status:** Draft
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

## US-040 - Produce The Pilot Readiness Report

**Parent:** EPIC-010
**Classification:** V1 pilot gate
**Status:** Draft
**Priority:** High

### User Story

As a pilot sponsor, I want a readiness report combining customer outcomes,
latency, escalations and operational risks, so that I can decide whether V1 is
ready for pilot exposure.

### Acceptance Criteria

```gherkin
Scenario: Pilot readiness can be decided
  Given the V1 pilot candidate has been tested
  When the readiness report is reviewed
  Then it includes customer outcome coverage, evidence reliability, p50/p95/p99 latency, escalation reasons, unresolved questions and open risks
  And it separates Genesys contact-center metrics from AI-layer metrics when Genesys participates
```

---

## US-041 - End The Call When The Customer Signals They Are Done

**Parent:** EPIC-006
**Classification:** V1 core
**Status:** Draft (proposed 2026-07-16)
**Priority:** Medium

### User Story

As an end customer, when I signal that I am finished (for example "au revoir",
"merci, c'est tout", "bonne journée"), I want the bot to acknowledge and end the
call cleanly, so that I do not have to hang up manually and the conversation
closes naturally.

### Business Rules

| ID | Rule |
|----|------|
| BR-041-1 | The bot must not end the call while the customer still needs help — a closing word inside a longer request (or a negation such as "non, pas au revoir") must not terminate the call. |
| BR-041-2 | On a detected closing, the bot asks a short confirmation ("Souhaitez-vous autre chose ?") and ends only on a positive confirmation of being done (or silence); it never ends abruptly on the first closing word. |
| BR-041-3 | The end-of-call reason must be observable for pilot review, distinct from a manual hangup or an error/drop. |
| BR-041-4 | V1 covers French closing formulas; broader language coverage is deferred. |

### Acceptance Criteria

```gherkin
Scenario: Customer says a closing formula and the call ends cleanly
  Given the customer has received their answer
  When the customer clearly signals they are done (for example "au revoir")
  Then the bot asks whether they need anything else
  And when the customer confirms they are done (or stays silent)
  Then the bot gives a short spoken closing
  And the call ends cleanly without the customer having to hang up
  And the end-of-call reason is observable for pilot review
```

```gherkin
Scenario: A closing word inside a longer request does not end the call
  Given the customer is still explaining their problem
  When they use a closing word as part of a longer sentence
  Then the bot does not end the call
  And the conversation continues normally
```

### Decisions (2026-07-16, user)

- DEC-041-a: **Confirmation step** — on a detected closing the bot asks
  "Souhaitez-vous autre chose ?" and ends only on positive confirmation / silence
  (resolves OQ-041-a).
- DEC-041-b: **Hybrid detection** — a config-tunable FR closing-phrase list plus an
  anti-false-positive guard (standalone phrase, no negation such as "non, pas au
  revoir"); no LLM intent classifier in V1 (resolves OQ-041-b).

### Open Questions

- OQ-041-c: Timeout-based end of call (prolonged customer silence) — kept as a
  **separate future story**, not in this ticket.
- OQ-041-d: V1 channel boundary = **web session close only**; phone/Genesys hangup
  semantics deferred to the contact-center integration.

---

## US-042 - Choose The Conversation Language In The UI

**Parent:** EPIC-006 (Web voice journey) / related EPIC-005 (answer engine)
**Classification:** V1 core — language control; runtime-affecting (STT/TTS/answer).
**Status:** ✅ **Validated by user (2026-07-22)** — manual live test of the FR/EN selector on the
batch web voice path passed. Merge-ready; merge awaiting explicit user request. Batch web voice
path (`index.html`) DONE & live-verified — deterministic end to end. WebRTC streaming path
(`webrtc.html`) DONE (2026-07-22) — awaiting live browser mic verify.
- **Answer language**: UI FR/EN selector → runtime forwards `language` → backend forces
  `AnswerLanguage` (overrides detection). Live: same French question answers in EN or FR per
  selection; forced language also drives fallbacks/refusals (BUG-002 consistency).
- **STT (listening)**: per-session Gradium STT provider built per language (`fr`/`en`), selected
  from `envelope.language` in `WebVoiceIngress`.
- **TTS (speaking)**: per-session Gradium voice selected from `envelope.language` in
  `WebVoiceEgress` — French uses the default voice, English uses `GRADIUM_VOICE_ID_EN`
  (`vimnD4UQG_36P43U`, provided by the user, live-verified: `/api/voice/tts?language=en` returns
  audio). Set `GRADIUM_VOICE_ID_EN` in the gitignored `.env`.
- **WebRTC streaming path (`webrtc.html`)** — DONE (2026-07-22). The UI FR/EN selector rides on the
  WebRTC offer body; `WebRtcSignalingService._new_session` puts it on the session `ChannelEnvelope`
  (`for_web_turn(language=...)`). The envelope then: (a) forces the backend answer language via the
  shared `AnswerProcessor`; (b) selects the per-session **streaming** Gradium STT provider (fr/en maps
  built once in `server._streaming_stt_by_language`); (c) selects the per-session **streaming** TTS
  voice (fr = default, en = `GRADIUM_VOICE_ID_EN`, built in `server._streaming_tts_by_language`). The
  selector is locked for the duration of a live call (language is fixed per session). The batch WebRTC
  fallback path reuses the already language-aware `WebVoiceIngress`/`WebVoiceEgress`.
- Tests green: backend **217**, runtime **320** unit (incl. `WebRtcLanguageSelectionTest`) + **26** BDD.

**Remaining**: live browser-mic verification of the WebRTC path in FR and EN (unit + startup validated:
the server builds fr+en streaming STT/TTS maps at boot without error).
OQ-042-a (per-session Gradium language) is resolved for both the batch and WebRTC paths.
**Priority:** High
**Branch:** `us/US-042-ui-language-selector` (stacked on `task/TASK-BE-017-fr-csv-translation`
so the forced-French path can be tested against the translated FR corpus).
**Related:** TASK-BE-015 (per-turn answer language + its open risk on voice STT/TTS language),
TASK-BE-017 (FR corpus coverage — complementary, not a substitute).

### User Story

As a customer using the web voice/text UI, I want to explicitly choose my language
(French or English), so that the assistant listens, answers and speaks in that
language deterministically, instead of relying on automatic detection.

### Context

Today the language is inferred by the backend (`LanguageDetector`: question language →
session stickiness → configured default). Voice STT/TTS language is a global runtime env
(`GRADIUM_LANGUAGE`). This makes voice input/output language non-deterministic per user and
leaves the TASK-BE-015 voice-language risk open. An explicit UI choice fixes the language on
all three layers (STT, answer, TTS).

**Scope note:** this story makes the I/O language deterministic; it does **not** by itself
improve French retrieval coverage (an English-only corpus can still trigger the
insufficient-evidence fallback for some French questions). It is complementary to TASK-BE-017.

### In Scope

- A language selector (FR/EN) in the web UI (`index.html` and `webrtc.html`).
- The chosen language is sent to the voice runtime **per session** and drives Gradium STT
  (listening) and TTS (speaking) language.
- The chosen language is sent to the backend on `/converse` (and `/retrieve`) as an explicit
  **override** of `LanguageDetector` (the forced language wins).
- A configured default when the user makes no explicit choice (English for the Eir pilot).

### Out Of Scope

- Languages beyond French and English.
- Auto-detecting the browser/OS language (explicit user choice only for V1).
- Any change to which documents are retrieved (retrieval scope unchanged).

### Business Rules

- **BR1** — When the user selects a language, every layer uses it: STT listens in it, the LLM
  answers in it, and TTS speaks in it.
- **BR2** — The selected language overrides automatic per-turn detection for the whole session
  until the user changes it.
- **BR3** — With no explicit selection, the deployment default language applies (English pilot),
  preserving today's detection behavior as the fallback.
- **BR4** — Fallbacks, refusals and the escalation sentence follow the selected language
  (consistent with TASK-BE-015 BR4).

### Acceptance Criteria

```gherkin
Scenario: Selecting French makes the assistant speak French
  Given the customer selects French in the UI
  When they ask a question by voice
  Then the runtime transcribes with the French STT
  And the assistant answers in French
  And the reply is spoken with the French TTS voice

Scenario: Selecting English makes the assistant speak English
  Given the customer selects English in the UI
  When they ask a question by voice
  Then the assistant answers in English and the reply is spoken in English

Scenario: Forced language overrides detection
  Given the customer selected English
  When they happen to phrase a question in French
  Then the assistant still answers in English (the forced language wins)

Scenario: No selection uses the deployment default
  Given the customer made no language choice
  Then the assistant behaves as today (default English, with per-turn detection)
```

### Non-Functional Expectations

- The forced language is **observable per turn** (correlation id; the `[LANGUAGE]` log/metric
  records it) so QA can confirm the override took effect.
- The added contract field must not degrade the voice latency SLO (`time_to_first_audio`).

### Open Questions

- OQ-042-a: Does Gradium accept a per-request/per-session language for both STT and TTS, or
  only a client-level default? (Determines whether the runtime re-instantiates providers per
  session or passes language per call.)
- OQ-042-b: Should changing the language mid-session reset the conversation memory bucket
  (avoid mixed-language history), or keep it? Default assumption: keep, since answers are
  forced to the new language anyway.
