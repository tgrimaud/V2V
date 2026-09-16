# Adversarial code review — TASK-BE-048 (billing escalation `reason` telemetry)

- **Branch:** `task/TASK-BE-048-billing-telemetry-reason`
- **Reviewed:** 2026-09-16
- **Scope:** optional `reason` on `BillingExplanation`, set by `BillingExplanationService`; consistent
  `reason` tag on `voice_support.slice` + `[TELEMETRY]` log via `BackendTelemetry`; billing adapter
  propagation. Follow-up to the BUG-020 review Info finding.

## Verdict

Proceed.

## Satisfaction Score

Score: 96/100
QA gate: Pass

## Blocking Findings

None.

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | `reason` is a nullable `String`, not an enum | `BillingExplanation.reason` | Acceptable — mirrors the existing `escalationCode` String convention; values are centralised as `REASON_*` constants. A `NotEnoughDataReason` enum could be a later tightening. |
| Info | PARTIAL (answerable) turns carry `reason=n/a`, not a symmetric `partial_residual` | `fromReadiness` PARTIAL branch | Out of scope — the finding was about escalations. Could add for symmetry if Ops wants residual-band drill-down on answered turns. |
| Info | Every slice metric now carries a constant `reason=n/a` tag | `BackendTelemetry.record` | Intended (keeps tag keys consistent across `voice_support.slice`); worth a one-line mention in the observability doc so dashboards know the new dimension exists. |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| `outcome` stays stable; `reason` distinguishes the 3 not-enough-data cases | Yes | Service sets `insufficient_history` / `evidence_unfetchable` / gate `no_usable_lines` \| `residual_too_high`; adapter records both tags |
| Other slices keep recording; existing lookups stay green | Yes | `time()` + 4-arg `recordLatency()` route through `record(...,REASON_NONE,...)`; Micrometer `find().tag()` is a subset match; full suite green |
| Unit tests per situation; non-escalation records `reason=n/a` | Yes | Adapter: `records_the_escalation_reason...` + `...tagged_by_outcome` (`reason=n/a`); service: 3 `reason()` assertions |
| No PII in the new dimension | Yes | `reason` is a bounded set of technical codes; no account/amount |

## Test Evidence

- Developer tests: +1 adapter telemetry test (reason tag), +3 service `reason()` assertions, updated
  the existing outcome-tag test to also assert `reason=n/a`.
- Missing tests: none blocking. (`residual_too_high` is covered indirectly by the confidence-gate
  tests; the service maps it deterministically via `reasonOf`.)
- Full backend suite: 583 tests, 0 failures, 0 errors.

## Observability And Latency

- Slice: `billing` (`voice_support.slice`), now tagged `slice/channel/provider/outcome/reason`.
- Metrics: bounded cardinality — `reason ∈ {n/a, insufficient_history, evidence_unfetchable,
  no_usable_lines, residual_too_high}`. p50/p95/p99 reporting unchanged; drill-down by reason enabled.
- Structured logs: `[TELEMETRY]` gains `reason={}`; correlation id preserved.
- Risk: none — no unbounded/user-supplied value can reach the tag.

## Security And Privacy

- Sensitive data risk: none. `reason` codes are technical; no transcript, account or amount.
- Consistency reinforces the BUG-020 outcome (evidence-unfetchable/ownership-drop now visible without
  exposing why an invoice was dropped).

## Required Developer Actions

None. (Optional: note the `reason` dimension in the observability doc — Info.)

## Residual Risk If Accepted

- `reason` typed as String rather than enum (Low); symmetric PARTIAL reason not emitted (Info).
