# BUG-015 — `/api/voice/turn` speaks only the last sentence when the backend streams

## Header

- **Bug ID:** BUG-015
- **Title:** The batch one-shot voice turn (`/api/voice/turn`, served by `index.html`) returns only the **last** synthesized sentence instead of the full multi-sentence answer, because it sends `tts_response.wav` (last synthesis) rather than the accumulated `result.audio` (all sentences)
- **Status:** Closed — validated by user on v0.5.2 (2026-08-14)
- **Severity:** High
- **Priority:** P1
- **Detected by:** User validation (pilot, browser UI at `https://vip-ai4cc-voice-t01.prod.lan/`)
- **Detected date:** 2026-08-14
- **Related user story:** TASK-WEB-005 (Pipecat batch runtime), TASK-WEB-020/022 (default-on backend streaming)
- **Related epic:** EPIC-012 (V1 pilot deployment)
- **Branch:** `feat/sprint-11-remote-deployment`
- **Owner:** Voice runtime developer

## Problem Statement

The full RAG answer is generated and displayed as text, but the voice only speaks the
**last sentence**. The root UI page (`/` → `index.html`) posts recorded audio to
`POST /api/voice/turn` (the batch one-shot runtime).

Since TASK-WEB-022 the backend answer streaming lever (`VOICE_BACKEND_STREAM`) is **on by
default**, so the backend emits the answer as **one vetted sentence per `chunk`**, and
`AnswerProcessor` pushes **one `TextFrame` per sentence**. In the batch pipeline the
`TtsFrameProcessor` synthesizes each sentence and overwrites `self.response` on every
`TextFrame`, so `BatchTurnResult.tts_response` holds only the **last** sentence's
synthesis. The `_AudioCaptureSink` correctly accumulates **all** sentences into
`BatchTurnResult.audio`, but `_handle_turn` sends `result.tts_response.wav` (last only)
and never uses `result.audio` (all).

The WebRTC path (`webrtc.html`) is **not** affected: it pushes each sentence's
`TTSAudioRawFrame` straight to the transport output track, so every sentence plays.

## Environment

- **Environment:** pilot (eir-ai4cc-tst); bridges `vla-ai4cc-t01/t02`; VIP `.10`/`.11`
- **Channel:** web voice batch one-shot (`POST /api/voice/turn`, `index.html`)
- **Build or commit:** voice image `0.5.x`; `web_voice/server.py` `_handle_turn`,
  `voice_pipeline/pipeline.py` `run_batch_turn`, `voice_pipeline/tts_service.py`
- **Correlation ID:** e.g. `86fb85c3-…` (3 `tts.audio.final` events, 1 truncated egress)

## Reproduction Steps

1. Given `VOICE_BACKEND_STREAM` unset/on and a question whose grounded answer is 2+ sentences.
2. When a turn runs over `POST /api/voice/turn` (root UI).
3. Then only the last sentence is audible, though the returned answer text is complete.

## Expected Result

The synthesized audio contains **every** vetted sentence of the answer, in order — the
same content the WebRTC path already plays and the same text carried by the backend
`done` event / `X-Voice-Answer` header.

## Actual Result

Only the final sentence is spoken. Per-call telemetry shows N `tts.audio.final` events
(one per sentence, all SUCCESS) but a single `web.voice.egress.sent` whose `audio_bytes`
equals only the **last** sentence.

## Evidence

- Backend `converse-stream` for the question emits **3** `chunk` events (3 sentences) +
  a `done` with the full text — backend is correct.
- Bridge per-call telemetry (correlation `86fb85c3-…`): three `tts.audio.final`
  (`245760`, `222720`, `220160` bytes) but one `web.voice.egress.sent` = `220204` bytes
  (= last sentence + 44-byte WAV header). The first two sentences are synthesized then dropped.

## Impact

- **Customer / pilot-readiness:** the caller hears a truncated answer (usually just the
  closing/offer sentence), losing the actual billing explanation — a demo-blocking defect.
- **Operational:** looked like a TTS/streaming glitch; the batch runtime silently drops
  all but the last synthesized sentence whenever backend streaming is on.
- No security/privacy impact.

## Acceptance Criteria For Fix

- [ ] `POST /api/voice/turn` returns audio containing **all** synthesized sentences in
      order (send the accumulated `BatchTurnResult.audio`, wrapped once as WAV).
- [ ] The `web.voice.egress` span / `web.voice.egress.sent` event report the **full**
      audio byte count, not the last sentence.
- [ ] Backward compatible: with streaming off (single answer / single `TextFrame`) the
      output is unchanged.
- [ ] Safe fallback: if nothing was accumulated at the sink, the last synthesis is used.
- [ ] Regression test: a multi-sentence streamed backend over the batch runtime yields a
      WAV whose PCM length equals the sum of the per-sentence syntheses.
- [ ] Adversarial code review ≥ 90%.
- [ ] QA retest passes live (multi-sentence answer fully spoken after image rebuild + redeploy).

## Developer Notes

- **root cause:** `_handle_turn` (and the TTS-only `/api/voice/tts` path is single-frame,
  unaffected) sends `result.tts_response.wav` — the **last** `TtsFrameProcessor.response`
  — instead of the accumulated `result.audio` from `_AudioCaptureSink`. The batch pipeline
  was written when the backend returned one answer (one `TextFrame`); the default-on
  streaming lever (TASK-WEB-022) turned that into one `TextFrame` per sentence.
- **files to change:** `web_voice/server.py` (`_handle_turn`: wrap + send `result.audio`,
  report the full length to `record_egress`).
- **interim mitigation (no rebuild):** set `VOICE_BACKEND_STREAM=0` on the voice tier so
  the backend returns a single answer → a single `TextFrame` → `tts_response.wav` = full
  answer. Trade-off: disables the first-sentence latency lever on the WebRTC path.
- **residual risk:** low; the fix sends what the sink already accumulates. Requires a voice
  image rebuild + redeploy to activate.

## Deployment record

- **Release:** git tag `v0.5.2` on `04c5ac6` (bundles BUG-013 backend base-URL guard + BUG-015 full-answer audio). CI `images.yml` published `ghcr.io/tgrimaud/voice-support-voice:0.5.2` and `voice-support-backend:0.5.2` (2026-08-14).
- **Voice tier:** both bridges recreated at `0.5.2`, container `healthy`, `HTTP 200` on each node's LAN IP:8090, LB VIP `https://vip-ai4cc-voice-t01.prod.lan/` returns `200`.
  - `vla-ai4cc-t01`: deployed via `deploy.yml --limit voice` (image pulled + stack up).
  - `vla-ai4cc-t02`: deployed manually (`.env` `IMAGE_TAG` bumped to `0.5.2`, `podman compose pull && up -d`) — see health-gate note below.
- **Health-gate caveat (recurring):** the Ansible voice health probe targets `http://127.0.0.1:8090/`, which returns `000` on these root/rootless Podman hosts even though the container is `healthy` and the same port answers `200` on the host LAN IP. The gate false-negatived on t01 (after the stack was already up at 0.5.2) and would have aborted before t02 (`serial:1`), so t02 was completed manually. Follow-up: point `health_url` at the reachable host IP / container exec probe instead of loopback.

## QA Retest

- **Retested by:** User (pilot UI) + voice-agent automated suite.
- **Retest date:** 2026-08-14
- **Scenarios rerun:** live multi-sentence turn on `https://vip-ai4cc-voice-t01.prod.lan/` (`/` → `/api/voice/turn`); voice-agent `unittest` (500 passed) + `behave` (13 features / 36 scenarios / 169 steps passed) on v0.5.2 sources.
- **Result:** PASS — the full multi-sentence answer is now spoken (no longer truncated to the last sentence).
- **Retest evidence:** both pilot bridges on `0.5.2` (`healthy`, host-IP:8090 → 200, VIP → 200); green automated suites.

## Closure

- **Closed by:** User validation (recorded by assistant)
- **Closed date:** 2026-08-14
- **Closure reason:** Fixed in `_full_turn_response` (send the sink-accumulated PCM as one WAV), released as `v0.5.2`, deployed to both pilot voice bridges, and validated end-to-end via the browser UI. Regression covered by `FullTurnResponseTest`.
