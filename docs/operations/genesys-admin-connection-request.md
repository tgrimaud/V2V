# Genesys Admin — Connection Request: Genesys Cloud → Voice Support Bot (Audio Connector / AudioHook)

> Ticket: TASK-INFRA-013 (created) · updated under TASK-INFRA-014 (2026-08-31) · coordination refresh TASK-INFRA-016 (2026-08-31) · Sprint 13 (Genesys Audio Connector, closed) · Status: **endpoint deployed + app-layer self-tested — ready for the Genesys admin to configure**
> Audience: Genesys Cloud administrators + our netops/runtime engineers.

## 1. Purpose
Configure a Genesys Cloud **Audio Connector (AudioHook)** integration so Genesys streams live call audio, over `wss`, to our Voice Support Bot pilot endpoint, and routes the by-reference handoff back to a human advisor queue at session end. **Genesys is the initiator** — it connects **inbound** to our endpoint.

## 1a. Current state (2026-08-31) — what is ready, what is not
- **Deployed:** the connector ships in pilot image **`v0.8.0`** and the AudioHook endpoint is **enabled** (`VOICE_GENESYS=on`) on both bridge nodes **`vla-ai4cc-t01` / `t02`** at `:8090`, path `/genesys/audiohook` (ADR-0047 single async server). Both containers report healthy.
- **Self-tested (Step 0b, PASSED):** a full Voice2Voice turn ran against the **deployed** endpoint — HMAC connection-auth accepted, **L16** codec round-trip, session lifecycle (`open`→`opened`→audio→`close`→`closed`), and a grounded RAG answer (~15.5 s of TTS audio, first response ~2.2 s) with the complete telemetry chain (`connection_auth` → `stt.transcript.final` → `voice.backend.streamed` → `tts.audio.final`).
- **This proves:** the application-layer contract (auth handshake, codec, session, RAG V2V) works on the running pilot behind the edge (validated at the bridge `:8090`, via an internal tunnel).
- **Edge verified internally (2026-08-31):** the HAProxy TLS edge on `:443`, the ingress NAT `10.195.59.39 → VIP .10`, and the served cert (CN+SAN match) are confirmed working from inside the network (§4).
- **This does NOT yet prove / resolve (needs the Genesys admin + our netops):** **⚠️ public-SaaS reachability + TLS trust** — the endpoint is a **private `10.x` / `.prod.lan`** name behind a **private CA** (`mtMC`), so Genesys Cloud can neither reach nor trust it as-is (top blocker, §4); plus the **Genesys egress firewall allowlist**, the **org-negotiated codec/native events**, and the Architect degraded branch. Those are the live-org steps (runbook Steps 1–6).
- **Credentials:** a pilot API key + base64 shared secret are generated and stored in our git-ignored vault (never committed). They are handed to the admin **out-of-band** for the first live test (see §7a), then rotated to any admin-mandated pair before real-PII calls.

## 2. Target endpoint (what Genesys connects TO — we provide)
| Item | Value | Status |
|---|---|---|
| Endpoint URL | `wss://vip-ai4cc-voice-t01.prod.lan/genesys/audiohook` | **resolved** — the bridge mounts the AudioHook handler at `GET /genesys/audiohook` (ADR-0047 server, `:8090`); the deployed HAProxy edge passes the path through unchanged (no rewrite, no prefix — TASK-INFRA-016), so the public path equals the application path. |
| Domain (TLS SNI) | `vip-ai4cc-voice-t01.prod.lan` | confirmed (flow-request §1) |
| Ingress IP (VIP) | **`10.195.59.39`** | confirmed (flow-request §1/§3) |
| Protocol / port | **`wss` over TLS, TCP `:443`** | confirmed |
| Direction | **Genesys cloud → our VIP (inbound)** | confirmed |
| Internal routing | TLS terminated at HAProxy → bridge `:8090` (ADR-0047 single async server) | confirmed (internal, FYI only) |
| Transport | WebSocket (AudioHook control + binary audio; **wire = 8 kHz L16 preferred, or PCMU** — the adapter resamples to the internal PCM16/16 kHz boundary) | confirmed |

> Discrepancy resolved: `pilot-voice-access.md` shows `.10/.103/.104` short names — these are internal tenant-mesh (`192.168.0.0/24`) addresses, NOT the external ingress. The correct inbound target is **`10.195.59.39`** per the authoritative `flow-requests-eir-ai4cc-tst.md`, corroborated by the live-measurement runbook.

> **AudioHook path + `@authority` — RESOLVED (TASK-INFRA-016, from the deployed HAProxy config).** The runtime route is fixed in code: the ADR-0047 async server mounts the AudioHook handler at **`GET /genesys/audiohook`** on the bridge `:8090` (`GENESYS_ROUTE = "/genesys/audiohook"`). The deployed edge (`deploy/haproxy/haproxy.cfg`, `frontend voice_https` on `192.168.0.10:443` → `default_backend voice_bridges` = `192.168.0.103:8090` / `.104:8090`) does **`mode http` with no path rewrite, no ACL, no prefix** and **does not rewrite the `Host` header** (it only adds `X-Forwarded-Proto`). Consequences:
> - **Public URL is exactly `wss://vip-ai4cc-voice-t01.prod.lan/genesys/audiohook`** — the path is passed through unchanged.
> - **`@authority` is preserved end-to-end** → the bridge re-derives the same authority Genesys signed, so **no `GENESYS_AUDIOHOOK_AUTHORITY` override is needed** (leave it empty).
> - The `Connection: upgrade` WS handshake is tunnelled on the same `voice_bridges` backend via the global `timeout tunnel 1h` — the config comment explicitly anticipates the Genesys Audio Connector.
> - Residual (host-level, not config): confirm the **`10.195.59.39` → VIP `192.168.0.10:443` ingress NAT/routing** and the **TLS cert** actually loaded (`voice-vip.pem`) covers `vip-ai4cc-voice-t01.prod.lan` — see §4.

## 3. Network / firewall (Genesys admin + our netops)
- Open **inbound TCP `:443` (wss)** from **Genesys org egress IP ranges → `10.195.59.39`**.
- **Genesys egress IP ranges = TO CONFIRM (Genesys admin)** — the flow-request doc states this allowlist does not exist yet; we need the ranges to open the firewall.
- No UDP / no TURN / no SIP media needed (AudioHook is TCP/wss only).

## 4. TLS
Live-verified 2026-08-31 (TASK-INFRA-016, read-only from a voice node):
- **DNS**: `vip-ai4cc-voice-t01.prod.lan` resolves to **`10.195.59.39`** (the ingress Genesys will resolve).
- **Reachability + NAT**: `10.195.59.39:443` and VIP `192.168.0.10:443` are both OPEN and serve the **same** edge cert → the ingress NAT `10.195.59.39 → VIP .10 → HAProxy` is wired.
- **Certificate served**: `subject CN=vip-ai4cc-voice-t01.prod.lan`, `SAN DNS:vip-ai4cc-voice-t01.prod.lan` (matches the SNI), valid **2026-08-14 → 2026-11-12** (renew before expiry for a longer pilot).
- ⚠️ **Trust blocker — issuer is a PRIVATE CA** (`CN=CA_2_NJJ_MTMC_Default, O=mtMC`), the hostname is on the **internal `.prod.lan`** zone, and `10.195.59.39` is **RFC1918 private** space. A public SaaS (Genesys Cloud) will neither trust a private CA out-of-the-box nor reach a private IP / resolve `.prod.lan` over the public internet.
- **MUST resolve before the live-org test (netops + Genesys admin):** confirm the actual Genesys→endpoint path (dedicated interconnect / VPN / private peering / on-prem Genesys edge) **and** the cert trust model — either (a) Genesys is configured/able to trust the internal `mtMC` CA chain, or (b) expose the AudioHook endpoint on a **public FQDN with a publicly-trusted cert**. *(This does not affect the internal Step 0b self-test, which already passed.)*

## 5. Audio Connector / AudioHook integration (Genesys admin configures)
| Item | Value | Status |
|---|---|---|
| Target URI | `wss://vip-ai4cc-voice-t01.prod.lan/genesys/audiohook` (§2) | resolved — HAProxy edge passes the path through unchanged (TASK-INFRA-016); public path = application path |
| Authentication | **API key header** (`X-API-KEY`, default) + **IETF HTTP Message Signature** (`Signature` + `Signature-Input`, `alg="hmac-sha256"`) over the AudioHook covered components (`@request-target`, `@authority`, `audiohook-organization-id`, `audiohook-session-id`, `audiohook-correlation-id`, `x-api-key`) | scheme **implemented + validated end-to-end on the deployed endpoint** (Step 0b self-test, 2026-08-31); verified BEFORE the WS upgrade (TASK-INFRA-012). Our pilot **shared secret + API key are ready** (handed over per §7a); the **live tenant's exact signing values (header casing, `expires`/`created`/`nonce`) TO CONFIRM** against the org. Endpoint **fails closed** if enabled but unconfigured. |
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

## 7a. Credential handover (API key + shared secret)
- A **pilot pair** (API key + base64-encoded shared secret) is generated and deployed on the endpoint (stored only in our git-ignored Ansible vault; never committed, never in this doc).
- **Handover channel:** deliver the pair to the Genesys admin **out-of-band** (password manager / encrypted message), never over email or chat in clear text and never in a ticket. The admin enters them in the Genesys Audio Connector integration credentials.
- **Who signs:** Genesys is the client and **signs each handshake** with the shared secret (API key sent as `X-API-KEY`); our runtime **base64-decodes the same secret** and re-verifies the HMAC-SHA256 before the WS upgrade. The pair must match byte-for-byte on both sides.
- **Rotation:** if the admin mandates their own secret, they provide it, we rotate the vault value + re-deploy, then re-run Step 0b. Rotate again to a fresh production secret **before any real-PII call** (the pilot secret is for the synthetic/non-PII measurement only).

## 8b. Request to the Genesys admin — start now (copy-paste checklist)
Send this alongside the tables above. What we need the admin to do/return to schedule the first live test:
1. **Confirm the network path (blocker):** the endpoint is a **private** `10.x` IP on the internal `.prod.lan` zone — Genesys Cloud cannot reach it over the public internet. Confirm how the org connects (dedicated interconnect / VPN / private peering / on-prem Genesys edge). The edge path itself is verified working internally (§4).
2. **Provide the Genesys egress IP ranges** so our netops can open inbound `:443` (the allowlist does not exist yet — §3).
3. **Confirm TLS trust (blocker):** our edge cert is issued by a **private CA** (`mtMC`) for `vip-ai4cc-voice-t01.prod.lan` — a public CA cannot issue for a `.lan` name. Confirm either Genesys can be made to trust the internal CA chain, or we must expose a **public FQDN with a publicly-trusted cert** (§4).
4. **Confirm a premium integration slot** is available (1 of ≤5) and the **15-min session cap** is acceptable for the pilot (§5).
5. **Create the Audio Connector integration**, receive our **API key + shared secret** via the secure channel (§7a), select codec **L16** (fallback PCMU), target the endpoint URL.
6. **Build the Architect inbound flow** on a **pilot DID** (to provide): Call Audio Connector action + a **failure/timeout branch → billing advisor queue** (to provide) + a **`handoff_id`** participant attribute (report the size/type limit) — §6.
7. **Grant Genesys Analytics access** so we can capture cloud-leg timings during measurement (§6).
8. **Agree a measurement slot** to run runbook Steps 1–6 together (synthetic/non-PII audio first; PII residency sign-off is a separate gate, §8 / OQ-006).

## 8. Values to confirm (owner)
| Item | Owner |
|---|---|
| ~~AudioHook URL path~~ — **resolved**: application route `/genesys/audiohook` | ✅ known (runtime) |
| ~~HAProxy edge rule → whether the public path == `/genesys/audiohook` or a rewritten prefix~~ — **resolved (TASK-INFRA-016)**: passed through unchanged (no rewrite/ACL/prefix) | ✅ known (`deploy/haproxy/haproxy.cfg`) |
| ~~Signed `@request-target` / `@authority` behind the edge (`GENESYS_AUDIOHOOK_AUTHORITY`)~~ — **resolved (TASK-INFRA-016)**: `Host` not rewritten → authority preserved, no override needed (leave empty) | ✅ known (`deploy/haproxy/haproxy.cfg`) |
| ~~Ingress NAT/routing `10.195.59.39` → VIP `192.168.0.10:443`, and TLS cert covers `vip-ai4cc-voice-t01.prod.lan`~~ — **verified 2026-08-31** (NAT wired, same cert, CN+SAN match; §4) | ✅ known (live check) |
| **TLS trust + public reachability blocker**: private CA (`mtMC`) + `.prod.lan` name + `10.x` private IP → how does Genesys Cloud reach + trust the edge? (interconnect/VPN + CA trust, or public FQDN + public cert) | Our netops + Genesys admin (§4) |
| Edge cert renewal before expiry (`2026-11-12`) for a longer pilot | Our netops |
| Shared secret + exact API-key header casing (`GENESYS_AUDIOHOOK_API_KEY_HEADER`, default `X-API-KEY`) | Genesys admin + us (TASK-INFRA-012) |
| Genesys egress IP ranges (firewall allowlist) | Genesys admin |
| Pilot DID / test number | Genesys admin |
| Billing advisor queue | Genesys admin |
| Negotiated codec (L16 vs PCMU) | Genesys admin |
| Architect variable/attribute limits | Genesys admin |
| PII-audio residency/egress sign-off (before real-PII calls) | Security/Compliance |

> Pilot note: the first live measurement runs with **synthetic / non-PII audio** (the PII residency sign-off is a separate OQ-006 item, required only before routing real customer calls).

> Internal pre-flight (no Genesys needed) — **done 2026-08-31**: our runtime team self-tested this endpoint's auth handshake, L16 codec and session lifecycle against the **deployed** pilot with `voice-agent/scripts/genesys_local_client.py` (runbook **Step 0b**, TASK-WEB-047) — **PASSED** with a full grounded V2V answer. This validates everything except the cloud legs, the org-negotiated codec and native events, which remain for the live-org campaign (Steps 1–6).

## References
- `docs/operations/genesys-live-measurement-runbook.md` (live cloud-leg measurement procedure, incl. **Step 0** local self-test)
- `docs/integrations/genesys-architect-flow-contract.md` (Architect control/routing contract + by-reference handoff)
- `docs/architecture/adrs/ADR-0049-genesys-audio-connector-sprint-13-delivery-shape.md`
- `docs/architecture/adrs/ADR-0047-single-async-http-websocket-server-one-port.md`
- Authoritative networking source: `flow-requests-eir-ai4cc-tst.md` (§1 IP↔hostname, §3 Genesys inbound wss/443)
