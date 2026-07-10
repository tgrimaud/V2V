# QA Functional And Latency Report - STT Validation (TASK-STT-004)

**Ticket:** TASK-STT-004 - Produce the STT QA report and Gherkin scenarios
**Related stories:** US-019, US-036
**Related tasks:** TASK-STT-001, TASK-STT-002, TASK-STT-003
**Branch:** `task/TASK-STT-004-stt-qa-report`
**Run date:** 2026-07-09
**Provider under test:** `fixture-stt` (deterministic `FixtureSttProvider`; real engine not yet selected)

> **Update 2026-07-10 (superseding note):** this report is the 2026-07-09 snapshot taken
> *before* the real engine was connected. The "no real STT provider" blocker below is
> now resolved — **Gradium (TASK-STT-008) is validated live end to end** (real transcripts
> + latency, `docs/qa/web-voice-qa-report.md`) and the 5 controlled fixtures now carry
> **real PCM16 audio** (TASK-STT-007) with a first live per-category run
> (`docs/qa/stt-transcription-quality.md`). The remaining STT-quality gap is WER scoring
> normalization (RF-008 → TASK-STT-011), not the absence of a provider or of real audio.

## Executive Summary

- **Overall readiness:** **Conditional GO** for the STT *validation slice* (harness,
  fixture coverage, telemetry and safe-failure behaviour are proven). **NO-GO** for
  declaring the *product STT capability* pilot-ready, because all numbers come from
  a deterministic fixture provider, not a real STT engine.
- **Main blockers:** No real STT provider is connected (RF-003, gated). Statistical
  significance is limited to one sample per category (RF-005, ticketed as
  TASK-STT-007).
- **Residual risks:** Fixture-provider quality is not representative of real
  accented/noisy speech; the ingress span is a scaffold analog (RF-002, gated by
  US-019/US-036).

## Scope Tested

- **Epics / stories:** TASK-STT-001/002/003 evidence consolidated; acceptance for
  US-019 and US-036 is only partially exercisable (labo path, no real channel).
- **Channels:** none real yet — controlled audio fixtures only.
- **Providers / fakes:** `fixture-stt` (`.txt` sidecar = simulated engine output).
- **Environment:** local, warm run, no cache/connection dependencies.
- **Automation:** Python **Behave** (`voice-agent/features/stt_validation.feature`)
  + developer `unittest` suite.

## Functional Results

| Area | Status | Evidence | Notes |
|---|---|---|---|
| Transcript quality reviewed per category | PASS | `docs/qa/stt-transcription-quality.md`; Behave "Each declared fixture category produces a reviewed transcript outcome" | short/long WER 0.0; noisy/accented WER 0.1 (≥ 0.8 threshold) |
| Missing categories reported explicitly | PASS | `missing_categories: []`; Behave "Declared fixture coverage is reported explicitly" | 5/5 declared categories present |
| Silence / unusable handled safely | PASS | `silence-clip` outcome `failed`, empty transcript; Behave "Silence is handled safely without an invented transcript" | no invented transcript |
| STT slice latency observable / percentile-ready | PASS | `LatencyReport` p50/p95/p99; Behave "STT latency is isolated and percentile-ready" | fixture-provider timings only |
| Failure observable without leaking sensitive data | PASS | sanitized reason + `error_code`; Behave "STT failure is observable without leaking a filesystem path" | `<redacted-path>`, stable code |
| STT provider replaceable | PASS (by design) | `SttProvider` protocol; manifest/harness unchanged when a real adapter is added | not exercised with a real engine |

## Latency Results

Source: `python3 -m stt_validation.quality_cli fixtures/manifest.json` (STT slice =
`stt.request.duration_ms`). Fixture provider, not a real engine — values prove the
measurement path, not production latency.

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| STT (`stt_request_ms`) | 0.026 ms | 0.034 ms | 0.034 ms | 5 | Warm | Deterministic fixture provider |
| Channel ingress | n/a | n/a | n/a | — | — | Scaffold analog only (RF-002); real ingress in US-019/US-036 |
| Backend / TTS / egress | n/a | n/a | n/a | — | — | Out of STT-validation scope |

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| STT quality harness (`quality.py`) | Good | WER + threshold gate + missing/failed category reporting | Re-run against a real provider (RF-003) |
| STT runner + telemetry (`runner.py`, `telemetry.py`) | Good | Isolated STT span, percentile-ready metric, sanitized failure | Confirm span mapping on real adapter |
| Fixture set (`fixtures/`) | Adequate for scaffold | 1 sample per category | Grow samples (TASK-STT-007) |
| Sanitization (`sanitization.py`) | Good | Path redaction, stable error codes | Broaden redaction beyond path tokens (TASK-STT-005) |

## Defects And Gaps

No **blocking** defects for the current fixture set: all declared categories pass
and no transcript is invented for silence. No new bug tickets are required for this
run. The bug-ticket process is documented below for future failing runs.

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Medium | Quality reflects `fixture-stt`, not a real STT engine (RF-003) | Numbers not representative of production | Architecture (provider choice) |
| Low | One sample per category → p95/p99 not statistically meaningful (RF-005 / TASK-STT-007) | Weak latency/quality confidence | QA |
| Low | Ingress span is a scaffold analog (RF-002) | Ingress latency not truly measured | Gated by US-019/US-036 |
| Low | Sanitization only redacts path-bearing tokens (RF-001 / TASK-STT-005) | Bare sensitive id could leak with a real adapter | Backend/voice runtime |

### Bug ticket process (no blocking defect this run)

If a future run reports `failed_categories` or `missing_categories`, QA MUST open a
ticket from `product-backlog/templates/bug-ticket-template.md` (`BUG-XXX`), attach
the correlation id + sanitized failure evidence, set severity/priority, and fix it
on a `fix/BUG-XXX-...` branch through the adversarial-review + QA-retest loop before
STT is declared ready.

## Open Questions

- **Product:** What transcript-quality threshold is acceptable for the pilot
  (current gate = 0.8)?
- **Architecture:** Which real STT provider is the first validation target? This
  unblocks RF-003 and RF-002.
- **Technical:** How many samples per category are required before p95/p99 are
  meaningful (TASK-STT-007)?

## Recommendation

- **Go / No-go:** **GO to close the STT-validation labo slice** (TASK-STT-001/002/003
  evidence is complete, automated and safe-failing). **NO-GO to declare the product
  STT capability pilot-ready** until a real provider is connected and the manifest is
  re-run.
- **Required fixes before pilot:**
  1. ~~Select and connect a real STT provider adapter~~ **Provider selected
     (Gradium, DEC-005) and a fresh `GradiumSttProvider` is implemented behind the
     `SttProvider` protocol (TASK-STT-008).** Still pending: a live run with a real
     `GRADIUM_API_KEY` + real audio to record real quality/latency, which keeps
     RF-003 open until executed.
  2. Grow the fixture set to statistically meaningful sample sizes (TASK-STT-007).
  3. Optionally harden sanitization for non-path sensitive tokens (TASK-STT-005).

## Reproduce

```bash
cd voice-agent
python3 -m venv .venv && ./.venv/bin/pip install behave
./.venv/bin/behave features/stt_validation.feature
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m stt_validation.quality_cli fixtures/manifest.json

# real Gradium engine (TASK-STT-008) — needs a valid key and real audio:
export GRADIUM_API_KEY=...
python3 -m stt_validation.quality_cli fixtures/manifest.json --provider gradium
```
