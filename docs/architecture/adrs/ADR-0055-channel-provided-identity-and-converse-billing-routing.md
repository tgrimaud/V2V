# ADR-0055: Channel-provided customer identity + RAG↔billing routing on `/converse`

## Status

Accepted (2026-09-29)

## Context

Since ADR-0052 the deterministic billing chain (identity → comparable invoices → comparison →
confidence gate → grounded phrasing) is reachable **only** through the dedicated
`POST /api/conversation/billing-explain` endpoint, which requires an explicit customer
`reference` in the request body. The conversational path used by the voice runtime and the web
UI — `POST /api/conversation/converse` — stays **RAG-only**: it never resolves an account and
never runs the billing chain. ADR-0052 explicitly left "routing from `/converse`" as a follow-up.

Two concrete gaps followed from that:

1. **No identity on `/converse`.** When a customer asks *"I don't understand, my bill is higher
   than last month"* through the app, the backend has no account reference, so it can only answer
   with generic RAG content — it cannot compare the customer's own invoices.

2. **Vocally collecting the account number is undesirable for the pilot.** Asking the customer to
   dictate an 8-digit account id over voice is slow, error-prone (STT on digit strings) and does
   not reflect the **target** architecture, where identity is established by the channel **up
   front**: Genesys supplies the ANI / an authenticated session, or an authenticated web/mobile
   front-end passes the account in a header or query parameter. The conversation engine should
   receive identity as ambient session context, not extract it from the transcript.

The target contract (ADR-0050 identity seam, BR-002-1) already accepts a **channel-provided
reference**: the channel is trusted to assert *who* the customer is; the backend resolves that
reference to a billing `AccountId` behind `CustomerDirectoryPort`. What was missing is the
**transport** of that reference from the channel into `/converse`, and the **routing** decision
once it is present.

## Decision

### D1 — The channel supplies the customer reference up front (primary path)

The customer account reference is provided by the **channel**, once, at the start of the
conversation, and carried as session identity:

- **Pilot / demo simulation.** The web UI (`ws.html`, `webrtc.html`, `index.html`) gains an
  account **listbox** with the three eir B2C sample accounts (`99224964`, `99226126`, `99226337`)
  plus a **"Sans compte"** (no account) default. The selection is sent on connect as
  `?account_id=<ref>` (WebSocket + batch) or in the WebRTC offer body (`account_id`). This
  **simulates** the target header/param without asking for the number vocally.
- **Target.** Genesys ANI / an authenticated header or query param populates the same
  `account_id`. No code change in the conversation engine is needed — only the channel producer
  changes.

The reference rides the Python `ChannelEnvelope` (`account_reference`), which is built **once per
connection** (session-locked, exactly like the ADR / BUG-026 language lock), then the
`AnswerRequest`, then the backend `/converse` body as `account_id`. **"Sans compte" → no
`account_id`** is sent.

Vocal collection of the account number is **explicitly out of scope** for this decision; if it is
ever needed it becomes a *fallback* behind the same identity seam (a later ticket), never the
primary path.

### D2 — the conversation endpoints route RAG ↔ billing on (identity present ∧ billing intent)

> **Amended (BUG-027, 2026-09-29):** routing applies to **both** conversation endpoints —
> the blocking `POST /api/conversation/converse` **and** the streaming
> `POST /api/conversation/converse-stream` (SSE). The streaming path is the **real voice
> path** (`VOICE_BACKEND_STREAM` on by default), so shipping the routing on `/converse`
> only meant the voice UI never reached the billing chain. Both paths now share one
> routing decision (`BillingRoutingService`); on a billing turn the streaming session emits
> the pre-computed grounded billing text as a `chunk` + `done` (the billing chain returns a
> full vetted answer, not a token stream — ADR-0052 D1a), otherwise it streams RAG tokens.

A turn is routed to the deterministic billing chain **iff**:

- the channel supplied an account reference (`account_id` non-blank), **and**
- the transcript is a billing question, per the existing deterministic `BillingIntentDetector`
  (ADR-0052 D2a — no embedding / no query classifier, BUG-007 / OQ-008).

Otherwise the turn takes the unchanged **RAG** path. In particular **"no account" + billing
question → RAG generic** (fail-safe: we never guess whose invoice to open). Identity resolution,
comparable-invoice selection, the confidence gate and DEC-002 grounding are all unchanged — this
ADR only *reaches* the ADR-0052 chain from `/converse`; it adds no new billing logic.

The routing **decision** is a single application service `BillingRoutingService`
(`Optional<GeneratedAnswer> billingAnswer(RoutableTurn)` — returns the billing answer on a hit,
empty on a miss). It composes `AnswerBillingQuestionUseCase` (the ADR-0052 billing chain) and a
new conversation **out-port** `BillingIntentPort`. Both endpoints share it (single source of
truth for the predicate + billing-request mapping):

- the blocking path wraps it in `ConversationRoutingService` (`ConversationRoutingUseCase`
  in-port), which `ConverseController` depends on instead of `ConverseUseCase`; a miss falls back
  to `ConverseUseCase` (RAG);
- the streaming path (`ConverseStreamSession`) calls `billingAnswer` first; a hit is emitted as a
  `chunk` + `done`, a miss streams RAG tokens via `ConverseStreamUseCase`.

The turn is passed as a `RoutableTurn` value object (`transcript`, `conversationKey`,
`forcedLanguage`, `accountReference`, `channel`, `correlationId`), which also owns the
`toBillingExplanationRequest()` mapping so both paths build an identical billing request.

### D3 — Cross-context intent seam (no type leakage)

The single source of truth for billing-intent detection stays `BillingIntentDetector` in the
billing context. It is now exposed through a **published inbound port**
`DetectBillingIntentUseCase` (billing `port/in`) and consumed from the conversation context
through the conversation-owned out-port `BillingIntentPort`, wired by a thin
`InProcBillingIntentAdapter`. This mirrors the existing `BillingExplanationPort` /
`InProcBillingExplanationAdapter` seam (ADR-0052 D3c) — no billing domain type crosses into the
conversation domain, and ContextBoundaryTest / HexagonalArchitectureTest stay green.

### D4 — Privacy

The account reference is **personal data**. It is **never logged or exported in clear** on either
tier. Only its **presence** is observable: the backend logs `[ROUTE] route={billing|rag}
account_ref_present={true|false}`, and the Python envelope telemetry adds
`account_ref_present="true"` (never the value). This aligns with ADR-0050 ("the claimed reference
is never logged in clear").

## Consequences

**Positive**

- The app path finally answers *"my bill is higher than last month"* with the customer's own
  invoices, without a dedicated endpoint call and without asking for the number vocally.
- The pilot listbox demonstrates the target header/param model with zero conversation-engine
  change when the real channel is wired.
- Hexagonal boundaries preserved: one billing-intent source of truth, exposed via a published
  port, consumed via a conversation seam. Streaming (`/converse-stream`) and every other
  `ConverseUseCase` consumer are untouched.
- Fail-safe: no account, or a non-billing turn, always keeps the RAG path.

**Negative / residual**

- **Pilot trust model (unchanged from ADR-0050).** A channel-provided reference is accepted at a
  low bar (existence in the mock `InMemoryCustomerDirectoryAdapter`). No strong auth — governed by
  **OQ-001**; must not ship to real customers until then.
- The routing decision is binary (billing vs RAG) with no mid-conversation identity change; the
  reference is session-locked. Switching account mid-call requires a reconnect (acceptable for the
  pilot).
- Confidence-gate escalations on structurally different multi-service invoices (new/removed
  services) remain — tracked by **TASK-BE-060**, not by this ADR.

## Alternatives considered

- **Keep `/billing-explain` only, collect the reference vocally.** Rejected: slow, STT-fragile on
  digit strings, and does not reflect the target channel-provided identity.
- **Run a runtime query/domain classifier to auto-detect billing turns without identity.**
  Rejected: BUG-007 / OQ-008 — no reliable per-question domain classifier exists; forcing one
  could drop relevant chunks. The deterministic `BillingIntentDetector` gates only *after* the
  channel has asserted identity.
- **Inject the billing use case straight into `ConverseController`.** Rejected: puts routing
  policy in the web adapter and couples the controller to two use cases + intent. A dedicated
  application service keeps the policy testable and the controller thin.

## References

- ADR-0052 (billing explanation behind the answer engine — the chain this ADR reaches)
- ADR-0050 (pilot customer identity resolution — channel-provided reference trust model)
- ADR-0019 (by-reference escalation handoff), DEC-002 (LLM only phrases grounded amounts)
- BUG-007 / OQ-008 (no runtime query classifier), BUG-026 (session-locked envelope precedent)
- TASK-BE-061 (implementation), TASK-BE-060 (multi-service cause-attribution follow-up)
