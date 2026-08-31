# Genesys Admin — Connection Request: Genesys Cloud → Voice Support Bot (Audio Connector / AudioHook)

> Ticket: TASK-INFRA-013 (created) · updated under TASK-INFRA-014 (2026-08-31) · Sprint 13 (Genesys Audio Connector) · Status: draft for Genesys admin handoff
> Audience: Genesys Cloud administrators + our netops/runtime engineers.

## 1. Purpose
Configure a Genesys Cloud **Audio Connector (AudioHook)** integration so Genesys streams live call audio, over `wss`, to our Voice Support Bot pilot endpoint, and routes the by-reference handoff back to a human advisor queue at session end. **Genesys is the initiator** — it connects **inbound** to our endpoint.

## 2. Target endpoint (what Genesys connects TO — we provide)
| Item | Value | Status |
|---|---|---|
| Endpoint URL | `wss://vip-ai4cc-voice-t01.prod.lan/genesys/audiohook` | **application path known** — the bridge mounts the AudioHook handler at `GET /genesys/audiohook` (ADR-0047 server, `:8090`). The public path depends on the HAProxy edge rule — see the note below. |
| Domain (TLS SNI) | `vip-ai4cc-voice-t01.prod.lan` | confirmed (flow-request §1) |
| Ingress IP (VIP) | **`10.195.59.39`** | confirmed (flow-request §1/§3) |
| Protocol / port | **`wss` over TLS, TCP `:443`** | confirmed |
| Direction | **Genesys cloud → our VIP (inbound)** | confirmed |
| Internal routing | TLS terminated at HAProxy → bridge `:8090` (ADR-0047 single async server) | confirmed (internal, FYI only) |
| Transport | WebSocket (AudioHook control + binary **PCM16 / 16 kHz**) | confirmed |

> Discrepancy resolved: `pilot-voice-access.md` shows `.10/.103/.104` short names — these are internal tenant-mesh (`192.168.0.0/24`) addresses, NOT the external ingress. The correct inbound target is **`10.195.59.39`** per the authoritative `flow-requests-eir-ai4cc-tst.md`, corroborated by the live-measurement runbook.

> **AudioHook path — resolved + one thing to confirm.** The runtime route is fixed in code: the ADR-0047 async server mounts the AudioHook handler at **`GET /genesys/audiohook`** on the bridge `:8090` (`GENESYS_ROUTE = "/genesys/audiohook"`). What remains to confirm is purely the **HAProxy edge rule** on the VIP:
> - If HAProxy passes the path through unchanged, the public URL to give Genesys is exactly **`wss://vip-ai4cc-voice-t01.prod.lan/genesys/audiohook`**.
> - If HAProxy adds/rewrites a prefix (e.g. `/voice/…`), Genesys dials the **edge** path and HAProxy must remap it to the bridge's `/genesys/audiohook`. In that case give Genesys the edge URL.
> - HMAC caveat: the AudioHook signature covers `@request-target` and `@authority`; if the edge rewrites host/path, pin the authority runtime-side via `GENESYS_AUDIOHOOK_AUTHORITY` (owner: our netops/runtime; `TODO(TASK-INFRA-012: live-measurement)`).

## 3. Network / firewall (Genesys admin + our netops)
- Open **inbound TCP `:443` (wss)** from **Genesys org egress IP ranges → `10.195.59.39`**.
- **Genesys egress IP ranges = TO CONFIRM (Genesys admin)** — the flow-request doc states this allowlist does not exist yet; we need the ranges to open the firewall.
- No UDP / no TURN / no SIP media needed (AudioHook is TCP/wss only).

## 4. TLS
- Our HAProxy edge certificate must be valid (trusted CA) for **`vip-ai4cc-voice-t01.prod.lan`** — Genesys will refuse an untrusted/self-signed cert.
- Confirm Genesys trusts our issuing CA chain. *(We provide the cert/domain; Genesys confirms trust.)*

## 5. Audio Connector / AudioHook integration (Genesys admin configures)
| Item | Value | Status |
|---|---|---|
| Target URI | `wss://vip-ai4cc-voice-t01.prod.lan/genesys/audiohook` (§2) | application path known; confirm the public path with our netops (HAProxy edge rule) |
| Authentication | **API key header** (`X-API-KEY`, default) + **IETF HTTP Message Signature** (`Signature` + `Signature-Input`, `alg="hmac-sha256"`) over the AudioHook covered components (`@request-target`, `@authority`, `audiohook-organization-id`, `audiohook-session-id`, `audiohook-correlation-id`, `x-api-key`) | scheme **implemented** and verified BEFORE the WS upgrade (TASK-INFRA-012); **shared secret + exact header casing TO CONFIRM** (negotiated with the Genesys admin). Endpoint **fails closed** if enabled but unconfigured. |
| Signature freshness / replay | `expires` mandatory; `created` age-bounded (default 300 s); reused `nonce` refused (bounded cache) | implemented (TASK-INFRA-012); exact `expires`/`created`/`nonce` the live tenant emits **TO CONFIRM** (all env-tunable) |
| Codec | request **L16** (preferred); **PCMU** acceptable | confirm negotiated codec |
| Premium integration slot | consumes 1 of the **≤5** premium integrations | confirm slot availability |
| Session cap | **15-minute** Audio Connector cap | confirm/tune vs worst-case billing journey |
| Concurrency | pilot target **3 concurrent sessions** | confirm fits ≤5 envelope |

## 6. Architect flow (Genesys admin builds)
- **Inbound call flow** on a pilot **DID / test number** — **provide the DID (TO CONFIRM)**.
- A **Call Audio Connector** action (fork/pause) targeting our endpoint.
- A **failure/timeout branch → billing advisor queue** (endpoint down → fail-safe to a human, never dead air) — **provide the queue (TO CONFIRM)**.
- An Architect **variable/participant attribute** carrying only the opaque **`handoff_id`** + minimal routing metadata (skill/language) — **no inline PII, no escalation context** (fetched by reference). **Report the variable size/type limits (TO CONFIRM).**
- **Genesys Analytics access** for us to capture cloud-leg timings during measurement.

## 7. Who provides what
**We provide to Genesys:** endpoint URL (`wss://vip-ai4cc-voice-t01.prod.lan/genesys/audiohook`, subject to the final HAProxy edge rule), TLS cert/domain, agreed auth shared secret + API-key header name, codec preference (L16), our inbound IP/port (`10.195.59.39:443`).
**Genesys provides to us:** egress IP ranges, pilot DID, advisor queue, integration-slot confirmation, AudioHook auth scheme details, Analytics access.

## 8. Values to confirm (owner)
| Item | Owner |
|---|---|
| ~~AudioHook URL path~~ — **resolved**: application route `/genesys/audiohook` | ✅ known (runtime) |
| HAProxy edge rule → whether the public path == `/genesys/audiohook` or a rewritten prefix | Our netops |
| Signed `@request-target` / `@authority` behind the edge (`GENESYS_AUDIOHOOK_AUTHORITY`) | Our netops/runtime |
| Shared secret + exact API-key header casing (`GENESYS_AUDIOHOOK_API_KEY_HEADER`, default `X-API-KEY`) | Genesys admin + us (TASK-INFRA-012) |
| Genesys egress IP ranges (firewall allowlist) | Genesys admin |
| Pilot DID / test number | Genesys admin |
| Billing advisor queue | Genesys admin |
| Negotiated codec (L16 vs PCMU) | Genesys admin |
| Architect variable/attribute limits | Genesys admin |
| PII-audio residency/egress sign-off (before real-PII calls) | Security/Compliance |

> Pilot note: the first live measurement runs with **synthetic / non-PII audio** (the PII residency sign-off is a separate OQ-006 item, required only before routing real customer calls).

## References
- `docs/operations/genesys-live-measurement-runbook.md` (live cloud-leg measurement procedure)
- `docs/integrations/genesys-architect-flow-contract.md` (Architect control/routing contract + by-reference handoff)
- `docs/architecture/adrs/ADR-0049-genesys-audio-connector-sprint-13-delivery-shape.md`
- `docs/architecture/adrs/ADR-0047-single-async-http-websocket-server-one-port.md`
- Authoritative networking source: `flow-requests-eir-ai4cc-tst.md` (§1 IP↔hostname, §3 Genesys inbound wss/443)
