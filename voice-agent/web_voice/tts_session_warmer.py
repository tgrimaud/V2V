"""Pre-opens a streaming TTS session so the connect + setup handshake is off the
per-turn critical path (TASK-WEB-011).

Gradium's TTS WebSocket is single-use: after one `synthesize()` + `end_of_stream`
the socket closes (a second synthesize on the same connection fails), so the
connection cannot be *reused* across turns — but it can be *pre-warmed*. This is a
thin, TTS-named specialization of the provider-agnostic `SessionWarmer` (shared with
the STT pre-warm, TASK-WEB-021); the lifecycle (start/acquire/aclose) is identical.

Measured impact (TASK-STT-013 post-fix baseline, docs/qa/stt-013-finalize-tail-spike.md):
the TTS `open()` costs ~90 ms warm / ~188 ms cold; moving it off the per-turn path
brings `tts_first_audio` p95 ~484 -> ~394 ms and the composite under the ADR-0018
800 ms gate. It never invents audio and carries no secret (the provider owns the key).
"""

from .session_warmer import SessionWarmer


class TtsSessionWarmer(SessionWarmer):
    """Keeps one streaming TTS session pre-opened, off the per-turn critical path."""
