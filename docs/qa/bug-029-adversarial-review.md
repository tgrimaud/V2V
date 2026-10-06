# BUG-029 — Adversarial code review (eval-viewer "OK" downgrade)

**Date:** 2026-10-06
**Branch:** `fix/BUG-029-eval-viewer-done-reset` (off `feat/restart-from-scratch`)
**Reviewer skill:** `.cursor/skills/adversarial-code-review/SKILL.md`
**Scope:** one JS function in `.cursor/skills/skill-creator/eval-viewer/viewer.html` (developer
tooling; not a bot runtime path). Fix = Option A (acknowledge-only `closeDoneDialog`).

## Verdict

**Proceed.** Minimal, behavior-correcting fix: "OK" on the completion overlay no longer re-saves,
so the `status:"complete"` submission from `showDoneDialog()` stays authoritative. No runtime,
security, latency or architecture impact.

## Satisfaction Score

Score: 94/100
QA gate: Pass

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | No automated regression test — the viewer is a single static HTML file with no JS test harness in the repo. | `rg "saveCurrentFeedback"` shows auto-save on typing (683, debounced) + navigation (691); no test runner for the asset. | Accept for a P3 tooling fix: the behavior is pinned by an explicit inline comment on `closeDoneDialog` + the ticket's reproduction/expected steps (manual check). Adding a JS harness for one skill asset is out of proportion. |
| Info | A future "re-open for editing after Done" feature would still need its own correct contract (`status:"in_progress"` with ALL runs, not the filtered auto-save). | documented in the ticket + inline comment. | No action now; captured so the next editor does not reintroduce the filtered path. |

## Story Coverage

| Acceptance criterion (BUG-029) | Covered? | Evidence |
|---|---|---|
| "OK" no longer downgrades `status` or drops runs | Yes | `closeDoneDialog()` now only hides the overlay (removed the `saveCurrentFeedback()` call) |
| Regression guard | Partial (manual) | inline comment pinning the intent + ticket repro steps; no JS harness exists (Non-Blocking Low) |
| OpenTelemetry | N/A | local tooling, no runtime telemetry |
| No collateral change | Yes | `saveCurrentFeedback` still used by auto-save (683/691) — not orphaned; `showDoneDialog`/auto-save untouched |

## Test Evidence

- Developer tests: none applicable (static HTML asset, no JS test runner). Verified by code reading:
  typing/navigation still auto-save (`in_progress`, correct mid-review); Done still writes `complete`
  with all runs; OK now leaves that intact.
- Missing tests: an automated DOM test would need a harness this skill asset does not have (accepted).
- QA scenarios to run: manual — Done → OK, then confirm `feedback.json` stays `status:"complete"` with
  one entry per run (including empty).

## Observability And Latency

- Relevant slices: none (developer tooling, not a measured runtime slice).
- OpenTelemetry / Metrics / Structured logs: not applicable.
- Missing: none.
- Risk: none.

## Security And Privacy

- Sensitive data risk: none (local eval feedback only).
- Identity/access risk: none.
- Logging risk: none.

## Required Developer Actions

1. None (no blocking finding).

## Residual Risk If Accepted

- The fix is guarded by an inline comment + ticket rather than an automated test (no JS harness for the
  viewer). Behavior is otherwise fully reasoned and the change is a single-line removal of an incorrect
  re-save. No runtime/security/latency exposure.
