# ADR-0021: Conversation Backend Answer Contract And Degraded Mode

## Status

Accepted (Sprint 5, TASK-WEB-003)

## Context

The Voice2Voice loop needs a neutral middle between the STT (voice-in) and TTS
(voice-out) halves: it takes a transcript and returns a response text to speak.
This "answer step" must:

- stay **agnostic** to the answer engine, so the deterministic offline stub, a
  real HTTP conversation endpoint (the Java backend) and future providers are
  interchangeable (product rule: LLM/STT/TTS behind replaceable ports);
- preserve the hard STT/TTS separation — the middle must not import either half or
  the web transport (enforced by `tests/test_architecture_separation.py`);
- never fabricate billing content and never crash the turn when the engine fails
  or is unsure (DEC-002; safe Voice2Voice behaviour);
- expose only privacy-safe, sanitized observability (RF-013): lengths, not raw
  transcript/answer text; a stable error code, not raw provider text or secrets.

## Decision

Define a small, neutral **conversation contract** in
`voice-agent/conversation_backend/` and a shared answer step that both runtimes
call identically.

### Port and models

- `BackendAnswerPort` — `name` + `answer(AnswerRequest) -> AnswerResult`.
- `AnswerRequest` — `transcript`, `conversation_id`, `correlation_id`, `channel`.
  `to_dict` exposes **`transcript_chars`**, never the raw transcript.
- `AnswerResult` — `text`, `provider`, `outcome`, `correlation_id`,
  `confidence?`, `degraded_reason?`, `duration_ms`, `error_code?`, `error_reason?`.
  `to_dict` exposes **`text_chars`**, never the raw answer.
- `AnswerOutcome` — `success` | `degraded` | `unavailable`.
- `EmptyTranscriptError` — provider-agnostic "nothing to answer" signal so the
  caller reports `unavailable` (stays silent) instead of inventing a turn. Mirrors
  `EmptyTextError` (TTS) / `NoSpeechDetectedError` (STT).

### Adapters

- `StubBackendAdapter` (default) — deterministic, digit/currency-free answer for
  dev, tests and demos. It cannot state a fabricated amount (DEC-002).
- `HttpBackendAdapter` (TASK-WEB-003-C) — posts the request as JSON to a
  configured endpoint and maps a 2xx `text` (alias `answer`) + optional
  `confidence` onto `AnswerResult`. Injectable transport (default stdlib
  `urllib`) so tests never hit the network. The API key lives only in the
  `x-api-key` header. Selected by `build_backend(name)` / `--backend {stub,http}`.

### Degraded mode (TASK-WEB-003-F)

The shared answer step `answer_with_telemetry` owns one degraded policy so both
runtimes behave identically:

- a backend fault (any exception except `EmptyTranscriptError`) → a **DEGRADED**
  result carrying the safe fallback text + a sanitized `error_code`/`error_reason`
  (`sanitize_error(domain="backend")`);
- a **below-threshold `confidence`** SUCCESS answer → replaced by the safe
  fallback (`low_confidence`); `confidence is None` means "not provided" and is
  **not** treated as low (so the stub is never wrongly degraded);
- a confident-but-**empty** answer → replaced by the safe fallback
  (`empty_answer`).

The safe fallback (`DEGRADED_FALLBACK_TEXT`) is a fixed, digit-free message owned
by the contract, so it can never state an amount. A DEGRADED result has text and
is spoken; only `unavailable` (empty transcript) stays silent. Default confidence
threshold: `0.5` (the real proof/confidence rule is gated by OQ-002).

### Observability

`answer_with_telemetry` emits `backend.first_token` and `backend.request` spans
(equal for a batch backend; a streaming backend diverges them — RF-021) plus a
`voice.backend.answered` event, all carrying the correlation id, provider,
`outcome`, `degraded`, `degraded_reason` and sanitized error — lengths only for
any text. A `warning` structured log is emitted on degrade. This closes the
US-036 `backend_first_token` slice.

## Consequences

- The answer engine is swappable without touching the runtimes, telemetry or the
  voice halves.
- The loop is safe by construction: no invented amount, no crash, no secret leak;
  a failing or unsure backend still yields a spoken, observable degraded turn.
- The wire shape of `HttpBackendAdapter` (request fields, `text`/`answer` keys,
  `confidence`) is **provisional**; this ADR is the reference until the Java
  backend endpoint is finalized. `confidence` is not yet range-validated (RF-015,
  gated by OQ-002).
- Adding a provider = implement `BackendAnswerPort` + register it in
  `build_backend`; the degraded policy and telemetry apply automatically.

## Alternatives Considered

- **Let the LLM/backend read the invoice and compute amounts directly:** rejected
  (DEC-002 / ADR-0005) — deterministic extraction + comparison precede any wording.
- **Per-adapter degraded handling:** rejected — duplicates logic and risks
  divergent runtime behaviour; centralized in the shared answer step.
- **Return HTTP transport errors to the caller as failures:** rejected — a failed
  turn must still speak a safe fallback, not a generic 502 (RF-020).
- **Put the answer step in `web_voice` or a voice half:** rejected — it must stay
  neutral to preserve the STT/TTS separation and channel-agnosticism.

## Related Documents

- `docs/architecture/voice-runtime-http-contract.md`
- `docs/observability/voice-journey-timing.md`
- `docs/architecture/adrs/ADR-0002-pipecat-gradium-target-voice-path.md`
- `docs/architecture/adrs/ADR-0005-invoice-pdf-extraction-before-llm-explanation.md`
- `docs/architecture/adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md`
- `docs/qa/web-voice-backend-bridge-qa-report.md`
