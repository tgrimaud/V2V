# Genesys Architect Flow — Control / Routing Contract (Voice Support Bot Audio Connector)

> Ticket: TASK-INFRA-012 · Sprint 13 (Genesys Audio Connector) · Status: **draft / preparation**
> Audience: Genesys Cloud administrators + architects, plus our runtime/ops engineers.
> Companion to the connection-auth verification shipped in the same ticket (voice runtime).

## Objective

Specify the **control/routing plane** the Genesys Architect flow must implement so a pilot
call can (1) reach our authenticated Audio Connector `wss` endpoint, (2) stream bidirectional
audio while the bot answers, and (3) resume and route the caller to a **human billing advisor
queue** at session end or on failure — carrying the escalation handoff **by reference**
(`handoff_id`, DEC-013) with no inline PII.

This is the plane owned by **Genesys Architect + the Platform API** (ADR-0040 / ADR-0049
decision point 2). No conversation logic, RAG, guardrails, or escalation content lives here —
that stays backend-owned (ADR-0001). This document is the shape the flow must implement; the
exact tenant-specific values are marked **TO CONFIRM** and are pending the live Genesys
measurement (`genesys-live-measurement-runbook.md`).

## Scope

- **In scope:** the Architect control vocabulary the flow must send/observe, the endpoint the
  flow forks to (incl. connection auth), the by-reference handoff routing back to the advisor
  queue, and the failure/timeout fail-safe branch.
- **Out of scope:** the media/transcode plane (TASK-WEB-041 transport adapter), the backend
  handoff store + fetch API (TASK-BE-036), the normalized envelope population (TASK-BE-037),
  and native barge-in/EOT ownership (TASK-WEB-042). This contract cross-links them.

## Source Systems

| System | Role in this contract |
|---|---|
| Genesys Cloud CX (Architect + Audio Connector integration) | Contact-center system of record: DID/IVR, Call Audio Connector fork, queues, advisor routing, participant attributes. |
| Voice Support Bot runtime (`voice-agent`, ADR-0047 async server) | Terminates the AudioHook `wss` connection, **authenticates it** (API key + HMAC signature, TASK-INFRA-012), runs the V2V session, ends the session so Architect resumes. |
| Voice Support Bot backend (Java) | Owns the audited `EscalationHandoff` and serves it by reference on `GET /api/conversation/escalation-handoffs/{handoff_id}` (TASK-BE-036, api-key gated). |

## Target Flow

```
Inbound DID ─▶ Architect inbound call flow
                 │
                 ├─▶ Call Audio Connector action ──(wss + X-API-KEY + Signature)──▶ our /genesys/audiohook
                 │        (fork + pause; bidirectional PCM16/16 kHz audio)          (auth verified BEFORE session build)
                 │
                 │   on session end (bot done OR escalation requested)
                 ▼
             flow resumes ─▶ set participant attribute escalation_context = { handoff_id, … }
                          └─▶ route to BILLING ADVISOR QUEUE (carrying the handoff reference)
                 │
                 └─(endpoint unreachable / no answer within guard delay)─▶ FAIL-SAFE branch ─▶ advisor queue (never dead air)
```

## Contract

### 1. Reaching the endpoint (connection + auth)

The **Call Audio Connector** action must target our endpoint and present the AudioHook
connection auth that the runtime now verifies **before building the session** (TASK-INFRA-012):

| Item | Value | Status |
|---|---|---|
| Endpoint URL | `wss://vip-ai4cc-voice-t01.prod.lan/<audiohook-path>` | path **TO CONFIRM** (runtime eng.) |
| Auth: API key header | `X-API-KEY: <api-key>` | header name configurable (`GENESYS_AUDIOHOOK_API_KEY_HEADER`, default `X-API-KEY`) — **TO CONFIRM** exact casing on the live tenant |
| Auth: signature | `Signature` + `Signature-Input` (IETF HTTP Message Signatures, `alg="hmac-sha256"`) over the covered components (`@request-target`, `@authority`, `audiohook-organization-id`, `audiohook-session-id`, `audiohook-correlation-id`, `x-api-key`) | scheme implemented; **shared secret TO CONFIRM** (negotiated with the Genesys admin) |
| Shared secret | configured Genesys-side (integration credentials) + runtime-side (`GENESYS_AUDIOHOOK_SECRET`, base64) | **TO CONFIRM** |
| Freshness | after the HMAC is verified, the signature MUST carry `expires` (absent/stale/future → refused); when `created` is present its age is bounded to `GENESYS_AUDIOHOOK_MAX_SIGNATURE_AGE_S` (default 300s) with a small clock skew | implemented |
| Replay | a reused `nonce` is refused via a bounded in-memory cache (`GENESYS_AUDIOHOOK_NONCE_CACHE_SIZE`, default 10000, FIFO eviction) | implemented |
| Fail-closed | if the runtime endpoint is enabled but no key + secret is configured it **refuses every connection** (`rejected_not_configured`) — never opens; the handler also requires an authenticator so a forgotten wiring fails closed | implemented |

> **Freshness / replay policy.** `expires` is mandatory (a missing/stale/future one is
> rejected via the ordinary bad-signature outcome, so no unbounded label is added). `created`
> and `nonce` stay OPTIONAL: the published Genesys golden vector carries a far-future
> `expires` and a fixed `created`, so it remains admissible when the clock is near that
> `created`; the signature base / canonicalization is unchanged. The nonce cache is bounded
> and safe for the single async handler thread. The **exact** `expires` / `created` / `nonce`
> and skew the live tenant emits are **TODO(TASK-INFRA-012: live-measurement)** — all
> env-tunable, so live values drop in without a code change.

> **`@request-target` / `@authority` note.** Behind the pilot HAProxy edge the signed
> request-target path and authority may be rewritten before reaching the bridge. The runtime
> exposes `GENESYS_AUDIOHOOK_AUTHORITY` to pin the authority; the exact signed values are
> **TODO(TASK-INFRA-012: live-measurement)** against the live tenant.

### 2. Control vocabulary (what the flow sends / observes)

| Control point | Direction | Meaning |
|---|---|---|
| Call Audio Connector **fork + pause** | Architect → runtime | Start streaming call audio bidirectionally; pause the flow while the bot owns the turn. |
| Session **end** (runtime closes the WS cleanly) | runtime → Architect | Bot is done (answer delivered) or escalation is requested; Architect **resumes** the flow. |
| Native turn events (`barge-in`, `playback-started`/`playback-completed`, `BotTurnResponse`) | Genesys ⇄ runtime | Own barge-in / end-of-turn **on the Genesys path**; in-house detectors are disabled there (ADR-0049 §4, TASK-WEB-042). |
| **15-minute cap** | both | AudioHook per-session cap; the runtime drains gracefully at the cap so Architect resumes and routes to a human — never a silent mid-call cut (R2). |

### 3. By-reference handoff → advisor queue (DEC-013)

On resume the flow routes the caller to the billing advisor queue **carrying only a reference**:

- Set an Architect **participant attribute / variable** `escalation_context` holding the opaque
  **`handoff_id`** plus **minimal routing metadata** the trust model permits — reference shape
  (TASK-BE-036, snake_case at the boundary):

```json
{
  "handoff_id": "<opaque id>",
  "reason_code": "<e.g. billing_dispute_unresolved>",
  "priority": "<e.g. normal|high>"
}
```

- **No inline escalation context and no PII** travel through Genesys. The full audited
  `EscalationHandoff` (ADR-0019: summary, citations, customer/billing context) stays
  backend-owned and is fetched **by reference** by the advisor tooling on an api-key-gated call:

  `GET /api/conversation/escalation-handoffs/{handoff_id}` → the audited handoff payload
  (TASK-BE-036; 401/403 without the api key, 404 for an unknown id).

- The advisor queue receives the caller with the `handoff_id` attached so the advisor desktop
  can retrieve the context server-side at answer time.

### 4. Fail-safe / degraded branch (R3)

The Call Audio Connector action must have a **failure / timeout branch**: if our endpoint is
unreachable or does not respond within a defined **guard delay**, the flow routes the caller
**straight to the billing advisor queue** — never dead air (ADR-0049 §5, pairs with
TASK-WEB-044). This branch is exercised deliberately in the live-measurement runbook (Step 4d).

## Error Cases

| Case | Expected behaviour |
|---|---|
| Auth fails (bad/missing API key or signature) | Runtime refuses the connection before the session builds (HTTP 401); Architect sees no media → fail-safe branch → advisor queue. |
| Endpoint enabled but unconfigured | Runtime fails closed (HTTP 503); same fail-safe outcome. |
| Endpoint unreachable / timeout | Fail-safe branch → advisor queue after the guard delay. |
| 15-minute cap reached | Runtime drains gracefully, ends the session; Architect resumes → advisor queue with the handoff reference. |
| Handoff fetch fails advisor-side | Advisor handles the call without the enriched context; the caller is still routed (never dropped). |

## Missing Inputs / To Confirm (owner)

| Item | Owner | Status |
|---|---|---|
| AudioHook URL path (`<audiohook-path>`) on the ADR-0047 server | Our runtime engineer | TO CONFIRM |
| Exact API-key header name/casing on the live tenant | Genesys admin + us | TO CONFIRM (`GENESYS_AUDIOHOOK_API_KEY_HEADER`) |
| Shared secret (API-key/HMAC) | Genesys admin + us | TO CONFIRM |
| Signed `@request-target` / `@authority` behind the HAProxy edge | Our runtime/netops | `TODO(TASK-INFRA-012: live-measurement)` |
| Pilot DID / test number | Genesys admin | TO CONFIRM |
| Billing advisor queue (id/name) | Genesys admin | TO CONFIRM |
| Genesys egress IP ranges (firewall allowlist) | Genesys admin | TO CONFIRM |
| Architect variable/attribute size + type limits (to size the routing metadata, R5) | Genesys admin | TO CONFIRM |
| Premium integration slot (of ≤5) consumed | Genesys admin | TO CONFIRM |
| Native barge-in/EOT events confirmed on the path (R4) | Genesys admin + us | TO CONFIRM (TASK-WEB-042) |

## Open Questions

- **OQ-006** — Genesys handoff integration shape (codec, 15-min cap fit, PII-audio residency,
  concurrency) — gates the ADR-0049 `Proposed → Accepted` flip alongside the live latency
  re-score.
- **DEC-015** — the Genesys build proceeds decoupled from the ADR-0029 latency gate; **no SLO
  is claimed** on the Genesys path until the base latency closes and the live re-score passes.

## Next Steps

1. Genesys admin fills the TO-CONFIRM values during the live-measurement run (runbook Steps 1–2).
2. Runtime engineer sets `GENESYS_AUDIOHOOK_API_KEY` / `GENESYS_AUDIOHOOK_SECRET` (and, if the
   edge rewrites host, `GENESYS_AUDIOHOOK_AUTHORITY`) and enables `--genesys on`.
3. Resolve the `TODO(TASK-INFRA-012: live-measurement)` seams (signed request-target/authority,
   header casing) against the live tenant.
4. Verify the fail-safe branch and the by-reference handoff end to end; only then consider the
   ADR-0049 Accepted flip (with the OQ-006 sign-offs).

## Related Documents

- `docs/operations/genesys-admin-connection-request.md` — admin connection request checklist (TASK-INFRA-013).
- `docs/operations/genesys-live-measurement-runbook.md` — live cloud-leg measurement procedure (TASK-WEB-025).
- `docs/architecture/adrs/ADR-0049-genesys-audio-connector-sprint-13-delivery-shape.md` — delivery shape + 3-plane split.
- `docs/architecture/adrs/ADR-0047-single-async-http-websocket-server-one-port.md` — the server that hosts the `wss` endpoint.
- `docs/architecture/adrs/ADR-0040-genesys-audio-connector-v2v-media-plane.md` — media/control/context plane split.
- Backend handoff fetch route (TASK-BE-036): `GET /api/conversation/escalation-handoffs/{handoff_id}` (api-key gated, snake_case).
- Voice-runtime connection auth (TASK-INFRA-012): `voice-agent/web_voice/genesys_auth.py` + `genesys_signature.py`.
