# QA Report — TASK-WEB-029: Barge-in / end-of-turn on the WebSocket path (pluggable seam)

**Ticket:** TASK-WEB-029 · **Branch:** `task/TASK-WEB-029-ws-barge-in-eot` (off
`feat/sprint-12-external-voice-websocket`) · **Date:** 2026-08-24
**Related:** ADR-0043 (control-signal seam), ADR-0025 (barge-in + point-7 amplitude gate),
ADR-0040 (Genesys events feed the same seam later)

## Executive summary

**GO** for merge-ready (pending adversarial review sign-off + explicit user merge request).
Both acceptance criteria are covered by automated tests; the pluggable control-signal seam is
transport-agnostic and a **transparent pass-through by default**, so the validated WebRTC/WS
energy-detector behaviour (350 ms hold, `VOICE_BARGE_IN_*`) is unchanged. No blockers. Residual
risks are live-only checks explicitly deferred to WEB-030/WEB-031, consistent with WEB-028.

## Functional results

| Acceptance criterion | Result | Evidence |
|---|---|---|
| **AC #1 — Barge-in cuts the bot cleanly** (in-flight synthesis cancelled, playback stops, connection stays open) | ✅ PASS | `features/websocket_control_signals.feature` scenario 2 + `tests/test_streaming_tts_processor.py` barge-in cancel: `broadcast_interruption()` → `tts.interrupted` + session `aclose()`; only the already-played chunk emitted; no `EndFrame`/`CancelFrame` so the socket stays open. |
| **AC #2 — Signal source is pluggable** (fake source emits end-of-turn → session finalizes without the energy detector) | ✅ PASS | `features/websocket_control_signals.feature` scenario 1 + `tests/test_streaming_stt_processor.py::test_control_end_of_turn_finalizes_without_energy_detector`: speech with **no trailing silence** (energy detector would keep buffering) is finalized to one transcript by the control source alone. |
| Genesys-named control vocabulary (1:1 mapping later) | ✅ PASS | `ControlSignalType` = `barge_in`/`end_of_turn`/`call_end`/`playback_started`/`playback_completed`; `voice.control_signal` telemetry asserted in unit + Behave. |
| No regression to the default (energy-detector) path | ✅ PASS | Processor with no source is a transparent pass-through (no consumer task, no control telemetry); 549 unit + 16/44/201 behave green, incl. the WebRTC signaling + STT + barge-in suites. |
| Safe no-op on control end-of-turn before any speech | ✅ PASS | `test_control_end_of_turn_is_a_noop_without_an_open_session`: no session opened, no fabricated transcript. |

## Clean-cancellation over `wss`

The interruption path is the **shared, transport-agnostic** one WEB-028 already runs on the WS
transport: `broadcast_interruption()` cancels the `StreamingTtsProcessor` task
(`asyncio.CancelledError` → `tts.interrupted`, best-effort `aclose()` in `finally`, TASK-WEB-008)
and the output transport flushes buffered audio. No `EndFrame`/`CancelFrame` is raised, so the
`wss` connection is not torn down and the next turn proceeds on the same socket. Verified via the
seam in `websocket_control_signals.feature` scenario 2 and the TTS-processor cancel tests.

## Test evidence

- **Unit:** `tests/test_control_signal_processor.py` (9) + 2 new STT finalize tests. Full suite
  **549** green (538 baseline + 11).
- **Behave:** `features/websocket_control_signals.feature` (2 scenarios / 9 steps). Full suite
  **16 features / 44 scenarios / 201 steps** green.

## Defects / residual risks

| Sev | Item | Disposition |
|---|---|---|
| Low | Live `wss` barge-in + mouth-to-ear latency not exercised (no real socket/mic in unit/Behave) | Deferred to **TASK-WEB-031** (external QA + latency), as for WEB-028. |
| Low | Seam `call_end` not yet wired to the WS drain teardown (farewell `end_call`) | Processor exposes `set_end_call`; default is a graceful `EndFrame`. WS lifecycle wiring is **TASK-WEB-030**. |
| Info | `call_end` fallback pushes an `EndFrame` (ends the whole pipeline) when no `end_call` is injected | Intended interim behaviour; documented in the ADR + ticket. |

## Recommendation

**GO** — merge-ready after adversarial review ≥ 90%. Merge into
`feat/sprint-12-external-voice-websocket` on explicit user request only.
