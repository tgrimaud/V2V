#!/usr/bin/env bash
# QA validation for TASK-OPS-003 (host prerequisites: Docker + compose on Rocky EL9).
# Deterministic, offline structural checks (no VM needed): syntax, targets, packages,
# service, firewalld wiring, per-tier firewall_port. Run from deploy/ansible/.
set -uo pipefail
cd "$(dirname "$0")"

pass=0; fail=0
ok()  { echo "PASS: $1"; pass=$((pass+1)); }
ko()  { echo "FAIL: $1"; fail=$((fail+1)); }
has() { grep -q "$1" "$2" 2>/dev/null; }

ROLE="roles/host_prereqs/tasks/main.yml"
PLAY="prereqs.yml"

# 1) Playbook parses.
if ansible-playbook "$PLAY" --syntax-check >/dev/null 2>&1; then ok "prereqs.yml syntax-check"; else ko "prereqs.yml syntax-check"; fi

# 2) Targets the deploy tiers, not the platform-managed data/lb hosts.
has "hosts: redis:backend:voice" "$PLAY" && ok "prereqs targets redis:backend:voice" || ko "prereqs targets redis:backend:voice"
has "become: true" "$PLAY" && ok "prereqs runs with become" || ko "prereqs runs with become"
if grep -qE "hosts:.*(data|lb)" "$PLAY"; then ko "prereqs must NOT target data/lb"; else ok "prereqs excludes data/lb (out of scope)"; fi

# 3) Docker CE repo + packages.
has "download.docker.com/linux/centos/docker-ce.repo" "$ROLE" && ok "adds Docker CE repo (EL9)" || ko "adds Docker CE repo (EL9)"
for pkg in docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; do
  has "$pkg" "$ROLE" && ok "installs $pkg" || ko "installs $pkg"
done

# 4) Service enabled/started + user in docker group.
has "name: docker" "$ROLE" && has "enabled: true" "$ROLE" && ok "enables/starts docker service" || ko "enables/starts docker service"
has "groups: docker" "$ROLE" && ok "adds deploy user to docker group" || ko "adds deploy user to docker group"

# 5) firewalld tier-aware + guarded (no-op when inactive), no external collection.
has "firewall-cmd --permanent --add-port" "$ROLE" && ok "opens tier port via firewall-cmd" || ko "opens tier port via firewall-cmd"
has "firewalld_state.stdout == 'active'" "$ROLE" && ok "firewalld tasks guarded on active state" || ko "firewalld tasks guarded on active state"
if grep -q "ansible.posix.firewalld" "$ROLE"; then ko "avoid ansible.posix collection dependency"; else ok "no external collection dependency"; fi

# 6) Idempotency intent on the firewalld add (ALREADY_ENABLED not treated as change).
has "ALREADY_ENABLED" "$ROLE" && ok "firewalld add is idempotent (ALREADY_ENABLED)" || ko "firewalld add is idempotent"

# 7) Per-tier firewall_port matches each service port.
grep -q "firewall_port: 6379" group_vars/redis.yml   && ok "redis firewall_port=6379"   || ko "redis firewall_port=6379"
grep -q "firewall_port: 8080" group_vars/backend.yml  && ok "backend firewall_port=8080" || ko "backend firewall_port=8080"
grep -q "firewall_port: 8090" group_vars/voice.yml    && ok "voice firewall_port=8090"   || ko "voice firewall_port=8090"

# 8) Post-install verification present.
has "docker compose version" "$ROLE" && ok "verifies docker compose availability" || ko "verifies docker compose availability"

echo "RESULT: $pass passed, $fail failed"
test "$fail" -eq 0
