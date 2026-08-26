# QA / Latency Evidence — TASK-WEB-039: Pilot WS-live mouth-to-ear (v0.6.0, direct-to-bridge)

**Ticket:** TASK-WEB-039 · **Branch:** `task/TASK-WEB-037-websocket-primary-transport` · **Date:** 2026-08-26
**Related:** ADR-0029 (mouth-to-ear gate), ADR-0046 (WebSocket primary), ADR-0047 (single-port target), ADR-0028 (per-slice timing)
**Companions:** TASK-WEB-031 (co-located WS score), TASK-WEB-032 (co-located WebRTC reference)
**Raw report:** [`task-web-039-ws-live-latency-report.json`](./task-web-039-ws-live-latency-report.json)

## Executive Summary

- **First live WebSocket sample on the actually-deployed pilot.** Ten warm turns were driven
  through the pilot voice bridge `vla-t01` (image **`0.6.0`**, `websocket=on:8091`) **direct to the
  bridge** (no HAProxy edge — the interim `voice_ws` route was dropped per ADR-0047), with the real
  provider stack co-located on the bridge (Gradium streaming STT + Mistral RAG backend + Gradium
  streaming TTS). This proves the V1 live WebSocket Voice2Voice loop end-to-end on the pilot.
- **ADR-0029 gate = FAIL.** mouth-to-ear (`voice_to_first_audio`) **p95 2759 ms** (target ≤ 1500 ms,
  margin −1259) and time-to-first-audio **p95 2409 ms** (target ≤ 1200 ms, margin −1209). Median
  mouth-to-ear 1929 ms also exceeds 1.5 s → not a tail-only miss.
- **The bottleneck is transport-independent and provider-side.** The two dominant slices are the
  **STT post-EOT finalize tail** (p95 **1235 ms**) then **backend first-token** (p95 **887 ms**).
  TTS first-audio (p95 401 ms) and channel egress (p95 0.03 ms) are comfortably inside budget.
- **The deployed 0.6.0 levers already helped.** vs the Sprint-12 co-located references
  (TASK-WEB-031/032: m2e p95 ≈ 3675–3743 ms), this pilot sample lands lower (m2e p95 2759 ms) —
  the finalize budget (TASK-WEB-035) and top-k=5 (TASK-WEB-036) baked into 0.6.0 are visible in the
  smaller STT tail (1235 vs 1535 ms) and backend first-token (887 vs 1717 ms). It is still **not
  enough** to clear the gate; the residual is owned by TASK-STT-014 + TASK-BE-020 / TASK-BE-033.

## Run Configuration

- **Transport:** WebSocket (`ws://<bridge>:8091`), the ADR-0043/0046 primary live path; driven by
  `voice-agent/scripts/ws_live_client.py --hold 12`.
- **Deployment:** pilot bridge `vla-t01`, container image `0.6.0` (published `:8091` added to
  `deploy/compose/voice/docker-compose.yml`; `:8090` unchanged). Both t01/t02 healthy.
- **Providers:** real Gradium **streaming** STT + **streaming** TTS; backend = the co-located Java
  conversation engine (Mistral `mistral-small-latest`, Ollama `nomic-embed-text`, pgvector), the
  same `converse-stream` guarded-sentence path (top-k=5, `VOICE_BACKEND_STREAM=1`).
- **Sample:** 10 warm turns, one spoken-French billing utterance (`fixtures/long/billing-question.pcm`)
  + trailing silence + a 12 s idle hold per turn. The report aggregated 11 turn dumps
  (`turn_index` 1–11) under one `correlation_id`.
- **Access path / caveat:** the SSH tunnel had to forward to the bridge **LAN IP** `:8091`, not
  `127.0.0.1:8091` — the podman host→loopback forwarder quirk breaks the loopback WS handshake
  (same root cause as the deploy health-gate hang, now ticketed **TASK-INFRA-011**). The
  client-observed mouth-to-ear proxy therefore carries SSH-tunnel RTT and is **not** the
  authoritative number; the server-side per-slice telemetry below is.
- **Scoring:** `scripts/streaming_latency_report.py --input /tmp/ws-telemetry.jsonl
  --channel web-voice-websocket --provider gradium-stt+mistral-rag+gradium-tts --warm`.

## Latency Results (server-side per slice, authoritative)

| Slice | p50 | p95 | p99 | n | Notes |
|---|---:|---:|---:|---:|---|
| channel_ingress | — | — | — | — | Not emitted on the headless WS path; `measured=false`, never faked (→ TASK-WEB-040). |
| end_of_turn | 350 | 350 | 350 | 65 | Fixed silence-window hold (`VOICE_END_OF_TURN_SILENCE_MS`, tuned default). |
| **stt** | 381 | **1235** | 1235 | 65 | Gradium streaming time-to-final (post-EOT). Median fast; **the tail is the cost.** |
| **backend_first_token** | 801 | **887** | 887 | 65 | RAG retrieval + Mistral first token. 2nd-largest slice (halved vs Sprint-12 via top-k=5). |
| tts_first_audio | 359 | 401 | 401 | 120 | Gradium streaming TTS — well inside budget. |
| channel_egress | 0.02 | 0.03 | 0.03 | 65 | Runtime egress (first frame → WS transport). Negligible. |
| **time_to_first_audio** | 1579 | **2409** | 2409 | 65 | stt + backend_first_token + tts_first_audio. **ADR-0029 sub-target ≤ 1.2 s → FAIL.** |
| **voice_to_first_audio (mouth-to-ear)** | 1929 | **2759** | 2759 | 65 | + end_of_turn + channel_egress. **ADR-0029 primary ≤ 1.5 s → FAIL.** |

**Context (off the critical path):** `stt.time_to_first_partial` p50 1407 / p95 2235 ms and
`tts.time_to_last_audio` p50 3337 / p95 4243 ms. The first-partial latency happens **while the
caller is still speaking** (pre-EOT), so it does **not** add to the post-EOT mouth-to-ear — do not
confuse it with the finalize tail. `time_to_last_audio` is the full-answer synthesis length, not
the responsiveness metric.

**Sample-weighting note:** the single-client WS socle accumulates spans on the persistent session,
so the slice counts (`n=65`/`120`) are larger than the 10 turns and later-turn-weighted (the
TASK-WEB-030 residual). The composite `time_to_first_audio`/`voice_to_first_audio` are computed
per turn (`n=65`) and are the numbers to trust.

## ADR-0029 Verdict

| Criterion | Target | Measured p95 | Margin | Status |
|---|---:|---:|---:|:--:|
| mouth-to-ear (`voice_to_first_audio`) | ≤ 1500 ms | 2759 ms | −1259 ms | ❌ FAIL |
| time-to-first-audio | ≤ 1200 ms | 2409 ms | −1209 ms | ❌ FAIL |

Gate **FAIL**. No pilot latency SLO is claimed on the WS path. This is the WS/real-pilot
counterpart to TASK-WEB-031 (co-located WS) and TASK-WEB-032 (co-located WebRTC), and it confirms
the same conclusion on the deployed artifact: the miss is an **STT-endpointing + LLM-first-token**
problem, not a transport-choice problem.

## Remediation (tracked, not duplicated)

| Residual slice | p95 | Owning ticket |
|---|---:|---|
| STT post-EOT finalize tail (dominant) | 1235 ms | **TASK-STT-014** (activate) |
| backend time-to-first-vetted-sentence | 887 ms | **TASK-BE-020** + **TASK-BE-033** / ADR-0045 (LLM first-token benchmark) |
| end-of-turn hold | 350 ms | tuned floor (TASK-WEB-022); limited further headroom |

A clean re-measure without the SSH-tunnel / loopback workaround should be taken once **TASK-WEB-038**
lands the single routed port (`wss://<vip>/` through HAProxy).

## Known Issues Surfaced By This Run

- **BUG-017** — `barge_in_count=45` over 10 headless turns (~4.5/turn) with no overlapping speaker,
  including during the idle hold. Suspected EOT/control-signal re-arm, TTS→onset feedback, or a
  per-turn counting artifact.
- **TASK-WEB-040** — `channel_ingress` is the only unmeasured canonical slice on the WS path (no
  browser-mic ingress span); the other five populate correctly.
- **TASK-INFRA-011** — the podman host→loopback quirk that forced the LAN-IP tunnel is the same
  quirk that hangs the Ansible voice health gate; repoint off `127.0.0.1`.

## Test Procedure (reproducible)

1. Deploy the compose `:8091` publish to the bridge (image `0.6.0`, config-only change).
2. From an operator host: `ssh -L 8091:<bridge-LAN-IP>:8091 <bridge>` (LAN IP, **not** loopback).
3. `cd voice-agent && ./.venv/bin/python scripts/ws_live_client.py --url ws://127.0.0.1:8091 --audio fixtures/long/billing-question.pcm --language fr --hold 12` (×10 warm).
4. Collect the server telemetry dumps from the container logs → `ws-telemetry.jsonl`.
5. Score: `./.venv/bin/python scripts/streaming_latency_report.py --input ws-telemetry.jsonl --channel web-voice-websocket --provider gradium-stt+mistral-rag+gradium-tts --warm`.

---

## Update 2026-08-26 — v0.7.0 single routed port, re-measured **through the HAProxy edge**

Re-run after `v0.7.0` (single async HTTP+WS server, ADR-0047) was deployed to eir-ai4cc-tst.
This closes both TASK-WEB-039 confirmation residuals **except** the latency gate itself.

- **Edge `101` confirmed (was pending).** `GET /ws` returns `HTTP/1.1 101 Switching Protocols`
  both **direct-to-bridge** (`http://<bridge-LAN-IP>:8090/ws`, both nodes) and **through the VIP**
  (`https://vip-ai4cc-voice-t01.prod.lan/ws`) — HAProxy tunnels the upgrade on the existing
  `voice_bridges` backend, no edge special-case, no `:8091`. Bridge boot line: `server=aiohttp …
  websocket=on:8090/ws`, container `healthy` on t01/t02.
- **ADR-0029 gate = FAIL (unchanged).** Warm n=10, driven **through the edge VIP** (`wss://…/ws`),
  real Gradium streaming STT/TTS + Mistral RAG, calls LB-balanced across t01/t02:
  mouth-to-ear **p95 2763 ms** (target ≤ 1500, margin −1263) / time-to-first-audio **p95 2413 ms**
  (target ≤ 1200, margin −1213).
- **The edge tunnel adds ≈ 0 ms.** Edge-routed m2e p95 **2763 ms** vs the v0.6.0 direct-to-bridge
  **2759 ms** — HAProxy's WS tunnelling is not a latency contributor. The bottleneck stays
  transport- and edge-independent: **STT finalize tail p95 1227 ms** + **backend first-token p95
  1388 ms**; TTS first-audio p95 390 ms and channel egress ~0 ms are inside budget.

| Slice (post-EOT) | p50 | p95 | Budget |
|---|---:|---:|---|
| end_of_turn | 350 | 350 ms | fixed window |
| stt (finalize tail) | 723 | **1227 ms** | dominant lever → TASK-STT-014 |
| backend_first_token | 901 | **1388 ms** | dominant lever → TASK-BE-020 / BE-033 |
| tts_first_audio | 353 | 390 ms | ✅ |
| channel_egress | ~0 | ~0 ms | ✅ |
| **mouth-to-ear** | 2437 | **2763 ms** | ❌ ≤ 1500 |
| **time-to-first-audio** | 2087 | **2413 ms** | ❌ ≤ 1200 |

**Residual now = latency only.** The transport/edge/deploy questions are answered (single routed
port live, edge `101` confirmed both ways, edge adds no latency). Reaching the ADR-0029 gate is
purely the STT-tail + backend-first-token work already ticketed (TASK-STT-014, TASK-BE-020/BE-033) —
no transport change will move it.

- **Raw report:** [`task-web-039-ws-edge-latency-report-v0.7.0.json`](./task-web-039-ws-edge-latency-report-v0.7.0.json)
- **Raw telemetry:** [`task-web-039-ws-edge-telemetry-v0.7.0.jsonl`](./task-web-039-ws-edge-telemetry-v0.7.0.jsonl)

### Procedure (edge re-measure)

1. Deploy `v0.7.0` (single port `:8090`, `/ws`) to the voice tier.
2. Confirm the upgrade: `curl -k -i -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' https://vip-ai4cc-voice-t01.prod.lan/ws` → `101`.
3. Drive warm turns through the edge: `ws_live_client.py --url wss://vip-ai4cc-voice-t01.prod.lan/ws --audio fixtures/long/<clip>.pcm --language fr --hold 14 --insecure` (×10+).
4. Collect per-call dumps from **both** bridges: `ssh <node> 'sudo podman logs --since 15m voice-support-bridge | grep pipeline_timing'` → merge into one `.jsonl`.
5. Score: `streaming_latency_report.py --input <merged>.jsonl --channel web --provider gradium-streaming --warm`.
