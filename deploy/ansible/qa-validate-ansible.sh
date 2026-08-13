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
[ "$(echo "$GRAPH" | grep -c 'vla-ai4cc-t0[12].prod.lan')" -eq 2 ] && ok "voice group has 2 bridges" || bad "voice group host count wrong"
[ "$(echo "$GRAPH" | grep -c 'vla-ai4cc-t0[34].prod.lan')" -eq 2 ] && ok "backend group has 2 nodes"  || bad "backend group host count wrong"

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
# TASK-INFRA-007: the drain/enable hooks are WIRED (socat -> admin.sock) but the
# hosts list defaults to EMPTY (opt-in) and the delegated tasks are non-fatal, so a
# platform-managed LB with no SSH access yet cannot abort the voice deploy.
VOICE_VARS="group_vars/voice.yml"
grep -Eq "voice_lb_drain_cmd: .+socat.+admin.sock" "$VOICE_VARS"  && ok "drain cmd populated (socat -> admin.sock)"  || bad "voice_lb_drain_cmd not wired to the admin socket"
grep -Eq "voice_lb_enable_cmd: .+socat.+admin.sock" "$VOICE_VARS" && ok "enable cmd populated (socat -> admin.sock)" || bad "voice_lb_enable_cmd not wired to the admin socket"
grep -q "state drain" "$VOICE_VARS" && grep -q "state ready" "$VOICE_VARS" && ok "drain/enable set HAProxy server state" || bad "drain/enable missing state drain|ready"
grep -q "voice_lb_socket_hosts" "$VOICE_VARS" && ok "LB socket hosts declared for delegation" || bad "no voice_lb_socket_hosts declared"
grep -q "delegate_to:" roles/compose_tier/tasks/drain.yml && ok "drain delegated to the LB node(s)" || bad "drain not delegated to LB"
grep -q "delegate_to:" roles/compose_tier/tasks/main.yml && ok "re-enable delegated to the LB node(s)" || bad "re-enable not delegated to LB"
# Adversarial review 2026-08-05: default hosts must be empty (opt-in) so delegating a
# drain to an unreachable platform-managed LB (serial:1 + max_fail_percentage:0) can't
# abort the voice deploy. Live enablement is gated with TASK-INFRA-006.
grep -Eq "^voice_lb_socket_hosts: \[\]" "$VOICE_VARS" && ok "LB drain defaults to opt-in (empty hosts -> grace-only)" || bad "voice_lb_socket_hosts default is not empty (could abort deploy on unreachable LB)"
# Even if an operator enables it, the delegated hooks must be non-fatal (degrade to grace).
grep -q "ignore_unreachable: true" roles/compose_tier/tasks/drain.yml && grep -q "failed_when: false" roles/compose_tier/tasks/drain.yml \
  && ok "drain hook is non-fatal (ignore_unreachable + failed_when:false)" || bad "drain hook can abort the deploy"
grep -q "ignore_unreachable: true" roles/compose_tier/tasks/main.yml && grep -q "failed_when: false" roles/compose_tier/tasks/main.yml \
  && ok "re-enable hook is non-fatal (ignore_unreachable + failed_when:false)" || bad "re-enable hook can abort the deploy"

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

# --- 11. Data backup/restore wiring (TASK-OPS-008) ----------------------------
BK="../backup"
grep -q "include_tasks: backup.yml" roles/compose_tier/tasks/main.yml && ok "backup.yml wired into the role" || bad "backup not wired"
grep -Eq "tier in \['redis', 'backend'\]" roles/compose_tier/tasks/main.yml && ok "backup gated to redis+backend tiers" || bad "backup not gated to data tiers"
# The four scripts exist, are executable and parse.
bk_ok=1
for s in redis-backup.sh redis-restore.sh pg-backup.sh pg-restore.sh; do
  [ -x "${BK}/${s}" ] || { bk_ok=0; echo "    missing/x: ${s}"; }
  bash -n "${BK}/${s}" >/dev/null 2>&1 || { bk_ok=0; echo "    bash -n failed: ${s}"; }
done
[ "$bk_ok" -eq 1 ] && ok "backup scripts present, executable and parse (bash -n)" || bad "a backup script is missing / non-exec / invalid"
# pg_dump / restore use pgvector-aware, credential-safe patterns.
grep -q 'CREATE EXTENSION IF NOT EXISTS vector' "${BK}/pg-restore.sh" && ok "pg-restore recreates the pgvector extension" || bad "pg-restore missing CREATE EXTENSION vector"
grep -q 'api/knowledge/sync' "${BK}/pg-restore.sh" && ok "pg-restore documents the KB re-sync fallback" || bad "pg-restore missing KB re-sync path"
grep -q 'REDISCLI_AUTH' "${BK}/redis-backup.sh" && ! grep -q 'redis-cli -a ' "${BK}/redis-backup.sh" && ok "redis backup auth via REDISCLI_AUTH (not argv)" || bad "redis backup exposes password in argv"
# Password must reach pg_dump via docker's -e PGPASSWORD env passthrough, never as a
# --password argv or an inline assignment (ignore the usage comment lines).
grep -q '\-e PGPASSWORD' "${BK}/pg-backup.sh" \
  && ! grep -vE '^[[:space:]]*#' "${BK}/pg-backup.sh" | grep -Eq '\-\-password[= ]|PGPASSWORD=[^"$]' \
  && ok "pg backup auth via PGPASSWORD env (not argv)" || bad "pg backup password not env-sourced"
# The Ansible role renders secrets into 0600 env files (no_log) sourced by cron, not the crontab.
grep -q 'redis-backup.env' roles/compose_tier/tasks/backup.yml && grep -q 'pg-backup.env' roles/compose_tier/tasks/backup.yml && ok "backup secrets in sourced env files" || bad "backup env files missing"
[ "$(grep -c 'no_log: true' roles/compose_tier/tasks/backup.yml)" -ge 2 ] && ok "backup env rendering uses no_log" || bad "backup env rendering not no_log"
grep -q 'ansible.builtin.cron' roles/compose_tier/tasks/backup.yml && ok "backup schedule uses cron" || bad "no backup cron scheduled"
grep -q "inventory_hostname == groups\['backend'\]\[0\]" roles/compose_tier/tasks/backup.yml && ok "pg backup runs on a single backend node" || bad "pg backup not pinned to one node"
grep -q 'vault_redis_password' roles/compose_tier/tasks/backup.yml && grep -q 'vault_db_password' roles/compose_tier/tasks/backup.yml && ok "backup passwords sourced from vault_* vars" || bad "backup passwords not from vault"
# Behavioral regression (BUG found in adversarial review 2026-08-05): a cron that sources an
# env file then EXEC's the backup script must `set -a` so the secret is exported to the child
# process. A bare `. env && ... script.sh` leaves the var non-exported -> the script never sees
# REDISCLI_AUTH -> silent backup failure. Both jobs must export.
env_src=$(grep -cE '(^|;|\s)\.\s+\{\{ compose_root \}\}.*backup\.env' roles/compose_tier/tasks/backup.yml)
set_a=$(grep -c 'set -a; \. {{ compose_root }}' roles/compose_tier/tasks/backup.yml)
[ "$env_src" -ge 2 ] && [ "$set_a" -ge 2 ] && ok "both backup crons export sourced secrets (set -a before sourcing)" \
  || bad "a backup cron sources its env file without 'set -a' -> secret not exported to the script (silent failure)"
# Prove the shell semantics the check relies on (documents WHY the bare pattern is a bug).
_qa_env="$(mktemp)"; printf 'QA_SECRET=xyz\n' > "$_qa_env"
_exported=$( set -a; . "$_qa_env"; set +a; sh -c 'printf %s "$QA_SECRET"' )
_bare=$( . "$_qa_env"; sh -c 'printf %s "$QA_SECRET"' )
rm -f "$_qa_env"
[ "$_exported" = "xyz" ] && [ -z "$_bare" ] && ok "verified: 'set -a' exports to exec'd child, bare source does not" \
  || bad "shell export semantics unexpected on this host"

# --- 12. WebRTC STUN/TURN wiring (TASK-INFRA-006) -----------------------------
# The runtime consumes STUN as plain URLs and TURN as credentialed ICE servers
# (build_ice_servers). The env must flow group_vars -> template -> compose -> container.
VOICE_TPL="roles/compose_tier/templates/voice.env.j2"
turn_ok=1
for k in VOICE_TURN VOICE_TURN_USERNAME VOICE_TURN_CREDENTIAL; do
  grep -q "^${k}=" "$VOICE_TPL" || { turn_ok=0; echo "    template missing ${k}"; }
done
[ "$turn_ok" -eq 1 ] && ok "voice template wires VOICE_TURN/USERNAME/CREDENTIAL" || bad "voice template missing a TURN var"
# The TURN credential is a secret -> must come from the vault, never a literal.
grep -q "VOICE_TURN_CREDENTIAL={{ vault_turn_credential | default('') }}" "$VOICE_TPL" \
  && ok "TURN credential sourced from vault_turn_credential (never committed)" || bad "TURN credential not sourced from a vault_* var"
# group_vars declares the non-secret TURN config (URLs + username), opt-in empty by default.
grep -Eq '^voice_turn: ""' "$VOICE_VARS" && grep -Eq '^voice_turn_username: ""' "$VOICE_VARS" \
  && ok "group_vars declares voice_turn + voice_turn_username (opt-in empty)" || bad "group_vars missing voice_turn/username defaults"
# The compose contract forwards the TURN vars into the container + the .env.example lists them.
VOICE_COMPOSE="${COMPOSE_DIR}/voice/docker-compose.yml"
VOICE_EXAMPLE="${COMPOSE_DIR}/voice/.env.example"
compose_ok=1
for k in VOICE_TURN VOICE_TURN_USERNAME VOICE_TURN_CREDENTIAL; do
  grep -q "${k}:" "$VOICE_COMPOSE" || { compose_ok=0; echo "    compose missing ${k}"; }
  grep -q "^${k}=" "$VOICE_EXAMPLE" || { compose_ok=0; echo "    .env.example missing ${k}"; }
done
[ "$compose_ok" -eq 1 ] && ok "compose + .env.example expose the TURN vars" || bad "compose/.env.example missing a TURN var"

# --- 13. Centralized OTLP observability wiring (TASK-OPS-007) ------------------
# One variable (otel_collector_endpoint) drives export on both tiers; empty => OFF.
ALL_VARS="group_vars/all/vars.yml"
grep -Eq '^otel_collector_endpoint: ""' "$ALL_VARS" && ok "otel_collector_endpoint declared, empty by default (export OFF)" \
  || bad "otel_collector_endpoint missing or not empty-by-default"
grep -Eq '^otel_traces_sampler_arg:' "$ALL_VARS" && ok "otel_traces_sampler_arg declared (pilot sampling)" || bad "otel_traces_sampler_arg missing"
# The pilot collector stack ships a store so slice percentiles aggregate in one place.
OTEL_DIR="../observability"
grep -q 'prometheus:' "${OTEL_DIR}/docker-compose.otel.yml" && ok "pilot collector stack adds Prometheus (metric aggregation)" || bad "collector stack missing Prometheus"
grep -q 'otel-collector:8889' "${OTEL_DIR}/prometheus.yml" && ok "Prometheus scrapes the collector's exporter" || bad "prometheus.yml missing collector scrape target"
# OFF path: default render keeps export disabled on both tiers (sampler 0.0, no endpoints).
ansible localhost -c local -m ansible.builtin.template \
  -a "src=roles/compose_tier/templates/backend.env.j2 dest=${TMP}/be_off.env mode=0600" \
  -e "@group_vars/backend.yml" -e ansible_become=false >/dev/null 2>&1
grep -q '^OTEL_METRICS_EXPORT_ENABLED=false' "${TMP}/be_off.env" && grep -q '^OTEL_TRACES_SAMPLER_ARG=0.0' "${TMP}/be_off.env" \
  && ok "backend export OFF by default (no collector endpoint)" || bad "backend default render is not export-OFF"
# ON path: setting the endpoint enables export and derives /v1/metrics + /v1/traces.
ansible localhost -c local -m ansible.builtin.template \
  -a "src=roles/compose_tier/templates/backend.env.j2 dest=${TMP}/be_on.env mode=0600" \
  -e "@group_vars/backend.yml" -e otel_collector_endpoint=http://obs.tst:4318 -e ansible_become=false >/dev/null 2>&1
grep -q '^OTEL_METRICS_EXPORT_ENABLED=true' "${TMP}/be_on.env" \
  && grep -q '^OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://obs.tst:4318/v1/metrics' "${TMP}/be_on.env" \
  && grep -q '^OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://obs.tst:4318/v1/traces' "${TMP}/be_on.env" \
  && ok "backend export ON derives metrics+traces endpoints from the base URL" || bad "backend export-ON render wrong"
ansible localhost -c local -m ansible.builtin.template \
  -a "src=roles/compose_tier/templates/voice.env.j2 dest=${TMP}/v_on.env mode=0600" \
  -e "@group_vars/voice.yml" -e otel_collector_endpoint=http://obs.tst:4318 -e ansible_become=false >/dev/null 2>&1
grep -q '^OTEL_EXPORTER_OTLP_ENDPOINT=http://obs.tst:4318$' "${TMP}/v_on.env" \
  && ok "voice export ON points OTEL_EXPORTER_OTLP_ENDPOINT at the collector" || bad "voice export-ON render wrong"

echo
echo "RESULT: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
