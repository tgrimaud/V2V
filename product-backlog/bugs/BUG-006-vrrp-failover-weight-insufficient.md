# BUG-006 — VRRP failover does not trigger on HAProxy process death

## Header

- **Bug ID:** BUG-006
- **Title:** Keepalived `chk_haproxy` weight too small — VIP is not released when HAProxy dies
- **Status:** Ready for QA retest
- **Severity:** High
- **Priority:** P1
- **Detected by:** Adversarial review
- **Detected date:** 2026-08-05
- **Related user story:** TASK-INFRA-002 (HAProxy + Keepalived VIPs)
- **Related epic:** EPIC-012 (V1 pilot deployment)
- **Branch:** `fix/BUG-006-vrrp-failover-weight`
- **Owner:** Cross-functional (infra)

## Problem Statement

When HAProxy stops on the active load-balancer node, the VIP is **not** failed over
to the standby. The VIP stays on the node whose HAProxy is dead, so traffic to the
voice edge (`.10:443`) and the backend VIP (`.11:80`) is blackholed instead of
being served by the healthy peer.

## Environment

- **Environment:** pilot (eir-ai4cc-tst), LB hosts `vlp-t01`/`t02` (`.100`/`.101`)
- **Channel:** all (both VIPs affected)
- **Build or commit:** `deploy/haproxy/keepalived-vlp-t01.conf` / `-t02.conf` as merged in Sprint 11 (`weight -40`)
- **Provider configuration:** Keepalived VRRP (unicast), HAProxy TLS edge + L7

## Reproduction Steps

1. Given t01 is MASTER (priority 150) and t02 is BACKUP (priority 100), both healthy.
2. When HAProxy is stopped on t01 (`systemctl stop haproxy`) while Keepalived keeps running.
3. Then `chk_haproxy` fails and t01's effective priority drops to `150 - 40 = 110`,
   which is still greater than t02's `100`, so t01 keeps the VIP.

## Expected Result

On HAProxy death, the VIP moves to the peer node that still has a running HAProxy,
within a few VRRP advert intervals.

## Actual Result

The VIP stays on the node with the dead HAProxy (`110 > 100`); the peer never
preempts. The VIP is up but nothing listens behind it → hard outage until the
process is restarted or the whole node goes down.

## Evidence

- `keepalived-vlp-t01.conf`: `priority 150`, `vrrp_script chk_haproxy { weight -40 }`.
- `keepalived-vlp-t02.conf`: `priority 100`.
- Priority math on fault: `150 - 40 = 110 > 100` → no failover.
- `deploy/haproxy/README.md` (pre-fix) claimed the `-40` penalty caused failover — incorrect.

## Impact

- **Operational / availability:** the primary failure `chk_haproxy` is meant to
  cover (HAProxy crash) does not fail over. Only a full node-down (Keepalived stops
  advertising) triggers failover. The HA story is effectively single-LB for the
  process-crash case.
- **Pilot-readiness:** invalidates the "HA across two AZs" claim until fixed.
- No customer data / security impact.

## Acceptance Criteria For Fix

- [x] The defect no longer reproduces (weight now crosses the peer priority).
- [x] A regression test covers the failure (QA script asserts `150 - weight < 100`).
- [x] OpenTelemetry: not applicable (LB config, no app runtime change).
- [ ] Adversarial code review ≥ 90% (re-review of this fix).
- [ ] QA retest passes (deterministic 27/27 green; live `systemctl stop haproxy`
      failover deferred to LB-host access).
- [x] Documentation updated (`deploy/haproxy/README.md`).

## Developer Notes

- **root cause:** VRRP fault penalty (`weight -40`) did not drop the master (150)
  below the backup (100); effective 110 kept the VIP on the failed node.
- **files changed:** `deploy/haproxy/keepalived-vlp-t01.conf`,
  `keepalived-vlp-t02.conf` (`weight -40` → `-60`, 150→90 < 100, with rationale),
  `deploy/haproxy/README.md` (corrected failover explanation),
  `deploy/haproxy/qa-validate-haproxy.sh` (+2 regression checks).
- **tests added/updated:** QA now parses the penalty and asserts
  `150 - weight < 100`, plus `weight -60` on both nodes (27/27).
- **OpenTelemetry added/updated:** n/a (LB config).
- **residual risk:** deterministic only; a real HAProxy-stop failover on the LB
  hosts is still to be run once network/host access is available (open input #1).

## QA Retest

- **Retested by:** QA (deterministic)
- **Retest date:** 2026-08-05
- **Scenarios rerun:** `deploy/haproxy/qa-validate-haproxy.sh` (27/27), incl. the two
  BUG-006 regression checks.
- **Result:** Passed (deterministic). Live failover pending LB-host access.
- **Retest evidence:** `RESULT: 27 passed, 0 failed`.

## Closure

- **Closed by:** (pending user validation / live failover test)
- **Closed date:** —
- **Closure reason:** —
