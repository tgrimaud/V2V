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
| Backend `.11` | `:8080` | internal L7 LB for the conversation API | `vla-t03/t04:8080` | `GET /actuator/health` → 200 (deep: DB + Redis) |

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

## Host prerequisites

- **`net.ipv4.ip_nonlocal_bind=1`** on both LB nodes. HAProxy binds the VIP
  addresses (`.10:443`, `.11:8080`) but the backup node does not hold the VIP, so
  without non-local bind HAProxy fails to start there. Set it persistently:
  ```bash
  echo 'net.ipv4.ip_nonlocal_bind=1' | sudo tee /etc/sysctl.d/90-haproxy.conf
  sudo sysctl --system
  ```
- **VRRP unicast** is configured (peer = the other LB node) because the two nodes
  are in different AZs; confirm the segment/routing allows VRRP unicast between
  `.100` and `.101`.
- `killall` available (`psmisc`) for the `chk_haproxy` track script.

## Health checks and failover

- Each backend server has `check`; HAProxy removes an instance after `fall 3`
  failed probes and restores it after `rise 2`, so an unhealthy node leaves
  rotation automatically.
- The backend VIP probes `/actuator/health` (TASK-INFRA-007), a **deep** check that
  aggregates the DB indicator (and Redis when `REDIS_HEALTH_ENABLED=true`) and returns
  `503` when a dependency is down — so a backend with Postgres/Redis broken is pulled
  from rotation, unlike the old static `/api/health`. The voice VIP keeps the lightweight
  `GET /` signaling probe (the bridge has no dependency-aware endpoint).
- Keepalived runs `chk_haproxy` (weight `-60`): if HAProxy dies on the active
  node its priority drops from 150 to 90, **below** the standby's 100, so the VIP
  fails over to the node that still has HAProxy. The penalty must cross the peer
  priority — a smaller `-40` left the master at 110 > 100 and kept the VIP on the
  dead node (BUG-006). Validate with a real `systemctl stop haproxy` on the master.
- Two independent `vrrp_instance` blocks (VOICE_VIP vrid 51, BACKEND_VIP vrid 52)
  let the two VIPs fail over independently.

## Edge rate limiting (TASK-INFRA-004)

The public voice frontend (`.10:443`) sheds per-source-IP bursts at the TLS edge
before they reach the bridges, using a stick-table:

```
stick-table type ip size 100k expire 10m store conn_rate(10s),http_req_rate(10s)
tcp-request connection track-sc0 src
tcp-request connection reject   if { sc0_conn_rate    gt 50 }   # >50 conns / 10s / IP
http-request deny deny_status 429 if { sc0_http_req_rate gt 100 }  # >100 reqs / 10s / IP
```

- Scope: **signaling + UI HTTP only.** WebRTC media is UDP peer-to-peer (not
  proxied), so a call's audio is never rate-limited by this.
- The thresholds are **pilot defaults** (generous for a browser loading many page
  assets); tune them once live traffic shape is known. The internal backend
  frontend (`.11:8080`, LB→backend only) is intentionally **not** rate-limited.
- A rejected request returns `429`; a connection-rate breach is dropped at accept.

## Voice draining hook (wires TASK-OPS-002)

The admin socket (`/run/haproxy/admin.sock`) lets the OPS-002 deploy drain a
bridge before recreating it (stop new calls, keep the peer serving):

```bash
# Drain (stop new calls to this bridge) - run on the active LB node:
echo "set server voice_bridges/vla-t01 state drain" | socat stdio /run/haproxy/admin.sock
# Re-enable once healthy:
echo "set server voice_bridges/vla-t01 state ready" | socat stdio /run/haproxy/admin.sock
```

The commands are wired (TASK-INFRA-007) in `deploy/ansible/group_vars/voice.yml`
(`voice_lb_drain_cmd` / `voice_lb_enable_cmd`) and delegated to every LB node listed
in `voice_lb_socket_hosts` by `roles/compose_tier/tasks/drain.yml` + `main.yml`, so
the socat command runs where the admin socket lives. Setting `state drain` on both
LB nodes covers either holding the VIP via Keepalived.

**Enablement is opt-in.** `voice_lb_socket_hosts` defaults to **empty** because the
`[lb]` group is platform-managed and SSH access to it is not confirmed yet (gated with
TASK-INFRA-006): with `serial:1` + `max_fail_percentage:0`, delegating to an unreachable
LB would abort the voice deploy. Until then the deploy runs grace-only (serial:1 +
grace window). Enable the hook once LB access exists, e.g.:

```bash
ansible-playbook deploy.yml --limit voice \
  -e '{"voice_lb_socket_hosts":["vlp-ai4cc-t01.mt.lan","vlp-ai4cc-t02.mt.lan"]}'
```

Even when enabled the delegated tasks are non-fatal (`ignore_unreachable` +
`failed_when: false`): a failing LB hook degrades to grace-only, it never aborts the
deploy. Combined with `serial:1` and the grace window, an enabled hook upgrades the
voice drain from best-effort to "no new calls during recreate". `socat` must be
installed on the LB nodes. Live behaviour is validated under TASK-INFRA-006.

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
