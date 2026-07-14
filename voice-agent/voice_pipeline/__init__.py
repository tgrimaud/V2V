"""Pipecat batch voice pipeline (Sprint 4 / TASK-WEB-005).

Wraps the existing STT and TTS paths as Pipecat frame processors and composes them
into an in-memory batch pipeline (STT -> echo -> TTS), the ADR-0002 target runtime
running in batch parity (no WebRTC/streaming yet). It is selectable at runtime
alongside the stdlib path.

Import submodules directly (`from voice_pipeline.stt_service import SttFrameProcessor`)
so the STT and TTS service modules keep their hard separation: `stt_service` must not
pull `tts_synthesis` and `tts_service` must not pull `stt_validation`. Only the
composing `pipeline` module may reference both halves.
"""

__all__: list[str] = []
