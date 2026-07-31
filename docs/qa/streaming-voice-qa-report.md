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

**Warm live sample against the real backend — captured 2026-07-29** (see the next
section). The instrumentation and gate are in place and now fed by a real mouth-to-ear
measurement: `voice_to_first_audio` p95 **≈ 4.1–4.4 s** over the streaming WebRTC path
with the real backend (Gradium streaming STT/TTS + Mistral + Ollama + pgvector) →
**ADR-0029 gate FAIL** (criterion ≤ 1.5 s). This is the measurement TASK-WEB-014 was
missing; the go/no-go is **NO-GO on the pilot latency gate as-is**, dominated by the
serial STT (~1 s) + backend (~1 s) slices — exactly the cost the TASK-WEB-015 levers 1
(SSE first-sentence streaming) and 2 (connect-time warm-up) target.

## Live Pilot Pass — Real Backend Mouth-To-Ear + Lever-3 Before/After (2026-07-29)

**Tickets:** TASK-WEB-014 (mouth-to-ear live closure) + TASK-WEB-015 lever 3 (end-of-turn
hold behavioural acceptance). **Branch:** `task/TASK-WEB-015-latency-levers`.
**Config:** streaming WebRTC (`/webrtc.html`), `--provider gradium --backend http
--stt-mode streaming --tts-mode streaming`, **real backend** (Mistral chat + Ollama
`nomic-embed-text` + pgvector), co-located dev host, warm server, headphones, natural
human turns with clear pauses. Two live sessions were captured with only the end-of-turn
hold changed: **500 ms** (default) then **350 ms** (`VOICE_END_OF_TURN_SILENCE_MS=350`).
Evidence: [`streaming-latency-eot500-live-2026-07-29.json`](./streaming-latency-eot500-live-2026-07-29.json),
[`streaming-latency-eot350-live-2026-07-29.json`](./streaming-latency-eot350-live-2026-07-29.json).

### Per-slice + composite (ms)

| Slice / composite | 500 ms p50 / p95 | 350 ms p50 / p95 | Note |
|---|---:|---:|---|
| `end_of_turn` (hold) | 500 / 500 | **350 / 350** | **−150 ms deterministic** (the only controlled change) |
| `stt` | 940 / 1780 | 1169 / 2367 | dominant; varies by utterance length/session |
| `backend_first_token` | 1012 / 2550 | 943 / 2002 | dominant; full LLM answer waited before TTS (no lever 1 yet) |
| `tts_first_audio` | 209 / 376 | 206 / 375 | flat — pre-warmed (TASK-WEB-011) ✅ |
| `channel_egress` (runtime) | ~0.05 | ~0.05 | runtime egress; browser-audible add-on is a stated residual gap |
| **`time_to_first_audio`** | 2271 / **3948** | 2480 / **3790** | ADR-0029 sub-target ≤ 1200 ms → **FAIL** |
| **`voice_to_first_audio` (mouth-to-ear)** | 2771 / **4448** | 2830 / **4140** | ADR-0029 primary ≤ 1500 ms → **FAIL** |

Sample: 500 ms run = 6 turns (all with complete composite); 350 ms run = 10 turns (6 with
a complete first-audio chain). At N=6 the p95 equals the max, so the cold **turn 1** (m2e
4448 ms at 500 ms / 4140 ms at 350 ms) sets the p95; warm turns range ~2.1–3.3 s m2e.

### ADR-0029 gate

| Metric | Criterion p95 | 500 ms measured | 350 ms measured | Verdict |
|---|---:|---:|---:|---|
| mouth-to-ear (`voice_to_first_audio`) | ≤ 1500 ms | 4448 ms (−2948) | 4140 ms (−2640) | **FAIL** |
| `time_to_first_audio` | ≤ 1200 ms | 3948 ms (−2748) | 3790 ms (−2590) | **FAIL** |

**Go/no-go: NO-GO on the pilot latency gate as-is.** The real-backend mouth-to-ear p95
(~4.1–4.4 s) is ~2.7× over the ≤ 1.5 s criterion, dominated by the two serial slices
**STT (~1 s p50)** + **backend first-token (~1 s p50)**. TTS is already flat (pre-warmed).

### Lever-3 behavioural acceptance (500 → 350 ms)

- **Gain:** the `end_of_turn` slice drops exactly **−150 ms** (500.0 → 350.0), deterministic
  and reversible via env var (250 ms safe floor enforced, verified by the clamp test).
- **Cost (false-cut rate):** every end-of-turn was a clean `silence_window` signal —
  **0/6 at 500 ms and 0/10 at 350 ms** premature `client_stop` cuts. No premature-endpoint
  regression observed at 350 ms in a calm, headphones, clear-pause session.
- **Composite is noise-dominated:** the −150 ms is swamped by STT/backend session-to-session
  variance (the 350 ms session happened to draw slower STT, p50 1169 vs 940 ms), so the
  mouth-to-ear composite does **not** show a clean 150 ms improvement — expected, since the
  hold is <5 % of a ~2.8 s warm `time_to_first_audio`.
- **Verdict — lever 3 accepted, deployable:** adopt `VOICE_END_OF_TURN_SILENCE_MS=350` as
  the tuned pilot default (free −150 ms, 0 observed false-cuts, reversible). **Residual:**
  0/10 in one calm session is not a strong statistical guarantee; the false-cut risk in a
  noisy environment stays to be watched (env-tunable, so reversible without a redeploy).
  Lever 3 **alone does not move the ADR-0029 gate** — that needs levers 1 & 2.

### Spoken filler (TASK-WEB-019) observed live

The generic spoken filler fired on the slowest turns (500 ms run: 1× on the cold turn 1;
350 ms run: 2×, turns 1 and 10), each at `wait_ms=1200`, `provider=http-backend`, and did
**not** pollute the `tts_first_audio` distribution (flat 202–376 ms) — confirming both the
US-020 behaviour and the "filler must not skew `tts_first_audio` p95" invariant in a real
call.

### What this pass establishes

1. **TASK-WEB-014 measurement is now real** (not stub, not fixture): mouth-to-ear p95
   ≈ 4.1–4.4 s with the real backend → the honest pilot number the ticket was missing.
2. **Levers 1 & 2 are confirmed as the decisive work** (STT + backend own ~2 s of the
   composite; TTS + hold are already small), validating the ADR-0037 prioritisation.
3. **Lever 3 is behaviourally safe at 350 ms** in this environment and is a keeper as a
   tuned default, but marginal against the gate.

## Live Lever-2 Pass — Connect-Time Warm-Up Before/After (2026-07-30)

**Tickets:** TASK-WEB-021 (connect-time warm-up runtime) consuming TASK-BE-017
(`POST /api/conversation/warm-up`). **Branches:** runtime on
`task/TASK-WEB-021-connect-time-warmup`; the backend `/warm-up` endpoint was run from a
`git worktree` of `task/TASK-BE-017-voice-latency-support` (no merge). **Config:**
streaming WebRTC (`/webrtc.html`), `--provider gradium --backend http --stt-mode
streaming --tts-mode streaming`, hold **350 ms**, **real backend** (Mistral chat + Ollama
`nomic-embed-text` + pgvector), co-located dev host, headphones. Two runs with only the
lever-2 flags changed, backend restarted cold + Ollama model evicted before each:
**control** (`VOICE_STT_PREWARM=0`, `VOICE_BACKEND_WARMUP=0`) vs **treatment**
(`VOICE_STT_PREWARM=1`, `VOICE_BACKEND_WARMUP=1`). Evidence:
[`streaming-telemetry-lever2-control-2026-07-30.jsonl`](./streaming-telemetry-lever2-control-2026-07-30.jsonl),
[`streaming-telemetry-lever2-treatment-2026-07-30.jsonl`](./streaming-telemetry-lever2-treatment-2026-07-30.jsonl).

### Mechanism confirmed live (the primary acceptance signal)

- **Backend warm-up:** `voice.backend.warmup = success` fired at connect on **both**
  treatment sessions (`provider=http-backend`); **zero** warm-up/prewarm events in the
  control run (flags off, as expected).
- **STT pre-warm:** `voice.stt.prewarm = hit` on the **first** STT open of each treatment
  session → **Gradium preserves the pre-opened idle socket** across the connect → first
  utterance window, and the spare is reused on turn 1. Subsequent opens report `cold`
  **by design** (the warmer pre-opens exactly one spare, consumed by turn 1; later
  utterance segments open on demand). **No `fallback` and no leak** observed — the opt-in
  `VOICE_STT_PREWARM=1` is validated live in this environment.
- **Turn-1 is flat with warm turns:** treatment turn-1 `stt.request` **379 ms** vs warm
  turns 377–413 ms (no socket-open penalty); treatment turn-1 `backend.first_token`
  **835 ms / 190 ch = 4.4 ms/ch** sits inside the warm-turn band (3.2–3.7 ms/ch) — the
  turn-1 backend cold cost was pre-paid off the critical path.

### Composite (noisy — read with the micro-benchmark below)

| Metric | Control p50 / p95 | Treatment p50 / p95 | Note |
|---|---:|---:|---|
| `voice_to_first_audio` (m2e) | 1954 / 2632 | 1940 / **2242** | p95 **−390 ms** (worst-turn, n=5, p95=max); p50 flat |
| `time_to_first_audio` | 1604 / 2282 | 1590 / 1892 | −390 ms p95 |

Both runs sit far below the 2026-07-29 baseline (m2e p95 4.1–4.4 s) because this session
drew **short STT finalizes (~380 ms)** — confirming the composite is dominated by
STT-finalize + LLM-generation-length variance, not cold-start. The lever-2 effect is a
**turn-1-only** reduction, so it shows on p95 (worst/first turn) but not p50, and neither
run passes ADR-0029 (≤ 1500 ms). **Comparing turn-1 composites across runs is comparing
noise**; the deterministic micro-benchmark below is the clean signal.

### Deterministic backend micro-benchmark (isolates cold-start)

Fixed transcript (`"pourquoi ma facture a augmenté ce mois-ci"`), backend restarted cold
+ Ollama evicted per phase, timing `POST /converse` calls. Per-phase **call-1 overhead =
call-1 − mean(calls 2–5)** (answer length ~constant, so this isolates the cold-start):

| Phase | warm-up first? | call-1 | warm steady mean | call-1 cold overhead |
|---|---|---:|---:|---:|
| A | no | 1450 ms | 1002 ms | **+448 ms** |
| A2 | no | **8503 ms** (empty answer, cold outlier) | ~950 ms (tail) | **multi-second** |
| B | yes | 1174 ms | 873 ms | +301 ms |
| B2 | yes | 1315 ms | 928 ms | +387 ms |

- `/warm-up` itself costs **~0.7–1.4 s** of off-critical-path work at connect
  (`fully_warmed: true`, embedding + LLM warmed) — a cost that never touches a turn.
- **Without warm-up** the turn-1 backend cold penalty is **+448 ms typical and can spike
  to multiple seconds** (A2: cold first Mistral call + JVM JIT produced an 8.5 s call-1).
- **With warm-up** the turn-1 backend is **bounded to ~1.2–1.3 s** (residual overhead
  ~300–390 ms).
- **Residual ~300 ms remains after warm-up:** `/warm-up` warms embedding + one LLM call
  but **not the full converse critical path** (RAG/pgvector retrieval, guardrail,
  sentence emitter first-hit JIT). **Follow-up:** have `/warm-up` run a full dummy
  converse so those paths JIT-compile off the critical path too.

### Measurement-fidelity findings (important for future latency work)

- **`backend.first_token` currently equals the full converse time** (no lever 1 yet), so
  the backend slice **scales with answer length** (control: 227 ms / 38 ch vs
  1532 ms / 147 ch same session). Normalise by `answer_chars` (ms/char) before comparing
  backend slices across turns/runs.
- **Ollama keeps `nomic-embed-text` resident ~5 min**, and the backend's **startup KB
  ingestion re-warms it at boot** — so a plain Spring cold restart is **not** an embedding
  cold state. Evict the model (`ollama stop nomic-embed-text`) to measure a true cold
  embedding.

### Verdict

- **TASK-WEB-021 mechanism accepted:** backend warm-up and STT pre-warm both fire at
  connect, succeed against the real backend/Gradium, remove the turn-1 socket-open and
  bound the turn-1 backend cold penalty, with correct observability and no leak/fallback.
- **Impact is real but turn-1-only and modest at p50** (≈ −150 ms deterministic backend
  saving, larger when the cold outlier is avoided; STT socket-open removed on turn 1).
  Lever 2 **does not move the ADR-0029 gate on its own** — that needs **lever 1**
  (stream the first vetted sentence to TTS), which owns the dominant STT-finalize +
  full-LLM-answer wait.
- **STT pre-warm default:** live evidence is positive (hit, no fallback) but small
  (2 sessions); keep `VOICE_STT_PREWARM` opt-in for now, ready to flip default-on after a
  larger sample.

## Live Lever-1 Pass — First-Sentence Streaming Before/After (2026-07-30)

**Ticket:** TASK-WEB-020 (stream the first vetted sentence to TTS) consuming the backend
`POST /converse-stream` SSE contract (ADR-0013). **Branch:**
`task/TASK-WEB-020-first-sentence-stream`. **Config:** streaming WebRTC (`/webrtc.html`),
`--provider gradium --backend http --stt-mode streaming --tts-mode streaming`, hold
**350 ms**, **real backend** (Mistral chat + Ollama `nomic-embed-text` + pgvector),
co-located dev host, headphones. Backend was **warm and identical for both runs** (a
`/converse-stream` curl pre-warmed the LLM/RAG path); the **only** variable changed
between runs is `VOICE_BACKEND_STREAM`: **control** (unset → blocking `/converse`, whole
answer waited before TTS) vs **treatment** (`=1` → first vetted sentence streamed to TTS).
5 warm turns per run, same question list, same order. Evidence:
[`streaming-telemetry-lever1-control-2026-07-30.jsonl`](./streaming-telemetry-lever1-control-2026-07-30.jsonl),
[`streaming-telemetry-lever1-treatment-2026-07-30.jsonl`](./streaming-telemetry-lever1-treatment-2026-07-30.jsonl).

### Mechanism confirmed live (the primary acceptance signal)

- **Streaming path taken:** `voice.backend.streamed = success` fired on **all 5**
  treatment turns (`provider=http-backend`); the control run shows **5×
  `voice.backend.answered`** and **zero** `streamed` events (blocking path, as expected).
- **DEC-002 preserved:** every streamed turn reported **`grounded=true`**; per-sentence
  grounding + output guardrail runs backend-side before each `chunk` (the curl warm-up
  showed the 3-sentence `chunk`→`chunk`→`chunk`→`done{grounded:true}` shape). No invented
  amount, no un-said sentence.
- **`backend.first_token` now stamps the first sentence** on the streamed path (14
  `voice.tts.first_audio` spans over 5 turns = the bot speaks sentence-by-sentence)
  vs the whole answer on the blocking path (9 spans = 5 answers + 4 fillers).
- **Filler coherence holds live:** fillers dropped **4 (control) → 1 (treatment)** — the
  first vetted sentence usually arrives before the holding-phrase threshold (TASK-WEB-019),
  so the filler rarely fires and there is no double-speak.
- **Barge-in intact:** 4 barge-ins observed in **both** runs; no post-cancel speech, no
  stuck stream.

### Per-slice + composite before/after (ms, warm, n=5)

| Metric (p50 / p95) | Control OFF | Treatment ON | Δ p50 | Δ p95 |
|---|---:|---:|---:|---:|
| `end_of_turn` | 350 / 350 | 350 / 350 | 0 | 0 |
| `stt` | 450.5 / 486.9 | 374.7 / 423.9 | −76 | −63 |
| **`backend_first_token`** | **1435.9 / 3481.5** | **777.6 / 1599.0** | **−658** | **−1883** |
| `tts_first_audio` | 389.3 / 580.1 | 353.2 / 378.9 | −36 | −201 |
| `time_to_first_audio` (stt+backend+tts) | 2346.8 / 4498.7 | 1480.5 / 2176.1 | −866 | −2323 |
| **`voice_to_first_audio` (mouth-to-ear)** | **2696.9 / 4848.7** | **1830.6 / 2526.1** | **−866** | **−2323** |

> **Read the backend slice as the lever, the composite as the fair comparison.**
> `backend_first_token` semantics differ by design across runs (control = full answer;
> treatment = first vetted sentence) — that difference *is* lever 1. `voice_to_first_audio`
> is the apples-to-apples end-to-end measure, and it drops **−866 ms at p50**. The control
> p95 (4849 ms) is inflated by one longer-answer turn (backend 3481 ms); even excluding it,
> control backend p50 ≈ 1436 ms vs treatment ≈ 778 ms.

### ADR-0029 gate (mouth-to-ear p95 ≤ 1500 ms)

| Run | m2e p50 | m2e p95 | Gate margin @ p95 | Status |
|---|---:|---:|---:|---|
| Control OFF | 2696.9 | 4848.7 | −3348.7 | fail |
| Treatment ON | 1830.6 | 2526.1 | −1026.1 | fail (much closer) |

Lever 1 is the **single biggest mover** measured so far (−866 ms p50, −2323 ms p95 on the
composite) and pulls the **median to 1831 ms**, but **does not close the gate alone**: the
residual p95 (2526 ms) is still owned by `end_of_turn` (350, fixed) + `stt` finalize
(~375–424) + `backend_first_token` (778/1599, the first-sentence LLM generation + RAG) +
`tts_first_audio` (~200–379). Closing to ≤ 1500 ms needs lever 1 **combined** with the STT
finalize-tail work and the residual backend warm-up follow-up (full dummy converse JIT).

### Cold-start pass (lever 1 ON, no warm-up) — 2026-07-31

To size the residual gate distance in real pilot conditions (first turn of a conversation),
a **cold** pass with the same config but **lever 1 ON, warm-up OFF**
(`VOICE_BACKEND_STREAM=1`, `VOICE_BACKEND_WARMUP=0`, `VOICE_STT_PREWARM=0`): backend restarted
**cold** (fresh JVM → cold JIT) and the Ollama embedding **evicted** (`ollama stop
nomic-embed-text`) so turn 1 pays the model reload. Same 5-question script (7 answered turns
captured). Evidence:
[`streaming-telemetry-lever1-cold-2026-07-31.jsonl`](./streaming-telemetry-lever1-cold-2026-07-31.jsonl).

| Turn | `backend_first_token` (ms) | mouth-to-ear (ms) |
|---|---:|---:|
| **1 (cold)** | **2042.0** | **3124.4** |
| steady (turns 2+) p50 | ~636 | ~1623 |

- **The cold first turn is the p95 driver:** cold-inclusive `voice_to_first_audio` p95 =
  **3124 ms** (= turn 1), ADR-0029 margin **−1624 ms**; the steady turns settle to ~1623 ms
  p50 (matching the warm treatment run).
- **The cold overhead lives in the backend slice:** turn-1 `backend_first_token` **2042 ms**
  vs steady ~640 ms → **≈ +1400 ms** cold penalty (JVM JIT of the converse path + Ollama
  embedding reload + first Mistral call), i.e. **≈ +1500 ms on mouth-to-ear**.
- **Lever 1 does not reduce this penalty** — it is a per-sentence effect, and the first
  sentence itself is delayed by the cold backend. **The turn-1 cold spike is lever 2's job**
  (connect-time warm-up pre-pays JIT/embedding/first-LLM off the critical path). Barge-in
  held (5 detected, 2 `tts.interrupted` mid-stream, no stuck stream).
- **Consequence for the gate:** closing ADR-0029 (≤ 1500 ms p95) needs **lever 1 + lever 2
  together** (lever 2 to pull the turn-1 spike from ~3.1 s toward the ~1.6–1.8 s steady band),
  **plus** STT finalize-tail reduction to bring even the steady p95 (~1.85 s warm) under
  1500 ms. Lever 1 alone caps the steady turns; it cannot cap the cold worst case.
- **Combined cold pass (lever 1 + lever 2) is worthwhile but needs the TASK-BE-017 backend**
  (`POST /warm-up`), which is not on this branch — run it from a BE-017 `git worktree` as the
  lever-2 pass did, lever 1 ON in both arms, comparing turn-1 cold with warm-up OFF vs ON.

### Verdict — GO to enable the flag on the pilot channel

- **TASK-WEB-020 accepted, deployable:** the streaming path fires on every turn, delivers a
  measured **−658 ms median** on its target slice and **−866 ms median mouth-to-ear**
  (within/above the −700–900 ms expectation), preserves DEC-002 (5/5 grounded), keeps
  filler coherence (no double-speak) and barge-in, with correct US-036 telemetry.
- **Enable `VOICE_BACKEND_STREAM=1` in the pilot deployment** — it is a strict improvement
  with no observed regression and no DEC-002 risk. Keep the **code default OFF** until a
  larger warm+cold sample confirms stability (this pass is n=5 warm on a co-located host).
- **Gate status unchanged:** ADR-0029 (≤ 1500 ms p95) is **not yet met**; lever 1 is
  necessary but not sufficient. Combine with STT finalize-tail reduction + the lever-2
  full-converse warm-up follow-up to attempt closure.

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
