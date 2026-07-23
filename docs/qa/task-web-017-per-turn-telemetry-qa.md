# QA Functional And Latency Report — TASK-WEB-017 (Per-turn identity on WebRTC streaming telemetry)

## Executive Summary
- **Overall readiness:** Go for merge-ready on the observability change. Each streaming
  turn is now individually traceable and the report derives per-turn slices from a
  single multi-turn call.
- **Main blockers:** none.
- **Residual risks:** the **warm live** per-turn p50/p95/p99 (Gradium STT/TTS + Mistral
  over a real `SmallWebRTCTransport`) is not captured in this session — it needs the
  paid live stack. Offline evidence proves the per-turn *structure* end to end through
  the real streaming processors; absolute durations are fixture-fast. Live warm sample
  stays the one remaining evidence item before the ticket is fully "done".

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
| No API key / raw audio / file-path leak in telemetry | Pass | Dump attribute scan: only id/latency/provider/outcome keys; leak regex empty | Attribute allowlist unchanged |

Regression net: **unittest 346 OK** (+12 for this ticket); **Behave 10 features / 27
scenarios / 126 steps OK** (+1 multi-turn scenario).

## Latency Results
Per-turn breakdown derived from one offline sample (2 calls × 3 paced turns), via
`scripts/streaming_per_turn_sample.py | scripts/streaming_latency_report.py`:

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| `stt.request` (fake) | ~0 ms | — | — | 6 turns | Warm | fixture-fast; per-turn separated |
| `backend.request` (stub) | ~0 ms | — | — | 6 turns | Warm | stub |
| `voice.tts.first_audio` (fake) | 0.02–0.06 ms | — | — | 6 turns | Warm | one composite **per turn** (6 distinct `time_to_first_audio_ms`) |

> The absolute numbers are fixture-fast and only prove the slices are **wired,
> per-turn separated, and non-overwriting** end to end. The point of this ticket is
> observability structure, not provider latency. Real warm p50/p95/p99 (ADR-0018
> `time_to_first_audio` p95<800 ms; ADR-0029 mouth-to-ear p95≤1.5 s) require the live
> Gradium/Mistral stack over a warm multi-turn WebRTC session — captured separately.

Proof of separation (one call, 3 paced turns): three distinct `message_id` under one
`correlation_id`, each with its own `time_to_first_audio_ms`; when a turn is barge-in
interrupted its composite is `null` while the other turns keep theirs (no desync).

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
| Low | Warm live per-turn p50/p95/p99 not captured this session (paid live stack) | No live latency number yet; structure proven offline | QA + user (live run) |

## Open Questions
- Product: none.
- Architecture: none — aligns with `docs/architecture/channel-identity-boundary.md`
  (correlation = conversation-level, message id = per turn).
- Technical: none.

## Recommendation
- **Go / No-go:** Go — merge-ready. Adversarial review 93/100; functional + regression
  green; per-turn structure proven end to end through the real streaming processors.
- **Required fixes before pilot:** none functional. Before classifying the ticket fully
  done, capture one **warm live/headless multi-turn** sample (Gradium/Mistral) confirming
  the `per_turn` section shows distinct per-turn slices with real durations.

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
```
