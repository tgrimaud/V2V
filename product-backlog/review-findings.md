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
| RF-001 | TASK-STT-003 | Low | Failure sanitization (`sanitization.py`) only redacts tokens containing a path separator; a bare sensitive identifier (e.g. `secret-customer.wav` with no slash) would not be redacted. | Safe today because `FixtureSttProvider` always emits full paths. Risk appears only with a real provider adapter. | **Resolved (TASK-STT-005, 2026-07-10):** `_redact_token` now also redacts bare filenames (`<redacted-file>`) and identifier-like tokens (`<redacted-id>`: UUID, secret prefixes, ≥7-digit runs, mixed ids); words/dates preserved; `error_code` + 160-char cap kept. Dedicated `test_sanitization.py`. | Closed |
| RF-002 | TASK-STT-003 | Low | `stt.audio.accept` span uses `path.exists()` as a channel-ingress analog, not a real ingress measurement. | Acceptable for the scaffold; the STT slice itself is correctly isolated. | **TASK-WEB-001** adds the real `web.voice.ingress` span (received audio bytes) for the web path. Remaining: phone/Genesys ingress and per-slice reporting via **US-036**. | Ticketed |
| RF-003 | TASK-STT-002 | Medium | Transcription quality numbers reflect the deterministic `FixtureSttProvider`, not a real STT engine. | Explicitly disclosed in `docs/qa/stt-transcription-quality.md`; harness re-runs unchanged against a real provider. | **Resolved (TASK-STT-008 + TASK-STT-007, 2026-07-10):** Gradium validated live end to end (`docs/qa/web-voice-qa-report.md`) and a full **live per-category Gradium run** over the 22-fixture set is recorded with normalized WER (`docs/qa/stt-transcription-quality.md`). Residual quality caveat (synthetic proxies → real human recordings) tracked as an open risk, not a scaffold-vs-engine gap. | Closed |
| RF-004 | TASK-STT-002 | Low | Silence/unusable audio maps to outcome `failed` (`invalid_fixture`) rather than a dedicated `UNAVAILABLE` outcome. AC allows either. | Behaviour is correct (no invented transcript); only the outcome label is coarse. | Follow-up ticket **TASK-STT-006** | Ticketed |
| RF-005 | TASK-STT-002 | Low | One fixture per category; p95/p99 and per-category quality are not yet statistically meaningful. | Sprint open question already flags required sample size. | **Resolved (TASK-STT-007, 2026-07-10):** 5 samples per usable category + per-category aggregation; `MIN_SAMPLES_FOR_PERCENTILES=5` flags underpowered categories. Residual (documented open risk): real human recordings still needed for representative `short`/`noisy` and stable p95/p99. | Closed |
| RF-006 | TASK-WEB-001 | Low | The web ingress endpoint (`POST /api/voice/stt`) has no authentication or identity gate; anyone reaching the host can post audio. | Ingress is a local pilot/dev server; the web voice identity model is explicitly deferred, and the backend (not the channel) owns billing-data exposure. | Gated by **OQ-001** (web voice identity) and **TASK-WEB-003** (backend orchestration / identity confidence). | Gated |
| RF-007 | TASK-WEB-001 | Low | `server._read_body` reads exactly `Content-Length` bytes and does not support chunked `Transfer-Encoding`. | Browser `fetch` with an `ArrayBuffer` body always sets `Content-Length`, which is the only client for this slice. | Follow-up ticket **TASK-STT-010** (streaming STT) adds the chunked/streaming ingress transport that closes this. | Ticketed |
| RF-008 | TASK-STT-002 / TASK-STT-007 | Medium | `word_error_rate` compares raw whitespace-split tokens with no normalization. Against a real engine this over-penalizes: `Bonjour` vs `Bonjour.` scores WER 1.0; ASCII references (`telephone`) vs accented output (`téléphone`) count as errors. The `ready` quality gate is therefore not usable against Gradium. | Surfaced by the first live Gradium per-category run (2026-07-10, `docs/qa/stt-transcription-quality.md`): 3/4 usable categories "failed" almost entirely on punctuation/case/accent artifacts, not real STT errors. | **Resolved (TASK-STT-011, 2026-07-10):** `normalize_transcript` folds case/punctuation/accents before WER. Live re-run: `short` WER 1.00→0.00, `long` 0.083, `accented` 0.182 pass; only `noisy` (0.40) fails on a genuine error (→ TASK-STT-007). Gate now trustworthy; threshold kept at 0.8. | Closed |
| RF-009 | TASK-STT-005 | Low | The sanitization identifier heuristics over-redact non-sensitive technical tokens: `pcm_16000` → `<redacted-id>`, `audio/pcm` → `<redacted-path>`, `line 12345678` → `<redacted-id>`. Diagnostic value is reduced. | Safety-first trade-off: over-redaction never leaks data, it only makes some error reasons less specific. Real sensitive tokens are still caught. | Optional follow-up: allowlist known technical tokens (format names, content-types) evaluated before the id heuristics. No ticket yet — raise if error diagnostics prove too opaque in practice. | Open |
| RF-010 | TASK-STT-007 | Low | Fixture references have two sources of truth kept in sync by hand: `generate_fixtures.py` `SPOKEN_SPECS[].text` and `manifest.json` `reference`. A silent divergence would break the fixture-provider WER (which assumes sidecar == reference). | Currently consistent (generator writes the sidecar from the same text); risk is future edits touching only one side. | Optional follow-up: add a test asserting each usable manifest `reference` equals its generated `.txt` sidecar, or derive the manifest from the specs. No ticket yet. | Open |
| RF-011 | TASK-STT-007 | Low | `all_categories_significant` includes the `silence` category (n=2, no WER), so it is effectively always `false`; and `MIN_SAMPLES_FOR_PERCENTILES=5` marks a category "significant" though 5 samples give a statistically weak p95 (nearest-rank p95 ≈ max). | Documented as a reporting floor, not a guarantee (`stt-transcription-quality.md` "Statistical significance"). | Optional follow-up: exclude unusable categories from the significance aggregate and/or raise the floor once real recordings exist. No ticket yet. | Open |

## Process

Non-blocking findings from every adversarial review **must** be appended here
before a branch is declared merge-ready (see `docs/operations/development-workflow.md`).
Actionable findings get a follow-up ticket in `product-backlog/tasks/`; gated
findings link the blocking dependency.
