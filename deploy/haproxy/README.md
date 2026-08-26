# HAProxy + Keepalived — eir-ai4cc-tst VIPs (TASK-INFRA-002)

Load-balancing and HA for the two pilot VIPs, running on the LB pair
`vlp-t01`/`t02` (`.100`/`.101`). The VIPs float between the two nodes via
Keepalived (VRRP).

> Topology & ports: [`docs/operations/deployment-eir-ai4cc-tst.md`](../../docs/operations/deployment-eir-ai4cc-tst.md).
> Decisions: ADR-0038 (remote topology), ADR-0046 (WebSocket primary transport,
> supersedes ADR-0033).

## What HAProxy does — and does not do

| VIP | Bind | Role | Backends | Health check |
|-----|------|------|----------|--------------|
| Voice `.10` | `:443` (TLS) | TLS edge + L7 LB: web UI + WebRTC signaling → `voice_bridges`; live voice WebSocket (`Upgrade: websocket`) → `voice_ws` | `vla-t01/t02:8090` (HTTP) + `:8091` (WS) | `GET /` → 200 (HTTP); TCP connect (WS) |
| Backend `.11` | `:80` | internal L7 LB for the conversation API | `vla-t03/t04:8080` | `GET /actuator/health` → 200 (deep: DB + Redis) |

**Live voice now flows THROUGH HAProxy over a WebSocket tunnel (ADR-0046,
TASK-WEB-037).** The primary V1 transport is a single `wss` connection: a browser
`new WebSocket(...)` (and, later, Genesys Audio Connector) opens an HTTP/1.1
request with `Upgrade: websocket`, which the voice frontend matches (`acl
is_voice_ws hdr(Upgrade) -i websocket`) and routes to the `voice_ws` backend on
`:8091`. `balance source` pins a call to one bridge (the socle WS transport is
single-client per listener, ADR-0043) and the global `timeout tunnel 1h` holds the
socket open for the whole call. This is TCP — **no TURN/UDP** is involved.

**HAProxy still does NOT carry WebRTC media.** WebRTC is now an **optional,
same-subnet / dev-only** path (ADR-0046). The SDP offer (`POST
/api/voice/webrtc/offer`) and the UI go through HAProxy over HTTPS, but the WebRTC
audio is RTP/SRTP over **UDP**, negotiated peer-to-peer with the bridge that
answered the offer — it never traverses HAProxy. Off-subnet WebRTC clients would
need **STUN/TURN**, which V1 deliberately avoids by using the WebSocket transport
instead. Use WebRTC only for local/same-subnet development.

> Voice entry points (batch one-shot vs streaming WebRTC), how to verify signaling
> live, and how to test/enable WebRTC media are documented in
> [`docs/operations/pilot-voice-access.md`](../../docs/operations/pilot-voice-access.md).

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
  addresses (`.10:443`, `.11:80`) but the backup node does not hold the VIP, so
  without non-local bind HAProxy fails to start there. Set it persistently:
  ```bash
  echo 'net.ipv4.ip_nonlocal_bind=1' | sudo tee /etc/sysctl.d/90-haproxy.conf
  sudo sysctl --system
  ```
- **VRRP unicast** is configured (peer = the other LB node) because the two nodes
  are in different AZs; confirm the segment/routing allows VRRP unicast between
  `.100` and `.101`.
- `killall` available (`psmisc`) for the `chk_haproxy` track script.

## Applying the config on the LB nodes (manual apply path — TASK-INFRA-006)

The `[lb]` pair is **platform-managed** (HAProxy/Keepalived run natively, not in
Docker) and is intentionally *not* driven by the app deploy playbooks
(`inventory/hosts.ini` lists it "reference only"). So the pilot apply path is the
documented manual sequence below; an Ansible `lb.yml` playbook is a later option
(the hosts already exist in inventory) once the platform team confirms we own
package/service management on those nodes. Run everything as root on **each** LB
node unless a step says otherwise.

```bash
# 1. Packages (Rocky EL9): LB, VRRP, killall for chk_haproxy, socat for the drain hook.
sudo dnf install -y haproxy keepalived psmisc socat

# 2. Non-local bind so the backup node (which does not hold the VIP) can start HAProxy.
echo 'net.ipv4.ip_nonlocal_bind=1' | sudo tee /etc/sysctl.d/90-haproxy.conf
sudo sysctl --system

# 3. HAProxy config (identical on t01 and t02).
sudo install -m 0644 haproxy.cfg /etc/haproxy/haproxy.cfg

# 4. Keepalived config — the MASTER file on t01, the BACKUP file on t02.
sudo install -m 0644 keepalived-vlp-t01.conf /etc/keepalived/keepalived.conf   # on t01
sudo install -m 0644 keepalived-vlp-t02.conf /etc/keepalived/keepalived.conf   # on t02

# 5. Substitute the three platform-confirmed placeholders IN PLACE (see Open inputs):
#    - interface name (eth0 -> the real NIC, `ip -br link`)
#    - VRRP secret (CHANGE_ME_VRRP -> the shared secret, from ansible-vault; see below)
#    - virtual_router_id (51/52 -> values with no VRRP clash on the segment)
IFACE=eth0
VRRP_SECRET='<from vault_vrrp_auth_pass>'   # do NOT paste a real secret into shell history
sudo sed -i "s/\beth0\b/${IFACE}/g; s/CHANGE_ME_VRRP/${VRRP_SECRET}/g" /etc/keepalived/keepalived.conf

# 6. TLS cert for the voice edge (t01/t02): combined cert+key PEM, 0600.
sudo install -m 0600 -D voice-vip.pem /etc/haproxy/certs/voice-vip.pem   # cert issuance = open input

# 7. Validate config BEFORE enabling.
haproxy -c -f /etc/haproxy/haproxy.cfg
keepalived -t -f /etc/keepalived/keepalived.conf

# 8. Enable + start (keepalived last so the VIP only floats once HAProxy answers).
sudo systemctl enable --now haproxy keepalived

# 9. Failover smoke test (on the MASTER, t01): killing HAProxy must move the VIP to t02.
sudo systemctl stop haproxy   # watch `ip -br addr | grep -E '\.10/|\.11/'` move to t02; then start again
sudo systemctl start haproxy
```

**VRRP secret handling.** The committed configs carry the literal `CHANGE_ME_VRRP`
placeholder on purpose — the real secret is a credential and must **never** be
committed. Store it in the ansible-vault (`vault_vrrp_auth_pass`, alongside the other
pilot secrets) and inject it at apply time (step 5). Keepalived's `auth_pass` is
truncated to **8 characters**, so pick an 8-char secret to avoid a silent mismatch
between the nodes (a mismatch makes both nodes claim MASTER → duplicate VIP). The
same secret must be set on both LB nodes and per `vrrp_instance`.

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

- Scope: **HTTP signaling + UI.** The live voice WebSocket is effectively
  unaffected — a whole call is a single `Upgrade` request on one long-lived
  connection (well under the per-10s burst thresholds); the audio then rides the
  tunnel, not new requests. WebRTC media (optional/dev) is UDP peer-to-peer (not
  proxied), so it is never rate-limited here either.
- The thresholds are **pilot defaults** (generous for a browser loading many page
  assets); tune them once live traffic shape is known. The internal backend
  frontend (`.11:80`, LB→backend only) is intentionally **not** rate-limited.
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
  -e '{"voice_lb_socket_hosts":["vlp-ai4cc-t01.prod.lan","vlp-ai4cc-t02.prod.lan"]}'
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

## Edge gotcha: HTTP/2 needs an HTTP/1.1 backend (BUG-012)

The voice frontend advertises `alpn h2,http/1.1`, so browsers negotiate **HTTP/2**.
HAProxy cannot mux an **HTTP/1.0** backend response onto an h2 client — it returns
"Empty reply from server" (curl HTTP `000`), even though the same request over
HTTP/1.1 returns `200`. The voice bridge's Python `BaseHTTPRequestHandler` defaults to
HTTP/1.0, which surfaced this at the pilot edge. Fixed app-side by pinning
`protocol_version = "HTTP/1.1"` on the bridge handler (BUG-012). If a backend ever
serves HTTP/1.0 again, either fix the backend or drop `h2` from the `alpn` list on the
`bind` (http/1.1-only is fine for WebRTC signaling + a static UI; media is UDP P2P).

The live voice WebSocket (ADR-0046) is **unaffected by this h2 concern**: browsers
never negotiate the WebSocket over HTTP/2 for `new WebSocket(...)` — they open a
**separate HTTP/1.1** connection carrying `Upgrade: websocket` + `Connection:
Upgrade`. So even though the `bind` advertises `h2,http/1.1`, the socket arrives as
http/1.1 and the `hdr(Upgrade) -i websocket` ACL matches. (RFC 8441 h2-tunnelled
WebSocket is not initiated by browsers here.) Verify once live: `curl -sv --http1.1
-H "Connection: Upgrade" -H "Upgrade: websocket" ... https://<voice-vip>/` should get
a `101 Switching Protocols` from a bridge, not a `200`/UI page.

## Open inputs (confirm with the platform team)

- Network **interface name** in the Keepalived configs (`eth0` placeholder).
- **virtual_router_id** uniqueness on the segment (51/52 placeholders).
- **VRRP auth secret** (`CHANGE_ME_VRRP`).
- Voice **Prod IP** `10.195.59.39` → private VIP `.10` mapping (platform NAT).
- **TLS certificate** issuance for the voice VIP FQDN.
- **WebSocket upgrade** end-to-end through the `.10:443` `h2,http/1.1` edge to
  `voice_ws` (`:8091`) — confirm live with the `101 Switching Protocols` curl above
  (ADR-0046, TASK-WEB-037 / TASK-INFRA-010).
- **STUN/TURN** is **no longer on the V1 path** (ADR-0046 uses the WebSocket
  transport instead); only needed if off-subnet WebRTC (optional/dev) is ever
  revived.
