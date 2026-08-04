#!/usr/bin/env bash
# QA validation for TASK-INFRA-001 - per-tier docker-compose deploy stacks.
# Deterministic, environment-free checks: renders each stack with docker compose
# config (using the .env.example templates) and asserts the deployment invariants
# the adversarial review and the ticket acceptance criteria require. Live "stack up
# reaches Postgres/Redis" smoke is deferred to the tst environment (open inputs:
# registry, egress, credentials).
#
# Usage: deploy/compose/qa-validate.sh   (run from anywhere; cd's to its own dir)
# Exit 0 = all checks pass; non-zero = at least one failure.

set -u
cd "$(dirname "$0")"

pass=0
fail=0
ok()   { printf '  PASS  %s\n' "$1"; pass=$((pass+1)); }
ko()   { printf '  FAIL  %s\n' "$1"; fail=$((fail+1)); }
have() { echo "$1" | grep -q -- "$2"; }

render() { # $1 = tier -> prints rendered, canonical compose config
  ( cd "$1" && docker compose --env-file .env.example config 2>/dev/null )
}

echo "== docker compose config renders =="
for t in backend voice redis; do
  if ( cd "$t" && docker compose --env-file .env.example config >/dev/null 2>&1 ); then
    ok "$t stack renders"
  else
    ko "$t stack fails to render"
  fi
done

echo "== backend invariants =="
B="$(render backend)"
have "$B" "/actuator/health"        && ok "backend healthcheck hits /actuator/health" || ko "backend healthcheck missing"
have "$B" "read_only: true"         && ok "KB volume mounted read-only (review fix)"   || ko "KB read-only mount missing"
have "$B" "/app/kb-assets"          && ok "KB paths point inside the mount"            || ko "KB mount path missing"
have "$B" "CONVERSATION_STORE"      && ok "backend wires CONVERSATION_STORE"           || ko "CONVERSATION_STORE missing"
have "$B" "REDIS_HOST"              && ok "backend wires REDIS_HOST"                   || ko "REDIS_HOST missing"
have "$B" "memory:"                 && ok "backend resource limit set"                 || ko "backend resource limit missing"
have "$B" "restart: unless-stopped" && ok "backend restart policy set"                 || ko "backend restart policy missing"

echo "== voice invariants =="
V="$(render voice)"
have "$V" "urllib.request.urlopen"  && ok "voice healthcheck probes GET /"             || ko "voice healthcheck missing"
have "$V" "VOICE_BACKEND_URL"       && ok "voice wires VOICE_BACKEND_URL (backend VIP)" || ko "VOICE_BACKEND_URL missing"
have "$V" "8090"                    && ok "voice publishes port 8090"                  || ko "voice port 8090 missing"
have "$V" "restart: unless-stopped" && ok "voice restart policy set"                   || ko "voice restart policy missing"

echo "== redis invariants =="
R="$(render redis)"
have "$R" "requirepass"     && ok "redis requires a password"          || ko "redis requirepass missing"
have "$R" "appendonly"      && ok "redis persistence enabled"          || ko "redis appendonly missing"
have "$R" "noeviction"      && ok "redis noeviction (keep sessions)"   || ko "redis eviction policy wrong"
have "$R" "redis-cli"       && ok "redis authenticated PING healthcheck" || ko "redis healthcheck missing"

echo "== secret hygiene =="
# No real .env is tracked by git; only *.env.example templates are versioned.
tracked_env="$(git ls-files 'deploy/compose/**/.env' 2>/dev/null)"
[ -z "$tracked_env" ] && ok "no rendered .env is committed" || ko "a real .env is tracked: $tracked_env"
# A real .env would be git-ignored.
if git check-ignore -q backend/.env 2>/dev/null; then ok ".env is git-ignored"; else ko ".env is NOT git-ignored"; fi
# Templates carry only placeholders, never a resolved secret.
if grep -RangE '=(sk-|Bearer |AKIA|ghp_)[A-Za-z0-9]+' */.env.example >/dev/null 2>&1; then
  ko "a .env.example contains a real-looking secret"
else
  ok ".env.example files carry only placeholders (CHANGE_ME)"
fi

echo "== api-key / password parity contract =="
have "$B" "CONVERSATION_API_KEY" && have "$V" "VOICE_BACKEND_API_KEY" \
  && ok "backend CONVERSATION_API_KEY <-> voice VOICE_BACKEND_API_KEY present" \
  || ko "api-key parity vars missing"

echo
printf 'RESULT: %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
