"""Spoken filler / acknowledgement config (TASK-WEB-019, delivers US-020).

When the backend answer takes longer than a comfortable wait, the voice loop speaks
one short neutral holding phrase so the caller knows the turn is still progressing
(perceived-latency, Sprint 10). This module owns the phrase set, the env-tunable
threshold/enable flags and the DEC-002 safety check; the *timer* that decides when to
speak lives in `AnswerProcessor` (the only place that wraps the backend call).

Transport/trigger rationale is recorded in ADR-0036: the filler is a Flow-A (live turn)
concern driven by a runtime-local timer — no broker, no fabricated content. The phrases
are intentionally free of any digit / currency / invoice specific (DEC-002): a holding
phrase can never state an amount.
"""

import os
import random
from collections.abc import Sequence

# Env knobs (product/UX-tunable without a code change; confirm wording with Product).
FILLER_ENABLED_ENV_VAR = "VOICE_FILLER_ENABLED"
FILLER_THRESHOLD_ENV_VAR = "VOICE_FILLER_THRESHOLD_MS"
FILLER_PHRASES_ENV_VAR = "VOICE_FILLER_PHRASES"

# Perceived-wait threshold: speak the filler only when the answer is not ready by this
# delay. Default chosen as a comfortable spoken wait; tune per deployment.
DEFAULT_FILLER_THRESHOLD_MS = 1200.0

# FR generic holding phrases — no digit / amount / invoice specific (DEC-002).
DEFAULT_FILLER_PHRASES: tuple[str, ...] = (
    "Un instant, je vérifie.",
    "Laissez-moi vérifier cela.",
    "Un moment, s'il vous plaît.",
)

# Telemetry (observable so QA can report how often / after what wait the filler fires).
FILLER_SPOKEN_EVENT = "voice.filler.spoken"
FILLER_SPOKEN_METRIC = "voice.filler.spoken.count"
FILLER_TRIGGER_REASON = "answer_wait_exceeded"


def _has_digit(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


# DEC-002 invariant enforced at import: the built-in phrases never carry a figure.
assert not any(_has_digit(phrase) for phrase in DEFAULT_FILLER_PHRASES), (
    "DEFAULT_FILLER_PHRASES must contain no digit (DEC-002)"
)


def filler_enabled(env: dict[str, str] | None = None) -> bool:
    """True unless explicitly disabled (`0`/`false`/`no`/`off`). Default on for voice."""
    raw = (env if env is not None else os.environ).get(FILLER_ENABLED_ENV_VAR)
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def resolve_filler_threshold_ms(env: dict[str, str] | None = None) -> float:
    """Resolve the perceived-wait threshold; fall back to the default on a bad value."""
    raw = (env if env is not None else os.environ).get(FILLER_THRESHOLD_ENV_VAR)
    if raw is None:
        return DEFAULT_FILLER_THRESHOLD_MS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_FILLER_THRESHOLD_MS
    return value if value > 0 else DEFAULT_FILLER_THRESHOLD_MS


def resolve_filler_phrases(env: dict[str, str] | None = None) -> tuple[str, ...]:
    """Parse `|`-separated phrases; drop any digit-bearing entry (DEC-002).

    Falls back to the built-in set when the override is unset or leaves nothing safe.
    """
    raw = (env if env is not None else os.environ).get(FILLER_PHRASES_ENV_VAR)
    if raw is None:
        return DEFAULT_FILLER_PHRASES
    safe = [p.strip() for p in raw.split("|") if p.strip() and not _has_digit(p)]
    return tuple(safe) if safe else DEFAULT_FILLER_PHRASES


def pick_phrase(phrases: Sequence[str], rng: random.Random | None = None) -> str:
    """Pick one phrase at random (2–3 variants avoid a robotic canned line)."""
    chooser = rng if rng is not None else random
    return chooser.choice(list(phrases))
