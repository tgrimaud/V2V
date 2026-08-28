# Genesys Audio Connector spike (TASK-WEB-025) — THROWAWAY

Investigation-only prototype + synthetic-audio latency harness for the Sprint 13 Genesys
go/no-go gate (ADR-0049, refines ADR-0040). **Throwaway** — isolated under `spikes/`,
**never imported by the production runtime**, and it touches **no backend business code**
(the ADR-0001 boundary invariant holds). Delete after the gate decision lands.

## What it does (synthetic / non-PII only — DEC-014)

- Models one bidirectional AudioHook session **in-process** (`audiohook_prototype.py`),
  reusing the real ADR-0043 control vocabulary (`web_voice.websocket_framing.ControlType`)
  and the PCM16/16 kHz internal boundary. In the real target (TASK-WEB-041) this becomes a
  transport adapter on the ADR-0047 single async server via the ADR-0043 session factory.
- Transcodes the two Genesys wire codecs to/from the internal boundary (`transcode.py`):
  **PCMU** (G.711 µ-law 8 kHz ↔ PCM16/16 kHz, companding + resample) and **L16**
  (8 kHz ↔ 16 kHz resample only). Pure stdlib (no new dependency; `audioop` is gone in 3.13+).
- Drives N synthetic round trips per codec and decomposes **per-leg latency** (p50/p95),
  re-scores full **mouth-to-ear vs ADR-0029** (1.5 s gate), and probes the **concurrency
  target = 3** (`harness.py`). Reuses the real `voice_common` telemetry + deterministic
  `traceparent` so a Genesys `conversationId` maps to **one OpenTelemetry trace**.

## What it cannot do (needs the live Genesys org)

The Genesys cloud legs (ingress, Architect Call-Audio-Connector fork, cloud egress), the
negotiated codec, the 15-minute cap, native barge-in/EOT events, and the degraded-mode
Architect behaviour need a human to run a minimal Architect flow. Those legs are reported
`measured=false` (US-036 rule). See the go/no-go report and its "Manual Genesys-Architect
Steps": `docs/qa/task-web-025-genesys-audio-connector-spike-report.md`.

## Run

```bash
cd voice-agent
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt   # first time
./.venv/bin/python spikes/genesys_audiohook/harness.py --turns 50
# tests:
./.venv/bin/python -m unittest tests.test_genesys_audiohook_spike
```

## Files

| File | Role |
|---|---|
| `transcode.py` | PCMU/L16 ↔ PCM16 codec transcode (stdlib, budgeted) |
| `synthetic_audio.py` | Deterministic low-amplitude non-PII audio generator |
| `audiohook_prototype.py` | Throwaway in-process AudioHook session (emits per-leg spans) |
| `genesys_legs.py` | Canonical Genesys per-leg model + per-leg report (US-036) |
| `rescore.py` | ADR-0029 mouth-to-ear re-score with the Genesys leg included |
| `harness.py` | CLI: synthetic round trips → per-leg + re-score + concurrency report |
