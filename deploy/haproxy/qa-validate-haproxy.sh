#!/usr/bin/env bash
# QA validation for the HAProxy + Keepalived VIP config (TASK-INFRA-002).
# Deterministic, offline: HAProxy config parse (haproxy -c, via Docker if no local
# binary) + structural invariants over haproxy.cfg and both keepalived files.
# Live "VIP load-balances / TLS terminates / VRRP failover" is deferred to the LB
# hosts (needs the real cert, interface and VRRP secret).
set -uo pipefail

cd "$(dirname "$0")"
PASS=0; FAIL=0
ok()  { echo "PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

CFG="haproxy.cfg"
T01="keepalived-vlp-t01.conf"
T02="keepalived-vlp-t02.conf"

# --- 1. HAProxy config parses (haproxy -c) ------------------------------------
# haproxy -c loads the TLS cert, so mount a throwaway self-signed PEM at the path
# the config references. In production the real cert replaces it.
CERTDIR="$(mktemp -d)"; trap 'rm -rf "$CERTDIR"' EXIT
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$CERTDIR/k.pem" -out "$CERTDIR/c.pem" \
  -days 2 -subj "/CN=voice-vip.tst" >/dev/null 2>&1
cat "$CERTDIR/c.pem" "$CERTDIR/k.pem" > "$CERTDIR/voice-vip.pem"

run_haproxy_check() {
  if command -v haproxy >/dev/null 2>&1; then
    haproxy -c -f "$CFG" >/dev/null 2>&1
  elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    docker run --rm \
      -v "$PWD/$CFG:/usr/local/etc/haproxy/haproxy.cfg:ro" \
      -v "$CERTDIR/voice-vip.pem:/etc/haproxy/certs/voice-vip.pem:ro" \
      haproxy:2.8 haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg >/dev/null 2>&1
  else
    return 2
  fi
}
run_haproxy_check
rc=$?
if   [ "$rc" -eq 0 ]; then ok "haproxy -c: config is valid"
elif [ "$rc" -eq 2 ]; then echo "WARN: neither haproxy nor Docker available; skipped haproxy -c"
else bad "haproxy -c: config is INVALID"; fi

# --- 2. haproxy.cfg structural invariants -------------------------------------
grep -Eq 'bind 192\.168\.0\.10:443 ssl crt' "$CFG"        && ok "voice frontend binds .10:443 with TLS" || bad "voice TLS bind missing"
grep -Eq 'bind 192\.168\.0\.11:80$' "$CFG"                && ok "backend frontend binds .11:80"         || bad "backend bind missing"
grep -q '192.168.0.103:8090' "$CFG" && grep -q '192.168.0.104:8090' "$CFG" && ok "voice backend targets both bridges :8090" || bad "voice backend targets wrong"
grep -q '192.168.0.105:8080' "$CFG" && grep -q '192.168.0.106:8080' "$CFG" && ok "backend backend targets both nodes :8080"  || bad "backend targets wrong"
grep -q 'http-check send meth GET uri /$' "$CFG"          && ok "voice health check GET /"              || bad "voice health check missing"
# ADR-0046 / TASK-WEB-037: the primary live voice transport is a WebSocket tunnel. The edge
# must detect `Upgrade: websocket`, route it to a dedicated :8091 backend, hold the tunnel
# open, and pin a call to one bridge (single-client-per-listener socle, ADR-0043).
grep -Eq 'acl +is_voice_ws +hdr\(Upgrade\) +-i +websocket' "$CFG" && ok "voice WS: Upgrade-header ACL present" || bad "voice WS Upgrade ACL missing"
grep -Eq 'use_backend +voice_ws +if +is_voice_ws' "$CFG"  && ok "voice WS: routes upgrades to voice_ws" || bad "voice WS use_backend missing"
grep -q '192.168.0.103:8091' "$CFG" && grep -q '192.168.0.104:8091' "$CFG" && ok "voice_ws targets both bridges :8091" || bad "voice_ws backend targets wrong"
grep -q 'timeout tunnel' "$CFG"                           && ok "long tunnel timeout holds the WS call open" || bad "no timeout tunnel for WS"
awk '/^backend voice_ws/{b=1} /^backend |^frontend /{if($0!~"voice_ws")b=0} b&&/balance source/{f=1} END{exit !f}' "$CFG" \
  && ok "voice_ws pins a call to one bridge (balance source)" || bad "voice_ws missing call affinity (balance source)"
# TASK-INFRA-007: the backend must use the deep dependency-aware /actuator/health,
# NOT the static /api/health (which never reflects DB/Redis degradation).
grep -q 'uri /actuator/health' "$CFG"                     && ok "backend deep health check GET /actuator/health" || bad "backend not using deep /actuator/health"
awk '/^backend backend_java/{b=1} /^backend |^frontend /{if($0!~"backend_java")b=0} b&&/uri \/api\/health/{f=1} END{exit f}' "$CFG" \
  && ok "backend no longer uses the static /api/health" || bad "backend still probes the shallow /api/health"
grep -Eq 'server .* check' "$CFG"                         && ok "backends use active health 'check'"    || bad "no 'check' on servers"
grep -q 'stats socket /run/haproxy/admin.sock' "$CFG"     && ok "admin socket present (OPS-002 drain seam)" || bad "admin socket missing"
grep -q 'ssl-min-ver TLSv1.2' "$CFG"                      && ok "TLS min version >= 1.2"                || bad "TLS floor not set"

# Edge rate limiting (TASK-INFRA-004): the public voice frontend sheds per-IP bursts.
grep -q 'stick-table type ip .*conn_rate' "$CFG" && grep -q 'http_req_rate' "$CFG" && ok "edge stick-table tracks conn_rate + http_req_rate" || bad "edge rate-limit stick-table missing"
grep -q 'tcp-request connection track-sc0 src' "$CFG"    && ok "source IP tracked at connection"       || bad "no per-source tracking"
grep -q 'tcp-request connection reject if { sc0_conn_rate gt' "$CFG" && ok "connection-rate burst rejected"     || bad "no connection-rate limit"
grep -q 'http-request deny deny_status 429 if { sc0_http_req_rate gt' "$CFG" && ok "request-rate burst denied (429)" || bad "no request-rate limit"
# The rate limit lives on the public voice edge, not the internal backend frontend.
awk '/^frontend voice_https/{v=1} /^frontend backend_http/{v=0} v&&/stick-table/{f=1} END{exit !f}' "$CFG" && ok "rate limit scoped to the voice TLS edge" || bad "rate limit not on the voice frontend"

# --- 3. Keepalived VRRP invariants --------------------------------------------
for f in "$T01" "$T02"; do
  grep -q 'vrrp_instance VOICE_VIP' "$f" && grep -q 'vrrp_instance BACKEND_VIP' "$f" \
    && ok "$f defines both VIP instances" || bad "$f missing a VIP instance"
  grep -q '192.168.0.10/24' "$f" && grep -q '192.168.0.11/24' "$f" \
    && ok "$f floats .10 and .11" || bad "$f missing a virtual IP"
  grep -q 'track_script' "$f" && grep -q 'chk_haproxy' "$f" \
    && ok "$f tracks HAProxy liveness" || bad "$f missing HAProxy track script"
done
# Matching virtual_router_id per VIP across nodes (51 voice, 52 backend).
[ "$(grep -c 'virtual_router_id 51' "$T01" "$T02" | awk -F: '{s+=$2} END{print s}')" -eq 2 ] && ok "VOICE_VIP vrid 51 matches on both nodes" || bad "VOICE_VIP vrid mismatch"
[ "$(grep -c 'virtual_router_id 52' "$T01" "$T02" | awk -F: '{s+=$2} END{print s}')" -eq 2 ] && ok "BACKEND_VIP vrid 52 matches on both nodes" || bad "BACKEND_VIP vrid mismatch"
# Master/backup roles + priorities.
grep -q 'state MASTER' "$T01" && grep -q 'priority 150' "$T01" && ok "t01 is MASTER (priority 150)" || bad "t01 not MASTER/150"
grep -q 'state BACKUP' "$T02" && grep -q 'priority 100' "$T02" && ok "t02 is BACKUP (priority 100)" || bad "t02 not BACKUP/100"
! grep -q 'state MASTER' "$T02" && ok "t02 declares no MASTER instance" || bad "t02 wrongly MASTER"
# BUG-006 regression: the chk_haproxy penalty MUST drop the master (150) below the
# backup (100), else an HAProxy process death keeps the VIP on a node with no HAProxy
# listening (blackhole) instead of failing over. weight -40 => 110 >= 100 was the bug.
W=$(grep -m1 -Eo 'weight -[0-9]+' "$T01" | grep -Eo '[0-9]+')
{ [ -n "$W" ] && [ $((150 - W)) -lt 100 ]; } && ok "HAProxy-death failover crosses priority (150-${W} < 100)" || bad "chk_haproxy weight too small: master stays >= backup on HAProxy death (BUG-006)"
grep -q 'weight -60' "$T01" && grep -q 'weight -60' "$T02" && ok "chk_haproxy weight -60 on both nodes" || bad "chk_haproxy weight not -60 on both nodes"

# --- 4. VRRP unicast across AZs -----------------------------------------------
grep -q 'unicast_src_ip 192.168.0.100' "$T01" && grep -q 'unicast_peer' "$T01" && ok "t01 uses VRRP unicast (peer .101)" || bad "t01 missing VRRP unicast"
grep -q 'unicast_src_ip 192.168.0.101' "$T02" && grep -q 'unicast_peer' "$T02" && ok "t02 uses VRRP unicast (peer .100)" || bad "t02 missing VRRP unicast"

# --- 5. Operational prerequisites documented ----------------------------------
grep -q 'ip_nonlocal_bind=1' README.md && ok "ip_nonlocal_bind prerequisite documented (backup-node bind)" || bad "ip_nonlocal_bind not documented"
grep -q 'state drain' README.md && grep -q 'state ready' README.md && ok "drain/enable socket commands documented" || bad "drain hook not documented"

echo
echo "RESULT: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
