# Genesys Admin — Connection Request: Genesys Cloud → Voice Support Bot (Audio Connector / AudioHook)

> Ticket: TASK-INFRA-013 · Sprint 13 (Genesys Audio Connector) · Status: draft for Genesys admin handoff
> Audience: Genesys Cloud administrators + our netops/runtime engineers.

## 1. Purpose
Configure a Genesys Cloud **Audio Connector (AudioHook)** integration so Genesys streams live call audio, over `wss`, to our Voice Support Bot pilot endpoint, and routes the by-reference handoff back to a human advisor queue at session end. **Genesys is the initiator** — it connects **inbound** to our endpoint.

## 2. Target endpoint (what Genesys connects TO — we provide)
| Item | Value | Status |
|---|---|---|
| Endpoint URL | `wss://vip-ai4cc-voice-t01.prod.lan/<audiohook-path>` | path **TO CONFIRM** (runtime eng.) |
| Domain (TLS SNI) | `vip-ai4cc-voice-t01.prod.lan` | confirmed (flow-request §1) |
| Ingress IP (VIP) | **`10.195.59.39`** | confirmed (flow-request §1/§3) |
| Protocol / port | **`wss` over TLS, TCP `:443`** | confirmed |
| Direction | **Genesys cloud → our VIP (inbound)** | confirmed |
| Internal routing | TLS terminated at HAProxy → bridge `:8090` (ADR-0047 single async server) | confirmed (internal, FYI only) |
| Transport | WebSocket (AudioHook control + binary **PCM16 / 16 kHz**) | confirmed |

> Discrepancy resolved: `pilot-voice-access.md` shows `.10/.103/.104` short names — these are internal tenant-mesh (`192.168.0.0/24`) addresses, NOT the external ingress. The correct inbound target is **`10.195.59.39`** per the authoritative `flow-requests-eir-ai4cc-tst.md`, corroborated by the live-measurement runbook.

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
| Target URI | our endpoint (§2) | provide once path confirmed |
| Authentication | API key + connection **HMAC signature** | scheme + **shared secret TO CONFIRM** (we must agree the secret; verification owned by TASK-INFRA-012; endpoint is currently **default-off** until then) |
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
**We provide to Genesys:** endpoint URL (once path fixed), TLS cert/domain, agreed auth shared secret, codec preference (L16), our inbound IP/port (`10.195.59.39:443`).
**Genesys provides to us:** egress IP ranges, pilot DID, advisor queue, integration-slot confirmation, AudioHook auth scheme details, Analytics access.

## 8. Values to confirm (owner)
| Item | Owner |
|---|---|
| AudioHook URL path (`<audiohook-path>`) | Our runtime engineer |
| Auth scheme + shared secret (API-key/HMAC) | Genesys admin + us (TASK-INFRA-012) |
| Genesys egress IP ranges (firewall allowlist) | Genesys admin |
| Pilot DID / test number | Genesys admin |
| Billing advisor queue | Genesys admin |
| Negotiated codec (L16 vs PCMU) | Genesys admin |
| Architect variable/attribute limits | Genesys admin |
| PII-audio residency/egress sign-off (before real-PII calls) | Security/Compliance |

> Pilot note: the first live measurement runs with **synthetic / non-PII audio** (the PII residency sign-off is a separate OQ-006 item, required only before routing real customer calls).

## References
- `docs/operations/genesys-live-measurement-runbook.md` (live cloud-leg measurement procedure)
- `docs/architecture/adrs/ADR-0049-genesys-audio-connector-sprint-13-delivery-shape.md`
- `docs/architecture/adrs/ADR-0047-single-async-http-websocket-server.md`
- Authoritative networking source: `flow-requests-eir-ai4cc-tst.md` (§1 IP↔hostname, §3 Genesys inbound wss/443)
