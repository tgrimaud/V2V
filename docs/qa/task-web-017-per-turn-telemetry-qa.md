# QA Functional And Latency Report — TASK-WEB-017 (Per-turn identity on WebRTC streaming telemetry)

## Executive Summary
- **Overall readiness:** Go — done. Each streaming turn is individually traceable and
  the report derives per-turn slices from a single multi-turn call. Confirmed on a
  **warm live Gradium STT/TTS + Mistral** multi-turn WebRTC session (3 turns, one
  `correlation_id`/`conversation_id`, 3 distinct `message_id`).
- **Main blockers:** none.
- **Residual risks:** none for this ticket. The live composite latency exceeds the
  ADR-0018/ADR-0029 gates, but that is **pre-existing STT-finalize latency** (Gradium
  batch-style finalize ~4 s), tracked by TASK-STT-010/011 (streaming/partial STT), and
  is **out of WEB-017 scope** (observability-only). WEB-017's contribution is that these
  per-turn numbers are now *derivable at all* — previously the streaming path collapsed
  all turns under one span name (no `turn_index`/`conversation_id`/`message_id`).

## Scope Tested
- **Epics / stories:** EPIC-006 (Voice2Voice) — observability hardening; feeds US-036
  (per-slice latency), ADR-0018 / ADR-0029 (latency gates), ADR-0028 (correlation).
- **Ticket:** TASK-WEB-017 — per-turn id on the streaming path while keeping a stable
  per-conversation `correlation_id`.
- **Channels:** web voice (WebRTC streaming path). Batch `/api/voice/turn` is out of
  scope (already one envelope per turn — regression-checked green).
- **Providers / fakes:** unit + Behave + the QA sample use fake streaming STT/TTS and the
  deterministic stub backend, driven through the **real** streaming processors
  (`StreamingSttProcessor` → `AnswerProcessor` → `StreamingTtsProcessor`), so the loop is
  offline and repeatable.
- **Environment:** local, `voice-agent/.venv`, `pipecat-ai` 1.5.0, macOS, warm.

## Functional Results
| Area | Status | Evidence | Notes |
|---|---|---|---|
| Each streaming turn's spans carry a unique per-turn id + stable `correlation_id` | Pass | `streaming_loop.feature` #2 (multi-turn), `test_telemetry_turn_baggage.py` | `turn_index` ∈ {1,2,…}, distinct `message_id` per turn, one `correlation_id` per call |
| `conversation_id`/`message_id` no longer `None` on the streaming path | Pass | QA sample dump attribute scan: `conversation_id`, `message_id`, `turn_index` present on every slice span | Was `None` pre-WEB-017 |
| Per-turn id stamped on **all** slice spans (STT + backend + TTS + egress), not just STT | Pass | `streaming_loop.feature` #2 "every slice span … carries a per-turn id"; dump span names all carry id | Proves cross-processor propagation via recorder baggage |
| Turn owner advances the id at each end-of-turn (live path) | Pass | `test_streaming_stt_processor.py` per-turn stamping tests | Fresh `message_id`, monotonic `turn_index` |
| Turn owner advances the id (batch-bridge path) | Pass | `test_utterance_aggregator.py` per-turn stamping tests | Parity with live path |
| `streaming_latency_report.py` derives per-turn slices from one multi-turn call, no overwrite | Pass | `scripts/streaming_per_turn_sample.py` → report `per_turn`: 2 calls × 3 turns, 6 distinct rows | See Latency Results |
| Multi-turn bucketing by `(correlation_id, turn_index)` + barge-in incomplete turn | Pass | `test_pipeline_timing.py` per-turn tests (barge-in turn → null composite, no desync) | Interrupted turn keeps null composite, others intact |
| Conversation trace still followable end to end (correlation stability) | Pass | Single `correlation_id` per call across all turns/slices | Meaning of `correlation_id` unchanged |
| Legacy / pre-WEB-017 samples (no per-turn id) still reconstructed | Pass | `test_pipeline_timing.py` positional-zip fallback tests | `per_turn` empty on old samples; no crash |
| **Live** WebRTC path stamps per-turn id on real Gradium+Mistral turns | Pass | Live call `3bcf0fac…`: `turn_index` 1/2/3, 3 distinct `message_id`, one `conversation_id`, every slice span once per turn | The real fix, confirmed on the live transport |
| Barge-in during a multi-turn live call does not corrupt per-turn separation | Pass | Live `barge_in_count=2`, all 3 turns still have a clean first-audio + own slices | Barge-in-safe bucketing holds live |
| No API key / raw audio / file-path leak in telemetry | Pass | Offline + **live** dump attribute scan: only id/latency/provider/outcome keys; leak regex empty | Attribute allowlist unchanged |

Regression net: **unittest 346 OK** (+12 for this ticket); **Behave 10 features / 27
scenarios / 126 steps OK** (+1 multi-turn scenario).

## Latency Results

### Live warm sample — Gradium STT/TTS + Mistral (the WEB-017 evidence)
One warm WebRTC call, 3 turns, headless `scripts/webrtc_live_client.py` driving a
multi-utterance clip; `--backend http` → Java/Mistral; server telemetry parsed by
`streaming_latency_report.py`. `correlation_id 3bcf0fac…`, `conversation_id 1e5b912d…`,
`turn_index` 1/2/3 with 3 distinct `message_id`. Every slice span appears **once per
turn** (no overwrite):

| Turn | `end_of_turn` | STT (final) | backend (first token, Mistral) | TTS first audio | **time_to_first_audio** | mouth-to-ear |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 500 ms | 3704 ms | 1075 ms | 375 ms | **5154 ms** | 5654 ms |
| 2 | 500 ms | 4181 ms | 1207 ms | 351 ms | **5740 ms** | 6240 ms |
| 3 | 500 ms | 4041 ms |  925 ms | 384 ms | **5350 ms** | 5850 ms |

Aggregate over the 3 turns (warm): `time_to_first_audio` p50 **5350 ms** / p95 **5740 ms**;
mouth-to-ear p50 **5850 ms** / p95 **6240 ms**. STT `time_to_first_partial` p50 **2390 ms**.
`barge_in_count = 2` observed — and **all 3 turns still produced a clean first-audio with
per-turn separation intact**, confirming the barge-in-safe bucketing.

> **SLO context (not a WEB-017 defect):** these exceed the ADR-0018 `time_to_first_audio`
> p95<800 ms and ADR-0029 mouth-to-ear p95≤1.5 s gates. The cause is **STT-finalize
> latency** (Gradium batch-style finalize ~4 s dominates every turn), the known latency
> lever owned by **TASK-STT-010/011** (streaming/partial STT), not this observability
> ticket. WEB-017 changes no latency — it makes the per-turn breakdown *derivable*, which
> was impossible before (turns collapsed under one span name). The gate evaluation is
> reported honestly as `fail` and routed to the STT streaming work.

### Offline structural sample (regression-friendly, no paid providers)
`scripts/streaming_per_turn_sample.py | streaming_latency_report.py` (2 calls × 3 paced
turns) drives the **real** streaming processors with fakes: 6 distinct per-turn rows,
distinct `message_id` under one `correlation_id`, one `time_to_first_audio` per turn.
Fixture-fast durations (~0.02–0.06 ms) — proves the slices are wired, per-turn separated
and non-overwriting without needing Gradium/Mistral. Barge-in interrupted turns keep a
`null` composite while other turns keep theirs (no desync).

## Component Findings
| Brick | Status | Findings | Next action |
|---|---|---|---|
| `TelemetryRecorder.begin_turn` (per-turn baggage) | Pass | Baggage merged into every span/event/metric/log; explicit attribute wins on key clash; resets each turn | — |
| `StreamingSttProcessor` / `UtteranceAggregator` (turn owners) | Pass | Advance `message_id`/`turn_index` at each end-of-turn; `conversation_id` stable | — |
| `pipeline_timing` bucketing + `per_turn_timings` | Pass | Groups by `(correlation_id, turn_index)`; positional-zip fallback for legacy; barge-in-safe | — |
| `streaming_latency_report.py` `per_turn` section | Pass | One row per turn; empty on pre-WEB-017 samples (never a silent gap) | — |
| Observability leak surface | Pass | Only id/latency/provider/outcome attributes; no key/audio/path | — |

## Defects And Gaps
| Severity | Finding | Impact | Owner |
|---|---|---|---|
| None (WEB-017) | — | — | — |
| Info (pre-existing, other ticket) | Live `time_to_first_audio`/mouth-to-ear p95 exceed ADR-0018/0029 gates, dominated by ~4 s Gradium STT finalize | Pilot latency target not met yet; unrelated to this observability ticket | TASK-STT-010/011 (streaming/partial STT) |

## Open Questions
- Product: none.
- Architecture: none — aligns with `docs/architecture/channel-identity-boundary.md`
  (correlation = conversation-level, message id = per turn).
- Technical: none.

## Recommendation
- **Go / No-go:** Go — done & merge-ready. Adversarial review 93/100; functional +
  regression green; per-turn structure proven end to end through the real streaming
  processors **and** on a warm live Gradium+Mistral multi-turn WebRTC session with real
  per-turn durations.
- **Required fixes before pilot:** none for WEB-017. The pilot **latency** gate is a
  separate concern (STT-finalize dominance) tracked by TASK-STT-010/011.

## How To Reproduce
```bash
cd voice-agent
# functional regression net
./.venv/bin/python -m unittest discover tests            # 346 OK
./.venv/bin/behave features/streaming_loop.feature       # multi-turn scenario
# per-turn latency sample (offline, real processors, fake providers)
./.venv/bin/python scripts/streaming_per_turn_sample.py --turns 3 --calls 2 \
  | ./.venv/bin/python scripts/streaming_latency_report.py \
      --channel web --provider fake-streaming --warm

# warm LIVE multi-turn capture (Gradium+Mistral) — server as a persistent job:
set -a && source ../.env && set +a
export VOICE_BACKEND_URL=http://127.0.0.1:8080/api/conversation/converse   # Java backend on :8080
./.venv/bin/python -m web_voice.server --host 127.0.0.1 --port 8090 \
  --provider gradium --backend http --runtime pipecat \
  --webrtc auto --stt-mode streaming --tts-mode streaming 2> /tmp/live-server.log
# drive one call with several utterances separated by long low-amplitude noise gaps
# (peak ≪ 1000, gap > full STT→Mistral→TTS so no barge-in), then hang up:
./.venv/bin/python scripts/webrtc_live_client.py --url http://127.0.0.1:8090 \
  --audio /tmp/multiturn.wav --hold 66
grep '"spans"' /tmp/live-server.log | tail -1 \
  | ./.venv/bin/python scripts/streaming_latency_report.py \
      --channel web --provider gradium-streaming --warm
```
