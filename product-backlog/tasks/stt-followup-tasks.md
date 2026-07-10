# STT Follow-up Technical Tasks

Follow-up tickets created from non-blocking adversarial-review findings recorded
in `product-backlog/review-findings.md`. They are not part of the core STT
validation sprint scope and should be scheduled deliberately.

## TASK-STT-005 - Redact Bare Sensitive Identifiers In Failure Sanitization

**Parent:** EPIC-010
**Related finding:** RF-001 (TASK-STT-003)
**Classification:** V1 pilot gate
**Status:** Draft
**Priority:** Medium
**Branch:** `task/TASK-STT-005-redact-bare-identifiers`

### Objective

Ensure sanitized failure reasons never leak sensitive identifiers even when the
STT provider surfaces a bare filename or id without a path separator.

### Scope

- Extend `stt_validation/sanitization.py` to redact filename/identifier-like
  tokens (e.g. `*.wav`, `*.mp3`, customer/id patterns), not only tokens with a
  path separator.
- Preserve the stable `error_code` and the length cap.
- Add tests covering bare-filename and id-like tokens.

### Acceptance Criteria

```gherkin
Scenario: A bare sensitive identifier is redacted
  Given an STT failure reason contains a bare filename or identifier
  When the reason is sanitized
  Then the identifier is replaced by a redaction marker
  And the stable error_code is still exposed
```

### Required Evidence

- Unit tests for bare-token redaction.
- Updated `docs/observability/stt-validation-telemetry.md` sanitization section.

---

## TASK-STT-006 - Add A Dedicated UNAVAILABLE STT Outcome

**Parent:** EPIC-010
**Related finding:** RF-004 (TASK-STT-002)
**Classification:** V1 pilot gate
**Status:** Draft
**Priority:** Low
**Branch:** `task/TASK-STT-006-unavailable-outcome`

### Objective

Distinguish "no usable speech detected" (silence/unusable audio) from a genuine
processing error, so QA and telemetry can tell them apart.

### Scope

- Introduce `SttOutcome.UNAVAILABLE` and map silence/no-speech to it.
- Audit all four telemetry surfaces and the quality harness for the new value.
- Keep "no invented transcript" behaviour intact.

### Acceptance Criteria

```gherkin
Scenario: Silence is reported as unavailable, not failed
  Given the audio fixture contains silence
  When the STT validation path processes it
  Then the outcome is UNAVAILABLE
  And no transcript is invented
```

### Required Evidence

- Unit tests for the new outcome.
- Updated telemetry and quality docs.

---

## TASK-STT-007 - Expand The STT Fixture Set With Multiple Samples Per Category

**Parent:** EPIC-010
**Related finding:** RF-005 (TASK-STT-002)
**Classification:** V1 pilot gate
**Status:** Draft
**Priority:** Medium
**Branch:** `task/TASK-STT-007-expand-fixture-samples`

### Objective

Make per-category quality and p95/p99 latency statistically meaningful by adding
multiple fixtures per category.

### Scope

- Add several fixtures per category (short, long, noisy, silence, accented).
- Extend the manifest and QA report to summarise quality per category.
- Define the minimum sample size before p95/p99 is reported as meaningful.

### Acceptance Criteria

```gherkin
Scenario: Category quality is reported over multiple samples
  Given each category has multiple fixtures
  When the quality run completes
  Then per-category quality and latency percentiles are reported
  And categories below the required sample size are flagged as not yet significant
```

### Required Evidence

- Expanded fixture set and manifest.
- Updated `docs/qa/stt-transcription-quality.md` with per-category summaries.

---

## TASK-STT-008 - Connect The Gradium STT Provider (Fresh Implementation)

**Parent:** EPIC-006, EPIC-010
**Related finding:** RF-003 (TASK-STT-002)
**Related stories:** US-019, US-036
**Related decision:** DEC-005 (Gradium + Pipecat reference voice path; ADR-0002)
**Classification:** V1 pilot gate
**Status:** Done (STT sprint scope) — live Gradium validated end to end via the web path; per-category fixture matrix re-pointed to TASK-STT-007
**Priority:** High
**Branch:** `task/TASK-STT-008-gradium-stt-provider`

### Objective

Replace the deterministic `FixtureSttProvider` with a real Gradium STT provider so
transcription quality and STT latency reflect the selected engine, not a fixture
sidecar. This makes RF-003 actionable now that the provider is chosen.

### Constraints

- **Fresh implementation.** Do not restore or port the legacy
  `voice-agent/agent/gradium_stt.py` from `main`/history. Only the functional
  contract may be reused as a target spec: Gradium ASR REST endpoint,
  `x-api-key` auth, audio input formats (`pcm_16000` for web/PCM, `ulaw_8000` for
  telephony), streaming line-delimited `type: text` tokens joined into a
  transcript.
- Implement against the existing `SttProvider` protocol
  (`voice-agent/stt_validation/providers.py`) so the manifest, quality harness,
  telemetry and Behave scenarios stay unchanged.

### Scope

- New `GradiumSttProvider` implementing `SttProvider` (`name`, `transcribe`).
- Configuration via `GRADIUM_API_KEY` (and language/format inputs); no secret in
  code, logs or telemetry.
- Map Gradium HTTP/credit/auth/unreachable failures to stable sanitized
  `error_code`s consistent with `sanitization.py`.
- Emit the same OpenTelemetry spans/metrics as the fixture path so the STT slice
  stays isolated and percentile-ready.
- Provider selection is configurable (fixture vs Gradium) so QA can run either
  without code changes.
- Re-run `fixtures/manifest.json` against Gradium and record real quality/latency.

### Acceptance Criteria

```gherkin
Scenario: Real Gradium transcription flows through the same harness
  Given the Gradium STT provider is configured with a valid API key
  When QA runs the STT validation harness with the Gradium provider
  Then each usable fixture produces a real transcript and quality score
  And the STT slice latency is reported for p50, p95 and p99
```

```gherkin
Scenario: Gradium failure stays observable and sanitized
  Given the Gradium STT provider fails (auth, credits, timeout or unreachable)
  When the failure is recorded
  Then a stable error_code and a sanitized reason are exposed
  And no API key, raw audio or filesystem path is logged
```

### Required Evidence

- Unit tests for `GradiumSttProvider` with a fake HTTP transport (no live call).
- Updated `docs/qa/stt-transcription-quality.md` and `docs/qa/stt-qa-report.md`
  with real Gradium quality and latency numbers.
- Behave scenarios pass against the configured provider.
- Confirmation that no secret is present in logs or telemetry.

### Delivery Evidence (implementation slice)

- `voice-agent/stt_validation/gradium_provider.py`: fresh `GradiumSttProvider`
  implementing `SttProvider`, injectable HTTP transport (stdlib `urllib` default,
  no new dependency), stable error mapping (auth/credits/timeout/unreachable/
  no-speech), API key never placed in an exception, log or telemetry attribute.
- `voice-agent/stt_validation/provider_factory.py` + `--provider {fixture,gradium}`
  on both CLIs: runtime provider selection with zero harness changes.
- `voice-agent/tests/test_gradium_provider.py`: 11 tests (success, auth, credits,
  no-speech, missing key, timeout→`stt_timeout`, no-key-in-telemetry, factory,
  PCM/u-law content-type) with a fake transport — no network. Full suite 28 tests
  passing; 5 Behave scenarios still green.
- No legacy code reused (`agent/gradium_stt.py` not restored).
- **Live smoke test (2026-07-09)** against `api.gradium.ai` with the real key:
  auth and connectivity confirmed (no 401). It surfaced a real bug — Gradium
  rejects the urllib default `application/x-www-form-urlencoded` and also
  `application/octet-stream`; the accepted Content-Type is `audio/pcm` for PCM
  (`audio/basic` for u-law). Fixed and locked with a regression test. A silence
  PCM buffer returns HTTP 200 with an empty transcript, correctly mapped to
  `failed` / "no speech" (no invented transcript).

### Live validation (done)

- **Live Gradium, real `GRADIUM_API_KEY`, end to end via the web path**
  (`docs/qa/web-voice-qa-report.md`, 2026-07-10): real transcripts and real STT
  latency (2296 ms injected `say` sample, 2694 ms human mic session, 1125 ms
  silence). Plus the 2026-07-09 smoke test (auth OK, `audio/pcm` content-type fix).
- This validates the real engine for the sprint's go/no-go decision.

### Remaining (not sprint-blocking, re-pointed)

- The per-category WER matrix over the 5 controlled fixtures still uses the fixture
  provider because those `.wav` are ASCII placeholders (19–33 bytes), not real
  audio — Gradium cannot transcribe them. A live per-category quality run needs
  real fixture audio, which is **TASK-STT-007**. RF-003's per-category matrix is
  re-pointed there.

### Notes

- RF-003 is **partially addressed**: the real engine is validated live (transcripts
  + latency); only the controlled per-category matrix remains, gated by real fixture
  audio (TASK-STT-007).
- RF-002 (channel ingress span is a scaffold analog) stays gated by US-019/US-036,
  which introduce the real channel ingress path.

---

## TASK-STT-009 - Detect And Instrument End-Of-Turn For The Voice Journey

**Parent:** EPIC-006, EPIC-010
**Related story:** US-036 (the `end_of_turn` slice it reports on)
**Related decision:** DEC-010 (per-step latency traces before any SLO claim)
**Classification:** V1 pilot gate
**Status:** Draft
**Priority:** Medium
**Branch:** `task/TASK-STT-009-end-of-turn-detection`

### Objective

Own the one voice-journey slice that US-036 reports with **no backing ticket**:
`end_of_turn`. Detect when the customer has finished speaking (VAD / silence
window / end-of-speech signal) and emit an OpenTelemetry span for that slice so
`PipelineTimingReport` measures it instead of flagging it as a gap.

### Context

US-036 (`docs/observability/voice-journey-timing.md`) reports six canonical
slices. `channel_ingress` and `stt` are instrumented; `backend_first_token`,
`tts_first_audio` and `channel_egress` are owned by TASK-WEB-003 / TASK-WEB-002.
`end_of_turn` is the only slice whose "not measured" note points to no ticket —
this task closes that traceability gap.

### Scope

- Detect end-of-turn on the captured web voice stream (silence/VAD threshold or an
  explicit stop signal), configurable and replaceable.
- Emit an `end.of.turn` (or equivalently named) OpenTelemetry span with the turn
  correlation id, so it feeds `PipelineTimingReport`.
- Register the span name in `stt_validation/pipeline_timing.py`
  (`_SLICE_SPAN_NAMES[END_OF_TURN]`) so the slice reports p50/p95/p99 once emitted.
- Safe behaviour when no clear end-of-turn is detected (timeout, no invented turn
  boundary).

### Out Of Scope

- Barge-in / interruption during playback (US-021).
- Backend orchestration (TASK-WEB-003) and TTS (TASK-WEB-002).

### Acceptance Criteria

```gherkin
Scenario: End-of-turn is detected and measured as its own slice
  Given a customer finishes speaking on the web voice page
  When the voice runtime detects the end of the turn
  Then an end-of-turn span is recorded with the turn correlation id
  And US-036's pipeline timing report measures the end_of_turn slice with p50/p95/p99
```

### Required Evidence

- Unit tests for the end-of-turn detector and its span emission.
- `pipeline_timing.py` mapping updated so `end_of_turn` is no longer a gap.
- Updated `docs/observability/voice-journey-timing.md` slice table.

---

## TASK-STT-010 - Stream Partial STT Transcripts To Cut Perceived Latency

**Parent:** EPIC-006, EPIC-010
**Related stories:** US-036 (the `stt` slice latency), US-019 (web voice), US-018 (phone voice)
**Related finding:** RF-007 (chunked/streaming ingress client)
**Related decision:** DEC-005 (Pipecat streaming voice path; ADR-0002), DEC-010 (per-step latency before any SLO claim)
**Depends on:** TASK-STT-008 (Gradium provider)
**Pairs with:** TASK-WEB-004 (streaming TTS voice-out) — the two form the low-latency voice loop
**Classification:** V1 pilot gate
**Status:** Draft
**Priority:** High (latency-driven)
**Branch:** `task/TASK-STT-010-streaming-stt`

### Objective

Move the STT path from whole-utterance **batch** transcription to **streaming /
incremental** transcription, so partial transcripts arrive *while the customer is
still speaking* and the final transcript lands shortly after end-of-turn — instead
of a single call whose latency grows with the utterance length.

### Context (why this is needed)

Live Gradium QA (`docs/qa/web-voice-qa-report.md`) measured the STT slice in
**batch** mode: **2296 ms** for a 3.37 s utterance, **2694 ms** for a 4.3 s mic
recording, **1125 ms** for 1 s of silence — i.e. latency scales with audio
duration because the whole clip is processed after upload. Streaming is the primary
lever to cut this perceived latency. Gradium already exposes line-delimited
`type: text` streaming tokens (the TASK-STT-008 target spec), and RF-007 notes the
current ingress reads a fixed `Content-Length` body and would need chunked/streaming
transport.

### Scope

- A streaming `SttProvider` variant emitting **partial** and **final** results over
  Gradium's streaming ASR; keep the batch provider for fixtures/offline dev.
- Streaming ingress transport (chunked or WebSocket) replacing/augmenting the fixed
  `Content-Length` read — **closes RF-007**.
- Telemetry: measure **time-to-first-partial** and **time-to-final** separately so
  US-036 can report both for the `stt` slice.
- Safe failure + no secret leak (reuse `sanitization.py`).

### Out Of Scope

- Streaming voice-out / TTS (TASK-WEB-004).
- End-of-turn detection itself (TASK-STT-009), though this task consumes it.

### Acceptance Criteria

```gherkin
Scenario: Partial transcripts stream during speech
  Given a customer is speaking on the web voice page
  When audio streams to the STT provider
  Then partial transcripts are emitted before the customer stops speaking
  And a final transcript is produced shortly after end-of-turn
  And time-to-first-partial and time-to-final are observable via OpenTelemetry
```

### Required Evidence

- Unit tests with a fake streaming transport (partial + final, no network).
- Latency numbers (time-to-first-partial vs time-to-final) recorded in the QA docs,
  compared against the batch baseline.
- Behave scenario for the streaming outcome.
- RF-007 moved to Closed once the streaming transport lands.
