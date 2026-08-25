# QA Functional And Latency Report — TASK-WEB-031: WebSocket path

**Ticket:** TASK-WEB-031 · **Branch:** `task/TASK-WEB-031-ws-qa-functional-latency` (off
`feat/sprint-12-external-voice-websocket`) · **Date:** 2026-08-25
**Related:** ADR-0043 (interim WS transport), ADR-0029 (mouth-to-ear gate), ADR-0028 (per-slice timing)

## Executive Summary

- **Overall readiness:** Functional **GO** for the interim external WebSocket demo path;
  pilot latency SLO **NOT yet claimed** (see below).
- **Main blockers:** None functional. The ADR-0029 latency gate is **not yet scored** on the WS
  path because a warm, co-located sample with the **real** providers (Gradium STT/TTS + Mistral
  backend) could not be captured in this environment (no provider credentials / co-located warm
  host available). This is a measurement gap, not a defect — marked explicitly, never a silent pass.
- **Residual risks:** TCP head-of-line blocking under packet loss (vs WebRTC/UDP) and weaker
  browser AEC without headphones on the WS path (mitigated by the ADR-0025 point-7 amplitude gate).

## Scope Tested

- **Epics / stories:** EPIC-006 — TASK-WEB-026…030 (WS socle, session factory, browser client,
  barge-in/EOT seam, capacity + observability).
- **Channels:** web (interim browser `wss`).
- **Providers / fakes:** functional coverage via Behave/unit fakes; latency scoring tool proven
  on a WebSocket-shaped telemetry sample. Live provider run pending (see runbook).
- **Environment:** co-located dev host; unit + Behave suites in `voice-agent/.venv`.

## Functional Results

| Area | Status | Evidence | Notes |
|---|---|---|---|
| WS audio transport (no FastAPI, JSON control vs binary PCM demux) | ✅ PASS | `features/websocket_transport.feature` (3 sc.), `tests/test_websocket_support.py`, `tests/test_websocket_framing.py` | Socle is the websockets-based single-client server transport. |
| External voice turn built over the shared session core | ✅ PASS | `features/websocket_voice_client.feature` sc.1, `tests/test_websocket_signaling.py` | Session assembled via shared `SessionFactory`, run on the background loop. |
| Barge-in cuts the bot cleanly (control-signal seam) | ✅ PASS | `features/websocket_control_signals.feature` sc.2, `features/websocket_transport.feature` barge-in, `tests/test_streaming_tts_processor.py` | `broadcast_interruption()` → clean `asyncio.CancelledError` cancel, socket stays open. |
| Pluggable end-of-turn (source-driven, no energy detector) | ✅ PASS | `features/websocket_control_signals.feature` sc.1, `tests/test_streaming_stt_processor.py` | Genesys-ready seam (WEB-029). |
| Capacity refusal (extra client refused cleanly, no crash) | ✅ PASS | `features/websocket_capacity.feature` sc.1, `tests/test_websocket_signaling.py`, `tests/test_websocket_support.py` | WS 1013 via pipecat's own guard + `voice.ws.session_rejected` event + active-session gauge. |
| Canonical per-slice spans in the per-call dump (one correlation id) | ✅ PASS | `features/websocket_capacity.feature` sc.2, `tests/test_session_telemetry.py` | Missing slice = `measured=false`, never omitted. |
| Safe failure surfaces (server busy 1013 → message; error/mic-denied → no fabricated transcript) | ✅ PASS | WEB-028 live validation (user-validated: open→opened, 1013 refusal, browser mic turn) + `static/ws.js` close-code handling | Client never fabricates output; covered live in WEB-028 QA. |
| Declared vs effective language (interim fr-first) | ✅ PASS | `features/websocket_voice_client.feature` sc.2 | Declared language captured for correlation; effective = server default (interim, ADR-0043). |

## Latency Results

The WebSocket per-call dump emits the **same** span names as the WebRTC path
(`voice.end_of_turn`, `stt.request`, `backend.first_token`/`backend.request`,
`voice.tts.first_audio`, `web.voice.egress` with `transport="websocket"`), so
`scripts/streaming_latency_report.py` scores it **unchanged**. Tool correctness on a
WebSocket sample is proven by `tests/test_streaming_latency_report.py::WebSocketSampleTest`
(per-slice measured + WS-egress folded into mouth-to-ear + ADR-0029 gate scored).

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| channel_ingress | — | — | — | 0 | — | Not yet measured — no warm real-provider WS capture in this environment. |
| end_of_turn | — | — | — | 0 | — | Runtime-only slice; measurable with the harness once a live sample is captured. |
| stt | — | — | — | 0 | — | Requires live Gradium STT. Not measured here. |
| backend_first_token | — | — | — | 0 | — | Requires live Mistral backend (`--backend http`). Not measured here. |
| tts_first_audio | — | — | — | 0 | — | Requires live Gradium TTS. Not measured here. |
| channel_egress | — | — | — | 0 | — | Runtime egress (first frame → transport output), WS-labelled. Not measured here. |
| **voice_to_first_audio (mouth-to-ear)** | — | — | — | 0 | — | **ADR-0029 primary gate (p95 ≤ 1.5 s): NOT YET SCORED.** |
| **time_to_first_audio** | — | — | — | 0 | — | **ADR-0029 sub-target (p95 ≤ 1.2 s): NOT YET SCORED.** |

**Why not measured here:** a trustworthy score against the ADR-0029 gate requires a warm,
co-located sample with the real providers; scoring fixture/stub timings against a real-provider
gate would be misleading (per the QA skill, an unmeasured slice is marked explicitly, not faked).
No provider credentials (`../.env` absent) were available in this session.

### Runbook to capture and score a warm WS sample (harness delivered)

`scripts/ws_live_client.py` (new) drives a real `wss` turn so the server emits its per-call
dump on disconnect; `scripts/streaming_latency_report.py` scores the sample.

```bash
cd voice-agent
# terminal 1 — real providers + backend; capture the per-call dumps
set -a; . ../.env; set +a
.venv/bin/python -m web_voice.server --websocket on --stt-mode streaming \
    --tts-mode streaming --backend http 2> /tmp/ws-telemetry.jsonl
# terminal 2 — drive N warm turns (one call each)
for i in $(seq 1 12); do
  .venv/bin/python scripts/ws_live_client.py --url ws://127.0.0.1:8091 \
    --audio fixtures/long/billing-question.pcm --language fr --hold 12
done
# score against the ADR-0029 gate (reports p50/p95/p99 per slice + go/no-go)
.venv/bin/python scripts/streaming_latency_report.py \
    --input /tmp/ws-telemetry.jsonl --channel web --provider gradium-streaming --warm
```

Report the utterance length alongside the latency (batch/streaming STT latency scales with
audio length). The harness prints a client-observed `mouth_to_ear_proxy_ms` per turn; the
server dump carries the authoritative per-slice truth.

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| WS latency harness (`ws_live_client.py`) | ✅ | Pure frame helpers unit-tested (`tests/test_ws_live_client.py`); async socket loop needs a live server | Run the runbook when provider creds are available. |
| Latency report tool | ✅ | Scores a WS sample with no change (same span names); WS-egress folding + ADR-0029 gate proven | None. |
| Functional Behave/unit coverage | ✅ | 10 WS scenarios across 4 features + unit suites green | None. |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Medium | Warm real-provider WS per-slice p95 not captured (no creds / warm host this session) | ADR-0029 gate not yet scored on WS | QA (run the delivered runbook) |
| Low | Correlation id is per WS server session, not per connection on the single-client socle (WEB-030 residual) | Reconnect would accumulate spans under one id | Carried from WEB-030; formalise in a live run |
| Low | Live `wss` barge-in mouth-to-ear + TCP head-of-line under loss not exercised | Degraded-mode behaviour uncharacterised | QA live run |

## Open Questions

- **Product:** none new.
- **Architecture:** confirm whether the interim WS path needs per-connection correlation before
  Genesys, or whether "one session = one call" is acceptable for the pilot demo (WEB-030 residual).
- **Technical:** none blocking; the harness + tool are ready.

## Recommendation

- **Go / No-go:** **GO (functional)** for the interim external WebSocket demo — the journey (turn,
  barge-in, capacity refusal, safe-failure surfaces) is covered and green. **Latency: NOT YET
  SCORED** against the ADR-0029 pilot gate on the WS path; no pilot SLO is claimed until a warm,
  co-located real-provider sample is captured with the delivered harness.
- **Required before pilot:** run the capture runbook to score mouth-to-ear + time-to-first-audio
  p95 against ADR-0029 (with utterance length), and characterise the degraded modes (TCP
  head-of-line under loss, AEC without headphones).
