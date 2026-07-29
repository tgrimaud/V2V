# STT Follow-up Technical Tasks

Follow-up tickets created from non-blocking adversarial-review findings recorded
in `product-backlog/review-findings.md`. They were out of the Sprint 1 (STT
validation) scope and have now been scheduled: **TASK-STT-005/006/007/009/011 are
in Sprint 2 (STT hardening)** — see `sprints/sprint-2-stt-hardening.md`.
**TASK-STT-010 (streaming STT) is deferred to Sprint 6** (latency optimization),
where it is built alongside streaming TTS (TASK-WEB-004).

## TASK-STT-005 - Redact Bare Sensitive Identifiers In Failure Sanitization

**Parent:** EPIC-010
**Related finding:** RF-001 (TASK-STT-003)
**Classification:** V1 pilot gate
**Status:** Done — Sprint 2 (STT hardening)
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

### Delivery Evidence (2026-07-10)

- `voice-agent/stt_validation/sanitization.py`: `_redact_token` now, in addition to
  path-separator tokens (`<redacted-path>`), redacts **bare filenames** with a
  media/data extension (`<redacted-file>`) and **identifier-like tokens**
  (`<redacted-id>`): UUIDs, secret-prefixed tokens (`gsk_/sk_/bearer_…`), long digit
  runs (≥ 7 digits), and mixed letter+digit ids. Surrounding punctuation is stripped
  before classification; the stable `error_code` and the 160-char cap are preserved.
- Plain words, short numbers (`HTTP 401`) and dates (`2026-07-10`) stay readable so
  the reason remains diagnostic (guarded by tests).
- `voice-agent/tests/test_sanitization.py`: new dedicated suite (13 tests) covering
  reason-code mapping, path/filename/UUID/secret/digit-run/mixed-id redaction,
  preservation of words/dates/no-speech messages, and the length cap. Full suite
  **72 unit tests + 8 Behave scenarios green**.
- **Closes RF-001.**

---

## TASK-STT-006 - Add A Dedicated UNAVAILABLE STT Outcome

**Parent:** EPIC-010
**Related finding:** RF-004 (TASK-STT-002)
**Classification:** V1 pilot gate
**Status:** ✅ Done — Sprint 2 (STT hardening), 2026-07-13
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

### Delivery Notes (2026-07-13)

- `SttOutcome.UNAVAILABLE` added; providers raise a provider-agnostic
  `NoSpeechDetectedError` on empty/no-speech transcripts (fixture + Gradium),
  so the runner maps a single exception to the outcome (no message matching).
- Runner emits a dedicated `stt.unavailable` event, an `info` log
  (`STT reported no usable speech`), `error_code=no_speech`, empty transcript;
  the `stt.request` span and `stt.validation.completed` carry `outcome=unavailable`.
- Quality harness reports the distinct note for unavailable unusable fixtures;
  behave scenario tightened to assert `unavailable` specifically.
- Evidence: 77 unit tests + 8 behave scenarios green; telemetry + QA docs updated.

---

## TASK-STT-007 - Expand The STT Fixture Set With Multiple Samples Per Category

**Parent:** EPIC-010
**Related finding:** RF-005 (TASK-STT-002), RF-003 (per-category matrix now audio-unblocked)
**Classification:** V1 pilot gate
**Status:** Done — Sprint 2 (STT hardening). Synthetic-proxy scope complete (5 samples/usable category, per-category aggregation, live Gradium run). **Real human recordings remain an explicit residual follow-up** (see Delivery Evidence).
**Priority:** Medium
**Branch:** `task/TASK-STT-007-expand-fixture-samples`

### Objective

Make per-category quality and p95/p99 latency statistically meaningful by adding
multiple fixtures per category — and, first, by replacing the placeholder audio
with real audio so the fixtures can actually run against a real engine.

### Scope

- ~~Replace the ASCII placeholder `.wav` fixtures with real audio~~ **Done**: the
  5 category fixtures are now raw PCM16 mono 16 kHz (`fixtures/generate_fixtures.py`).
- Add several fixtures per category (short, long, noisy, silence, accented).
- Prefer real human recordings for `noisy` and `accented` (current ones are `say`
  proxies: synthetic white noise, fr_CA voice).
- Extend the manifest and QA report to summarise quality per category.
- Define the minimum sample size before p95/p99 is reported as meaningful.
- Run `--provider gradium` over the manifest and record the per-category WER
  (now unblocked by real audio; needs a `GRADIUM_API_KEY`) — this closes RF-003.

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

### Delivery Evidence (2026-07-10)

- **Expanded fixture set:** `voice-agent/fixtures/generate_fixtures.py` now produces
  **22 raw PCM16 mono 16 kHz clips** — 5 samples per usable category (short, long,
  noisy, accented) with varied fr_FR/fr_CA voices and phrasings, plus 2 silence
  clips. Each clip is padded 300 ms lead-in / 200 ms lead-out so Gradium's
  endpointing does not clip the first word. Manifest rebuilt to 22 entries.
- **Per-category aggregation + significance rule:** `quality.py` now emits a
  `CategorySummary` per category (sample_count, usable/passed counts, mean/worst WER,
  latency percentiles, `significant`) plus `underpowered_categories()` and
  `all_categories_significant`. `MIN_SAMPLES_FOR_PERCENTILES = 5` is the documented
  reporting floor; categories below it (silence, n=2) are flagged not significant.
- **Tests:** +8 unit tests (`test_quality.py` category summaries; `test_manifest.py`
  expanded coverage + per-category counts). Full suite **59 unit tests + 8 Behave
  scenarios green**.
- **Live Gradium per-category run** (`docs/qa/stt-transcription-quality.md`,
  2026-07-10, normalized WER): accented 4/5 (mean 0.149), long 2/5 (0.191),
  short 2/5 (0.280), noisy 1/5 (0.383), silence 2/2 (not significant). Overall STT
  latency: p50 2165 ms, p95 3063 ms, p99 3150 ms over 22 samples. **Closes RF-003**
  (real-engine per-category matrix) and **RF-005** (multiple samples/category).
- **Honest residual (not sprint-blocking):** `say` still clips the first word of
  ultra-short 2–3 word clips (short WER inflated) and synthetic white noise is a harsh
  proxy (noisy genuinely degraded). **Real human recordings** — especially for
  `short` and `noisy` — are the highest-value remaining follow-up before STT quality
  can be certified pilot-ready. Tracked as an open risk in the QA doc.

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

- The 5 controlled fixtures are now real PCM16 16 kHz audio (**TASK-STT-007** merged)
  and a first live per-category Gradium run was executed
  (`docs/qa/stt-transcription-quality.md`, 2026-07-10). The remaining gap is that the
  per-category WER figures are not yet a usable pass/fail gate: the scorer counts
  punctuation/case/accents as errors (WER 1.0 for `Bonjour` vs `Bonjour.`), so
  transcript normalization (RF-008 → **TASK-STT-011**) is required before the matrix
  can gate quality.

### Notes

- RF-003 is **addressed**: the real engine is validated live (transcripts + latency)
  and the controlled fixtures now carry real audio; only the WER scoring artifact
  (RF-008 → TASK-STT-011) stands between the per-category run and a usable gate.
- RF-002 (channel ingress span is a scaffold analog) stays gated by US-019/US-036,
  which introduce the real channel ingress path.

---

## TASK-STT-009 - Detect And Instrument End-Of-Turn For The Voice Journey

**Parent:** EPIC-006, EPIC-010
**Related story:** US-036 (the `end_of_turn` slice it reports on)
**Related decision:** DEC-010 (per-step latency traces before any SLO claim)
**Classification:** V1 pilot gate
**Status:** ✅ Done — Sprint 2 (STT hardening), 2026-07-13
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
- Register the span name in `voice_common/pipeline_timing.py`
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

### Decision — authoritative end-of-turn signal (closes the sprint open question)

For the V1 batch web path the **trailing-silence window** over the captured PCM16
is authoritative, with an **explicit client stop** as the fallback when the buffer
ends before a full window. A streaming **VAD** is the future drop-in replacement
(ticketed as **TASK-STT-012**, Sprint 6): `EndOfTurnDetector` is injected into
`WebVoiceIngress`, so it can be swapped without touching the ingress, span or
pipeline wiring.

### Delivery Notes (2026-07-13)

- New `web_voice/end_of_turn.py`: `EndOfTurnDetector` (silence-window +
  client-stop fallback, configurable threshold/window, endianness-safe PCM16).
- `WebVoiceIngress` runs the detector between ingress and STT and emits a
  `voice.end_of_turn` span (duration = slice latency) + `voice.end_of_turn.detected`
  event; a silent/empty buffer invents no boundary and records
  `voice.end_of_turn.absent` instead (no span).
- `pipeline_timing.py`: `end_of_turn -> ("voice.end_of_turn",)`; the unmeasured
  note no longer points to a pending ticket. Slice now reports p50/p95/p99.
- Evidence: 88 unit tests + 8 behave scenarios green; docs updated
  (`voice-journey-timing.md`, README).

---

## TASK-STT-010 - Stream Partial STT Transcripts To Cut Perceived Latency

**Parent:** EPIC-006, EPIC-010
**Related stories:** US-036 (the `stt` slice latency), US-019 (web voice), US-018 (phone voice)
**Related finding:** RF-007 (chunked/streaming ingress client)
**Related decision:** DEC-005 (Pipecat streaming voice path; ADR-0002), DEC-010 (per-step latency before any SLO claim)
**Depends on:** TASK-STT-008 (Gradium provider)
**Pairs with:** TASK-WEB-004 (streaming TTS voice-out) — the two form the low-latency voice loop
**Classification:** V1 pilot gate
**Status:** ✅ Merged into `feat/restart-from-scratch` (Sprint 6, 2026-07-16, `e12b42f`;
validated by user in `51aacdc`, branch deleted post-merge) — stacked on TASK-STT-012; live
WebRTC gate green (streaming `stt.request` tail **818 ms** vs ~3.4 s batch); RF-007 closed
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

### Delivery Evidence (2026-07-16)

- **Spike (`docs/qa/stt-010-streaming-stt-spike.md`):** confirmed Gradium WebSocket
  ASR (`wss://api.gradium.ai/api/speech/asr`); post-end-of-turn tail 0.78 s vs ~3.4 s
  batch (~4×); `websockets`/`aiohttp` already in the venv (no new dependency).
- **Provider seam:** `stt_validation/streaming.py` — `GradiumStreamingSttProvider` +
  `GradiumStreamingSession` (async, injectable WS connector; key only in the connect
  header; error/drop → `StreamingSttError`). `build_streaming_provider` factory.
- **Pipeline:** `web_voice/streaming_stt_processor.py` — streams audio during speech,
  pushes `InterimTranscriptionFrame` partials, owns end-of-turn via
  `StreamingEndOfTurnDetector` (`has_speech` gate), emits the final `TranscriptionFrame`
  + `stt.request` span with `time_to_first_partial`/`time_to_final`. Wired via
  `StreamingVoiceSession.stt_processor` + `WebRtcSignalingService`; `server --stt-mode`
  (default `streaming`, Gradium only; `batch` keeps the aggregator fallback).
- **Tests:** +9 provider unit (fake WS), +6 processor unit (fake provider), +2 Behave
  scenarios (`features/streaming_stt.feature`). Full suite **241 unit / 7 Behave
  features (21 scenarios)** green.
- **Live gate (`docs/qa/stt-010-streaming-stt-qa.md`):** real Gradium streaming STT over
  WebRTC — `stt.request` **818 ms** tail, `time_to_first_partial` 1249 ms (mid-speech),
  one `voice.end_of_turn` span, correlation-id continuity through backend + TTS.
- **ADR-0023** records the transport + turn-finalization decision. **RF-007 → Closed**.

---

## TASK-STT-011 - Normalize Transcripts Before WER Scoring

**Parent:** EPIC-010
**Related finding:** RF-008 (TASK-STT-002 / TASK-STT-007)
**Related story:** US-036 (quality gate feeding pilot readiness)
**Classification:** V1 pilot gate
**Status:** Done — Sprint 2 (STT hardening)
**Priority:** Medium
**Branch:** `feat/sprint-2-stt-hardening`

### Objective

Make `word_error_rate` (and the `quality_score` gate) meaningful against a real STT
engine by normalizing both reference and hypothesis before comparison, so trivial
formatting differences stop counting as transcription errors.

### Context (why this is needed)

The first live Gradium per-category run (2026-07-10,
`docs/qa/stt-transcription-quality.md`) marked 3/4 usable categories as "failed"
almost entirely on artifacts, not real errors:

- `Bonjour` vs `Bonjour.` → WER **1.0** (punctuation).
- ASCII references (`telephone`, `elevee`) vs accented engine output (`téléphone`,
  `élevée`) → counted as word errors.
- Case differences (`Est-ce` vs `est-ce`).

The `ready` gate is unusable against a real engine until this is fixed.

### Scope

- Normalize before WER: lowercase, strip/normalize punctuation, collapse
  whitespace, and fold accents (or store accented references) — applied identically
  to reference and hypothesis.
- Keep the raw transcript in the report for audit; score on the normalized form.
- Re-run the live Gradium manifest and record realistic per-category WER.
- Decide whether the default `quality_threshold` needs revisiting once artifacts
  are removed.

### Out Of Scope

- Fixture realism / multiple samples (TASK-STT-007).
- Semantic scoring beyond WER.

### Acceptance Criteria

```gherkin
Scenario: Formatting differences do not count as transcription errors
  Given a reference and a hypothesis that differ only by case, punctuation or accents
  When the word error rate is computed
  Then the WER is 0.0
  And a genuine word substitution or omission still increases the WER
```

### Required Evidence

- Unit tests: punctuation/case/accent-only diffs score WER 0.0; real
  substitutions/omissions still counted.
- Updated `docs/qa/stt-transcription-quality.md` with the re-run per-category WER.
- RF-008 moved to Closed.

### Delivery Evidence (2026-07-10)

- `voice-agent/stt_validation/quality.py`: new `normalize_transcript` (NFKD accent
  folding, lowercase, `[^\w\s]` punctuation → space, whitespace collapse; stdlib
  only). `word_error_rate` now normalizes both sides before the Levenshtein diff;
  the raw `transcript`/`reference` are still stored verbatim in the report for
  audit — only the score uses the normalized form. Exported from the package barrel.
- `voice-agent/tests/test_quality.py`: +8 tests — punctuation/case/accent-only and
  combined formatting diffs score WER 0.0; real substitution/omission still 0.25;
  `normalize_transcript` behaviour. Full suite **55 tests green**.
- **Live Gradium re-run (2026-07-10)** over the PCM16 manifest: `short` WER
  **1.00 → 0.00**, `long` 0.083, `accented` 0.182 (all pass at 0.8); only `noisy`
  fails (WER 0.40) on a **genuine** transcription error from the synthetic
  white-noise fixture (owned by TASK-STT-007). The `ready` gate now reflects real
  quality — RF-008 resolved. Default `quality_threshold` kept at 0.8 (it cleanly
  separates good transcripts ≥ 0.82 from the degraded noisy sample at 0.60).

---

## TASK-STT-012 - Streaming VAD-Based End-Of-Turn Detection

**Parent:** EPIC-006, EPIC-010
**Related story:** US-036 (the `end_of_turn` slice), US-019 (web voice), US-018 (phone voice)
**Builds on:** TASK-STT-009 (batch end-of-turn detector + `voice.end_of_turn` span)
**Pairs with:** TASK-STT-010 (streaming STT) — real-time turn detection is a prerequisite for the streaming path
**Classification:** V1 pilot gate
**Status:** ✅ Done — Merged into `feat/sprint-6-streaming` (2026-07-16, ff; branch deleted), Sprint 6 closed and merged to `feat/restart-from-scratch`. Validated by user (2026-07-16) — adversarial review 93/100 (Pass); QA Go (live WebRTC gate, `docs/qa/stt-012-streaming-end-of-turn-qa.md`). (Reconciled 2026-07-23: an earlier note wrongly re-scheduled this to Sprint 9 "merge + close" — it was already merged in Sprint 6.)
**Priority:** Medium
**Branch:** `task/TASK-STT-012-streaming-vad-end-of-turn` (merged + deleted in Sprint 6)

### Objective

Replace the batch trailing-silence `EndOfTurnDetector` (TASK-STT-009) with a
**real-time voice-activity-detection (VAD)** end-of-turn signal that decides the
turn is over *while the audio streams*, instead of inspecting a fully captured
buffer after the fact. This is the "future drop-in" the TASK-STT-009 decision
explicitly deferred.

### Context (why this is needed)

TASK-STT-009 shipped a **batch** detector: it computes trailing silence over the
whole captured PCM16 buffer, which only works once the client has stopped and
uploaded the full utterance. The streaming path (TASK-STT-010) delivers audio in
chunks and cannot wait for a complete buffer — it needs a detector that consumes
frames incrementally and fires an end-of-turn event as soon as a silence window
elapses. The `EndOfTurnDetector` is already **injected** into `WebVoiceIngress`,
so this is a replacement of the strategy, not a rewrite of the wiring.

### Scope

- A streaming/frame-incremental VAD detector implementing the same injection
  point as `EndOfTurnDetector` (energy-based VAD at minimum; pluggable to a
  library VAD such as WebRTC/Silero later).
- Fire `voice.end_of_turn` incrementally (same span/attributes contract as
  TASK-STT-009) so `PipelineTimingReport` keeps measuring the slice unchanged.
- Configurable silence window / hangover; safe behaviour on no-speech (no
  invented boundary — keep the TASK-STT-009 guarantee).
- Keep the batch detector for fixtures/offline dev.

### Out Of Scope

- Barge-in / interruption during playback (US-021).
- The streaming STT transport itself (TASK-STT-010).

### Acceptance Criteria

```gherkin
Scenario: End-of-turn fires from streamed audio frames
  Given audio is streamed to the voice runtime frame by frame
  When the speaker stops and a silence window elapses
  Then an end-of-turn is fired before the full buffer is available
  And a voice.end_of_turn span with the turn correlation id is recorded
  And no turn boundary is invented when the stream carries no speech
```

### Required Evidence

- Unit tests driving the detector with a frame sequence (speech → silence →
  fire), including the no-speech guarantee.
- Behave scenario for the streaming end-of-turn outcome.
- `docs/observability/voice-journey-timing.md` updated to note the streaming
  detector once it lands.

---

## TASK-STT-013 - Reduce STT Post-EOT Finalize Tail To Meet ADR-0018 (p95 < 800 ms)

**Parent:** EPIC-006, EPIC-010
**Related stories:** US-036 (the `stt` slice + `time_to_first_audio`), US-019 (web voice)
**Related decisions:** ADR-0018 (pilot latency criterion), ADR-0023 (streaming STT transport + turn finalization), DEC-010 (per-step latency before any SLO claim)
**Builds on:** TASK-STT-010 (streaming STT), TASK-WEB-009 (baseline that measured the gap)
**Classification:** V1 pilot gate — **blocks the Sprint 6 Definition of Done**
**Status:** Implemented (Sprint 6, 2026-07-17) — STT lever done. Streaming STT finalizes on Gradium's `flushed` ack (not `end_of_stream`): `stt` tail p95 **1389 → 373 ms**, `time_to_first_audio` p95 **1698 → 853 ms**. ADR-0018 gate margin **−898 → −53 ms**; residual is now TTS-bound (per-turn TTS WebSocket connect) → **TASK-WEB-011**. Adversarial review **93/100 (Pass)** — no blocking findings (2026-07-17). QA acceptance **GO** (2026-07-17): 315 unit / 10 Behave features (26 scenarios) green + ADR-0018 gate re-confirmed (`streaming-voice-qa-report.md`). **Validated by user (2026-07-17)** — merged into `feat/sprint-6-streaming`.
**Priority:** High (latency-driven; sprint-blocking)
**Branch:** `task/TASK-STT-013-reduce-finalize-tail`

### Objective

Bring `time_to_first_audio` p95 below the ADR-0018 pilot criterion of **800 ms**
warm on the web channel, by reducing the dominant slice: the **STT post-end-of-turn
finalize tail**.

### Context (why this is needed)

The TASK-WEB-009 warm live sample (Gradium streaming STT+TTS, stub backend,
`docs/qa/streaming-latency-warm-sample.json`) measured `time_to_first_audio`
**p50 1310 ms / p95 1698 ms** — NO-GO on ADR-0018. The breakdown:

| Slice | p50 | p95 |
|---|---:|---:|
| `stt` (post-EOT finalize tail) | 866 ms | **1389 ms** |
| `backend_first_token` (stub) | ~0 ms | ~0 ms |
| `tts_first_audio` | 309 ms | 479 ms |

The STT finalize tail **alone exceeds the whole 800 ms budget**. Root cause in the
code: on end-of-turn, `GradiumStreamingSession.finish()` sends `flush` +
`end_of_stream` and `wait_final()` blocks on the server's terminal `end_of_stream`
round-trip — even though the "final" transcript is just `" ".join(parts)`, the
concatenation of partials **already received**. So the transcript content is
largely in hand at EOT; we are paying a server round-trip for confirmation.

### Scope

**Phase 1 — Spike (do first, decides feasibility before implementation):**
- Measure the `flush → end_of_stream` round-trip in isolation against live Gradium
  (how much of the 866–1389 ms tail is the server finalization vs local overhead).
- Quantify the accuracy delta between the last stable partial(s) at EOT and the
  authoritative final (does committing on the last partial lose trailing words?).
- Prototype **commit-on-last-partial** finalization (commit the answer on the last
  stable partial at EOT; let the authoritative final confirm/correct asynchronously
  for telemetry/audit) and measure the resulting `time_to_first_audio`.
- Explore provider-side finalization tuning and the EOT silence-window contribution
  (the latter is excluded from the ADR-0018 metric but affects perceived latency).
- Record findings + a go/no-go on reaching 800 ms in
  `docs/qa/stt-013-finalize-tail-spike.md`.

**Phase 2 — Implementation (only if the spike confirms 800 ms is reachable):**
- Add a configurable finalization strategy (commit-on-last-partial and/or tuned
  provider finalize) behind the existing streaming STT seam; keep the current
  authoritative-final behaviour available as a fallback.
- Preserve all safety invariants: no invented transcript, no secret leak, safe
  degraded fallback, no invented turn boundary on no-speech.
- Re-measure with `scripts/streaming_latency_report.py` over a warm sample
  (N large enough for meaningful p95) and update the ADR-0018 evidence + the
  streaming QA report go/no-go.

### Out Of Scope

- Streaming backend answer (`first_token` ≠ `request`, RF-021) — the answer engine
  stays the Sprint 5 stub/http backend.
- Reducing the TTS first-audio slice (already ~309 ms; not the bottleneck).

### Acceptance Criteria

```gherkin
Scenario: The streaming voice loop meets the ADR-0018 pilot latency criterion
  Given the streaming WebRTC voice runtime with the reduced finalize tail
  When a warm sample of turns is measured on the web channel
  Then time_to_first_audio p95 is below 800 ms
  And the per-slice p50/p95/p99 baseline is published
  And no transcript is invented and no safety invariant is regressed
```

If the spike concludes 800 ms is **not** reachable with Gradium on this path, the
alternative acceptance is an explicit Product/Architecture revision of the ADR-0018
criterion recorded in the ADR (not a silent weakening).

### Required Evidence

- `docs/qa/stt-013-finalize-tail-spike.md` (spike findings + feasibility go/no-go).
- If implemented: unit tests for the finalization strategy (fake WS), a re-measured
  warm sample, updated ADR-0018 evidence + streaming QA report.
- Adversarial review ≥ 90% + QA acceptance + user validation before merge.

### Delivery Evidence (2026-07-17)

- **Spike (`docs/qa/stt-013-finalize-tail-spike.md`, live Gradium, short/long/noisy,
  very stable):** after our end-of-turn flush the last `text` partial lands at
  ~60–204 ms (full transcript in hand), Gradium's `flushed` ack lands at a
  clip-length-independent **~350 ms**, but the terminal `end_of_stream` we blocked on
  lands at **~780 ms** — ~430 ms of pure waiting after the transcript was already
  complete. Commit-on-last-partial was **rejected** (drops the trailing word: the
  ~800 ms `delay_in_frames` lookahead lands after flush); finalize-on-`flushed` is
  lossless and faster. Tool: `voice-agent/scripts/stt013_finalize_spike.py`.
- **Implementation:** `GradiumStreamingSession._handle_message` finalizes on the
  `flushed` ack (guarded by `_flush_id > 0`) via `_finalize_from_parts()`;
  `end_of_stream` (and `error`) kept as safe fallback terminals. All safety invariants
  unchanged (transcript = concatenation of real partials, key never logged, drop/error
  still `StreamingSttError`).
- **Tests:** +2 provider unit tests (finalize-on-`flushed` with zero word loss via a
  flush-driven fake WS that proves `end_of_stream` was never consumed; `end_of_stream`
  fallback still finalizes). Full suite **305 unit / 10 Behave features (26 scenarios)**
  green.
- **Live re-measurement (`docs/qa/streaming-latency-warm-postfix.json`, 8 warm turns,
  WebRTC, stub backend):** `stt` p95 **1389 → 373 ms**; `time_to_first_audio` p50/p95
  **1310/1698 → 827/853 ms** (−845 ms). ADR-0018 gate still FAIL but margin **−898 →
  −53 ms**.
- **Residual (now TTS-bound, not STT):** `tts_first_audio` p95 484 ms includes a
  ~90 ms per-turn TTS WebSocket connect (measured: `open()` ~90 ms warm / ~188 ms
  cold; first chunk after open ~350 ms). Pre-warming/reusing it → **TASK-WEB-011**,
  projected composite p95 ~763 ms (PASS). ADR-0018 evidence + streaming QA report
  updated with the post-fix baseline.
