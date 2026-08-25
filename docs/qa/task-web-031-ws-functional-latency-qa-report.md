# QA Functional And Latency Report — TASK-WEB-031: WebSocket path

**Ticket:** TASK-WEB-031 · **Branch:** `task/TASK-WEB-031-ws-qa-functional-latency` (off
`feat/sprint-12-external-voice-websocket`) · **Date:** 2026-08-25
**Related:** ADR-0043 (interim WS transport), ADR-0029 (mouth-to-ear gate), ADR-0028 (per-slice timing)

## Executive Summary

- **Overall readiness:** Functional **GO** for the interim external WebSocket demo path.
  Pilot latency SLO **NOT met** — the ADR-0029 gate was scored on a warm, real-provider sample
  and **FAILS** (see below). This is an honest measurement, not a projection.
- **Latency gate (measured 2026-08-25, 16 warm calls, real Gradium streaming STT/TTS + Mistral
  RAG backend, co-located dev host):** **ADR-0029 FAIL** — mouth-to-ear p95 **3675 ms** (target
  ≤ 1500 ms) and time-to-first-audio p95 **3325 ms** (target ≤ 1200 ms). Even the *median*
  mouth-to-ear (2055 ms) exceeds the 1.5 s target. Dominant levers: **STT time-to-final p95
  2250 ms** and **backend first-token p95 1642 ms**; TTS first audio is already excellent
  (p95 402 ms) and channel egress is negligible (~4 ms).
- **Main blockers:** No functional blocker. Latency is the gating issue: the interim WS path as
  measured does not meet the pilot mouth-to-ear SLO — a No-Go on the SLO claim (not on the demo).
- **Residual risks:** TCP head-of-line blocking under packet loss (vs WebRTC/UDP) and weaker
  browser AEC without headphones on the WS path (mitigated by the ADR-0025 point-7 amplitude gate).

## Scope Tested

- **Epics / stories:** EPIC-006 — TASK-WEB-026…030 (WS socle, session factory, browser client,
  barge-in/EOT seam, capacity + observability).
- **Channels:** web (interim browser `wss`).
- **Providers / fakes:** functional coverage via Behave/unit fakes; **latency scored on a live
  real-provider sample** — Gradium streaming STT/TTS + the Java backend (`--backend http`, Mistral
  chat + Ollama embeddings + pgvector, 10 163 KB vectors).
- **Environment:** co-located dev host (voice runtime, Java backend, Postgres/Ollama all local);
  unit + Behave suites in `voice-agent/.venv`.

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

**Sample:** 16 warm calls, web channel, provider `gradium-streaming-websocket`, real Java
backend (`--backend http`), co-located dev host. Each call drives one ~4 s spoken-French billing
question (varied `fixtures/long/*.pcm`) at real-time cadence + an 800 ms trailing silence to
trigger the energy end-of-turn. Server-side per-call dumps parsed by
`scripts/streaming_latency_report.py`. Raw scored output versioned at
[`task-web-031-ws-latency-report.json`](./task-web-031-ws-latency-report.json).

| Slice | p50 | p95 | p99 | Warm | Notes |
|---|---:|---:|---:|---|---|
| channel_ingress | — | — | — | — | Not emitted on the WS path (no ingress span). Marked `measured=false`, never faked. |
| end_of_turn | 350 | 350 | 350 | ✅ | Fixed silence window (`PILOT_END_OF_TURN_SILENCE_MS`). |
| **stt** | 380 | **2250** | 2250 | ✅ | Gradium streaming finalization — scales with the ~4 s utterance. **#1 latency lever.** |
| **backend_first_token** | 714 | **1642** | 1642 | ✅ | Mistral first token after RAG retrieval. **#2 latency lever.** |
| tts_first_audio | 361 | 402 | 410 | ✅ | Gradium streaming TTS — already excellent, well inside budget. |
| channel_egress | 0 | 4 | 4 | ✅ | Runtime egress (first frame → WS transport), WS-labelled. Negligible. |
| **time_to_first_audio** | 1705 | **3325** | 3343 | ✅ | stt + backend_first_token + tts_first_audio. **ADR-0029 sub-target p95 ≤ 1.2 s → FAIL.** |
| **voice_to_first_audio (mouth-to-ear)** | 2055 | **3675** | 3693 | ✅ | + end_of_turn + channel_egress. **ADR-0029 primary p95 ≤ 1.5 s → FAIL.** |

**ADR-0029 gate result: FAIL.** mouth-to-ear p95 3675 ms exceeds the 1500 ms primary criterion by
2175 ms; time-to-first-audio p95 3325 ms exceeds the 1200 ms sub-target by 2125 ms. The median
mouth-to-ear (2055 ms) already exceeds the 1.5 s target, so this is not a tail-only miss.

**Root cause / levers (in priority order):**
1. **STT time-to-final (p95 2250 ms)** — Gradium finalizes after the full ~4 s utterance; the
   streaming *first partial* arrives at p50 ≈ 1494 ms but the *final* is the gating value. Lever:
   earlier end-pointing / partial-final acceptance / shorter test utterances representative of real
   turns (utterance length is reported here because batch/streaming STT latency scales with it).
2. **Backend first token (p95 1642 ms)** — RAG retrieval + Mistral first token. Lever: retrieval
   caching, warm-up (already present), a faster/co-located LLM, or a shorter prompt.
3. **TTS first audio (p95 402 ms)** and **egress (~4 ms)** are already inside budget — no action.

**Measurement caveat (honest):** on the single-client socle the server session persists across
reconnects, so each per-call dump accumulates all spans since server start (WEB-030 residual —
correlation id per server session, not per connection). Summed across 16 dumps the report counts
`n=136` span-instances per slice (= 1+2+…+16), over-weighting later turns. Every counted latency is
a **genuine real-provider measurement**; only the sample weighting is skewed. Given the fail margin
(> 2 s on both criteria and the p50 already over target) the conclusion is robust. A per-connection
correlation reset (carried from WEB-030) would make the sample weighting exact.

### Runbook (executed 2026-08-25 — reproducible)

`scripts/ws_live_client.py` drives a real `wss` turn so the server emits its per-call dump on
disconnect; `scripts/streaming_latency_report.py` scores the sample.

```bash
cd voice-agent
# 0. deps up: Postgres (pgvector) + Ollama; Java backend on :8080
(cd ../backend && set -a && . ../.env && set +a && mvn -q spring-boot:run)   # :8080
# 1. voice runtime — real providers + HTTP backend; capture per-call dumps
set -a; . ../.env; set +a; export VOICE_BACKEND_URL=http://127.0.0.1:8080
.venv/bin/python -m web_voice.server --provider gradium --backend http --websocket on \
    --stt-mode streaming --tts-mode streaming 2> /tmp/ws-telemetry.jsonl   # WS :8091
# 2. drive N warm turns (one call each), varied long fixtures
for f in fixtures/long/*.pcm; do
  .venv/bin/python scripts/ws_live_client.py --url ws://127.0.0.1:8091 \
    --audio "$f" --language fr --hold 12
done
# 3. score against the ADR-0029 gate (p50/p95/p99 per slice + go/no-go)
.venv/bin/python scripts/streaming_latency_report.py \
    --input /tmp/ws-telemetry.jsonl --channel web --provider gradium-streaming-websocket --warm
```

The harness prints a client-observed `mouth_to_ear_proxy_ms` per turn (a rough cross-check that
can go negative when first-audible-frame detection races the bot); the server dump carries the
authoritative per-slice truth used above.

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| WS latency harness (`ws_live_client.py`) | ✅ | Pure frame helpers unit-tested (`tests/test_ws_live_client.py`); drove 16 warm real-provider turns end to end | None — used to score the gate. |
| Latency report tool | ✅ | Scored the live WS sample with no change (same span names); WS-egress folded into mouth-to-ear; ADR-0029 gate evaluated | None. |
| STT slice (Gradium streaming) | ⚠️ | Real p95 time-to-final 2250 ms on ~4 s utterances — the dominant latency contributor | Lever #1 — earlier end-pointing / partial-final; track as follow-up. |
| Backend first-token (Mistral + RAG) | ⚠️ | Real p95 1642 ms | Lever #2 — retrieval cache / co-located or faster LLM. |
| TTS first audio (Gradium streaming) | ✅ | Real p95 402 ms — inside budget | None. |
| Functional Behave/unit coverage | ✅ | 10 WS scenarios across 4 features + unit suites green | None. |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| **High** | **ADR-0029 mouth-to-ear p95 = 3675 ms (target ≤ 1500 ms); TTFA p95 = 3325 ms (target ≤ 1200 ms) — gate FAILS** on the interim WS path with real providers | No pilot latency SLO can be claimed for the WS path as-is | Architecture/Product — plan STT/backend latency levers (out-of-sprint follow-up) |
| Medium | STT time-to-final (p95 2250 ms) and backend first-token (p95 1642 ms) dominate the budget | ~90 % of mouth-to-ear sits in these two slices | Follow-up latency ticket |
| Low | Correlation id is per WS server session, not per connection on the single-client socle (WEB-030 residual) → accumulated spans inflate the sample count (`n=136` = 1+2+…+16) | Sample weighting skewed toward later turns; per-span latencies still genuine; conclusion robust given the margin | Carried from WEB-030; per-connection reset for exact weighting |
| Low | Live `wss` barge-in mouth-to-ear + TCP head-of-line under loss not exercised under network impairment | Degraded-mode behaviour uncharacterised | QA follow-up |

## Open Questions

- **Product:** given the measured ADR-0029 FAIL, is the interim WS path acceptable for a
  functional demo only (no latency SLO), while the latency levers are scheduled separately?
- **Architecture:** which lever is prioritised first — STT end-pointing (biggest single win) or a
  co-located/faster LLM for backend first-token? Confirm whether per-connection correlation is
  needed before Genesys or whether "one session = one call" is acceptable for the pilot demo.
- **Technical:** none blocking; the harness + tool are ready and reproduce the score.

## Recommendation

- **Go / No-go:** **GO (functional)** for the interim external WebSocket demo — the journey (turn,
  barge-in, capacity refusal, per-slice observability, safe-failure surfaces) is covered and green.
  **NO-GO on the pilot latency SLO:** the ADR-0029 mouth-to-ear gate was scored on a warm
  real-provider sample and **FAILS** (p95 3675 ms vs 1500 ms; median already 2055 ms). No pilot
  latency SLO is claimed for the WS path as measured.
- **Required before any pilot SLO claim:** attack the two dominant levers — STT time-to-final
  (earlier end-pointing / partial-final acceptance) and backend first-token (retrieval cache /
  faster or co-located LLM) — then re-score with this same harness. Also characterise degraded
  modes (TCP head-of-line under loss, AEC without headphones). These are latency-optimisation
  follow-ups beyond the WEB-026…031 interim-transport scope.
