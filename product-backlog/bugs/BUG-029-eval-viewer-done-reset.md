# BUG-029 — eval-viewer "OK" on completion overlay downgrades `complete` back to `in_progress`

## Header

- **Bug ID:** BUG-029
- **Title:** `closeDoneDialog` re-POSTs `in_progress` and drops empty-feedback runs after "Done"
- **Status:** Fixed (Option A), awaiting user validation (not merged) — **Adversarial review 94/100 (Pass, 2026-10-06)**, no blocking finding; residual (accepted): no JS test harness for the viewer → guarded by inline comment + manual check. Full review: `docs/qa/bug-029-adversarial-review.md`
- **Severity:** Low
- **Priority:** P3
- **Detected by:** Adversarial review (independent Bugbot pass during TASK-OPS-015 V1b/V2/V3)
- **Detected date:** 2026-10-06
- **Related user story:** n/a (internal tooling — `skill-creator` eval-viewer)
- **Related epic:** n/a (developer tooling)
- **Branch:** `fix/BUG-029-eval-viewer-done-reset`
- **Owner:** Cross-functional

## Problem Statement

In the `skill-creator` eval-viewer, after a reviewer clicks **Done** (which persists
`feedback.json` with `status: "complete"` and one entry per run, including empty
"looks good" feedback), clicking **OK** on the completion overlay silently rewrites
`feedback.json` back to `status: "in_progress"` and drops every empty-feedback run —
erasing the completion signal the skill-creator workflow relies on.

## Environment

- **Environment:** local (developer tooling, not a runtime path)
- **Channel:** n/a (static/served HTML viewer)
- **Build or commit:** `.cursor/skills/skill-creator/eval-viewer/viewer.html` on `feat/restart-from-scratch`
- **Correlation ID:** n/a

## Reproduction Steps

1. Given an eval review served by the viewer with at least one run left with empty feedback.
2. When the reviewer clicks **Done** (POST `{reviews(all runs), status: "complete"}`) and then clicks **OK** on the overlay.
3. Then `closeDoneDialog()` calls `saveCurrentFeedback()`, which POSTs `{reviews(non-empty only), status: "in_progress"}`.

## Expected Result

Acknowledging the completion overlay ("OK") leaves the completed submission intact:
`feedback.json` stays `status: "complete"` with one entry per run (empty = reviewed/looks good).

## Actual Result

`feedback.json` is overwritten to `status: "in_progress"` with only the non-empty runs;
the completion signal and the "empty = looks good" distinction are lost.

## Evidence

- Code: `viewer.html` `showDoneDialog()` (POST `complete`, all runs) vs `saveCurrentFeedback()`
  (POST `in_progress`, non-empty only) vs `closeDoneDialog()` (calls `saveCurrentFeedback()`).

## Impact

- Operational (tooling only): the skill-creator workflow that reads `feedback.json` sees the
  review as unfinished and loses the per-run "looks good" entries. No customer/advisor/runtime,
  security or latency impact; not on the pilot path.

## Acceptance Criteria For Fix

- [ ] "OK" on the completion overlay no longer downgrades `status` or drops runs.
- [ ] A regression check covers the behavior (viewer is static HTML — a documented manual check or a lightweight DOM assertion).
- [ ] OpenTelemetry: not applicable (local tooling, no runtime telemetry).
- [ ] Adversarial code review is at least 90% satisfied.
- [ ] Documentation/backlog updated if behavior changed.

## Developer Notes

- root cause: `closeDoneDialog()` reuses the filtered auto-save (`saveCurrentFeedback()`), whose
  contract is `status: "in_progress"` + non-empty runs only — the wrong contract for acknowledging
  a completed submission.
- fix (option A): `closeDoneDialog()` only hides the overlay; the completed submission from
  `showDoneDialog()` stays authoritative. "OK" is an acknowledgement, not an edit.
- files changed: `.cursor/skills/skill-creator/eval-viewer/viewer.html`
- residual risk: if the viewer ever needs "re-open for editing after Done", that is a separate
  feature (would re-POST `in_progress` with ALL runs), not covered here.

## QA Retest

- **Retested by:**
- **Retest date:**
- **Scenarios rerun:**
- **Result:**

## Closure

- **Closed by:**
- **Closed date:**
- **Closure reason:**
