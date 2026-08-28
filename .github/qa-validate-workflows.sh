#!/usr/bin/env bash
# QA validation for TASK-OPS-001 - GitHub Actions CI (test gate + image build/push).
# Deterministic static checks on the workflow definitions: lints them (actionlint if
# available) and asserts the CI/CD invariants the ticket acceptance criteria and the
# adversarial review require. The real "PR runs the gates / tag publishes images" run
# can only be proven on GitHub Actions and is validated on the first PR/tag.
#
# Usage: .github/qa-validate-workflows.sh   (run from anywhere; cd's to repo root)
# Exit 0 = all checks pass; non-zero = at least one failure.

set -u
cd "$(dirname "$0")/.."   # repo root
WF=.github/workflows

pass=0; fail=0
ok() { printf '  PASS  %s\n' "$1"; pass=$((pass+1)); }
ko() { printf '  FAIL  %s\n' "$1"; fail=$((fail+1)); }
has()  { grep -q -- "$2" "$1"; }      # file contains pattern
hasnt(){ ! grep -q -- "$2" "$1"; }    # file does NOT contain pattern

echo "== YAML well-formed =="
python3 - <<'PY' && ok "all workflows parse as YAML" || ko "a workflow is not valid YAML"
import yaml, glob, sys
for f in sorted(glob.glob(".github/workflows/*.yml")):
    yaml.safe_load(open(f))
PY

echo "== actionlint (if available) =="
AL="$(command -v actionlint || echo /tmp/actionlint)"
if [ -x "$AL" ]; then
  "$AL" "$WF"/*.yml && ok "actionlint clean" || ko "actionlint reported issues"
else
  echo "  SKIP  actionlint not installed (YAML parse + structural checks still enforced)"
fi

echo "== reusable test gate =="
has  "$WF/tests.yml"  "workflow_call"                     && ok "tests.yml is reusable (workflow_call)"      || ko "tests.yml not reusable"
has  "$WF/ci.yml"     "uses: ./.github/workflows/tests.yml" && ok "ci.yml reuses the shared test gate"        || ko "ci.yml does not reuse tests.yml"
has  "$WF/images.yml" "uses: ./.github/workflows/tests.yml" && ok "images.yml reuses the shared test gate"    || ko "images.yml does not reuse tests.yml"
has  "$WF/images.yml" "needs: tests"                      && ok "image build-push is gated by tests"          || ko "image publish NOT gated by tests"

echo "== test gate content =="
has "$WF/tests.yml" "mvn -B"            && ok "backend mvn test present"               || ko "backend mvn test missing"
has "$WF/tests.yml" "unittest discover" && ok "voice unittest present"                 || ko "voice unittest missing"
has "$WF/tests.yml" "behave"           && ok "voice behave present"                    || ko "voice behave missing"
has "$WF/tests.yml" "libgl1"           && ok "cv2 system libs installed (import-safe)" || ko "cv2 libs missing (import will fail)"

echo "== image publish scheme =="
has "$WF/images.yml" "type=sha"              && ok "immutable sha- tag"          || ko "sha tag missing"
has "$WF/images.yml" "type=semver"           && ok "semver release tag"          || ko "semver tag missing"
has "$WF/images.yml" "type=raw,value=latest" && ok "latest on default branch"    || ko "latest tag missing"
has "$WF/images.yml" "backend/Dockerfile" && has "$WF/images.yml" "voice-agent/Dockerfile" \
  && ok "both images built (backend + voice)" || ko "an image is missing from the matrix"

echo "== security posture =="
hasnt "$WF/images.yml" "pull_request"   && ok "images.yml does NOT run on pull_request (no fork push)" || ko "images.yml triggers on pull_request"
has   "$WF/images.yml" "packages: write" && ok "images.yml has packages:write"                          || ko "images.yml missing packages:write"
hasnt "$WF/ci.yml"     "packages: write" && ok "ci.yml has no packages:write (least privilege)"         || ko "ci.yml over-privileged"
hasnt "$WF/tests.yml"  "packages: write" && ok "tests.yml has no packages:write (least privilege)"      || ko "tests.yml over-privileged"
has   "$WF/images.yml" "secrets.GITHUB_TOKEN" && ok "GHCR login via GITHUB_TOKEN (no external secret)"  || ko "GHCR login not using GITHUB_TOKEN"

echo "== no hardcoded secrets in workflows =="
if grep -REn '(sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{12,})' "$WF"/*.yml >/dev/null 2>&1; then
  ko "a workflow contains a hardcoded secret"
else
  ok "no hardcoded secret in workflows"
fi

echo "== referenced Dockerfiles exist =="
[ -f backend/Dockerfile ]      && ok "backend/Dockerfile exists"      || ko "backend/Dockerfile missing"
[ -f voice-agent/Dockerfile ]  && ok "voice-agent/Dockerfile exists"  || ko "voice-agent/Dockerfile missing"

echo "== action pinning to commit SHA (supply-chain, TASK-OPS-006) =="
# Every third-party `uses:` must reference a 40-hex commit SHA (immutable), not a
# floating tag (@v4, @main). The local reusable `uses: ./...` is exempt (same repo).
refs=$(grep -REh '^[[:space:]]*(- )?uses:[[:space:]]' "$WF"/*.yml \
  | sed -E 's/.*uses:[[:space:]]*([^[:space:]]+).*/\1/')
unpinned=$(printf '%s\n' "$refs" | grep -vE '^\./' | grep -vE '@[0-9a-f]{40}$' || true)
if [ -n "$unpinned" ]; then
  ko "action ref(s) NOT pinned to a commit SHA: $(printf '%s' "$unpinned" | tr '\n' ' ')"
else
  ok "all third-party actions pinned to a 40-hex commit SHA"
fi
# Readability guard: a pinned SHA should keep a trailing `# vX.Y.Z` version comment.
if grep -REn '@[0-9a-f]{40}[[:space:]]*$' "$WF"/*.yml >/dev/null 2>&1; then
  ko "a SHA-pinned action has no trailing # vX.Y.Z version comment"
else
  ok "pinned actions carry a # vX.Y.Z readability comment"
fi

echo "== dependabot (reviewed SHA bumps, TASK-OPS-006) =="
[ -f .github/dependabot.yml ] \
  && ok "dependabot.yml present" || ko "dependabot.yml missing"
has .github/dependabot.yml "package-ecosystem: github-actions" \
  && ok "dependabot tracks the github-actions ecosystem" || ko "dependabot github-actions ecosystem missing"
python3 - <<'PY' && ok "dependabot.yml is valid YAML" || ko "dependabot.yml is not valid YAML"
import yaml, sys
yaml.safe_load(open(".github/dependabot.yml"))
PY

echo
printf 'RESULT: %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
