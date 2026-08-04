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
grep -Eq 'bind 192\.168\.0\.11:8080' "$CFG"               && ok "backend frontend binds .11:8080"       || bad "backend bind missing"
grep -q '192.168.0.103:8090' "$CFG" && grep -q '192.168.0.104:8090' "$CFG" && ok "voice backend targets both bridges :8090" || bad "voice backend targets wrong"
grep -q '192.168.0.105:8080' "$CFG" && grep -q '192.168.0.106:8080' "$CFG" && ok "backend backend targets both nodes :8080"  || bad "backend targets wrong"
grep -q 'http-check send meth GET uri /$' "$CFG"          && ok "voice health check GET /"              || bad "voice health check missing"
grep -q 'uri /api/health' "$CFG"                          && ok "backend health check GET /api/health" || bad "backend health check missing"
grep -Eq 'server .* check' "$CFG"                         && ok "backends use active health 'check'"    || bad "no 'check' on servers"
grep -q 'stats socket /run/haproxy/admin.sock' "$CFG"     && ok "admin socket present (OPS-002 drain seam)" || bad "admin socket missing"
grep -q 'ssl-min-ver TLSv1.2' "$CFG"                      && ok "TLS min version >= 1.2"                || bad "TLS floor not set"

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

# --- 4. Drain hook documented -------------------------------------------------
grep -q 'state drain' README.md && grep -q 'state ready' README.md && ok "drain/enable socket commands documented" || bad "drain hook not documented"

echo
echo "RESULT: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
