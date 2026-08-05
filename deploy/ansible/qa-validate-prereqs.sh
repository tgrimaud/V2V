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

# 3b) Conflict handling for Rocky EL9 container-tools (podman/runc vs containerd.io).
has "allowerasing: true" "$ROLE" && ok "handles podman/runc conflict (allowerasing)" || ko "handles podman/runc conflict (allowerasing)"

# 4) Service enabled/started + user in docker group.
has "name: docker" "$ROLE" && has "enabled: true" "$ROLE" && ok "enables/starts docker service" || ko "enables/starts docker service"
has "groups: docker" "$ROLE" && ok "adds deploy user to docker group" || ko "adds deploy user to docker group"

# 5) firewalld tier-aware + guarded (no-op when inactive), no external collection.
has "firewall-cmd --permanent --add-port" "$ROLE" && ok "opens tier port via firewall-cmd" || ko "opens tier port via firewall-cmd"
has "firewalld_state.stdout == 'active'" "$ROLE" && ok "firewalld tasks guarded on active state" || ko "firewalld tasks guarded on active state"
if grep -q "ansible.posix.firewalld" "$ROLE"; then ko "avoid ansible.posix collection dependency"; else ok "no external collection dependency"; fi

# 6) Idempotency intent on the firewalld add (ALREADY_ENABLED not treated as change).
has "ALREADY_ENABLED" "$ROLE" && ok "firewalld add is idempotent (ALREADY_ENABLED)" || ko "firewalld add is idempotent"

# 6b) Source scoping (TASK-OPS-004): least-privilege rich rules + guarded fallback.
grep -qe '--add-rich-rule=rule' "$ROLE" && has "source address" "$ROLE" && ok "opens port via source-scoped rich rule" || ko "no source-scoped rich rule"
has "firewall_allowed_sources | default(\[\])" "$ROLE" && has "length > 0" "$ROLE" && ok "rich-rule path gated on a non-empty source list" || ko "rich-rule path not gated on source list"
has "length == 0" "$ROLE" && ok "unscoped add-port kept only as empty-list fallback" || ko "unscoped fallback not gated on empty source list"

# 7) Per-tier firewall_port matches each service port.
grep -q "firewall_port: 6379" group_vars/redis.yml   && ok "redis firewall_port=6379"   || ko "redis firewall_port=6379"
grep -q "firewall_port: 8080" group_vars/backend.yml  && ok "backend firewall_port=8080" || ko "backend firewall_port=8080"
grep -q "firewall_port: 8090" group_vars/voice.yml    && ok "voice firewall_port=8090"   || ko "voice firewall_port=8090"

# 7b) Per-tier allowed sources (least privilege): backend VMs reach Redis; LB nodes
# reach the app ports. A drift here would silently widen or break the firewall scope.
grep -q "192.168.0.105/32" group_vars/redis.yml && grep -q "192.168.0.106/32" group_vars/redis.yml \
  && ok "redis 6379 scoped to the backend VMs (.105/.106)" || ko "redis source scope wrong"
grep -q "192.168.0.100/32" group_vars/backend.yml && grep -q "192.168.0.101/32" group_vars/backend.yml \
  && ok "backend 8080 scoped to the LB nodes (.100/.101)" || ko "backend source scope wrong"
grep -q "192.168.0.100/32" group_vars/voice.yml && grep -q "192.168.0.101/32" group_vars/voice.yml \
  && ok "voice 8090 scoped to the LB nodes (.100/.101)" || ko "voice source scope wrong"

# 7c) Provisioning-time egress is documented (download.docker.com + OS mirrors).
DOC="../../docs/operations/deployment-eir-ai4cc-tst.md"
grep -q "download.docker.com" "$DOC" && grep -qi "provisioning" "$DOC" \
  && ok "provisioning-time egress documented (download.docker.com + mirrors)" || ko "provisioning egress not documented"

# 8) Post-install verification present.
has "docker compose version" "$ROLE" && ok "verifies docker compose availability" || ko "verifies docker compose availability"

echo "RESULT: $pass passed, $fail failed"
test "$fail" -eq 0
