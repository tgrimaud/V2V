# QA Functional And Latency Report — Streaming Voice Loop (Sprint 6 close, TASK-WEB-009)

**Ticket:** TASK-WEB-009 — Streaming QA, latency SLO report and ADR update
**Branch:** `task/TASK-WEB-009-streaming-qa-latency`
**Stories:** US-019 (voice loop), US-036 (per-slice timing), US-021 (barge-in)
**Decision:** ADR-0018 (pilot criterion `time_to_first_audio` p95 < 800 ms)
**Run date:** 2026-07-16 (warm live sample)

> **Update 2026-07-17 (TASK-STT-013 + TASK-WEB-011): PILOT LATENCY GATE NOW MET.**
> Two levers closed the gap the baseline below surfaced:
> - **TASK-STT-013** — streaming STT finalizes on Gradium's `flushed` ack instead of
>   the terminal `end_of_stream` (zero word loss): `stt` p95 **1389 → 373 ms**,
>   `time_to_first_audio` p95 **1698 → 853 ms**
>   ([`streaming-latency-warm-postfix.json`](streaming-latency-warm-postfix.json)).
> - **TASK-WEB-011** — the TTS WebSocket is pre-warmed off the per-turn critical path
>   (~90 ms connect removed): `tts_first_audio` p95 **484 → 381 ms**,
>   `time_to_first_audio` p50/p95 **827/853 → 739/761.5 ms**
>   ([`streaming-latency-warm-prewarm.json`](streaming-latency-warm-prewarm.json)).
>
> **ADR-0018 gate: `time_to_first_audio` p95 761.5 ms < 800 ms → GO (margin +38.5 ms)**,
> warm, web channel, **stub backend** (a real answer path adds backend time; see
> caveats in the ADR post-fix baseline). Full arc: 1698 ms (−898) → 853 ms (−53) →
> 761.5 ms (+38.5). See [`stt-013-finalize-tail-spike.md`](stt-013-finalize-tail-spike.md).
> The original pre-fix baseline is preserved verbatim below.

> **QA acceptance 2026-07-17 (TASK-STT-013 + TASK-WEB-011): GO.** Following the
> adversarial review **93/100 (Pass, no blocking findings)**, QA re-ran the full
> regression net and re-confirmed the latency gate:
> - **Functional regression:** `315 unit tests OK`; **Behave 10 features / 26
>   scenarios / 120 steps** — green (run via `voice-agent/.venv`). Adds the
>   finalize-on-`flushed` STT tests and the `TtsSessionWarmer` + processor pre-warm
>   tests to the streaming net.
> - **Pilot latency gate:** [`streaming-latency-warm-prewarm.json`](streaming-latency-warm-prewarm.json)
>   `adr_0018_gate.status = pass`, `time_to_first_audio` p95 **761.5 ms < 800 ms**
>   (margin **+38.5 ms**), warm, web channel, N=8, stub backend.
> - **Accepted residual (unchanged):** stub backend (real answer time is a separate
>   budget line), `channel_egress` excluded, N=8; pre-warm warm/miss not yet a
>   dedicated metric (non-blocking review finding). No safety invariant regressed
>   (no invented transcript/audio, key never logged).
> - **QA verdict:** both tickets pass functional + latency acceptance → **merge-ready,
>   pending explicit user validation** (per the delivery workflow, merge stays a
>   user decision).

## Executive Summary
- **Overall readiness (functional):** Go — the streaming loop answers end to end
  (partials → answer → incremental first audio), barge-in interrupts playback, and
  error/degraded paths stay safe and observable.
- **Overall readiness (pilot latency):** **NO-GO on the pilot latency criterion.**
  The consolidated warm live sample (5 turns) measures `time_to_first_audio`
  **p50 1310 ms / p95 1698 ms**, ~2.1× over the ADR-0018 criterion of **p95 < 800 ms**
  (margin −898 ms). The dominant cost is the STT post-end-of-turn finalize tail
  (p95 ~1389 ms). Note this is with a **stub backend**, so a real BSS/RAG/LLM answer
  will only add to the composite.
- **Main blockers:** none functional. The pilot latency criterion is not met on the
  current streaming path (measured gap, not a silent pass).
- **Residual risks:** (1) `channel_egress` not instrumented on the WebRTC path, so
  the composite covers EOT → first synthesized audio (not the last transport hop);
  (2) one WebSocket per turn (setup/teardown cost); (3) live numbers depend on
  network path to Gradium and warm state.

## Scope Tested
- **Epics / stories:** EPIC-006 / EPIC-010; US-019, US-036, US-021.
- **Channels:** web voice (streaming WebRTC path, `SmallWebRTCTransport`).
- **Providers / fakes:** unit + Behave use fake streaming STT/TTS providers and the
  deterministic stub backend (no network); the latency baseline uses **Gradium
  streaming STT + streaming TTS** + stub backend over a real WebRTC session.
- **Environment:** local, `voice-agent/.venv`, `pipecat-ai[webrtc]`, macOS, warm
  (server process pre-warmed), co-located.

## Functional Results
| Area | Status | Evidence | Notes |
|---|---|---|---|
| Streaming loop answers end to end (partials → answer → incremental first audio) | Pass | `streaming_loop.feature`; live run | Composed streaming STT → answer → streaming TTS, one correlation id |
| Partial transcripts stream during speech | Pass | `streaming_stt.feature` #1; `streaming_loop.feature`; `test_streaming_stt_processor` | `InterimTranscriptionFrame` partials before end-of-turn |
| Final transcript after end-of-turn drives the answer | Pass | `streaming_loop.feature`; `stt.request` span emitted | Final consumed by the answer step (spoken back), not echoed |
| Bot answer starts on the first synthesized chunk | Pass | `streaming_tts.feature` #1; `streaming_loop.feature`; live run | Incremental `TTSAudioRawFrame`s |
| `time_to_first_audio` derivable end to end under one correlation id | Pass | `streaming_loop.feature`; `test_pipeline_timing.TimeToFirstAudioCompositeTest` | Composite = STT tail + backend + TTS first-audio |
| Barge-in interrupts playback and starts the next turn | Pass | `barge_in.feature` #1; `test_streaming_stt_processor` (barge-in) | `InterruptionFrame` broadcast; `tts.interrupted`; `voice.barge_in.detected` |
| Normal turn is not a barge-in (anti-echo gate) | Pass | `barge_in.feature` #2 | Amplitude + sustained-frame gate |
| Empty answer → UNAVAILABLE, no invented audio | Pass | `streaming_tts.feature` #2 | `tts.unavailable` (`empty_text`) |
| STT/TTS/turn error → client-safe 502, no raw provider text | Pass | `test_error_response`, `test_voice_runtime` (TASK-WEB-006) | Stable `error_code` + `correlation_id` + generic `message` |
| Trailing partial utterance drained on call end | Pass | `webrtc_signaling` drain-and-discard; `test_*` | A mid-speech hangup still yields an end_of_turn + final |
| Batch HTTP path + stdlib/fixture path unchanged | Pass | full suite green; `--stt-mode/--tts-mode batch` | Fallbacks preserved |

Regression net: **298 unit tests OK**; **Behave 10 features / 26 scenarios /
120 steps** (adds `streaming_loop.feature`, the `time_to_first_audio` composite
tests, `streaming_latency_report` tests, and the WebRTC teardown telemetry
regression test — a hanging `drain()` must stay bounded and still emit the dump).

## Latency Results

`time_to_first_audio` composite = `stt` (post-EOT finalize tail) +
`backend_first_token` (answer) + `tts_first_audio` (time-to-first-audio); the
end-of-turn silence hold ends at the composite's start, and `channel_ingress` /
`channel_egress` are batch-HTTP-only (WebRTC gaps). See
[voice-journey-timing](../observability/voice-journey-timing.md) and ADR-0018.

### Indicative warm single-turn (from Sprint 6 slice tickets)
Single warm live turns already measured per slice (Gradium streaming STT + TTS,
stub backend). These indicate the composite; the consolidated distribution is the
live run below.

| Slice / composite | Warm value | Source |
|---|---:|---|
| `voice.end_of_turn` (silence hold, ends at composite start) | ~500 ms | `stt-012-streaming-end-of-turn-qa.md` |
| `stt.request` (post-EOT finalize tail) | ~800 ms | `stt-010-streaming-stt-qa.md` |
| `backend_first_token` (stub) | ~few ms | stub backend, offline |
| `tts_first_audio` (time-to-first-audio) | ~363 ms | `web-004-streaming-tts-qa.md` |
| **`time_to_first_audio` (indicative composite)** | **~1.1–1.2 s** | sum of the post-EOT slices |

> Indicative composite **~1.1–1.2 s > 800 ms** pilot criterion. The dominant cost is
> the STT post-end-of-turn finalize tail (~0.8 s); backend (stub) and TTS first-audio
> are comparatively small. The optimization lever is the STT finalize tail (partial /
> incremental finalization), already reduced from ~3.4 s (batch) to ~0.8 s by
> TASK-STT-010.

### Consolidated warm sample (live run, 2026-07-16)

Gradium streaming STT + streaming TTS, stub backend, `pipecat` runtime, co-located
dev host, server pre-warmed. 7 warm calls streamed a real speech clip; **5 turns**
produced an STT finalize + first audio, **2 calls produced no turn telemetry** (see
Defects). Reproducible sample committed at
[`streaming-latency-warm-sample.json`](./streaming-latency-warm-sample.json).

| Field | Value |
|---|---|
| Sample size (turns) | 5 (from 7 warm calls) |
| `time_to_first_audio` p50 / p95 / p99 (ms) | 1310.4 / 1697.9 / 1697.9 |
| `time_to_first_audio` min / max / mean (ms) | 961.6 / 1697.9 / 1317.5 |
| `stt` p50/p95/p99 (ms) | 865.8 / 1388.6 / 1388.6 |
| `backend_first_token` p50/p95/p99 (ms) | 0.01 / 0.01 / 0.01 (stub) |
| `tts_first_audio` p50/p95/p99 (ms) | 309.3 / 478.9 / 478.9 |
| `end_of_turn` (silence hold, before composite start) | 500.0 / 500.0 / 500.0 |
| `channel_ingress` / `channel_egress` | Gap (batch-HTTP-only on WebRTC) |
| Pilot gate (`p95 < 800 ms`) | **FAIL** — measured p95 1697.9 ms, margin −897.9 ms |

Collected with the streaming report over server telemetry dumps:

```bash
cd voice-agent
set -a && source ../.env && set +a
python3 -m web_voice.server --host 127.0.0.1 --port 8090 \
  --provider gradium --backend stub --runtime pipecat \
  --webrtc auto --stt-mode streaming --tts-mode streaming 2> /tmp/streaming-telemetry.jsonl
# run N warm turns (browser /static/webrtc.html or scripts/webrtc_live_client.py)
python3 scripts/streaming_latency_report.py --input /tmp/streaming-telemetry.jsonl \
  --channel web --provider gradium-streaming --warm
```

### Provider baseline — TTS time to first audio buffer (2026-07-16)

The Gradium dashboard publishes its own "time to first audio buffer" percentiles
for the TTS API. On the same day as the consolidated sample, it reported
**min 186 ms / p50 330 ms / p90 364 ms / p95 364 ms**. Because our
`tts.time_to_first_audio_ms` metric measures the same thing one hop further out
(provider + network/transport + agent handling, over the `count=4` metric
distribution), the difference is the **transport/handling delta** our path adds on
top of the provider.

| Percentile | Gradium (provider, server-side) | Measured (`tts.time_to_first_audio_ms`) | Delta (measured − provider) |
|---|---:|---:|---:|
| min | 186 ms | 307 ms | +120 ms |
| p50 | 330 ms | 309 ms | −20 ms |
| p90 | 364 ms | — (not computed) | — |
| p95 | 364 ms | 479 ms | +115 ms |

Reading: on the median turn our path adds essentially nothing (co-located dev
host, negligible network on the typical case); the ~115 ms p95 gap is the
transport/handling cost surfacing on the slow tail. **Caveat:** the delta is not
pure transport — the sign flips (min +120 ms but p50 −20 ms), which only happens
because the two distributions have very different sample sizes: our side is
4–5 turns (p95 = p99 = max, and our fastest turn is not as fast as the provider's
best-of-a-full-day), while the provider p95 is over a full day of calls and is far
more robust. Treat this as directional until a larger warm sample lands (see the
Sprint 6 "Out Of Sprint" follow-up, blocked on Gradium credit). This still
confirms the TTS brick is **not** the latency blocker; the dominant cost remains
the STT post-EOT finalize tail (p95 ~1389 ms).

Regenerate the comparison by passing the published provider percentiles to the
report:

```bash
python3 scripts/streaming_latency_report.py --input /tmp/streaming-telemetry.jsonl \
  --channel web --provider gradium-streaming --warm \
  --tts-baseline "min=186.36,p50=329.53,p90=364.19,p95=364.19" \
  --tts-baseline-source "Gradium dashboard 2026-07-16"
# -> adds a "provider_baseline" section with per-percentile delta_ms (measured - provider)
```

## Mouth-To-Ear Composite (TASK-WEB-014, ADR-0029)

TASK-WEB-014 closes the ADR-0018 / TASK-WEB-009 `channel_egress` + end-of-turn known
gap and instruments the **mouth-to-ear** metric the market actually measures:

- **`voice_to_first_audio` composite** (`voice_common/pipeline_timing.py`) = end-of-turn
  hold + STT + backend + TTS + `channel_egress`, per turn under one correlation id,
  reported alongside `time_to_first_audio`. Egress is folded per turn when present and
  reported as an explicit residual gap otherwise (never a silent zero).
- **`channel_egress` on WebRTC** (`web_voice/channel_egress_probe.py`): the
  `ChannelEgressProbe` sits between TTS and the transport output and times the runtime
  egress of the first audio frame of each spoken turn, emitting the same
  `web.voice.egress` span the batch path uses — so the CHANNEL_EGRESS slice is now
  measured on the streaming path (previously batch-HTTP-only).
- **ADR-0029 gate** in `scripts/streaming_latency_report.py`: mouth-to-ear p95 ≤ 1.5 s
  (primary) + `time_to_first_audio` p95 ≤ 1.2 s (engineering); overall `not_measured`
  when either has no complete turn (never a silent pass).
- **Residual browser-audible gap** (RTP encode/packetize + network + jitter buffer +
  playout) is not server-observable; the headless client
  (`scripts/webrtc_live_client.py`) logs a client-side first-audible proxy
  (`mouth_to_ear_proxy_ms`) to close it during a live sample.

Developer coverage: `tests/test_pipeline_timing.py` (composite computation, fake
spans), `tests/test_channel_egress_probe.py` (egress emission on the WebRTC path),
`tests/test_streaming_latency_report.py` (mouth-to-ear + ADR-0029 gate). Full suite:
unittest **334** green, behave **10 features / 26 scenarios / 120 steps** green.

**Pending before pilot sign-off (honest gap):** a **warm live sample against the real
backend** to record measured `voice_to_first_audio` p50/p95/p99 and evaluate the
ADR-0029 gate. The instrumentation and gate are in place; the measured mouth-to-ear
number is the remaining input (ticket is an out-of-sprint pre-pilot measurement).

## Component Findings
| Brick | Status | Findings | Next action |
|---|---|---|---|
| Streaming STT | Pass | Partials during speech; finalize tail ~0.8 s dominates the composite | STT partial-finalization optimization (out of sprint) |
| Backend answer | Pass | Stub negligible; a live HTTP backend would add its own slice | Measure with `--backend http` when a live endpoint is available |
| Streaming TTS | Pass | First audio ~363 ms; incremental playback stable | Reuse/multiplex the WebSocket (out of sprint) |
| Barge-in | Pass | Interrupts playback; anti-echo gate holds on normal turns | — |
| Observability | Pass | One correlation id per call; spans + metrics dumped on teardown | — |
| Channel egress (WebRTC) | Pass | Instrumented by `ChannelEgressProbe` (TASK-WEB-014): runtime egress of the first frame per turn, folded into `voice_to_first_audio` | Capture browser-audible residual via the client first-audible proxy in a live sample |

## Defects And Gaps
| Severity | Finding | Impact | Owner |
|---|---|---|---|
| High | Measured `time_to_first_audio` p95 1698 ms > 800 ms (with stub backend) | Pilot latency criterion not met; STT finalize tail is the lever | QA / Architecture (measured gap) |
| Medium | 2 of 7 warm calls produced no turn telemetry (empty session) | Reliability/measurement caveat; likely the headless client replaying the same clip in rapid succession rather than a server defect, but unconfirmed | Follow-up (out of sprint) |
| Resolved | `channel_egress` not measured on WebRTC | Closed by TASK-WEB-014 (`ChannelEgressProbe` + `voice_to_first_audio` mouth-to-ear composite); browser-audible residual is a stated gap covered by the client proxy | Done |
| Info | One WebSocket per turn | Setup/teardown cost | Backlog (out of sprint) |

## Open Questions
- **Product:** is a functional pilot acceptable with `time_to_first_audio` p95 ~1.7 s
  while the STT finalize tail is optimized, or is `p95 < 800 ms` a hard pilot gate?
- **Architecture:** ~~should the WebRTC channel-egress hop be instrumented before the
  pilot?~~ **Resolved (TASK-WEB-014):** yes — `channel_egress` is now instrumented on
  the WebRTC path and folded into the `voice_to_first_audio` mouth-to-ear composite
  (ADR-0029), with the browser-audible residual covered by the client first-audible
  proxy. Remaining: capture the warm live sample.
- **Technical:** target for the STT post-EOT finalize tail (main lever to reach
  `p95 < 800 ms`); with the tail at p95 ~1.39 s it alone exceeds the whole budget.

## Recommendation
- **Functional:** Go — the streaming loop, barge-in and safe-failure paths meet their
  acceptance criteria with unit + Behave regression coverage.
- **Pilot latency:** **GO (margin +38.5 ms).** After TASK-STT-013 (finalize on
  `flushed`) and TASK-WEB-011 (TTS WebSocket pre-warm), the warm sample measures
  `time_to_first_audio` **p95 761.5 ms < 800 ms** (STT tail p95 373 ms, `tts_first_audio`
  p95 381 ms). Full arc: 1698 ms (−898) → 853 ms (−53) → 761.5 ms (+38.5). **Caveats:**
  measured with a **stub backend** (the real BSS/RAG/LLM answer time is a separate
  budget line, not in this EOT→first-audio number), `channel_egress` still excluded,
  N = 8 warm turns. The streaming voice path meets the pilot latency criterion as
  specified; a production SLO claim still needs a real backend + the ADR-0010
  operational controls.
- **Required before an SLO claim (ADR-0010):** per-channel/per-step dashboards,
  alerting, degraded-mode and provider-outage tests — out of this sprint.
