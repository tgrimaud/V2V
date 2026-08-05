# QA Functional And Latency Report — TASK-INFRA-002 (HAProxy + Keepalived VIP configuration)

## Executive Summary

- **Overall readiness:** GO for merge-ready. The HAProxy + Keepalived config
  (`deploy/haproxy/`) satisfies the ticket acceptance criteria and the adversarial
  review. **25/25 deterministic checks pass** via `deploy/haproxy/qa-validate-haproxy.sh`,
  including a real `haproxy -c` config parse (run in the `haproxy:2.8` Docker image
  with a throwaway self-signed cert) plus HAProxy and VRRP structural invariants.
- **Post-merge correction ([BUG-006](../../product-backlog/bugs/BUG-006-vrrp-failover-weight-insufficient.md), 2026-08-05):** the Sprint 11 full adversarial
  review found the `chk_haproxy` penalty (`weight -40`) too small to fail the VIP
  over on an HAProxy **process** death (master `150-40=110` > backup `100` →
  blackhole). Fixed on `fix/BUG-006-vrrp-failover-weight` (`weight -60` → `90 < 100`)
  with two new regression checks; the QA suite is now **27/27**. See
  `product-backlog/bugs/BUG-006-vrrp-failover-weight-insufficient.md`. Live
  `systemctl stop haproxy` failover still deferred to LB-host access.
- **Main blockers:** none.
- **Residual risks:**
  1. **WebRTC media is not proxied.** HAProxy is the TLS edge for the WebRTC
     *signaling* (HTTPS) + UI only; RTP/SRTP media is UDP, peer-to-peer to the
     answering bridge. Prodpriv clients need **STUN/TURN** (open input) to establish
     media — documented in the config header, README and the environment doc.
  2. **Platform open inputs** — interface name, `virtual_router_id` uniqueness, VRRP
     auth secret, the voice Prod-IP→VIP NAT mapping, and TLS cert issuance are
     placeholders confirmed with the platform team. Live "load-balances / TLS
     terminates / VRRP failover" runs on the LB hosts (deferred, same pattern as the
     other Sprint 11 tickets).

## Scope Tested

- **Epic / task:** EPIC-012 (Pilot deployment, release & operations) / TASK-INFRA-002.
- **Channels:** N/A (network edge config; no conversation behavior changed).
- **Environment:** local; `haproxy:2.8` via Docker for config parse; no LB host contacted.

## Acceptance Scenarios (Gherkin)

```gherkin
Feature: VIP load balancing, TLS edge and failover

  Scenario: Backend VIP load-balances two instances
    Given both backends healthy behind VIP .11
    When requests hit the VIP
    Then they are distributed and an unhealthy instance is removed from rotation

  Scenario: Voice VIP terminates TLS
    Given a certificate installed for the voice VIP FQDN
    When a client connects over HTTPS/WSS to VIP .10
    Then TLS terminates at HAProxy and the WebRTC signaling reaches a bridge

  Scenario: Failover
    Given the active LB node fails
    Then Keepalived moves the VIP to the standby node without dropping the VIP
```

## Test Results (deterministic, offline)

`deploy/haproxy/qa-validate-haproxy.sh` — **25 passed, 0 failed**:

| Area | Checks | Result |
|------|--------|--------|
| HAProxy config parse | `haproxy -c` (Docker `haproxy:2.8` + temp cert) | PASS |
| HAProxy binds | voice `.10:443` TLS, backend `.11:8080` | PASS |
| Backend pools | voice→`.103/.104:8090`, backend→`.105/.106:8080`, `check` on all | PASS |
| Health checks | voice `GET /`, backend `GET /api/health` | PASS |
| TLS floor | `ssl-min-ver TLSv1.2` | PASS |
| Admin socket | `/run/haproxy/admin.sock` (OPS-002 drain seam) | PASS |
| VRRP instances | both files define VOICE_VIP (vrid 51) + BACKEND_VIP (vrid 52), float `.10`/`.11`, track HAProxy | PASS |
| VRRP roles | t01 MASTER/150, t02 BACKUP/100, matching vrids | PASS |
| VRRP unicast | unicast peer per node (cross-AZ) | PASS |
| Prerequisites/doc | `ip_nonlocal_bind` documented, drain/enable socket commands documented | PASS |

## Scenario Coverage

| Acceptance scenario | Covered? | Evidence |
|---|---|---|
| Backend VIP load-balances two instances | Structurally yes; live deferred | `backend_java` roundrobin over `.105/.106` with `check` + `option httpchk GET /api/health`; unhealthy node leaves rotation after `fall 3`. |
| Voice VIP terminates TLS | Structurally yes; live deferred | `frontend voice_https bind .10:443 ssl crt … alpn h2,http/1.1` + TLS floor; `haproxy -c` validates the TLS bind. Live needs the real cert. Media (UDP) is out of HAProxy scope (STUN/TURN). |
| Failover | Structurally yes; live deferred | Two VRRP instances, MASTER/BACKUP priorities, `chk_haproxy` weight `-40`, unicast peering across AZs. Live VRRP move needs the LB hosts + interface. |

## Observability And Latency

- **Runtime-affecting?** No application code; this is network-edge configuration.
  No new OpenTelemetry instrumentation required (not-runtime-affecting carve-out).
- Edge visibility: HAProxy stats UI (`127.0.0.1:8404/stats`), per-server health
  state, and structured `httplog`. The health checks fail a server out of rotation
  and Keepalived fails the VIP over — both observable operationally.

## Security And Privacy

- **TLS floor** TLSv1.2+ with modern cipher suites; `no-tls-tickets`.
- **Secrets:** VRRP `auth_pass` and the TLS cert are placeholders/open inputs, not
  committed with real values. No application secret touches this layer.
- Admin socket is mode `660 level admin` on a local path; drain uses it locally.

## Adversarial Review

- **Score:** 92/100 (Pass, ≥90 gate).
- **Blocking findings fixed:** (1) multicast VRRP may not cross the two AZs → added
  `unicast_src_ip`/`unicast_peer` on both nodes. (2) HAProxy would fail to start on
  the backup node (VIP absent) → documented `net.ipv4.ip_nonlocal_bind=1` prerequisite.
- **Accepted residual risk:** WebRTC media not proxied (needs STUN/TURN, open input);
  deferred live LB validation; platform-confirmed placeholders (interface, vrid,
  VRRP secret, Prod-IP NAT, cert issuance).

## Verdict

**GO — merge-ready.** All deterministic checks pass (incl. real `haproxy -c`);
blocking adversarial findings fixed; residual risks documented with owners/open
inputs. Merge on the user's explicit request; live VIP/TLS/failover proof runs on
the LB hosts with the platform team.
