# Gradium TTS WebSocket contract (spike ST-1, 2026-07-13)

Observed live against `wss://api.gradium.ai/api/speech/tts` with the real API key
(TASK-WEB-002, script `voice-agent/scripts/gradium_tts_spike.py`). This is the
verified contract the `GradiumTtsProvider` (ST-3) is built against.

## Handshake

1. Connect with header `x-api-key: <key>` (no query params).
2. Send `setup`:
   ```json
   {"type":"setup","model_name":"default","voice_id":"<voice>","output_format":"pcm_16000"}
   ```
3. Server replies `ready` on success:
   ```json
   {"type":"ready","request_id":"…","model_name":"default","sample_rate":16000,"frame_size":1280,
    "audio_stream_names":["tts"],"text_stream_names":["tts"]}
   ```
   On an invalid voice it replies `{"type":"error","code":1011,"message":"Embeddings not found for <voice>…"}`.
4. Send the text then close the stream:
   ```json
   {"type":"text","text":"<text>"}
   {"type":"end_of_stream"}
   ```
5. Server streams messages until `{"type":"end_of_stream"}`:
   - `{"type":"audio","audio":"<base64 PCM16>"}` — decode base64 and concatenate.
   - `{"type":"text", …}` — token/timing echoes; **ignored** by the provider.

## Output

- `output_format=pcm_16000` → raw **PCM16 mono 16 kHz**. Wrap in a 44-byte WAV header
  for browser `decodeAudioData` (`pcm_to_wav`). `ulaw_8000` (telephony) is out of scope.

## Measured (single sample, 53-char FR sentence, voice Elise FR)

| Metric | Value |
|---|---|
| setup → ready | ~immediate |
| audio chunks | 53 |
| total PCM | 135 680 bytes (~4.24 s) |
| first-chunk latency | ~340 ms |
| total synthesis | ~1590 ms |

## Key findings

- **`voice_id=default` is INVALID** (`Embeddings not found for default`). A real catalog
  voice id is required, e.g. `b35yykvVppLXyw_l` (Elise, FR) /
  [catalog](https://docs.gradium.ai/guides/voices/all-voices).
- **Action required on `.env`:** the current `GRADIUM_VOICE_ID=default` will fail TTS.
  Set a real voice id before running the live TTS path. The provider factory (ST-3)
  will default to the FR Elise voice and treat `default` as unset.
- The server sends non-audio `text` messages interleaved — the provider must filter to
  `type=="audio"` and stop on `type=="end_of_stream"`.
- Batch strategy for Sprint 3: collect all `audio` chunks until `end_of_stream`, then
  play once. Streaming (play on first chunk) is Sprint 4 / TASK-WEB-004.
