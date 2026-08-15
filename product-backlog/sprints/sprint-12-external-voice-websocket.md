# Sprint 12 — External Voice via Interim WebSocket Audio (Genesys-Ready)

## Sprint Objective

Give an **external** customer (a browser off the pilot subnet) a working
Voice2Voice path **without provisioning TURN**, by adding a **WebSocket audio
transport** (client→server TCP/TLS through the existing HAProxy edge) alongside
the same-subnet WebRTC path. Per ADR-0042 the external WebRTC media plane has no
route off `192.168.0.0/24` and TURN is deliberately unprovisioned; the WebSocket
path reuses the TLS edge that already works and carries the **same NAT-traversal
property as Genesys Audio Connector**.

The second, equally important goal is **capitalisation**: the transport is built
behind reusable seams so the Sprint 13 **Genesys Audio Connector** work
(ADR-0040) becomes *one more transport adapter*, not a from-scratch project.
ADR-0040 confirms Genesys AudioHook is "WebSocket over TLS, JSON control frames +
binary audio" — the same shape we build here.

**Decision of record:** ADR-0043 (refines ADR-0033, implements ADR-0042 point 4).

## Status

**Status:** 📋 **Planned** (defined 2026-08-15). Starts after Sprint 11 closes.
Decision #1 of the 2026-08-15 global-review decision loop (posture **B**:
interim WebSocket audio path) recorded in ADR-0042 (update) and specified by
ADR-0043.

**Sprint branch:** `feat/sprint-12-external-voice-websocket` (to fork from
`feat/restart-from-scratch` at sprint start). Two-level branch model as before:
ticket branches fork from and merge back into the sprint branch (`--no-ff`); the
sprint branch merges only on the user's explicit request.

## Roadmap Context

> **Re-sequencing note (2026-08-15, user-clarified):** the sprint order is **12 =
> WebSocket voice, 13 = Genesys, 14 = billing**. Inserting the external-voice WebSocket
> transport as Sprint 12 keeps **Genesys at Sprint 13** (its existing slot) and pushes
> **billing/identity to Sprint 14**. Genesys before billing is deliberate: the ADR-0043
> transport seams built here feed Genesys Audio Connector directly, so doing Genesys next
> capitalises while the design is fresh. The billing EPICs (EPIC-002/003/004) are **not**
> dropped, only resequenced.

| Sprint | Theme | State |
|---|---|---|
| Sprint 10 | Pilot-readiness latency & perceived latency | ✅ Done (closed 2026-07-31) |
| Sprint 11 | Remote deployment & release readiness (eir-ai4cc-tst) | 🚧 In progress |
| **Sprint 12** | **External voice via interim WebSocket audio (Genesys-ready)** | 📋 Planned (defined 2026-08-15) |
| Sprint 13 (tentative) | Telephony channel (US-018) + Genesys Audio Connector + advisor handoff (EPIC-007/012) | Planned — gated by OQ-006 |
| Sprint 14 (tentative, was 12) | Customer identity + BSS/PDF evidence + deterministic comparison (EPIC-002/003/004) | Planned — gated by OQ-001/003/004 |

## Why now (state that justifies the sprint)

- The pilot currently has **no external customer voice path**: on-subnet WebRTC and
  the batch `/api/voice/turn` demo work, but an off-subnet browser gets silent audio
  (ADR-0042). External stakeholders cannot try the bot before Genesys (Sprint 13).
- Standing up TURN for public WebRTC is **throwaway infra** the target (Genesys Audio
  Connector) replaces (ADR-0042). A WebSocket path avoids TURN entirely and reuses the
  working HAProxy TLS edge.
- Building the WebSocket transport **now, behind reusable seams**, turns the Sprint 13
  Genesys integration from a greenfield build into a transport-adapter swap — the
  session core, socket/demux, telemetry, correlation and capacity layers are shared
  (ADR-0043).
- The conversation core (`StreamingVoiceSession`) is already transport-agnostic; the
  only reason a second transport is "new work" is that the wiring is buried inside
  `WebRtcSignalingService`. Extracting it pays off twice (WebSocket now, Genesys later).

## Tickets

| Ticket | Title | Role | Status |
|---|---|---|---|
| TASK-WEB-026 | ADR-0043 + design spike: WebSocket audio transport socle (pipecat `WebsocketServerTransport` sans FastAPI vs hand-rolled WS upgrade on the stdlib server) + JSON-control/binary-PCM framing, on the shared async loop | Decide (architecture) | 📋 Planned |
| TASK-WEB-027 | Transport-agnostic **session factory**: extract session-building out of `WebRtcSignalingService`; WebRTC + WebSocket (+ future Genesys) become thin transport adapters over one `StreamingVoiceSession`; PCM16/16 kHz internal boundary, codec conversion inside adapters | Refactor (capitalisation) | 📋 Planned |
| TASK-WEB-028 | Browser WebSocket voice client: `ws.html` + `ws.js` (AudioWorklet mic capture → PCM16 frames over `wss`; return-audio playback via `pcm-worklet.js`); language selected at connect; safe failure surfaces | Build (frontend) | 📋 Planned |
| TASK-WEB-029 | Barge-in / end-of-turn on the WebSocket path via the **pluggable control-signal seam** (energy/amplitude detectors + 350 ms hold reused; ADR-0025 point-7 amplitude gate applies; verify interruption cancels cleanly over WS) | Build (runtime) | 📋 Planned |
| TASK-WEB-030 | Session capacity ceiling + backpressure + **per-slice OpenTelemetry** on the WebSocket path (reuse `VOICE_MAX_*`, `voice.webrtc.*`-equivalent gauges, one correlation id/call) | Build (runtime + observability) | 📋 Planned |
| TASK-INFRA-010 | HAProxy edge: `wss` upgrade routing to the bridge (Connection: upgrade, long-lived timeouts, sticky to a bridge for the call), deploy env + docs; no TURN | Wire (infra) | 📋 Planned |
| TASK-WEB-031 | QA: functional validation + **per-slice latency report** on the WebSocket path (mouth-to-ear p95 vs ADR-0029) + degraded-behaviour note (TCP head-of-line, weaker AEC) | QA | 📋 Planned |

Full ticket details live in `tasks/web-voice-tasks.md` (TASK-WEB-026…031) and
`tasks/deployment-tasks.md` (TASK-INFRA-010).

## Genesys-readiness checklist (capitalisation — enforced at review)

- [ ] Framing is **JSON control frames + binary PCM16/16 kHz audio** (AudioHook-shaped).
- [ ] A **transport-agnostic session factory** exists; WebRTC and WebSocket both build
      through it; no session logic remains WebRTC-specific.
- [ ] The internal audio boundary is **PCM16/16 kHz**; no sample-rate/codec assumption
      leaks into the shared core (Genesys PCMU/L16-8 kHz transcoding fits in an adapter).
- [ ] Barge-in/end-of-turn/playback/call-end are an **internal event vocabulary** with a
      **pluggable source**, named after Genesys semantics for a 1:1 mapping.
- [ ] The AudioHook **schema/auth/codec is NOT built** here (deferred to Sprint 13 — YAGNI).

## Out Of Scope

- **TURN / STUN provisioning** — explicitly rejected (ADR-0042); the WebSocket path
  removes the need for it.
- **The Genesys AudioHook protocol** (schema, handshake, auth, PCMU/L16 transcoding,
  Architect flow) — Sprint 13, gated by OQ-006; only the reusable seams are built now.
- **Billing/identity, BSS/PDF evidence, deterministic comparison** — resequenced to
  Sprint 14.
- **Any change to what the bot says** — DEC-002 grounding stays enforced; this sprint
  changes *how external audio reaches the runtime*, not answer content.
- **WebRTC replacement** — WebRTC stays the same-subnet/dev live transport (ADR-0033);
  WebSocket is the external-reach interim path, not a WebRTC replacement.

## Exit Criteria

- An **off-subnet browser** completes a full Voice2Voice turn over the WebSocket path
  through the HAProxy edge, with no TURN provisioned (TASK-WEB-026/028/030, TASK-INFRA-010).
- WebRTC same-subnet behaviour is **unchanged** after the session-factory extraction; the
  existing WebRTC + voice-agent tests stay green (TASK-WEB-027).
- Barge-in and end-of-turn work on the WebSocket path via the shared control-signal seam;
  interruption cancels cleanly (TASK-WEB-029).
- The WebSocket path emits the canonical **per-slice OpenTelemetry** spans under one
  correlation id, and honours the session-capacity ceiling (TASK-WEB-030).
- A QA report records functional pass + per-slice p50/p95 vs ADR-0029 and documents the
  TCP/AEC degraded behaviour (TASK-WEB-031).
- The **Genesys-readiness checklist** above is satisfied and confirmed at adversarial
  review — the Sprint 13 Genesys Audio Connector is reachable as a transport-adapter swap.
- Each ticket passes adversarial review ≥ 90% then QA before the branch is merge-ready.
  Merge only on the user's explicit request.
