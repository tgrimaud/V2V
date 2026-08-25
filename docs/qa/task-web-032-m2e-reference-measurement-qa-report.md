# QA / Latency Report — TASK-WEB-032: Reference mouth-to-ear measurement (warm WebRTC + real backend)

**Ticket:** TASK-WEB-032 · **Branch:** `task/TASK-WEB-032-m2e-reference-measurement` (off
`feat/sprint-12-external-voice-websocket`) · **Date:** 2026-08-25
**Related:** ADR-0029 (mouth-to-ear gate), ADR-0028 (per-slice timing), OQ-005 · **Companion:** TASK-WEB-031 (WebSocket score)

## Executive Summary

- **Reference number captured (not a projection).** A warm, co-located **WebRTC** sample on the
  **web** channel against the **real** backend (`--backend http`: Mistral chat + Ollama embeddings
  + pgvector, 10 163 KB vectors) with real Gradium streaming STT/TTS was measured end to end and
  scored against the ADR-0029 gate. This retires the ADR-0029 "still a projection" caveat for the
  primary reference transport.
- **ADR-0029 gate = FAIL.** mouth-to-ear (`voice_to_first_audio`) **p95 3743 ms** (target ≤ 1500 ms)
  and time-to-first-audio **p95 3393 ms** (target ≤ 1200 ms). The **median** mouth-to-ear
  (1951 ms) also exceeds 1.5 s, so this is not a tail-only miss.
- **The bottleneck is transport-independent.** WebRTC and WebSocket (TASK-WEB-031) land at nearly
  the same composite (m2e p95 3743 ms vs 3675 ms), dominated by the **same two slices**: STT
  time-to-final tail and backend first-token. **Transport egress is negligible on both**
  (WebRTC 0.1 ms, WebSocket 4 ms) — so the interim WebSocket choice costs ~nothing in latency vs
  WebRTC, and the pilot latency problem is an **STT-endpointing + LLM-first-token** problem, not a
  transport-choice problem.

## Run Configuration

- **Transport:** WebRTC (`/api/voice/webrtc/offer`), same path the browser uses; driven by
  `voice-agent/scripts/webrtc_live_client.py` (aiortc 1.15.0).
- **Providers:** real Gradium **streaming** STT + **streaming** TTS (`--stt-mode streaming
  --tts-mode streaming --provider gradium`); backend `--backend http` → Java conversation engine
  (Mistral `mistral-small-latest`, Ollama `nomic-embed-text`, pgvector).
- **Sample:** 16 warm calls (1 smoke + 15 loop), 5 distinct spoken-French billing utterances
  (~4.0–5.5 s speech each), co-located dev host. Each mic clip is the fixture speech **plus a
  1.5 s low-amplitude noise tail** (peak ≈ 300) so Opus does not DTX-drop the trailing silence and
  the energy end-of-turn actually flushes (the file-based WebRTC pitfall from TASK-WEB-007).
- **Scoring:** `scripts/streaming_latency_report.py --channel web --provider
  gradium-streaming-webrtc --warm`. Raw output versioned at
  [`task-web-032-m2e-reference-report.json`](./task-web-032-m2e-reference-report.json).

## Latency Results (WebRTC, authoritative server-side per slice)

| Slice | p50 | p95 | p99 | n | Notes |
|---|---:|---:|---:|---:|---|
| channel_ingress | — | — | — | — | Not emitted on this path; `measured=false`, never faked. |
| end_of_turn | 350 | 350 | 350 | 16 | Fixed silence-window hold. |
| **stt** | 396 | **1535** | 1535 | 16 | Gradium streaming time-to-final. Median fast; **tail is the cost**. |
| **backend_first_token** | 869 | **1717** | 1717 | 16 | RAG retrieval + Mistral first token. **Largest single p95 slice.** |
| tts_first_audio | 358 | 395 | 400 | 31 | Gradium streaming TTS — inside budget. |
| channel_egress | 0 | 0.1 | 0.1 | 16 | Runtime egress (first frame → WebRTC transport). Negligible. |
| **time_to_first_audio** | 1601 | **3393** | 3393 | 15 | stt + backend_first_token + tts_first_audio. **ADR-0029 sub-target ≤ 1.2 s → FAIL.** |
| **voice_to_first_audio (mouth-to-ear)** | 1951 | **3743** | 3743 | 15 | + end_of_turn + channel_egress. **ADR-0029 primary ≤ 1.5 s → FAIL.** |

**Sample quality:** WebRTC negotiates a **fresh session per offer**, so each per-call dump carries
exactly its own spans (`n=16`, clean per-call weighting) — unlike the WebSocket single-client socle
where the persistent session accumulated spans (`n=136` = 1+2+…+16, later-turn-weighted;
TASK-WEB-031 / WEB-030 residual). **This WebRTC sample is therefore the cleaner reference
distribution.**

Client-observed `mouth_to_ear_proxy_ms` values (429, 207, …, some negative) are **not** used: the
1.5 s noise tail pushes the client's "clip end" mark ~1.5 s past the real end of speech, so the
proxy under-reads. The server-side per-slice composite above is authoritative.

## Cross-Transport Comparison (WEB-032 WebRTC vs WEB-031 WebSocket)

| Slice (p95, ms) | WebRTC (WEB-032) | WebSocket (WEB-031) | Verdict |
|---|---:|---:|---|
| end_of_turn | 350 | 350 | identical (fixed hold) |
| stt | 1535 | 2250 | same order; WS p95 inflated by accumulation bias, medians ~equal (396 vs 380) |
| backend_first_token | 1717 | 1642 | ~equal |
| tts_first_audio | 395 | 402 | ~equal (inside budget) |
| channel_egress | 0.1 | 4 | both negligible |
| **mouth_to_ear** | **3743** | **3675** | **~equal FAIL** (~2.2 s over the 1.5 s gate) |

**Conclusion:** the transport is not the lever. STT time-to-final tail + backend first-token are,
on both paths.

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| **High** | mouth-to-ear p95 3743 ms (target ≤ 1500) / TTFA p95 3393 ms (target ≤ 1200) — ADR-0029 **FAIL** on the reference WebRTC transport with real providers | No pilot latency SLO can be claimed on the current pipeline | Architecture/Product |
| High | backend_first_token p95 1717 ms and stt time-to-final p95 1535 ms together are ~90 % of the budget | These two slices decide the gate | New optimisation tickets (below) |
| Info | TTS first audio (395 ms) and transport egress (~0 ms) are inside budget on both transports | No transport/TTS action needed | — |

## Concrete Levers (feed the follow-up optimisation tickets)

1. **Backend first-token (p95 1717 ms) — biggest single slice.** RAG retrieval + Mistral first
   token. Levers: retrieval/embedding cache, shorter/leaner prompt, a faster or co-located LLM,
   begin TTS on the first *token* rather than first *sentence*. → proposed **TASK-WEB-036**.
2. **STT time-to-final tail (p95 1535 ms; p50 only 396 ms).** The median is fine — the tail
   dominates. Levers: end-pointing tuning (shorter confirmation), partial-final acceptance,
   consolidated `end_text`. → proposed **TASK-WEB-035**.
3. **Transport / TTS: no action** — negligible egress, TTS inside budget.

## Recommendation

- **Reference measurement: DONE.** The ADR-0029 gate now has a **measured** WebRTC mouth-to-ear
  number (p95 3743 ms), not a projection — and a matching WebSocket number (3675 ms). Both **FAIL**
  the 1.5 s gate.
- **No pilot latency SLO** is claimed on the current pipeline. Progress is gated on the two levers
  above (STT end-pointing, backend first-token), which are **transport-independent** — fix them
  once, both transports benefit. Re-score with the same harness (`webrtc_live_client.py` /
  `ws_live_client.py` + `streaming_latency_report.py`) after each lever.
- **Interim WebSocket decision validated on latency grounds:** choosing WebSocket over WebRTC for
  external reach costs ~nothing in mouth-to-ear (egress 4 ms vs 0.1 ms), so ADR-0043's interim path
  carries no latency penalty.
