# Firewall flow requests — eir-ai4cc-tst pilot

Network-flow requests for the pilot, in the format the platform netsec team uses
(`Ip Src | Hostname Src | Ip Dst | Hostname Dst | Port | Proto | Description`).
Client sources are the two authorized ingress origins:

- `10.195.80.81` — `EXT_H_NAT-ITSF-Nice_Users` (Nice office NAT, VLAN NA)
- `10.195.29.11` — `EXT_H_NAT-ITSF-WireguardUsr` (Wireguard VPN, VLAN 456)

All pilot VMs sit on the Prodpriv network (VLAN 2909); their Prod IPs are in
[`deployment-eir-ai4cc-tst.md`](deployment-eir-ai4cc-tst.md#vm-inventory).

> **Scope — external ingress only.** Inter-VM / service traffic runs on the tenant mesh
> `192.168.0.0/24` (short names), which is **open between VMs, UDP included** (firewalld
> inactive on the app VMs; verified by a VM↔VM UDP round-trip). It therefore needs **no**
> flow request, and no internal flows are listed here — only external ingress from the two
> client sources. See the network model in
> [`deployment-eir-ai4cc-tst.md`](deployment-eir-ai4cc-tst.md#network-model--name-resolution).

## 1. Already requested (2026-08-13) — management + web signaling (TCP)

Opened per the 2026-08-13 request; recorded here for completeness.

| Ip Src | Ip Dst | Hostname Dst | Port | Proto | Description |
|--------|--------|--------------|------|-------|-------------|
| `10.195.80.81` / `10.195.29.11` | `10.195.56.56` | `vlp-ai4cc-t01.prod.lan` | 22 | TCP | SSH admin/deploy |
| `10.195.80.81` / `10.195.29.11` | `10.195.56.147` | `vlp-ai4cc-t02.prod.lan` | 22 | TCP | SSH admin/deploy |
| `10.195.80.81` / `10.195.29.11` | `10.195.58.234` | `vlb-ai4cc-t01.prod.lan` | 22 | TCP | SSH admin/deploy |
| `10.195.80.81` / `10.195.29.11` | `10.195.59.127` | `vla-ai4cc-t01.prod.lan` | 22 | TCP | SSH admin/deploy |
| `10.195.80.81` / `10.195.29.11` | `10.195.56.240` | `vla-ai4cc-t02.prod.lan` | 22 | TCP | SSH admin/deploy |
| `10.195.80.81` / `10.195.29.11` | `10.195.56.102` | `vla-ai4cc-t03.prod.lan` | 22 | TCP | SSH admin/deploy |
| `10.195.80.81` / `10.195.29.11` | `10.195.56.39` | `vla-ai4cc-t04.prod.lan` | 22 | TCP | SSH admin/deploy |
| `10.195.80.81` / `10.195.29.11` | `10.195.56.100` | `vlb-ai4cc-t02.prod.lan` | 22 | TCP | SSH admin/deploy |
| `10.195.80.81` / `10.195.29.11` | `10.195.59.39` | `vip-ai4cc-voice-t01` | 443, 80 | TCP | Voice UI + WebRTC **signaling** (HTTPS) |

> These carry the browser UI and the WebRTC **signaling** (SDP offer/answer over
> HTTPS). They do **not** carry the live audio: WebRTC **media is UDP** and is not in
> this request — see §2.

## 2. NEW request — WebRTC media (audio), remote clients

**Why:** the §1 flows are TCP-only. A browser voice turn negotiates the audio as
**UDP RTP/SRTP** media, peer-to-peer between the client and the answering bridge. The
mesh-level UDP openness is **VM↔VM only** — an external client crosses the filtered
Prodpriv boundary and the bridge advertises only its private `192.168.0.x` ICE candidate,
so it does not apply here. With remote clients behind NAT (Nice NAT, Wireguard) a **TURN
relay** is required so the media has a single, firewallable, publicly reachable path. The voice runtime already
consumes a TURN endpoint (`VOICE_TURN`/`VOICE_TURN_USERNAME`/`VOICE_TURN_CREDENTIAL` →
browser `iceServers`); it needs the relay to exist and be reachable (open input #12).

### Option A — TURN relay (recommended)

Requires a TURN server (e.g. coturn) with a known Prod IP `<TURN_PROD_IP>` and an agreed
relay media port range `<RELAY_MIN>-<RELAY_MAX>` (coturn `min-port`/`max-port`; a small
range is enough for the pilot, e.g. 64 ports). Open, from both client sources:

| Ip Src | Ip Dst | Port | Proto | Description |
|--------|--------|------|-------|-------------|
| `10.195.80.81` / `10.195.29.11` | `<TURN_PROD_IP>` | 3478 | UDP | STUN/TURN allocate + relay control |
| `10.195.80.81` / `10.195.29.11` | `<TURN_PROD_IP>` | `<RELAY_MIN>-<RELAY_MAX>` | UDP | TURN relayed media (RTP/SRTP) |
| `10.195.80.81` / `10.195.29.11` | `<TURN_PROD_IP>` | 3478 | TCP | TURN-over-TCP fallback (UDP blocked) |
| `10.195.80.81` / `10.195.29.11` | `<TURN_PROD_IP>` | 5349 | TCP | TURN-over-TLS (turns:) fallback |

Notes:
- Media is **bidirectional**; if the firewall is not stateful for UDP, allow the return
  path too.
- The TURN host must reach the two bridges (`10.195.59.127`, `10.195.56.240`) to relay
  media inward; if TURN sits on a different segment, add TURN↔bridge UDP relay flows.
- Decision owner for the relay port range = whoever hosts TURN (platform or VSB).

### Option B — direct host candidates (fallback, no TURN)

Open a UDP media range straight to each bridge Prod IP. Simpler, but **fragile behind
symmetric NAT** and needs the bridge's WebRTC UDP port range pinned (currently ephemeral;
would need a runtime change). Only viable if the client NAT allows it.

| Ip Src | Ip Dst | Hostname Dst | Port | Proto | Description |
|--------|--------|--------------|------|-------|-------------|
| `10.195.80.81` / `10.195.29.11` | `10.195.59.127` | `vla-ai4cc-t01.prod.lan` | `<UDP_RANGE>` | UDP | WebRTC media to bridge (host candidate) |
| `10.195.80.81` / `10.195.29.11` | `10.195.56.240` | `vla-ai4cc-t02.prod.lan` | `<UDP_RANGE>` | UDP | WebRTC media to bridge (host candidate) |

## 3. Genesys Audio Connector — ACTIVE (Sprint 13 shipped + deployed 2026-08-31)

**Status change (2026-08-31):** Sprint 13 is closed and the Genesys **Audio Connector**
endpoint is **deployed** on the pilot voice bridges (`v0.8.0`, `VOICE_GENESYS=on`, endpoint
`GET /genesys/audiohook` on the ADR-0047 routed `:8090`). This is now a **real flow request**,
not a future note. It uses a **different** profile from the WebRTC UDP/TURN flows in §1–§2.

- **Transport is `wss://` (WebSocket over TLS, TCP `:443`)**: AudioHook carries the JSON
  control frames **and** the 8 kHz L16/PCMU audio **in-band inside the WebSocket**. There is
  **no separate UDP media** and **no STUN/TURN** on the Genesys path.
- **Direction is inbound to us**: Genesys Cloud (SaaS) is the client — the Architect
  *Call Audio Connector* action opens the `wss` connection **from Genesys to our Audio
  Connector endpoint**. The flow to request is **inbound TCP `:443` (wss) from Genesys
  Cloud's published egress IP ranges** to the voice VIP.

| Source | Destination | Host | Port | Proto | Description |
|--------|-------------|------|------|-------|-------------|
| `<GENESYS_EGRESS_RANGES>` | `10.195.59.39` | `vip-ai4cc-voice-t01.prod.lan` (443 → HAProxy VIP `192.168.0.10:443` → `voice_bridges` `.103`/`.104:8090`) | `443` | TCP (wss) | Genesys Cloud AudioHook → `/genesys/audiohook` (control + in-band audio) |

- **Open blocker (netops + Genesys admin):** the endpoint is currently on a **private**
  RFC1918 IP (`10.195.59.39`), an internal `.prod.lan` name, and a **private-CA** TLS cert.
  Genesys Cloud (public SaaS) can neither reach the private IP over the internet nor trust a
  private CA by default. A network path (interconnect/VPN + internal-CA trust) **or** a public
  FQDN + publicly-trusted cert must be decided before the live-org test. See
  `genesys-admin-connection-request.md` §4/§8b (items 1 & 3).
- Still to obtain from the Genesys admin: **Genesys Cloud's egress IP allowlist**
  (`<GENESYS_EGRESS_RANGES>`) for the target region/org.
