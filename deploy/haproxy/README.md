# HAProxy + Keepalived — eir-ai4cc-tst VIPs (TASK-INFRA-002)

Load-balancing and HA for the two pilot VIPs, running on the LB pair
`vlp-t01`/`t02` (`.100`/`.101`). The VIPs float between the two nodes via
Keepalived (VRRP).

> Topology & ports: [`docs/operations/deployment-eir-ai4cc-tst.md`](../../docs/operations/deployment-eir-ai4cc-tst.md).
> Decisions: ADR-0038 (remote topology), ADR-0033 (WebRTC/TLS).

## What HAProxy does — and does not do

| VIP | Bind | Role | Backends | Health check |
|-----|------|------|----------|--------------|
| Voice `.10` | `:443` (TLS) | TLS edge + L7 LB for WebRTC **signaling** + web UI | `vla-t01/t02:8090` | `GET /` → 200 |
| Backend `.11` | `:8080` | internal L7 LB for the conversation API | `vla-t03/t04:8080` | `GET /api/health` → 200 |

**HAProxy does NOT carry WebRTC media.** The SDP offer (`POST
/api/voice/webrtc/offer`) and the UI go through HAProxy over HTTPS; the actual
audio is RTP/SRTP over **UDP**, negotiated peer-to-peer with the bridge that
answered the offer — it never traverses HAProxy. Because the bridges have no
Prodpriv-routable address, Prodpriv clients need **STUN/TURN** to reach the
bridge's media (open input, out of scope for this ticket). Without a TURN relay,
media will not establish for remote clients even though signaling succeeds.

## Files

| File | Deploy to | Notes |
|------|-----------|-------|
| `haproxy.cfg` | `/etc/haproxy/haproxy.cfg` on both LB nodes | identical on t01/t02 |
| `keepalived-vlp-t01.conf` | `/etc/keepalived/keepalived.conf` on t01 | MASTER (priority 150) |
| `keepalived-vlp-t02.conf` | `/etc/keepalived/keepalived.conf` on t02 | BACKUP (priority 100) |

## TLS certificate (voice edge)

`haproxy.cfg` expects a combined cert+key PEM at
`/etc/haproxy/certs/voice-vip.pem` for the voice VIP FQDN. Issuance policy is an
open input (out of scope). Install it with `0600`, HAProxy user readable. Reload
HAProxy after rotation (`systemctl reload haproxy`).

## Health checks and failover

- Each backend server has `check`; HAProxy removes an instance after `fall 3`
  failed probes and restores it after `rise 2`, so an unhealthy node leaves
  rotation automatically.
- Keepalived runs `chk_haproxy` (weight `-40`): if HAProxy dies on the active
  node, its priority drops and the VIP fails over to the standby node.
- Two independent `vrrp_instance` blocks (VOICE_VIP vrid 51, BACKEND_VIP vrid 52)
  let the two VIPs fail over independently.

## Voice draining hook (wires TASK-OPS-002)

The admin socket (`/run/haproxy/admin.sock`) lets the OPS-002 deploy drain a
bridge before recreating it (stop new calls, keep the peer serving):

```bash
# Drain (stop new calls to this bridge) - run on the active LB node:
echo "set server voice_bridges/vla-t01 state drain" | socat stdio /run/haproxy/admin.sock
# Re-enable once healthy:
echo "set server voice_bridges/vla-t01 state ready" | socat stdio /run/haproxy/admin.sock
```

Wire these into `deploy/ansible/group_vars/voice.yml` (`voice_lb_drain_cmd` /
`voice_lb_enable_cmd`), running them on an LB node (e.g. via `delegate_to`).
Combined with the OPS-002 rolling `serial:1` and grace window, this upgrades the
voice drain from best-effort to "no new calls during recreate".

## Validate

```bash
cd deploy/haproxy
./qa-validate-haproxy.sh          # haproxy -c (via Docker) + structural checks
# On a host with the binaries:
haproxy -c -f haproxy.cfg
keepalived -t -f keepalived-vlp-t01.conf
```

## Open inputs (confirm with the platform team)

- Network **interface name** in the Keepalived configs (`eth0` placeholder).
- **virtual_router_id** uniqueness on the segment (51/52 placeholders).
- **VRRP auth secret** (`CHANGE_ME_VRRP`).
- Voice **Prod IP** `10.195.59.39` → private VIP `.10` mapping (platform NAT).
- **TLS certificate** issuance for the voice VIP FQDN.
- **STUN/TURN** provisioning for WebRTC media (see above).
