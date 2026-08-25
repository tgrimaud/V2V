# QA Report — TASK-WEB-030: WebSocket capacity ceiling + per-slice observability

**Ticket:** TASK-WEB-030 · **Branch:** `task/TASK-WEB-030-ws-capacity-observability` (off
`feat/sprint-12-external-voice-websocket`) · **Date:** 2026-08-25
**Related:** ADR-0043 (interim WS transport), ADR-0028 (per-slice OTel), TASK-WEB-024 (WebRTC ceiling)

## Executive summary

**GO** for merge-ready (pending adversarial review sign-off + explicit user merge request).
Both acceptance criteria are covered by automated tests. The WS path now has WebRTC-parity
backpressure (a session ceiling with a clean WS 1013 refusal made observable) and always dumps
the canonical per-slice journey timing under one correlation id. The refusal reuses pipecat's
own single-client guard (no accept logic duplicated), so it cannot crash the server. No blockers;
residual risks are live-edge checks explicitly deferred to WEB-031.

## Functional results

| Acceptance criterion | Result | Evidence |
|---|---|---|
| **AC #1 — sessions past the cap are refused cleanly** (clear close/error, no crash) | ✅ PASS | `features/websocket_capacity.feature` scenario 1 + `tests/test_websocket_support.py::WebSocketCapacityRejectionSeamTest`: an extra concurrent client is surfaced to `on_client_rejected` **before** pipecat's parent performs the real WS 1013 close; the capacity-aware input subclass adds no accept logic, so the refusal path is pipecat's own. |
| **AC #1 — active-session gauge + refusal event recorded** | ✅ PASS | `tests/test_websocket_signaling.py::WebSocketSignalingCapacityTest`: `voice.ws.active_sessions` emitted on connect (`accepted`), disconnect (`closed`) and refusal (`rejected`) stamped with `max_sessions`; `voice.ws.session_rejected` carries `reason=single_client_capacity`, `active_sessions`, `max_sessions`. |
| **AC #2 — canonical per-slice spans under one correlation id** | ✅ PASS | `tests/test_session_telemetry.py` + `features/websocket_capacity.feature` scenario 2: `build_payload` always includes `pipeline_timing` with all six slices (channel ingress → end-of-turn → STT → backend → TTS first audio → channel egress). |
| **AC #2 — a missing slice is `measured=false`, never omitted** | ✅ PASS | Same tests: a partial turn (only end-of-turn + STT measured) still reports `backend_first_token` and `channel_egress` as `measured=false`. |
| No regression to the WebRTC path or the WEB-028 WS client | ✅ PASS | Shared `build_payload`/`SessionFactory` (`transport_label` default `webrtc`); 558 unit + 17/46/209 behave green incl. WebRTC signaling/STT/egress suites. WEB-028 unit + Behave transport-builder fakes updated for the new `on_client_rejected` kwarg. |

## Capacity model (interim, honest scope)

The socle `SingleClientWebsocketServerTransport` is **single-client per listener**, so the
effective ceiling is 1. `VOICE_MAX_WS_SESSIONS` (default 1) is kept env-tunable and stamped on
the gauge for cross-transport parity, but a real ceiling > 1 needs a listener-per-session
topology (deferred — same open question as dynamic per-call language selection, ADR-0043). The
refusal is not reimplemented: `_CapacityAwareTransport` only *observes* the incoming client that
pipecat is about to close with 1013, then delegates to the parent handler.

## Observability

`session_telemetry.build_payload` (shared by WebRTC + WS) is the single source of the per-call
evidence line and now always carries `pipeline_timing = PipelineTimingReport.from_spans(...)`.
The channel-egress span carries a `transport="websocket"` label so a latency report can split WS
from WebRTC. The dump now fires at **call end** (client disconnect), not only at server shutdown,
and is idempotent (`_dump_once`) so a shutdown after a clean disconnect does not double-dump.

## Test evidence

- **Unit:** `tests/test_session_telemetry.py` (2) + `tests/test_websocket_support.py` capacity
  seam (2) + `tests/test_websocket_signaling.py` capacity/idempotent-dump/`ws_max_sessions_config`
  (5). Full suite **558** green (549 baseline + 9).
- **Behave:** `features/websocket_capacity.feature` (2 scenarios / 8 steps). Full suite
  **17 features / 46 scenarios / 209 steps** green.

## Defects / residual risks

| Sev | Item | Disposition |
|---|---|---|
| Low | Live end-to-end refusal + per-slice p50/p95 latency through the HAProxy edge not exercised (no real socket in unit/Behave) | Deferred to **TASK-WEB-031** (external QA + latency report). |
| Low | The `_client_handler` refusal-surfacing path is not driven against a real websocket in unit tests (only the wiring + signaling-side recording are) | The refusal itself is pipecat's own guard; end-to-end 1013 was already proven live in WEB-028 QA. Re-covered by WEB-031. |
| Info | Ceiling is effectively 1 (single-client socle); `VOICE_MAX_WS_SESSIONS > 1` has no effect without a listener-per-session topology | Intended interim behaviour; documented in ADR-0043 + ticket. |

## Recommendation

**GO** — merge-ready after adversarial review ≥ 90%. Merge into
`feat/sprint-12-external-voice-websocket` on explicit user request only.
