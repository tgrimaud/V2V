#!/usr/bin/env bash
# QA validation for the Ansible deploy (TASK-OPS-002). Deterministic, offline
# checks: playbook syntax, inventory topology, template render (no undefined var),
# .env key parity vs the compose .env.example, secret hygiene, deploy order and
# voice draining wiring. Live "reaches the tst VMs" is deferred (needs SSH + vault).
#
# Requires ansible-core on PATH:  pip install ansible-core
# Usage:  cd deploy/ansible && ./qa-validate-ansible.sh
set -uo pipefail

cd "$(dirname "$0")"
PASS=0
FAIL=0
ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
bad()  { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }
have() { command -v "$1" >/dev/null 2>&1; }

for bin in ansible ansible-playbook ansible-inventory; do
  have "$bin" || { echo "ERROR: $bin not found. Run: pip install ansible-core"; exit 2; }
done

COMPOSE_DIR="../compose"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- 1. Playbook syntax --------------------------------------------------------
for pb in deploy.yml rollback.yml; do
  if ansible-playbook "$pb" --syntax-check >/dev/null 2>&1; then
    ok "syntax-check clean: $pb"
  else
    bad "syntax-check FAILED: $pb"
  fi
done

# --- 2. Inventory topology -----------------------------------------------------
GRAPH="$(ansible-inventory -i inventory/hosts.ini --graph 2>/dev/null)"
for grp in redis backend voice; do
  echo "$GRAPH" | grep -q "@${grp}:" && ok "inventory has group '$grp'" || bad "inventory missing group '$grp'"
done
[ "$(echo "$GRAPH" | grep -c 'vla-ai4cc-t0[12].mt.lan')" -eq 2 ] && ok "voice group has 2 bridges" || bad "voice group host count wrong"
[ "$(echo "$GRAPH" | grep -c 'vla-ai4cc-t0[34].mt.lan')" -eq 2 ] && ok "backend group has 2 nodes"  || bad "backend group host count wrong"

# --- 3. Template render (no undefined var) + .env key parity -------------------
for tier in backend voice redis; do
  if ansible localhost -c local -m ansible.builtin.template \
        -a "src=roles/compose_tier/templates/${tier}.env.j2 dest=${TMP}/${tier}.env mode=0600" \
        -e "@group_vars/${tier}.yml" -e ansible_become=false >/dev/null 2>&1; then
    ok "template renders with no undefined var: ${tier}.env.j2"
  else
    bad "template render FAILED (undefined var?): ${tier}.env.j2"
    continue
  fi
  # Key parity: every KEY= in the rendered .env must exist in the compose .env.example
  # (ignoring the REGISTRY/CHANGE_ME placeholder lines), and vice versa.
  keys_rendered="$(grep -oE '^[A-Z0-9_]+=' "${TMP}/${tier}.env" | sort -u)"
  keys_example="$(grep -oE '^[A-Z0-9_]+=' "${COMPOSE_DIR}/${tier}/.env.example" | sort -u)"
  if [ "$keys_rendered" = "$keys_example" ]; then
    ok "key parity rendered .env == .env.example: ${tier}"
  else
    bad "key drift between rendered .env and .env.example: ${tier}"
    diff <(echo "$keys_example") <(echo "$keys_rendered") | sed 's/^/    /'
  fi
done

# --- 4. Secret hygiene ---------------------------------------------------------
grep -q '^group_vars/all/vault.yml$' .gitignore && ok "vault.yml is git-ignored" || bad "vault.yml NOT git-ignored"
if git ls-files --error-unmatch group_vars/all/vault.yml >/dev/null 2>&1; then
  bad "a real vault.yml is tracked in git"
else
  ok "no real vault.yml tracked in git"
fi
# Secret .env keys must be sourced from vault_* (never a literal value in the template).
sec_ok=1
grep -q 'DB_PASSWORD={{ vault_db_password }}'            roles/compose_tier/templates/backend.env.j2 || sec_ok=0
grep -q 'MISTRAL_API_KEY={{ vault_mistral_api_key }}'    roles/compose_tier/templates/backend.env.j2 || sec_ok=0
grep -q 'CONVERSATION_API_KEY={{ vault_conversation_api_key }}' roles/compose_tier/templates/backend.env.j2 || sec_ok=0
grep -q 'VOICE_BACKEND_API_KEY={{ vault_conversation_api_key }}' roles/compose_tier/templates/voice.env.j2 || sec_ok=0
grep -q 'GRADIUM_API_KEY={{ vault_gradium_api_key }}'    roles/compose_tier/templates/voice.env.j2   || sec_ok=0
grep -q 'REDIS_PASSWORD={{ vault_redis_password }}'      roles/compose_tier/templates/redis.env.j2   || sec_ok=0
[ "$sec_ok" -eq 1 ] && ok "all secret keys are sourced from vault_* vars" || bad "a secret key is not sourced from a vault_* var"
# The shared API key parity (backend == voice) must hold in the templates.
[ "$(grep -h 'vault_conversation_api_key' roles/compose_tier/templates/backend.env.j2 roles/compose_tier/templates/voice.env.j2 | wc -l | tr -d ' ')" -eq 2 ] \
  && ok "shared API key parity backend==voice in templates" || bad "shared API key parity broken"
# The rendered .env must NOT be committed; the deploy guard rejects placeholders.
grep -q "vault_conversation_api_key | default('CHANGE_ME') != 'CHANGE_ME'" deploy.yml \
  && ok "deploy guard rejects CHANGE_ME placeholder secrets" || bad "deploy guard missing placeholder rejection"

# --- 5. Reproducibility: refuse 'latest' --------------------------------------
grep -q "image_tag != 'latest'" deploy.yml   && ok "deploy refuses image_tag=latest"   || bad "deploy does not refuse 'latest'"
grep -q "image_tag != 'latest'" rollback.yml && ok "rollback refuses image_tag=latest" || bad "rollback does not refuse 'latest'"
grep -q 'import_playbook: deploy.yml' rollback.yml && ok "rollback reuses the deploy path" || bad "rollback does not reuse deploy"

# --- 6. Deploy order + rolling -------------------------------------------------
order="$(grep -oE 'hosts: (redis|backend|voice)' deploy.yml | awk '{print $2}' | paste -sd, -)"
[ "$order" = "redis,backend,voice" ] && ok "deploy order redis->backend->voice" || bad "deploy order wrong: $order"
[ "$(grep -c 'serial: 1' deploy.yml)" -eq 2 ] && ok "backend and voice deploy rolling (serial:1)" || bad "rolling serial:1 not set on both app tiers"

# --- 7. Voice draining wiring --------------------------------------------------
grep -q "include_tasks: drain.yml" roles/compose_tier/tasks/main.yml && ok "drain.yml wired into the role" || bad "drain not wired"
grep -q "tier == 'voice'" roles/compose_tier/tasks/main.yml && ok "drain gated to the voice tier" || bad "drain not gated to voice"
grep -q "voice_drain_grace_seconds" roles/compose_tier/tasks/drain.yml && ok "bounded grace window in drain" || bad "no grace window in drain"
grep -q "voice_lb_drain_cmd" roles/compose_tier/tasks/drain.yml && ok "LB node-down hook present (INFRA-002 seam)" || bad "no LB drain hook"
# TASK-INFRA-007: the drain/enable hooks are now WIRED (not empty) to the HAProxy
# admin socket, delegated to the LB nodes; QA asserts the wiring offline.
VOICE_VARS="group_vars/voice.yml"
grep -Eq "voice_lb_drain_cmd: .+socat.+admin.sock" "$VOICE_VARS"  && ok "drain cmd populated (socat -> admin.sock)"  || bad "voice_lb_drain_cmd not wired to the admin socket"
grep -Eq "voice_lb_enable_cmd: .+socat.+admin.sock" "$VOICE_VARS" && ok "enable cmd populated (socat -> admin.sock)" || bad "voice_lb_enable_cmd not wired to the admin socket"
grep -q "state drain" "$VOICE_VARS" && grep -q "state ready" "$VOICE_VARS" && ok "drain/enable set HAProxy server state" || bad "drain/enable missing state drain|ready"
grep -q "voice_lb_socket_hosts" "$VOICE_VARS" && ok "LB socket hosts declared for delegation" || bad "no voice_lb_socket_hosts declared"
grep -q "delegate_to:" roles/compose_tier/tasks/drain.yml && ok "drain delegated to the LB node(s)" || bad "drain not delegated to LB"
grep -q "delegate_to:" roles/compose_tier/tasks/main.yml && ok "re-enable delegated to the LB node(s)" || bad "re-enable not delegated to LB"

# --- 8. Health verification ----------------------------------------------------
grep -q "ansible.builtin.uri" roles/compose_tier/tasks/health.yml && ok "HTTP health probe present" || bad "no HTTP health probe"
grep -q "redis-cli" roles/compose_tier/tasks/health.yml && ok "Redis ping health present" || bad "no Redis ping health"
grep -q 'REDISCLI_AUTH=' roles/compose_tier/tasks/health.yml && ! grep -q 'redis-cli -a ' roles/compose_tier/tasks/health.yml \
  && ok "Redis password via REDISCLI_AUTH (not argv)" || bad "Redis password exposed in argv (-a)"

# --- 9. KB provisioning (self-contained deploy) -------------------------------
grep -q "include_tasks: kb_assets.yml" roles/compose_tier/tasks/main.yml && ok "KB provisioning wired into the role" || bad "KB provisioning not wired"
grep -q "tier == 'backend'" roles/compose_tier/tasks/main.yml && ok "KB provisioning gated to the backend tier" || bad "KB provisioning not gated to backend"
grep -q "knowledge-base/" roles/compose_tier/tasks/kb_assets.yml && grep -q "articles.csv" roles/compose_tier/tasks/kb_assets.yml \
  && ok "KB task copies knowledge-base/ + articles.csv" || bad "KB task missing sources"

# --- 10. Registry credential hygiene (TASK-OPS-004) ---------------------------
# The role logs in before the pull; it must also log out afterwards so the token
# does not linger in ~/.docker/config.json, and both must be gated + no_log.
ROLE_MAIN="roles/compose_tier/tasks/main.yml"
awk '/docker login/{login=NR} /docker logout/{logout=NR} END{exit !(login && logout && logout>login)}' "$ROLE_MAIN" \
  && ok "registry logout runs after login (drops cached credentials)" || bad "no docker logout after the pull"
grep -q "docker logout {{ registry }}" "$ROLE_MAIN" \
  && grep -A4 "docker logout" "$ROLE_MAIN" | grep -q "registry_login_required | bool" \
  && ok "logout gated on registry_login_required" || bad "logout not gated on registry_login_required"

echo
echo "RESULT: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
