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
| RF-002 | TASK-STT-003 | Low | `stt.audio.accept` span uses `path.exists()` as a channel-ingress analog, not a real ingress measurement. | Acceptable for the scaffold; the STT slice itself is correctly isolated. | **TASK-WEB-001** adds the real `web.voice.ingress` span (received audio bytes) for the web path. Remaining: phone/Genesys ingress and per-slice reporting via **US-036**. | Ticketed |
| RF-003 | TASK-STT-002 | Medium | Transcription quality numbers reflect the deterministic `FixtureSttProvider`, not a real STT engine. | Explicitly disclosed in `docs/qa/stt-transcription-quality.md`; harness re-runs unchanged against a real provider. | **Partially addressed:** Gradium (DEC-005, **TASK-STT-008**) validated live end to end (real transcripts + latency, `docs/qa/web-voice-qa-report.md`). The 5 controlled fixtures are now **real audio** (TASK-STT-007, 2026-07-10), so the per-category WER matrix is no longer blocked by placeholders — it now only needs a `GRADIUM_API_KEY` (`quality_cli --provider gradium`). | Ticketed |
| RF-004 | TASK-STT-002 | Low | Silence/unusable audio maps to outcome `failed` (`invalid_fixture`) rather than a dedicated `UNAVAILABLE` outcome. AC allows either. | Behaviour is correct (no invented transcript); only the outcome label is coarse. | Follow-up ticket **TASK-STT-006** | Ticketed |
| RF-005 | TASK-STT-002 | Low | One fixture per category; p95/p99 and per-category quality are not yet statistically meaningful. | Sprint open question already flags required sample size. | Follow-up ticket **TASK-STT-007** (real single-sample audio now committed; multiple samples per category still pending). | Ticketed |
| RF-006 | TASK-WEB-001 | Low | The web ingress endpoint (`POST /api/voice/stt`) has no authentication or identity gate; anyone reaching the host can post audio. | Ingress is a local pilot/dev server; the web voice identity model is explicitly deferred, and the backend (not the channel) owns billing-data exposure. | Gated by **OQ-001** (web voice identity) and **TASK-WEB-003** (backend orchestration / identity confidence). | Gated |
| RF-007 | TASK-WEB-001 | Low | `server._read_body` reads exactly `Content-Length` bytes and does not support chunked `Transfer-Encoding`. | Browser `fetch` with an `ArrayBuffer` body always sets `Content-Length`, which is the only client for this slice. | Follow-up ticket **TASK-STT-010** (streaming STT) adds the chunked/streaming ingress transport that closes this. | Ticketed |
| RF-008 | TASK-STT-002 / TASK-STT-007 | Medium | `word_error_rate` compares raw whitespace-split tokens with no normalization. Against a real engine this over-penalizes: `Bonjour` vs `Bonjour.` scores WER 1.0; ASCII references (`telephone`) vs accented output (`téléphone`) count as errors. The `ready` quality gate is therefore not usable against Gradium. | Surfaced by the first live Gradium per-category run (2026-07-10, `docs/qa/stt-transcription-quality.md`): 3/4 usable categories "failed" almost entirely on punctuation/case/accent artifacts, not real STT errors. | Follow-up ticket **TASK-STT-011** (normalize case/punctuation/accents before WER). | Ticketed |

## Process

Non-blocking findings from every adversarial review **must** be appended here
before a branch is declared merge-ready (see `docs/operations/development-workflow.md`).
Actionable findings get a follow-up ticket in `product-backlog/tasks/`; gated
findings link the blocking dependency.
