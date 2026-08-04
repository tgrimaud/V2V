# QA Functional And Latency Report — TASK-OPS-001 (GitHub Actions CI: test gate + image build/push)

## Executive Summary

- **Overall readiness:** GO for merge-ready. The three workflows
  (`.github/workflows/{tests,ci,images}.yml`) lint clean and satisfy every CI/CD
  invariant in the ticket acceptance criteria and the adversarial review
  (22/22 automated checks pass via `.github/qa-validate-workflows.sh`).
- **Main blockers:** none.
- **Residual risks:** the two acceptance scenarios ("a PR runs the gates", "a
  release tag publishes tagged images") execute only on GitHub-hosted runners, so
  their live proof happens on the **first PR and the first `v*.*.*` tag** after
  merge. Static validation (actionlint + structural invariants) is complete; the
  live run is deferred, not skipped (same pattern as INFRA-001's tst smoke).

## Scope Tested

- **Epic / task:** EPIC-012 (Pilot deployment, release & operations) / TASK-OPS-001.
- **Channels:** N/A (CI/CD; no conversation behavior changed).
- **Providers / fakes:** none — validation is static over the workflow definitions.
- **Environment:** local, `actionlint` + Python YAML + Bash. GitHub Actions runners
  not invoked (no live push/PR triggered from QA).

## Acceptance Scenarios (Gherkin)

```gherkin
Feature: CI gates and versioned image publishing

  Scenario: A pull request runs the quality gates
    Given a pull request against the mainline
    When CI runs
    Then the backend mvn test job runs and must pass
    And the voice-agent unittest and behave jobs run and must pass

  Scenario: A release tag publishes tested, versioned images
    Given a v*.*.* tag is pushed
    When the image workflow runs
    Then the shared test gate runs first and must pass
    And both the backend and voice images are built and pushed
    And each image carries an immutable sha-<short> tag and the semantic version

  Scenario: Untrusted pull requests cannot publish images
    Given a pull request from any branch or fork
    Then the image build/push workflow does not run
    And no registry credentials are exposed to PR code

  Scenario: The image tag scheme is reusable by the deploy
    Given a published image
    Then it is addressable by an immutable tag (sha or semver)
    So the Ansible deploy (TASK-OPS-002) can pin and roll back by tag
```

Automation: `.github/qa-validate-workflows.sh` (22 deterministic checks) is the
regression net for these scenarios until the first live GitHub Actions run.

## Functional Results

| Area | Status | Evidence | Notes |
|---|---|---|---|
| Workflows lint + parse | ✅ Pass | actionlint clean + YAML parse (3 files) | expressions + shellcheck via actionlint |
| PR test gate (backend + voice) | ✅ Pass (static) | reusable `tests.yml`: `mvn -B test`, `unittest discover`, `behave`, cv2 libs | live proof on first PR |
| Release publishes tested images | ✅ Pass (static) | `images.yml` `build-push: needs: tests`; matrix backend+voice → GHCR | live proof on first `v*.*.*` tag |
| Immutable/version tag scheme | ✅ Pass | `type=sha` + `type=semver` + `latest` on default branch | reusable by OPS-002 rollback |
| PRs cannot publish images | ✅ Pass | `images.yml` has no `pull_request` trigger | fork-safe |
| Least-privilege + secret hygiene | ✅ Pass | `packages:write` only in `images.yml`; GHCR via `GITHUB_TOKEN`; no hardcoded secret | ci/tests are `contents:read` |
| Live GitHub Actions execution | ⏳ Deferred | runs only on GitHub | verify on first PR + first tag post-merge |

## Latency Results

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| — | — | — | — | — | — | **N/A — not runtime-affecting.** OPS-001 is CI/CD tooling; it adds no request path, span or measurable pipeline slice. (CI job wall-clock is an ops metric, not a product latency SLO.) |

No pipeline slice is claimed rather than fabricated: this ticket does not run the
voice loop.

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| `tests.yml` (reusable gate) | ✅ Pass | backend + voice suites, cv2 libs mirrored from Dockerfile | live run on first PR |
| `ci.yml` | ✅ Pass | reuses gate; push scoped to mainline (no duplicate PR+push) | — |
| `images.yml` | ✅ Pass | gated by tests; GHCR; fork-safe; buildx+gha cache | live run on first tag; confirm registry (open input #5) |
| Secret hygiene | ✅ Pass | no hardcoded secret; `GITHUB_TOKEN` only | rotate to registry creds if Nexus chosen |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Info | Live workflow execution not triggered from QA | Static validation complete; runtime proof only on GitHub | Ops — verify on first PR + tag |
| Low | Registry is GHCR by default (open input #5 not finalized) | If an internal Nexus/Artifactory is mandated, change `REGISTRY` + login + add creds | TASK-INFRA-003 / platform |
| Info | `latest` tracks `feat/restart-from-scratch`, not `main` | Intentional (active integration branch) | documented in workflow header |

## Open Questions

- **Product:** none.
- **Architecture:** confirm the container registry (GHCR vs internal) — open input #5.
- **Technical:** confirm GHCR package visibility/permissions for the org, and (if
  Nexus) the credential secrets to add.

## Recommendation

- **Go / No-go:** **GO** — merge-ready. Adversarial review 93/100 (Pass) + 22/22
  QA checks green.
- **Required fixes before pilot:** none from this ticket. On the first PR after
  merge, confirm both gate jobs run and pass; on the first `v*.*.*` tag, confirm
  both images publish with the expected tags. Finalize the registry choice
  (open input #5) before relying on published images for the tst deploy (OPS-002).
