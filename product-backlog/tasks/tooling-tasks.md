# Tooling / Environment Technical Tasks

Cross-cutting developer-environment and tooling tickets (not tied to a single
product story). They keep the delivery workflow reproducible.

## TASK-ENV-001 - Standardize The voice-agent Test Virtualenv

**Parent:** Delivery tooling
**Classification:** Developer experience / CI enabler
**Status:** ✅ Done (Sprint 5, 2026-07-15) — venv setup documented in `voice-agent/README.md` + `CLAUDE.md`, already on `feat/restart-from-scratch`. (Reconciled 2026-07-23: an earlier note wrongly re-scheduled this to Sprint 9 "validate + merge" — nothing was pending, the work shipped in Sprint 5.)
**Priority:** Medium
**Branch:** `task/TASK-ENV-001-test-venv` (from `feat/sprint-5-backend-bridge`)

### Problem

Since Sprint 4 the full `voice-agent` test suite depends on `pipecat-ai` (and QA
on `behave`). These live in `voice-agent/.venv`, not in the system Python, so
running the documented `python3 -m unittest discover tests` with a bare system
`python3` fails with `ModuleNotFoundError: No module named 'pipecat'` and silently
reports fewer tests plus 8 import errors. The README and `CLAUDE.md` pointed at the
system interpreter and the README's venv snippet only installed `behave` (not
`-r requirements.txt`), so the pipecat dependency was never pulled.

### Objective

Make "run the tests" reproducible: one documented virtualenv, created from
`requirements.txt`, used for both `unittest` and `behave`.

### Scope

- `voice-agent/README.md`: an "Environment setup (run this first)" section
  (`python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt`) and all
  run commands routed through `./.venv/bin/python` / `./.venv/bin/behave`.
- `CLAUDE.md`: the voice-runtime test command uses the venv; a gotcha row explains
  the `pipecat` `ModuleNotFoundError`.

### Out Of Scope

- CI pipeline definition (no CI on this branch yet).
- Any runtime/behaviour change (documentation + tooling only).

### Acceptance Criteria

```gherkin
Scenario: A fresh clone can run the whole voice-agent suite
  Given a developer follows the documented environment setup
  When they create the venv from requirements.txt and run the tests through it
  Then the full unittest suite passes (211 tests as of Sprint 5)
  And the behave suite passes (5 features / 17 scenarios / 78 steps as of Sprint 5)
  And no pipecat ModuleNotFoundError occurs
```

### Delivery Evidence

- Verified in the existing `voice-agent/.venv` (pipecat-ai 1.5.0, behave 1.3.3,
  websockets 16.1): at delivery the suite was **165 tests / 4 features / 14 scenarios
  / 62 steps**; re-verified after Sprint 5 it is **211 tests OK** and
  **5 features / 17 scenarios / 78 steps passed** (the venv standardization still
  holds as the suite grows).
- Docs updated: `voice-agent/README.md`, `CLAUDE.md`. `.venv/` is git-ignored.
- OpenTelemetry: **not applicable** (documentation / tooling only, no runtime change).
