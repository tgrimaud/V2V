# Adversarial Code Review — Python Voice Runtime (pre-sprint cleanliness)

- **Date:** 2026-08-28
- **Branch:** `feat/sprint-12-external-voice-websocket`
- **Reviewer method:** local `.cursor/skills/adversarial-code-review`, `.cursor/skills/code-guidelines`, `.cursor/skills/test-guidelines`
- **Purpose:** confirm the `voice-agent/` Python runtime is clean before the next sprints begin, and that TASK-STT-014 (reverted, commit `f0472b5`) left no runtime residue.
- **Constraints honoured:** no source file modified, no branch switch, no commit/push. Only this report was created.

---

## Scope

Everything under `voice-agent/` in the runtime critical path:

- Streaming WebRTC pipeline (`web_voice/webrtc_signaling.py`, `session_factory.py`, `streaming_runtime.py`, `async_loop.py`, `ingress.py`, `egress.py`, `channel_egress_probe.py`).
- External-voice WebSocket server (ADR-0043, sprint-12 theme): `web_voice/websocket_signaling.py`, `websocket_support.py`, `websocket_framing.py`.
- STT/TTS provider adapters + ports: `stt_validation/streaming.py`, `tts_synthesis/streaming.py`, `web_voice/streaming_stt_processor.py`, `web_voice/streaming_tts_processor.py`, session warmers.
- Streaming answer consumption of `converse-stream`: `voice_pipeline/streaming_answer.py`, `voice_pipeline/answer.py`, `conversation_backend/streaming.py`, `conversation_backend/http_backend.py`.
- Barge-in / interruption: native Pipecat `InterruptionFrame` path, amplitude + N-frame gating, drain (`streaming_stt_processor.py`, `control_signal_processor.py`, `webrtc_signaling.py`).
- End-of-turn detection + silence window config (`_silence_window_config`, `PILOT_END_OF_TURN_SILENCE_MS`) in `session_factory.py`, `end_of_turn.py`.
- `CallEndFarewellProcessor` (US-041 confirmation turn) + `closing_intent.py`.
- Batch `/api/voice/turn` (BUG-015 full-answer accumulation): `web_voice/server.py`, `web_voice/runtime.py`, `voice_pipeline/pipeline.py`.
- Telemetry (`voice_common`: `TelemetryRecorder`, `pipeline_timing`, `otel_export`, `trace_context` deterministic traceparent), failure sanitization/redaction (`voice_common/sanitization.py`).
- `backend_factory` URL handling (BUG-013 base URL), `VOICE_BACKEND_STREAM` default + fail-safe env parsing.

---

## Method (what was inspected + results)

### Tests

- **unittest:** `./.venv/bin/python -m unittest discover tests` → **`Ran 568 tests … OK`** (0 failures, 0 errors; ~46 s).
- **behave:** `./.venv/bin/behave` → **17 features passed, 46 scenarios passed, 209 steps passed** (0 failed, 0 skipped). Re-run confirmed identical counts.
- Counts match the brief's post-revert expectations (~568 unittest, ~46 scenarios / 209 steps).

### Static / manual inspection

- Read every file in scope in full (not sampled).
- Grepped (via `rg`, since the Grep tool returns spurious "no matches" in this nested repo) for: `except Exception` vs `except asyncio.CancelledError`, `aclose`, `finally`, `broadcast_interruption`, `InterruptionFrame`, `TODO/FIXME/HACK/XXX/WIP`, `print(`, `api_key/secret/password`, and dead-pipeline references (`deepgram/piper/bridge_server`).
- Cross-checked the CLAUDE.md / AGENTS.md "issues historically hit" list against the current code.

### Findings against the mandated checklist

| Check | Result |
|---|---|
| Bare `except Exception` swallowing `CancelledError` on barge-in | **None.** Every interruptible path (`streaming_answer.py:105`, `streaming_tts_processor.py:127`, `session_warmer.py:67`, `call_end_farewell.py:134`, `control_signal_processor.py:88`) catches `asyncio.CancelledError` **before** `except Exception` and re-raises / returns correctly. |
| Missing `finally`/`aclose` on interruptible streams | **None.** `streaming_tts_processor._synthesize` closes the session in `finally` on all paths (`_safe_aclose`); `streaming_stt_processor._finalize` acloses on success and failure; `http_backend._urllib_stream_transport` closes the socket in `finally` and binds `StreamControl` for barge-in abort. |
| WebSocket / connection leaks | **None found.** STT/TTS streaming sessions, the SSE socket, and WebRTC connections are all released on success, failure, barge-in, drain and shutdown. |
| Telemetry gaps (correlation id / provider / outcome / duration) | Runtime emitters consistently stamp `correlation_id`, `provider`, `outcome` and a duration/elapsed. Per-turn baggage (`begin_turn`) keeps identity across a long-lived streaming recorder. |
| Spans left unparented | **None.** `otel_export._do_export` parents the `voice.turn` root under the correlation-derived context and every child span under `root_ctx` (`set_span_in_context`). |
| `pipeline_timing` outcome-filter correctness | Correct. `_counts_toward_slice` drops only non-success `voice.tts.first_audio` (BUG-008) and leaves outcome-less slices unaffected; deliberate metric definition is documented and locked. |
| Thread / asyncio loop safety | Single persistent loop (`BackgroundEventLoop`) on a daemon thread; the threaded stdlib server submits via `run_coroutine_threadsafe`; `run(timeout=)` cancels the wrapped task on timeout so `finally` reservations (`_pending`) are released (voice review V-M1). |
| Env-var parsing pitfalls | Fail-safe across the runtime: `_silence_window_config`, `_barge_in_config`, `_finalize_budget_config`, `_farewell_config`, `ws_port_config`, `_max_sessions_config`, `resolve_confidence_threshold`, `backend_stream_enabled`, `backend_warmup_enabled` all fall back on invalid input. `VOICE_BACKEND_STREAM` is fail-safe (`not in {"0","false","no","off"}`) and only takes the streaming path when the backend exposes `answer_stream` (`_stream_this_turn`). One inconsistency — see Minor M2. |
| Dead code from removed pipelines | **None.** No `deepgram/piper/bridge_server` references. |
| STT-014 (reverted) residue | **None.** No `partial-quiet` / early-finalization / async-reconcile code. (The retained QA report `docs/qa/task-stt-014-finalize-tail-qa.md` is intentionally kept and NOT flagged.) The retained `finalize budget` fallback in `streaming_stt_processor._await_final` is TASK-WEB-035 (caps waiting for the provider *terminal ack*), a different, legitimate feature — not STT-014. |
| TODO/FIXME | **None** (the sole `NotImplementedError` is an abstract port default — Minor M4). |
| Secret / PII leakage in logs | **None.** The Gradium `x-api-key` lives only in connection headers, never in a span/event/log; `sanitize_error` redacts paths/filenames/UUIDs/secret-prefixes/digit-runs; STT emits no transcript text; the answer path emits `answer_chars` (length), not text. |

---

## Overall score: 96 / 100

**QA gate: Pass.**

Deductions: −4 total for maintainability (module/class size budget breaches, one env-parse inconsistency, a stale comment, and a couple of slightly-over-budget methods). No functional, observability, security or architecture deductions.

## Verdict: **CLEAN for the next sprint.**

The runtime is disciplined and internally consistent: cancellation-safe barge-in, no stream/socket leaks, complete and correctly-scoped telemetry, deterministic cross-tier tracing, robust sanitization, fail-safe env parsing, and a fully green test + behave suite. The reverted STT-014 left no runtime residue. The remaining findings are non-blocking maintainability items to address opportunistically.

---

## Blockers

**None.**

---

## Majors

**None.**

---

## Minors

| # | Severity | Finding | Evidence (file:line) | Recommended fix |
|---|---|---|---|---|
| M1 | Minor (maintainability) | Several modules/classes exceed the mandatory 200-non-blank-line budget (`.cursor/rules/voice-support-bot.mdc`: "Max 200 lines per module"; code-guidelines: 200-line class max). Most notable: `StreamingSttProcessor` is a single class of **382 non-blank lines**. | `web_voice/streaming_stt_processor.py` (class 117–531, 382 nb); `web_voice/server.py` (606 nb); `voice_pipeline/answer.py` (357 nb, `AnswerProcessor` 171 nb); `voice_common/pipeline_timing.py` (333); `web_voice/webrtc_signaling.py` (328); `web_voice/session_factory.py` (327); `conversation_backend/http_backend.py` (241); `web_voice/streaming_tts_processor.py` (222); `web_voice/end_of_turn.py` (211) | Extract cohesive collaborators from `StreamingSttProcessor` (e.g. a barge-in gate object, a finalize/telemetry helper) and split `server.py`'s handler factory. Behaviour-preserving, covered by the existing suite. Track as a refactor ticket; not required before the sprint. |
| M2 | Minor (consistency) | `_timeout()` parses `VOICE_BACKEND_TIMEOUT_S` with a bare `float(raw)` and no guard, so a non-numeric value raises `ValueError` at backend build time — inconsistent with the fail-safe env parsing used everywhere else in the runtime. | `conversation_backend/backend_factory.py:62-64` | Wrap in `try/except ValueError` and fall back to `DEFAULT_TIMEOUT_S` (and ignore ≤0), mirroring `_float_env` in `session_factory.py`. Fail-fast at startup is arguably acceptable, so this is purely a consistency fix. |
| M3 | Minor (doc drift / Boy Scout) | Comment claims "Unset → the processor default (500 ms)" for the silence window, but `_silence_window_config()` never returns `{}` — it always returns `PILOT_END_OF_TURN_SILENCE_MS` (350 ms). So `StreamingSttProcessor`'s `DEFAULT_SILENCE_WINDOW_MS` (500 ms) is effectively dead on the streaming path, and the comment misleads a future reader. | `web_voice/session_factory.py:280-283` (vs `_silence_window_config` at 113-133) | Update the comment to state the streaming default is 350 ms via `_silence_window_config`; the 500 ms library constant applies only to batch/fixture callers. |
| M4 | Minor (style) | A couple of methods slightly exceed the 20-line method guideline. | `voice_common/otel_export.py:78-129` (`_do_export`, ~30 code lines); `web_voice/webrtc_signaling.py:175-209` (`_new_session`, ~25) | Optional: extract the child-span loop / the transport-build block into helpers. Low priority. |
| M5 | Minor (style) | `ControlSignalSource.signals()` uses a plain class + `raise NotImplementedError` as a port. | `web_voice/control_signals.py:42-50` | Consider `typing.Protocol` or `abc.abstractmethod` for a clearer port contract. Cosmetic. |

---

## Concrete remediation per finding

- **M1** — `web_voice/streaming_stt_processor.py:117` : split the 382-line `StreamingSttProcessor`; the barge-in amplitude/N-frame gate (`_maybe_barge_in`/`_trigger_barge_in` + its state) and the finalize/telemetry emitters are natural extraction seams. `web_voice/server.py:1` : split the request-handler factory (turn / tts / static / openapi handlers). Both behaviour-preserving under the current suite.
- **M2** — `conversation_backend/backend_factory.py:62` : `try: value = float(raw) except ValueError: return DEFAULT_TIMEOUT_S; return value if value > 0 else DEFAULT_TIMEOUT_S`.
- **M3** — `web_voice/session_factory.py:280` : correct the inline comment to reflect the 350 ms streaming default.
- **M4** — `voice_common/otel_export.py:78` and `web_voice/webrtc_signaling.py:175` : optional helper extraction to fit the 20-line method guideline.
- **M5** — `web_voice/control_signals.py:42` : convert to `Protocol`/`abstractmethod`.

---

## Residual risk (if minors accepted as-is)

- **Low.** The oversized modules (M1) increase future change cost and review load but do not affect correctness; the suite green-lights any refactor later. M2 could crash backend startup only on an operator typo in `VOICE_BACKEND_TIMEOUT_S` (loud, immediate, easy to spot) — not a runtime-degradation risk. M3/M4/M5 are cosmetic. None of the residuals touch money, identity, escalation, guardrails (DEC-002 stays backend-side), barge-in safety, telemetry completeness or secret handling. Accepting them for the sprint boundary is safe; schedule M1 as a refactor ticket.

### Observability note (for continuity)

Runtime telemetry is complete and correctly scoped: correlation-id continuity via per-turn baggage, one trace across voice↔backend via the deterministic `traceparent`, per-slice p50/p95/p99 with explicit "not measured" markers, and outcome-filtered `tts_first_audio` (BUG-008). No missing required instrumentation was found — consistent with a runtime-affecting body of work that is ready for the next sprint.
