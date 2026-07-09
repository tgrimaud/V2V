# Adversarial Review Findings Register

Central log of **non-blocking** findings raised by `adversarial-code-review`
across delivered tickets. Blocking findings are fixed before merge and are not
tracked here; QA defects go through the bug-ticket process instead
(`product-backlog/templates/bug-ticket-template.md`).

Each finding records: source ticket, severity, the accepted residual risk, and
either a follow-up ticket (when the fix is actionable now) or the dependency
that gates it.

## Status legend

- **Open** — accepted residual risk, not yet addressed.
- **Ticketed** — a follow-up ticket exists to fix it.
- **Gated** — cannot be actioned until a dependency is resolved (linked).
- **Closed** — resolved; keep the row for history.

## Findings

| ID | Source | Severity | Finding | Residual risk accepted | Disposition | Status |
|---|---|---|---|---|---|---|
| RF-001 | TASK-STT-003 | Low | Failure sanitization (`sanitization.py`) only redacts tokens containing a path separator; a bare sensitive identifier (e.g. `secret-customer.wav` with no slash) would not be redacted. | Safe today because `FixtureSttProvider` always emits full paths. Risk appears only with a real provider adapter. | Follow-up ticket **TASK-STT-005** | Ticketed |
| RF-002 | TASK-STT-003 | Low | `stt.audio.accept` span uses `path.exists()` as a channel-ingress analog, not a real ingress measurement. | Acceptable for the scaffold; the STT slice itself is correctly isolated. | Superseded by real ingress in **US-019** / **US-036** | Gated |
| RF-003 | TASK-STT-002 | Medium | Transcription quality numbers reflect the deterministic `FixtureSttProvider`, not a real STT engine. | Explicitly disclosed in `docs/qa/stt-transcription-quality.md`; harness re-runs unchanged against a real provider. | Provider selected: **Gradium** (DEC-005). Follow-up ticket **TASK-STT-008** connects it (fresh impl) and re-runs the manifest. | Ticketed |
| RF-004 | TASK-STT-002 | Low | Silence/unusable audio maps to outcome `failed` (`invalid_fixture`) rather than a dedicated `UNAVAILABLE` outcome. AC allows either. | Behaviour is correct (no invented transcript); only the outcome label is coarse. | Follow-up ticket **TASK-STT-006** | Ticketed |
| RF-005 | TASK-STT-002 | Low | One fixture per category; p95/p99 and per-category quality are not yet statistically meaningful. | Sprint open question already flags required sample size. | Follow-up ticket **TASK-STT-007** | Ticketed |

## Process

Non-blocking findings from every adversarial review **must** be appended here
before a branch is declared merge-ready (see `docs/operations/development-workflow.md`).
Actionable findings get a follow-up ticket in `product-backlog/tasks/`; gated
findings link the blocking dependency.
