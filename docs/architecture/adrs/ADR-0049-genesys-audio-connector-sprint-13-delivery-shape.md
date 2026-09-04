# ADR-0049: Genesys Audio Connector Sprint 13 Delivery Shape (Spike-Gated)

## Status

Proposed (2026-08-27). **Strategic direction decided, technical delivery spike-gated.**

Two product decisions are now fixed (2026-08-27) and are treated as settled inputs to
this ADR:

- **[DEC-012] Genesys is the full phone entry point for the pilot** — full Audio
  Connector voice routing is the pilot target (not spike-only); Twilio/SIP (US-018) is
  deferred.
- **[DEC-013] Escalation handoff travels by reference** — Genesys carries only an opaque
  `handoff_id` + minimal routing metadata; the backend owns and serves the context/PII.

What stays **Proposed / spike-gated** is the *technical feasibility* of that committed
direction: the **TASK-WEB-025** spike remains a **latency/feasibility go/no-go** on the
measured Genesys leg vs the [ADR-0029](ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md)
budget (mouth-to-ear p95 ≤ 1.5 s). Deciding Genesys as the entry does **not** waive that
gate: a **gate-fail escalates to the user for a decision** (mitigation / re-scope /
timeline) — it is **not** an auto-proceed onto the V1 critical path, and **not** a silent
drop of the committed direction. This ADR moves to **Accepted** once the spike returns
**GO** and the residual [OQ-006](../../../product-backlog/open-questions/v1-open-questions.md#oq-006---genesys-handoff-integration-shape)
technical/compliance items (codec, 15-min cap, PII-audio residency, concurrency) are
signed off. **Refines** [ADR-0040](ADR-0040-genesys-audio-connector-v2v-media-plane.md)
(the 3-plane split). **Builds on** [ADR-0046](ADR-0046-websocket-primary-live-voice-transport.md),
[ADR-0047](ADR-0047-single-async-http-websocket-server-one-port.md),
[ADR-0043](ADR-0043-interim-websocket-audio-transport-genesys-ready.md),
[ADR-0019](ADR-0019-escalation-rules-and-handoff-contract.md),
[ADR-0020](ADR-0020-genesys-handoff-v1-full-audio-connector-optional.md),
[ADR-0009](ADR-0009-independent-channel-adapters-shared-java-backend.md),
[ADR-0029](ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md),
[ADR-0025](ADR-0025-barge-in-native-interruption.md), [ADR-0001](ADR-0001-java-backend-owns-conversation-domain.md).
Source review: `docs/architecture/reviews/genesys-audio-connector-adversarial-review-2026-08-07.md`
(Must-fix R1–R6). Sprint: `product-backlog/sprints/sprint-13-genesys-audio-connector.md`.

### Spike outcome hook (TASK-WEB-025) — status still Proposed (do not flip yet)

- **2026-08-28 — synthetic-first partial measurement (DEC-014).** The TASK-WEB-025 spike ran on
  **synthetic / non-PII audio only** and produced a **NO-GO-pending** result: the ADR-0029
  mouth-to-ear re-score is a **definitive FAIL at the measured floor** — the in-house base
  (p95 2.76 s, TASK-WEB-039) already exceeds the 1.5 s gate before any Genesys leg is added, while
  the Genesys transport+transcode overhead is small (L16 ~3.3 ms p95; PCMU ~17.4 ms p95). Codec:
  prefer **L16** end to end. Concurrency at target 3: pure-Python transcode serializes on 1 vCPU
  (~2.96×) → a native codec is required (R6). Report:
  `docs/qa/task-web-025-genesys-audio-connector-spike-report.md`.
- **This ADR stays `Proposed`.** The synthetic run does not, by itself, satisfy the gate: the
  Genesys cloud legs (ingress / Architect fork / egress), the negotiated codec, the 15-min cap and
  native barge-in/EOT events are **unmeasured** (need the live org). Per DEC-012 the FAIL floor is a
  **user decision** (mitigation / re-scope / timeline), not an auto-proceed.
- **2026-08-28 — user decision: DECOUPLE (DEC-015).** The DEC-012 escalation is resolved: the
  **Genesys connector build proceeds** (TASK-WEB-041 + follow-ons are unblocked from the ADR-0029
  gate), and the **ADR-0029 gate is tracked as a separate latency workstream** (documented FAIL,
  owned by TASK-BE-033 model choice / OpenAI key + TASK-STT-014 + TASK-BE-020) — because the FAIL is
  driven by the in-house base, not the (de-risked) Genesys transport. **The build is authorized
  under this decouple decision, but this ADR remains `Proposed`** and **no Genesys-path SLO is
  claimed** until the base latency closes and ADR-0029 is re-scored PASS. See
  `product-backlog/decisions/v1-decisions.md#dec-015` and the live-measurement runbook
  `docs/operations/genesys-live-measurement-runbook.md`.
- **Flip Proposed → Accepted only when** (a) the live-org measurement lands with a re-scored
  **GO** against ADR-0029, and (b) the residual OQ-006 items (codec confirmed, 15-min cap fit,
  PII-audio residency sign-off, concurrency within the premium ≤5 / 1-vCPU envelope) sign off. On a
  sustained NO-GO, park this ADR at `Proposed` with the report as the rationale. **The DEC-015
  decouple authorizes the build; it does not pre-satisfy this Accepted condition.**

## Context

ADR-0040 fixed the *target* Genesys integration as a three-plane split (media / control /
context) with **Audio Connector** (the bidirectional AudioHook feature) as the V2V media
plane, but explicitly **not implemented** and deferred to Sprint 13 under OQ-006. The
2026-08-07 adversarial review scored that target **2.2/5** and said *"proceed with
conditions — as a bounded, measured feasibility spike, NOT as V1 core"*, raising six
Must-fix risks (R1–R6): latency deficit, the 15-minute cap, absent degraded modes, dual
barge-in/end-of-turn logic, an unproven handoff mapping, and unquantified concurrency.

Two things changed the runtime foundation **after** ADR-0040:

- **ADR-0046** made **WebSocket the primary V1 live transport** (web + Genesys), demoting
  WebRTC to optional same-subnet/dev.
- **ADR-0047** unified the runtime onto a **single async HTTP+WebSocket server on one port**
  (delivered by TASK-WEB-038, shipped v0.7.0), reusing the **ADR-0043 transport-agnostic
  session factory** and a **PCM16/16 kHz internal boundary**.

Net: the Audio Connector media plane is now deliverable as **one more transport adapter** on
an async server that already exists — not a parallel stack. Sprint 13 needs a decision that
(a) fixes this delivery shape, (b) settles the R1–R6 conditions into concrete ticket-level
commitments, and (c) is honest that several sub-choices are **spike-to-confirm**, not
assumed.

## Decision

> **Implementation note (2026-08-31).** The TASK-WEB-025 spike returned NO-GO vs ADR-0029, but
> the user resolved the escalation as **DECOUPLE (DEC-015)**: the connector build proceeded
> (spike = GO-for-build) and shipped in Sprint 13 (deployed `v0.8.0`, `VOICE_GENESYS=on`). The
> ADR-0029 latency gate is a separate workstream; this ADR stays **Proposed** until the live-org
> cloud-leg re-score + OQ-006 sign-off. Points 4 and 6 below describe the **target** shape; see
> the per-point implementation notes for the current default.

Deliver the Genesys integration in Sprint 13 as the following shape (originally **gated by the
TASK-WEB-025 go/no-go**, resolved as DECOUPLE — see the note above):

1. **Media plane = a transport adapter, not a stack.** The Audio Connector AudioHook
   `wss://` endpoint is exposed on the **ADR-0047 single async HTTP+WebSocket server**,
   built via the **ADR-0043 session factory**. Codec conversion (**PCMU/µ-law ↔ PCM16**,
   **L16 ↔ PCM16**) lives **inside the transport adapter**; the shared session core stays
   PCM16/16 kHz. One bidirectional stream per session, IVR channel (TASK-WEB-041).

2. **Control/routing plane stays in Genesys Architect + Platform API.** A Genesys Architect
   **Call Audio Connector** action forks + pauses the flow to our endpoint; on session end
   the flow resumes and routes to the billing advisor queue. Our runtime never transfers the
   call itself (TASK-INFRA-012).

3. **Context/handoff plane stays backend-owned, transported by reference (DEC-013 —
   decided).** Genesys carries only an opaque **`handoff_id` + minimal routing metadata**
   through Architect variables / conversation attributes; the full audited
   `EscalationHandoff` (ADR-0019) is **fetched from the backend on demand** on an
   access-controlled, audited call. Carrying the escalation context **inline** in the
   Genesys event / Architect variables is **rejected** on **PII / trust-boundary** grounds
   (independent of, and in addition to, the Architect variable size/type limits, R5). The
   identifiers allowed to travel through Genesys are limited to the `handoff_id` + the
   minimal routing metadata the pilot trust model permits (TASK-BE-036 + TASK-BE-037).

4. **Barge-in / end-of-turn ownership is per path.** On the **Genesys path** the native
   Genesys events (`barge-in`, `playback-started`/`playback-completed`, `BotTurnResponse`)
   are the **target** authoritative source, with the in-house energy/amplitude detectors
   (ADR-0025) disabled; the in-house detectors remain the mechanism for the **WS/WebRTC dev
   path** (R4, TASK-WEB-042).
   > **Implementation note (2026-08-31).** As shipped, the default control mode is
   > `VOICE_GENESYS_CONTROL_MODE=detector`: the in-house detectors stay authoritative on the
   > Genesys path too, and the native-event map is an inert seam. The flip to native-authoritative
   > requires the live-org run that confirms the actual AudioHook event names/shapes (OQ-006).

5. **Degraded modes fail safe to the advisor queue.** Endpoint down/slow/timeout, session
   drop, 15-minute-cap timeout, and transcode failure each end the streaming session cleanly
   so Architect resumes and routes to a human — never dead air (R3, TASK-WEB-044 +
   TASK-INFRA-012). Backend conversation memory is preserved (ADR-0044 posture).

6. **Genesys is the committed full pilot entry (DEC-012), but delivery is latency-gated.**
   The strategic direction is fixed — full Audio Connector voice routing is the pilot
   target, not a spike-only experiment. What remains gated is *technical feasibility*: the
   full round trip is decomposed into per-leg slices under **one trace** (Genesys
   `conversationId` → OpenTelemetry) and re-scored against **ADR-0029** (mouth-to-ear
   p95 ≤ 1.5 s). While that gate is FAIL, the Audio Connector path is not moved onto the V1
   critical path, and a **gate-fail is escalated to the user for a decision** (mitigation /
   re-scope / timeline) — never an auto-proceed and never a silent drop of the committed
   direction. A minimal concurrency ceiling + backpressure is measured on a 1-vCPU-class
   runtime, and the premium ≤5-integrations/org budget is tracked (R1 + R6, TASK-WEB-043).

7. **The Genesys boundary is fixed (ADR-0001).** No RAG, billing reasoning, guardrails,
   escalation policy, handoff content, or conversation memory moves into Genesys. Genesys is
   the contact-center system of record; the Java backend is the conversation brain. Genesys
   is one channel behind the normalized envelope (ADR-0009): `channel`, `external_session_id`,
   `message_id`, `idempotency_key`, `reply_mode`, `escalation_context` (TASK-BE-037).

### What the spike (TASK-WEB-025) must resolve before commitment

This ADR is Proposed precisely because the following are **not assumed** — they are the
gate's outputs (also OQ-006 decision items):

- **R1 — Isolated Genesys-leg latency** and the ADR-0029 re-score (go/no-go for the media
  plane on the critical path).
- **R2 — 15-minute cap** vs the worst-case billing journey → keep-as-is, checkpoint/resume,
  or call-back.
- **R3 — At least one degraded mode** observed (Architect behaviour on endpoint-down).
- **R4 — Confirmation of the Genesys native events** and the per-path ownership rule.
- **R5 — Architect variable/attribute size + type limits** → the by-reference transport is
  already decided (DEC-013); the spike only measures the limits to size the **minimal
  routing metadata** riding alongside the `handoff_id` and to confirm which identifiers the
  trust model permits (inline context transport is not on the table).
- **R6 — A minimal concurrency ceiling** on a 1-vCPU-class runtime + the premium
  ≤5-integrations impact.
- **Codec (PCMU vs L16)** end to end + the transcode budget.
- **Data residency / egress** for the PII audio leaving the Genesys cloud to the runtime VMs.

### Implementation status (TASK-WEB-041, 2026-08-28)

The **media-plane transport adapter** (Decision point 1) is implemented on the ADR-0047
single async server; the spike (`voice-agent/spikes/genesys_audiohook/`) stays intact as
evidence. It lives entirely in the voice runtime (`voice-agent/web_voice/`) — **no backend
code changed** (ADR-0001 held):

- `genesys_app.py` — `GET /genesys/audiohook` handler: one bidirectional stream per session
  built through the unchanged ADR-0043 `SessionFactory`, a concurrency ceiling (default 3,
  `VOICE_GENESYS_MAX_SESSIONS`) with WS 1013 backpressure, and a **graceful 15-minute cap**
  (at the cap the session is *drained* — trailing partial finalized, answer spoken — then
  ended so Architect resumes; never a silent mid-call cut, R2). Per-channel OpenTelemetry
  (session/gauge/cap events + a deterministic `conversationId → traceparent`, one trace).
  The cap/drain machinery lives in `genesys_cap.py`; the constants, env resolvers and
  telemetry emitters in `genesys_config.py` (module-budget split, review remediation).

### Review remediation (TASK-WEB-041, 2026-08-28)

The 2026-08-28 adversarial code review raised two Major findings, both now closed in the
runtime (still ADR-0001-clean — no backend code):

- **Hard-bounded cap drain (Major #1).** At the cap the drain is wrapped in
  `asyncio.wait_for(drain, timeout=grace)`; if the drain wedges (a stuck STT/TTS provider)
  the session is force-`stop()`ped after the grace and a `voice.genesys.session_cap_forced`
  event is recorded, so the concurrency slot + WS are **always** freed at cap+grace and can
  never be held indefinitely. The grace is env-tunable (`VOICE_GENESYS_CAP_DRAIN_GRACE_MS`,
  default 5 s). A `DrainOnce` guard ensures the cap timer and the peer-disconnect handler
  never both drain the same session.
- **Endpoint exposure posture (Major #2, security).** The endpoint is now **default-off**
  (`--genesys off` / `VOICE_GENESYS=off`) and, when explicitly enabled, enforces an Origin
  allowlist (`VOICE_GENESYS_ALLOWED_ORIGINS`) mirroring `/ws`. **AudioHook signature / HMAC
  / API-key verification of the Genesys leg (TASK-INFRA-012) is now IMPLEMENTED** (IETF HTTP
  Message Signatures, HMAC-SHA256, X-API-KEY, fail-closed, golden-vector locked; Step 0b
  self-test PASSED 2026-08-31). The endpoint stays **default-off** and adds the Origin
  allowlist as a second reversible guard. Only the exact live-tenant header casing/secret
  remain TO CONFIRM against the real org (OQ-006).
- `genesys_framing.py` — subclasses the AudioHook-shaped `WebSocketAudioSerializer`, reusing
  its whole control channel and overriding only the audio path; emits `genesys.transcode.in`
  / `.out` per-leg spans.
- `genesys_codec.py` — **native, numpy-vectorized** PCMU/L16 ↔ PCM16/16 kHz transcode
  (prefer L16). This resolves **R6**: the spike's pure-Python per-sample loop held the GIL
  and serialized ~2.96× at concurrency 3; numpy releases the GIL on its vectorized C ops, so
  three concurrent transcodes now run **faster than three sequential** ones (measured
  `conc3/seq3 ≈ 0.45–0.54` on a multicore box; well under the pure-Python blow-up on 1 vCPU).
  `numpy` is already a transitive dependency (`opencv-python → numpy`), so this adds **zero**
  new wheels; it is pinned explicitly in `requirements.txt` because the codec now uses it
  directly (`audioop` is removed in Python 3.13+, so it was not an option).

What is **still gated / out of this ticket**: the ADR-0029 latency re-score on the real
Genesys leg (R1, needs a live org), the native barge-in/EOT ownership wiring (R4,
TASK-WEB-042), and the degraded-mode / resume-callback policy (R2/R3, TASK-WEB-044 +
TASK-INFRA-012). This ADR therefore stays **Proposed / latency-gated**.

## Consequences

- Sprint 13 is **gate-first**: the spike commits or defers everything else. A **NO-GO** parks
  this ADR at Proposed with the rationale, and the follow-on tickets carry forward — the
  backend conversation engine and the web/WS channels are unaffected.
- The Sprint-12 WebSocket transport + ADR-0043 session factory + ADR-0047 async server are
  **reused, not duplicated** — Genesys becomes a transport-adapter swap.
- The handoff stays **backend-owned and auditable** even under Genesys variable limits, which
  keeps escalation policy and billing evidence centralized (ADR-0001/0019).
- Latency honesty is preserved: the Genesys path is a **measured spike** until the gate is
  re-scored, so no premium provider silently degrades the (already-FAIL, TASK-WEB-039) gate.
- A per-path control-signal rule prevents the runtime from fighting the Genesys protocol
  (self-interruptions / lost turns).

## Alternatives Considered

- **Ship the Audio Connector media plane as V1 core now (no spike gate):** rejected — the
  ADR-0029 gate is already FAIL and the Genesys leg is unmeasured; the adversarial review
  explicitly required a measured spike first (R1).
- **Carry the full `EscalationHandoff` inline in Architect variables:** **rejected**
  (DEC-013) — primarily on **PII / trust-boundary** grounds (the audited escalation
  context and PII must not leave the backend trust boundary), and secondarily because
  variable/attribute size limits risk truncating summary + citations (R5). This is no
  longer kept as a fallback: only the opaque `handoff_id` + minimal routing metadata
  travels through Genesys.
- **Keep the in-house barge-in/end-of-turn detectors active on the Genesys path too:**
  rejected — duplicates and fights the Genesys native events (R4).
- **Build a bespoke Genesys media stack separate from the WS transport:** rejected — throws
  away the ADR-0043/0046/0047 capital; the async server + session factory are the intended
  substrate.
- **Add Twilio/SIP telephony as a second pilot entry in the same sprint:** **deferred**
  (US-018) — the single pilot entry is now decided as **Genesys** (DEC-012, the review's
  "pick one"); a second media profile would double the barge-in/latency surface to test.
- **Let Genesys own routing decisions / a Genesys-native voicebot:** rejected — contradicts
  ADR-0001/0040 (the backend is the conversation brain).

## Related Documents

- [ADR-0040 — Genesys Audio Connector V2V media plane](ADR-0040-genesys-audio-connector-v2v-media-plane.md) (refined by this ADR)
- [ADR-0046 — WebSocket primary live voice transport](ADR-0046-websocket-primary-live-voice-transport.md)
- [ADR-0047 — Single async HTTP+WebSocket server on one port](ADR-0047-single-async-http-websocket-server-one-port.md)
- [ADR-0043 — Interim WebSocket audio transport, Genesys-ready](ADR-0043-interim-websocket-audio-transport-genesys-ready.md)
- [ADR-0019 — Escalation rules and handoff contract](ADR-0019-escalation-rules-and-handoff-contract.md)
- [ADR-0020 — Genesys handoff in V1, full Audio Connector optional](ADR-0020-genesys-handoff-v1-full-audio-connector-optional.md)
- [ADR-0009 — Independent channel adapters, shared Java backend](ADR-0009-independent-channel-adapters-shared-java-backend.md)
- [ADR-0029 — Pilot latency criterion](ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md)
- [ADR-0025 — Barge-in native interruption](ADR-0025-barge-in-native-interruption.md)
- [ADR-0001 — Java backend owns the conversation domain](ADR-0001-java-backend-owns-conversation-domain.md)
- `docs/architecture/reviews/genesys-audio-connector-adversarial-review-2026-08-07.md` (R1–R6)
- `product-backlog/sprints/sprint-13-genesys-audio-connector.md`
- `product-backlog/open-questions/v1-open-questions.md` (OQ-006)
- `product-backlog/decisions/v1-decisions.md` — **DEC-012** (Genesys = full pilot entry),
  **DEC-013** (escalation handoff by reference), **DEC-014** (spike synthetic-first),
  **DEC-015** (DECOUPLE — ADR-0029 gate decoupled from the Genesys build)
- `docs/operations/genesys-live-measurement-runbook.md` — live-org cloud-leg measurement procedure
- `docs/qa/task-web-025-genesys-audio-connector-spike-report.md` — spike go/no-go report
- Tickets: TASK-WEB-025 (gate), TASK-WEB-041/042/043/044, TASK-BE-036/037, TASK-INFRA-012
