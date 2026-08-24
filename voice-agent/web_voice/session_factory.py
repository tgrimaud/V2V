"""Transport-agnostic voice session factory (TASK-WEB-027, ADR-0043).

The session-building logic (STT/TTS processors, end-of-call farewell, channel-egress
probe, per-language provider selection, streaming vs batch `StreamingVoiceSession`
assembly) used to live **inside** `WebRtcSignalingService`. That coupling was the only
reason a second transport counted as "new work". This factory takes an **already-built
transport** plus the call envelope + telemetry and returns a built session, so WebRTC,
the interim WebSocket path (TASK-WEB-028) and the future Genesys Audio Connector
(ADR-0040) are thin transport adapters over one session core.

The internal audio boundary stays **PCM16 / 16 kHz**; any codec / sample-rate conversion
lives inside each transport adapter, never here (ADR-0043 point 3).
"""

import logging
import os
from typing import Any

from .call_end_farewell import (
    DEFAULT_CLOSING_MESSAGE,
    DEFAULT_CONFIRM_PROMPT,
    DEFAULT_CONFIRM_TIMEOUT_S,
    CallEndFarewellProcessor,
)
from .channel_egress_probe import ChannelEgressProbe
from .closing_intent import (
    DEFAULT_CLOSING_PHRASES,
    DEFAULT_DONE_PHRASES,
    ClosingIntentDetector,
)
from .end_of_turn import MIN_SAFE_SILENCE_WINDOW_MS
from .streaming_runtime import StreamingVoiceSession
from .streaming_stt_processor import StreamingSttProcessor
from .streaming_tts_processor import StreamingTtsProcessor
from .utterance_aggregator import UtteranceAggregator

_logger = logging.getLogger(__name__)
# Warn at most once per process when the end-of-turn hold override is clamped to the
# safe floor, so an operator sees the effective value without per-connection spam.
_silence_clamp_warned = False

DEFAULT_SAMPLE_RATE = 16000

_FALSE_VALUES = frozenset({"0", "false", "no", "off"})

# TASK-WEB-022 (lever 3): the tuned end-of-turn hold is the pilot RUNTIME default. The live
# before/after pass (2026-07-29, real backend) measured 350 ms with a 0/10 premature-cut rate
# (vs 500 ms), so the streaming runtime holds 350 ms by default while the detector library
# default (`DEFAULT_SILENCE_WINDOW_MS`, 500 ms) stays untouched for batch/fixture callers.
PILOT_END_OF_TURN_SILENCE_MS = 350.0


def _farewell_config() -> dict[str, Any]:
    """Resolve the env-tunable end-of-call farewell settings (TASK-WEB-010, ADR-0035).

    Mirrors the barge-in env pattern: bad values fall back to the defaults rather than
    crashing a call. `VOICE_FAREWELL_ENABLED=0` disables the feature entirely (the
    pre-existing manual-hangup behaviour then applies).
    """
    enabled = os.environ.get("VOICE_FAREWELL_ENABLED", "1").strip().lower() not in _FALSE_VALUES
    return {
        "enabled": enabled,
        "prompt": os.environ.get("VOICE_FAREWELL_PROMPT", DEFAULT_CONFIRM_PROMPT),
        "closing": os.environ.get("VOICE_FAREWELL_CLOSING", DEFAULT_CLOSING_MESSAGE),
        "timeout_s": _float_env("VOICE_FAREWELL_CONFIRM_TIMEOUT_S", DEFAULT_CONFIRM_TIMEOUT_S),
        "closing_phrases": _phrase_env("VOICE_FAREWELL_PHRASES", DEFAULT_CLOSING_PHRASES),
        "done_phrases": _phrase_env("VOICE_FAREWELL_DONE_PHRASES", DEFAULT_DONE_PHRASES),
    }


def _float_env(env_var: str, default: float) -> float:
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _phrase_env(env_var: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    phrases = tuple(part.strip() for part in raw.split(",") if part.strip())
    return phrases or default


def _barge_in_config() -> dict[str, int]:
    """Read the optional anti-echo barge-in overrides from the environment.

    Returns only the keys that are set so the `StreamingSttProcessor` defaults apply
    otherwise. Invalid values are ignored (defaults win) rather than crashing a call.
    """
    config: dict[str, int] = {}
    for env_var, kwarg in (
        ("VOICE_BARGE_IN_THRESHOLD", "barge_in_amplitude_threshold"),
        ("VOICE_BARGE_IN_FRAMES", "barge_in_confirm_frames"),
    ):
        raw = os.environ.get(env_var)
        if raw is None:
            continue
        try:
            config[kwarg] = int(raw)
        except ValueError:
            continue
    return config


def _silence_window_config() -> dict[str, float]:
    """Resolve the end-of-turn hold for the streaming runtime (TASK-WEB-015/022 lever 3).

    Defaults to the validated tuned hold (`PILOT_END_OF_TURN_SILENCE_MS`, 350 ms).
    `VOICE_END_OF_TURN_SILENCE_MS` overrides it: a value below `MIN_SAFE_SILENCE_WINDOW_MS`
    is clamped to the floor (never honoured) so a misconfiguration can't drop the loop into
    constant premature cuts; unset or invalid -> the pilot default applies.
    """
    raw = os.environ.get("VOICE_END_OF_TURN_SILENCE_MS")
    if raw is None:
        return {"silence_window_ms": PILOT_END_OF_TURN_SILENCE_MS}
    try:
        value = float(raw)
    except ValueError:
        return {"silence_window_ms": PILOT_END_OF_TURN_SILENCE_MS}
    if value <= 0:
        return {"silence_window_ms": PILOT_END_OF_TURN_SILENCE_MS}
    if value < MIN_SAFE_SILENCE_WINDOW_MS:
        _warn_silence_clamp_once(value)
        return {"silence_window_ms": MIN_SAFE_SILENCE_WINDOW_MS}
    return {"silence_window_ms": value}


def _stt_prewarm_enabled() -> bool:
    """Whether to pre-open the first turn's STT session at connect (TASK-WEB-021 / lever 2).

    OFF by default (opt-in) pending a live validation of Gradium's idle-socket behaviour.
    See the original rationale in the Sprint 6/7 notes: `acquire()` only recovers from an
    open *failure*, not from a stale-but-opened session, so this stays opt-in
    (`VOICE_STT_PREWARM=1`) until a live turn-1 sample confirms a `hit` (not a stale
    `fallback`). The connect-time backend warm-up (the larger, side-effect-free win) stays on.
    """
    raw = os.environ.get("VOICE_STT_PREWARM")
    if raw is None:
        return False
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _warn_silence_clamp_once(requested: float) -> None:
    """Warn (once per process) that a below-floor end-of-turn hold was clamped."""
    global _silence_clamp_warned
    if _silence_clamp_warned:
        return
    _silence_clamp_warned = True
    _logger.warning(
        "VOICE_END_OF_TURN_SILENCE_MS=%.0f is below the safe floor; clamped to %.0f ms",
        requested,
        MIN_SAFE_SILENCE_WINDOW_MS,
    )


class SessionFactory:
    """Builds a `StreamingVoiceSession` over any transport (WebRTC / WebSocket / Genesys).

    Holds the transport-independent dependencies (ingress, egress, backend, streaming
    STT/TTS providers and their per-language maps). `build_session` is the single seam a
    transport adapter calls; the transport itself is built by the adapter and passed in.
    """

    def __init__(
        self,
        *,
        ingress: Any,
        egress: Any,
        backend: Any,
        streaming_provider: Any = None,
        streaming_tts_provider: Any = None,
        streaming_providers_by_language: dict[str, Any] | None = None,
        streaming_tts_providers_by_language: dict[str, Any] | None = None,
    ) -> None:
        self._ingress = ingress
        self._egress = egress
        self._backend = backend
        self._streaming_provider = streaming_provider
        self._streaming_tts_provider = streaming_tts_provider
        self._streaming_providers_by_language = {
            key.lower(): value for key, value in (streaming_providers_by_language or {}).items()
        }
        self._streaming_tts_providers_by_language = {
            key.lower(): value for key, value in (streaming_tts_providers_by_language or {}).items()
        }

    def build_session(self, transport, envelope, telemetry) -> tuple[StreamingVoiceSession, Any]:
        """Assemble the session for a built transport: streaming (with STT processor +
        farewell) when a streaming provider is configured, else the batch aggregator path.
        Returns `(session, farewell_or_None)` exactly as the WebRTC path did."""
        tts_processor = self._build_tts_processor(envelope, telemetry)
        if self._streaming_provider is not None:
            return self._build_streaming_session(transport, envelope, telemetry, tts_processor)
        return self._build_batch_session(transport, envelope, telemetry, tts_processor), None

    def _streaming_provider_for(self, envelope) -> Any:
        language = (getattr(envelope, "language", None) or "").lower()
        return self._streaming_providers_by_language.get(language, self._streaming_provider)

    def _streaming_tts_provider_for(self, envelope) -> Any:
        language = (getattr(envelope, "language", None) or "").lower()
        return self._streaming_tts_providers_by_language.get(language, self._streaming_tts_provider)

    def _build_egress_probe(self, envelope, telemetry) -> ChannelEgressProbe:
        """Runtime channel-egress probe (TASK-WEB-014): measures the first audio frame's
        hand-off to `transport.output()` so the CHANNEL_EGRESS slice is measured on the
        streaming path and the mouth-to-ear composite folds it in. Provider label mirrors
        the active TTS provider so the egress span carries a meaningful provider attribute."""
        provider = self._streaming_tts_provider_for(envelope)
        provider_name = getattr(provider, "name", None) or "gradium-tts"
        return ChannelEgressProbe(envelope, telemetry, provider_name=provider_name)

    def _build_tts_processor(self, envelope, telemetry):
        """Streaming TTS processor for the session, or None (batch TTS fallback)."""
        if self._streaming_tts_provider is None:
            return None
        provider = self._streaming_tts_provider_for(envelope)
        return StreamingTtsProcessor(
            provider,
            envelope,
            telemetry,
            provider_name=provider.name,
        )

    def _build_streaming_session(
        self, transport, envelope, telemetry, tts_processor
    ) -> tuple[StreamingVoiceSession, Any]:
        provider = self._streaming_provider_for(envelope)
        stt = StreamingSttProcessor(
            provider,
            envelope,
            telemetry,
            provider_name=provider.name,
            # Anti-echo barge-in gate, tunable without a code change (TASK-WEB-008): raise
            # VOICE_BARGE_IN_THRESHOLD on echoey speaker setups so the bot's own residual
            # echo does not self-interrupt; VOICE_BARGE_IN_FRAMES sets the sustained-onset
            # count. Unset -> the processor defaults apply.
            **_barge_in_config(),
            # End-of-turn hold, tunable without a code change (TASK-WEB-015 lever 3):
            # VOICE_END_OF_TURN_SILENCE_MS shortens the trailing-silence confirmation to
            # shave latency, clamped to a safe floor. Unset -> the processor default (500 ms).
            **_silence_window_config(),
            # Pre-open the first turn's STT session at connect (TASK-WEB-021 / lever 2);
            # opt-in via VOICE_STT_PREWARM=1 (off by default pending live idle-socket
            # validation — see _stt_prewarm_enabled).
            prewarm=_stt_prewarm_enabled(),
        )
        farewell = self._build_farewell_processor(envelope, telemetry)
        session = StreamingVoiceSession(
            transport,
            ingress=self._ingress,
            egress=self._egress,
            envelope=envelope,
            backend=self._backend,
            telemetry=telemetry,
            # The streaming STT processor consumes continuous audio, owns end-of-turn
            # detection + its span and emits the final transcript itself.
            stt_processor=stt,
            tts_processor=tts_processor,
            # Conversational end-of-call (TASK-WEB-010): inspects the final transcript
            # between STT and the answer step, before the backend is asked.
            pre_answer=[farewell] if farewell is not None else [],
            pre_output=[self._build_egress_probe(envelope, telemetry)],
        )
        return session, farewell

    def _build_farewell_processor(self, envelope, telemetry) -> Any:
        """End-of-call farewell processor for the session, or None when disabled."""
        config = _farewell_config()
        if not config["enabled"]:
            return None
        detector = ClosingIntentDetector(
            closing_phrases=config["closing_phrases"], done_phrases=config["done_phrases"]
        )
        return CallEndFarewellProcessor(
            detector,
            envelope,
            telemetry,
            confirm_prompt=config["prompt"],
            closing_message=config["closing"],
            confirm_timeout_s=config["timeout_s"],
        )

    def _build_batch_session(
        self, transport, envelope, telemetry, tts_processor
    ) -> StreamingVoiceSession:
        aggregator = UtteranceAggregator(
            sample_rate_hz=DEFAULT_SAMPLE_RATE,
            telemetry=telemetry,
            envelope=envelope,
            provider_name=self._ingress.provider_name,
        )
        return StreamingVoiceSession(
            transport,
            ingress=self._ingress,
            egress=self._egress,
            envelope=envelope,
            backend=self._backend,
            telemetry=telemetry,
            pre_stt=[aggregator],
            # The aggregator owns incremental end-of-turn detection + its span on the
            # streaming path, so the batch detector in the ingress is skipped here.
            stt_detects_end_of_turn=False,
            tts_processor=tts_processor,
            pre_output=[self._build_egress_probe(envelope, telemetry)],
        )
