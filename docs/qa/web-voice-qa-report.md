# QA Functional And Latency Report - Web Voice STT Ingress (TASK-WEB-001)

**Ticket:** TASK-WEB-001 - Capture web voice and transcribe through Gradium STT (US-019 STT half)
**Related story:** US-019 (STT half)
**Branch:** `us/US-019-web-voice-chat`
**Run date:** 2026-07-10
**Provider under test:** `gradium-stt` (real Gradium ASR, live call)
**Browser:** Chrome via Chrome DevTools MCP, page `http://localhost:8090/`

## Executive Summary

- **Overall readiness:** **GO** for the web voice **STT ingress + capture + render
  + provider** path — proven end to end in a real browser against the live Gradium
  engine, including a **real microphone session** exercising the `app.js` capture +
  48 kHz→16 kHz downsampling code, plus injected-sample and safe-failure runs, with
  real ingress telemetry and no secret leak.
- **Remaining before the US-019 STT half is Done:** user validation of the branch
  before any merge. (TASK-WEB-002 voice-out and TASK-WEB-003 backend bridge remain
  separate slices of US-019.)
- **Residual risks:** limited number of utterances/accents tested; no auth on the
  ingress endpoint (RF-006, gated by OQ-001/TASK-WEB-003).

## Scope Tested

- **Story:** US-019 STT half (voice-in) — TASK-WEB-001 slice only (no backend/LLM/TTS).
- **Channel:** `web_voice` (real browser page → `POST /api/voice/stt`).
- **Provider:** `gradium-stt`, live call with a real `GRADIUM_API_KEY`.
- **Input:** a pre-recorded French utterance standing in for the microphone —
  macOS `say` → PCM16 mono 16 kHz, 107 956 bytes (~3.37 s): *"Bonjour, pourquoi ma
  facture a augmenté ce mois-ci ?"*
- **Environment:** local, warm; server `python3 -m web_voice.server --provider gradium`.
- **Automation backing this run:** `tests/test_web_voice_ingress.py` (13 tests) and
  `features/web_voice.feature` (2 scenarios) cover the ingress contract on the same
  code path; this report adds the real-browser + live-engine evidence.

## Functional Results

| Area | Status | Evidence |
|---|---|---|
| Page loads and renders the capture UI | PASS | a11y snapshot (heading, Record button, Idle status, transcript placeholder); `web-voice-idle.png` |
| No JavaScript/console errors | PASS | `list_console_messages` empty after the `favicon.ico` 204 fix (was a single cosmetic 404) |
| Captured audio is transcribed and shown | PASS | Real browser round-trip rendered transcript *"Bonjour, pourquoi ma facture augmentée ce mois-ci?"*, success styling; `web-voice-transcript.png` |
| Request contract | PASS | `POST /api/voice/stt` → `200`, `Content-Type: audio/pcm`, `content-length: 107956`, same-origin |
| STT failure stays safe and observable | PASS | Silence buffer → *"Gradium STT recognized no speech in the audio"*, error styling, status "Failed.", **no invented transcript**; `web-voice-failure.png` |
| Real channel-ingress telemetry | PASS | server span `web.voice.ingress` (`audio_bytes: 107956`, `channel: web_voice`) + `stt.request` span, correlation id propagated end to end |
| No sensitive-data leak | PASS | server log scan: zero `gsk_` occurrences; failure reason sanitized |
| Microphone capture + 48k→16k downsampling (`app.js`) | PASS | **Human mic session** (2026-07-10): live mic → `app.js` capture + downsample → 137 898 B of 16 kHz PCM → transcript *"Bonjour. J'ai un problème avec ma facture."* rendered, success styling; `web-voice-mic-session.png` |

## Latency Results

Real Gradium engine over the web ingress. Time-to-transcript measured in-page with
`performance.now()` around the real `sendAudio()` call.

| Slice | Value | Sample | Warm/Cold | Notes |
|---|---:|---:|---|---|
| Channel ingress (`web.voice.ingress`) | 0.026 ms | 1 | Warm | Real receive-off-wire time; small because the upload is already buffered |
| STT slice (`stt_request_ms`, injected sample) | 2296 ms | 1 | Warm | Live Gradium ASR on a 3.37 s utterance |
| STT slice (`stt_request_ms`, real mic) | 2694 ms | 1 | Warm | Live Gradium ASR on a ~4.3 s mic recording (137 898 B PCM) |
| STT slice (`stt_request_ms`, silence) | 1125 ms | 1 | Warm | Live Gradium ASR on 1 s of silence |
| End-to-end time-to-transcript (browser) | 2307 ms | 1 | Warm | fetch + POST + Gradium + render |
| Backend / TTS / egress | n/a | — | — | Out of TASK-WEB-001 scope (TASK-WEB-002/003) |

STT latency is dominated by the live Gradium call (~2.3 s). This is the real engine
timing, not a fixture analog — it supersedes the fixture-based numbers in
`stt-qa-report.md` for the web path and feeds US-036 per-slice reporting.

## Defects And Gaps

| Severity | Finding | Impact | Disposition |
|---|---|---|---|
| Cosmetic (fixed) | `GET /favicon.ico` returned 404 → one console error | Noisy console in the delivered UI | Fixed: server returns `204`; locked by `test_favicon_returns_no_content` |
| Low | Few utterances tested (injected sample + one real mic recording + silence) | Weak statistical confidence on accents/noise | Add more real utterances over time |
| Low | Ingress endpoint has no auth (RF-006) | Open endpoint on the pilot host | Gated by OQ-001 (web voice identity) / TASK-WEB-003 |

No blocking defect for the tested path; no bug ticket opened.

## Open Questions

- **Product/Security:** which identity source gates the web voice ingress (OQ-001)?
- **QA:** how many real utterances (accents, noise) are required before web STT
  quality is declared representative?

## Recommendation

- **Go / No-go:** **GO** to accept the web voice **STT half of US-019** — the full
  path (microphone capture + downsampling + ingress + live Gradium + render) is
  proven in-browser, safe-failing, observable and secret-free. Only user validation
  of the branch remains before merge.
- **Next:** TASK-WEB-002 (voice-out / TTS) and TASK-WEB-003 (backend bridge) to
  complete the US-019 Voice2Voice loop.

## Reproduce

```bash
# 1) real speech sample standing in for the mic (macOS)
say "Bonjour, pourquoi ma facture a augmenté ce mois-ci ?" -o /tmp/q.wav \
  --data-format=LEI16@16000 --file-format=WAVE
python3 -c "import wave;w=wave.open('/tmp/q.wav');open('sample.pcm','wb').write(w.readframes(w.getnframes()))"

# 2) run the ingress with the real engine
export GRADIUM_API_KEY=...            # never commit this
cd voice-agent && python3 -m web_voice.server --provider gradium

# 3) open http://localhost:8090/ and either record with a mic,
#    or inject the sample from the page console:
#    const b = await (await fetch(URL.createObjectURL(new Blob([pcmBytes])))).arrayBuffer();
#    await window.sendAudio(b);
```

## Assets

- `assets/web-voice-idle.png` — idle capture UI
- `assets/web-voice-transcript.png` — injected-sample transcript rendered (success)
- `assets/web-voice-mic-session.png` — real microphone recording transcribed (success)
- `assets/web-voice-failure.png` — sanitized no-speech failure (safe)
