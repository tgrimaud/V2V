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
grep -q 'GENESYS_AUDIOHOOK_API_KEY={{ vault_genesys_audiohook_api_key }}' roles/compose_tier/templates/voice.env.j2 || sec_ok=0
grep -q 'GENESYS_AUDIOHOOK_SECRET={{ vault_genesys_audiohook_secret }}'   roles/compose_tier/templates/voice.env.j2 || sec_ok=0
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
# The re-enable hook was extracted into lb_reenable.yml (TASK-INFRA-007) so the delegated
# loop is only built on the voice tier; the non-fatal flags now live there, not in main.yml.
grep -q "ignore_unreachable: true" roles/compose_tier/tasks/lb_reenable.yml && grep -q "failed_when: false" roles/compose_tier/tasks/lb_reenable.yml \
  && ok "re-enable hook is non-fatal (ignore_unreachable + failed_when:false)" || bad "re-enable hook can abort the deploy"

# --- 8. Health verification ----------------------------------------------------
grep -q "ansible.builtin.uri" roles/compose_tier/tasks/health.yml && ok "HTTP health probe present" || bad "no HTTP health probe"
grep -q "redis-cli" roles/compose_tier/tasks/health.yml && ok "Redis ping health present" || bad "no Redis ping health"
# TASK-INFRA-011: container-health probe (docker inspect .State.Health.Status) is the
# preferred gate for tiers with a container HEALTHCHECK, immune to host loopback/firewall.
grep -q ".State.Health.Status" roles/compose_tier/tasks/health.yml && ok "container-health probe present" || bad "no container-health probe"
grep -q "health_container_name" roles/compose_tier/tasks/health.yml && ok "container-health probe gated by health_container_name" || bad "container-health probe not gated"
grep -q 'health_container_name: "voice-support-bridge"' group_vars/voice.yml && ok "voice tier uses the container-health gate" || bad "voice tier not set to container-health gate"
grep -q 'REDISCLI_AUTH=' roles/compose_tier/tasks/health.yml && ! grep -q 'redis-cli -a ' roles/compose_tier/tasks/health.yml \
  && ok "Redis password via REDISCLI_AUTH (not argv)" || bad "Redis password exposed in argv (-a)"

# --- 9. KB provisioning (self-contained deploy) -------------------------------
grep -q "include_tasks: kb_assets.yml" roles/compose_tier/tasks/main.yml && ok "KB provisioning wired into the role" || bad "KB provisioning not wired"
grep -q "tier == 'backend'" roles/compose_tier/tasks/main.yml && ok "KB provisioning gated to the backend tier" || bad "KB provisioning not gated to backend"
grep -q "knowledge-base/" roles/compose_tier/tasks/kb_assets.yml && grep -q "kb_csv_filename" roles/compose_tier/tasks/kb_assets.yml \
  && ok "KB task copies knowledge-base/ + the CSV corpus (kb_csv_filename)" || bad "KB task missing sources"
# ADR-0048 / TASK-OPS-009: FR corpus default + post-deploy sync trigger + non-empty verify.
grep -q 'kb_csv_filename: "articles-fr.csv"' group_vars/backend.yml && grep -q 'kb_csv_language: "fr"' group_vars/backend.yml \
  && ok "Backend defaults to the French CSV corpus (ADR-0048)" || bad "FR CSV corpus default missing"
grep -q 'KB_CSV_PATH=/app/kb-assets/{{ kb_csv_filename }}' roles/compose_tier/templates/backend.env.j2 \
  && grep -q 'KB_CSV_LANGUAGE={{ kb_csv_language }}' roles/compose_tier/templates/backend.env.j2 \
  && ok "backend.env.j2 wires KB_CSV_PATH + KB_CSV_LANGUAGE from vars" || bad "backend.env.j2 KB CSV wiring missing"
grep -q "include_tasks: kb_sync.yml" roles/compose_tier/tasks/main.yml \
  && ok "Post-deploy KB sync wired into the role" || bad "Post-deploy KB sync not wired"
grep -q 'api/knowledge/sync' roles/compose_tier/tasks/kb_sync.yml \
  && grep -q 'api/conversation/retrieve' roles/compose_tier/tasks/kb_sync.yml \
  && ok "KB sync triggers sync + verifies retrieval non-empty" || bad "KB sync task missing sync/verify"
grep -q 'no_log: true' roles/compose_tier/tasks/kb_sync.yml \
  && ok "KB sync reads the api key with no_log" || bad "KB sync api-key not no_log-protected"
# The first CSV sync runs ~15-30 min (CPU embeddings), so it must be fired async and waited
# on via async_status, then gated on SyncReport.processed (CSV seen, not markdown-only).
grep -q 'async_status' roles/compose_tier/tasks/kb_sync.yml \
  && grep -q 'poll: 0' roles/compose_tier/tasks/kb_sync.yml \
  && ok "KB sync fires async + waits via async_status (slow CPU embed)" || bad "KB sync not async (600s would time out)"
grep -q 'kb_sync_min_processed' roles/compose_tier/tasks/kb_sync.yml \
  && grep -q 'json.processed' roles/compose_tier/tasks/kb_sync.yml \
  && ok "KB sync gates on SyncReport.processed (proves CSV corpus loaded)" || bad "KB sync missing processed gate"

# --- 10. Registry credential hygiene (TASK-OPS-004) ---------------------------
# The role logs in before the pull; it must also log out afterwards so the token
# does not linger in the registry auth file, and both must be gated + no_log.
# Runtime is podman on the EL9 VMs (TASK-INFRA-008), so the commands are `podman login/logout`.
ROLE_MAIN="roles/compose_tier/tasks/main.yml"
awk '/podman login/{login=NR} /podman logout/{logout=NR} END{exit !(login && logout && logout>login)}' "$ROLE_MAIN" \
  && ok "registry logout runs after login (drops cached credentials)" || bad "no podman logout after the pull"
grep -q "podman logout {{ registry }}" "$ROLE_MAIN" \
  && grep -A4 "podman logout" "$ROLE_MAIN" | grep -q "registry_login_required | bool" \
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

# --- 14. Single routed-port live WebSocket wiring (ADR-0047 / TASK-WEB-038) ---
# The runtime now serves the live WebSocket on the SAME routed :8090 at /ws (single async
# aiohttp server). The interim second listener/port (:8091 + VOICE_WS_PORT) is RETIRED:
# assert it is gone from group_vars/template/compose/.env.example, and that the WS session
# ceiling (VOICE_MAX_WS_SESSIONS) flows group_vars -> template -> compose -> container.
# Per ADR-0047 there is still NO separate edge firewall opening (WS tunnels on :8090).
! grep -q 'voice_ws_port' "$VOICE_VARS"  && ok "group_vars drops voice_ws_port (WS on the routed :8090)"   || bad "stale voice_ws_port in group_vars (retired per ADR-0047)"
! grep -q 'VOICE_WS_PORT' "$VOICE_TPL"   && ok "voice template drops VOICE_WS_PORT"                          || bad "stale VOICE_WS_PORT in voice template"
! grep -q 'VOICE_WS_PORT' "$VOICE_EXAMPLE" && ok ".env.example drops VOICE_WS_PORT"                          || bad "stale VOICE_WS_PORT in .env.example"
! grep -Eq ':8091' "$VOICE_COMPOSE"      && ok "compose no longer publishes a separate :8091 port"           || bad "compose still publishes :8091 (retired per ADR-0047)"
[ "$(grep -cE '^\s+- "\$\{VOICE_BIND' "$VOICE_COMPOSE")" -eq 1 ] && ok "compose publishes exactly one port (the routed :8090)" || bad "compose publishes more than one port"
grep -Eq '^voice_max_ws_sessions: [0-9]+' "$VOICE_VARS" && ok "group_vars declares voice_max_ws_sessions" || bad "group_vars missing voice_max_ws_sessions"
grep -q '^VOICE_MAX_WS_SESSIONS={{ voice_max_ws_sessions }}' "$VOICE_TPL" && ok "voice template renders VOICE_MAX_WS_SESSIONS" || bad "voice template missing VOICE_MAX_WS_SESSIONS"
grep -q 'VOICE_MAX_WS_SESSIONS:' "$VOICE_COMPOSE" && ok "compose forwards VOICE_MAX_WS_SESSIONS into the container" || bad "compose missing VOICE_MAX_WS_SESSIONS"
grep -q '^VOICE_MAX_WS_SESSIONS=' "$VOICE_EXAMPLE" && ok ".env.example lists VOICE_MAX_WS_SESSIONS" || bad ".env.example missing VOICE_MAX_WS_SESSIONS"
! grep -q '^firewall_extra_ports:' "$VOICE_VARS" && ! grep -q 'firewall_extra_ports' roles/host_prereqs/tasks/main.yml \
  && ok "no firewall_extra_ports dead config (ADR-0047: WS tunnels on the routed :8090)" || bad "stale firewall_extra_ports present (dropped per ADR-0047)"
# The rendered .env must actually carry the WS ceiling (default render, export irrelevant).
ansible localhost -c local -m ansible.builtin.template \
  -a "src=roles/compose_tier/templates/voice.env.j2 dest=${TMP}/v_ws.env mode=0600" \
  -e "@group_vars/voice.yml" -e ansible_become=false >/dev/null 2>&1
grep -Eq '^VOICE_MAX_WS_SESSIONS=[0-9]+$' "${TMP}/v_ws.env" && ok "rendered voice .env sets VOICE_MAX_WS_SESSIONS" || bad "rendered voice .env missing VOICE_MAX_WS_SESSIONS"

echo
echo "RESULT: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
