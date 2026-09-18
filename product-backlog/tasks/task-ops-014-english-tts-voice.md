# TASK-OPS-014 — Configure the English TTS voice (Gradium)

**Type:** Ops / config task · **Status:** ✅ Done (2026-09-18) — deployed to t01+t02, voice id validated live
**Branch:** `task/TASK-OPS-014-english-tts-voice` (off `feat/restart-from-scratch`)
**Related:** TASK-OPS-013 (English KB), US-042 (per-language voice), ADR-0031

## Context

The Eir pilot answers in English (TASK-BE-056 persona + TASK-OPS-013 English KB), but the spoken
path fell back to the **French** Gradium voice because `gradium_voice_id_en` was empty — the voice
runtime selects the English voice from `GRADIUM_VOICE_ID_EN` and otherwise uses the default (FR)
voice (`web_voice/server.py`: `english_voice = os.environ.get("GRADIUM_VOICE_ID_EN")` → per-language
provider for both streaming and batch). The stakeholder provided the English Gradium voice id.

## Change

- `deploy/ansible/group_vars/voice.yml`: `gradium_voice_id_en: "vimnD4UQG_36P43U"` (was empty),
  rendered into the voice `.env` as `GRADIUM_VOICE_ID_EN`. No code change; `.env`-only, so it ships
  at the current voice image tag (0.9.0) via a voice-tier deploy (container recreate, env re-render).

## Acceptance

- [x] `gradium_voice_id_en` set to the provided id.
- [x] Voice tier (t01+t02) redeployed at `0.9.0` (env re-render); `GRADIUM_VOICE_ID_EN=vimnD4UQG_36P43U`
      present in the rendered `.env`; bridges healthy.
- [x] Voice id validated live against Gradium TTS (`wss://api.gradium.ai/api/speech/tts`, English
      text) from the bridge container: **38 audio frames (~130 KB base64), no error** — Gradium
      accepts the id (not rejected à la `n=default`), so English turns synthesize with this voice.
