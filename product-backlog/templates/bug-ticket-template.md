# Bug Ticket Template

Use this template whenever QA finds a defect during functional, UI, integration,
latency or pilot-readiness validation.

No bug fix starts without a bug ticket. If a defect is discovered informally, the
first action is to create a bug ticket from this template, then assign it to the
developer.

## Header

- **Bug ID:** BUG-XXX
- **Title:** Short, explicit failure summary
- **Status:** New / Assigned / In progress / Ready for adversarial review / Ready for QA retest / Closed / Reopened
- **Severity:** Critical / High / Medium / Low
- **Priority:** P0 / P1 / P2 / P3
- **Detected by:** QA / Adversarial review / Developer / Product / User validation
- **Detected date:** YYYY-MM-DD
- **Related user story:** US-XXX
- **Related epic:** EPIC-XXX
- **Branch:** `fix/BUG-XXX-short-title`
- **Owner:** Frontend developer / Backend developer / Voice runtime developer / Cross-functional

## Problem Statement

Describe the defect in one or two sentences. State the observable failure, not
the assumed technical cause.

## Environment

- **Environment:** local / test / staging / pilot / production
- **Channel:** web voice / phone / text fallback / Genesys handoff / backend-only
- **Browser/device:** if relevant
- **Provider configuration:** STT / TTS / LLM / BSS / Genesys sandbox details when relevant
- **Build or commit:** commit SHA or branch state
- **Correlation ID:** if available

## Reproduction Steps

1. Given ...
2. When ...
3. Then ...

## Expected Result

Describe the expected product-observable behavior.

## Actual Result

Describe what happened instead.

## Evidence

- Logs:
- Screenshot or recording:
- API response:
- Test output:
- Trace/span link:
- Metrics or latency sample:

## Impact

Explain who is affected and how:

- customer impact;
- advisor impact;
- operational impact;
- security/privacy impact;
- latency or SLO impact;
- pilot-readiness impact.

## Acceptance Criteria For Fix

- [ ] The defect no longer reproduces.
- [ ] A regression test covers the failure.
- [ ] Relevant OpenTelemetry traces, metrics and structured logs are present or
      explicitly not applicable.
- [ ] Adversarial code review is at least 90% satisfied.
- [ ] QA retest passes.
- [ ] Related documentation or backlog notes are updated if behavior changed.

## Developer Notes

Developer fills this during resolution:

- root cause:
- files changed:
- tests added/updated:
- OpenTelemetry added/updated:
- residual risk:

## QA Retest

- **Retested by:**
- **Retest date:**
- **Scenarios rerun:**
- **Result:** Passed / Failed / Reopened
- **Retest evidence:**

## Closure

- **Closed by:**
- **Closed date:**
- **Closure reason:** Fixed / Duplicate / Not reproducible / Accepted risk / Out of scope
