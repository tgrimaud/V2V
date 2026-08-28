"""Genesys AudioHook replay / freshness protection (TASK-INFRA-012).

Split out of `genesys_auth.py` (module size budget) but conceptually part of the
connection-auth policy. Two enforcement concerns, both applied AFTER the HMAC
signature has been verified as authentic:

1. **Freshness** (`signature_is_fresh`): the signature MUST carry an ``expires`` param
   (absent -> not fresh -> the caller rejects it). When a ``created`` param is present
   its age is bounded — rejected if it is in the future beyond a small clock skew, or
   older than ``max_age_s`` (env ``GENESYS_AUDIOHOOK_MAX_SIGNATURE_AGE_S``, default 300s).
   ``created`` stays OPTIONAL so the published Genesys golden vector (which sets a far
   ``expires`` and a fixed ``created``) is still admissible when the clock is near its
   ``created``; the signature base / canonicalization is untouched.

2. **Replay** (`NonceCache`): a bounded, in-memory cache rejects a ``nonce`` reused
   within the window. Memory-bounded (FIFO eviction past the cap, env
   ``GENESYS_AUDIOHOOK_NONCE_CACHE_SIZE``, default 10000) and safe for the single
   async handler thread (no locking needed). A missing/empty ``nonce`` is not subject
   to replay rejection (the scheme leaves ``nonce`` optional).

No secret / signature / API-key / PII is handled here — only the signature params
(``created`` / ``expires`` / ``nonce``), which are non-sensitive protocol metadata.
"""

from __future__ import annotations

from collections import OrderedDict

DEFAULT_MAX_SIGNATURE_AGE_S = 300.0
DEFAULT_CLOCK_SKEW_S = 5.0
DEFAULT_NONCE_CACHE_SIZE = 10000


def signature_is_fresh(
    params: dict[str, str],
    now: float,
    max_age_s: float,
    skew_s: float = DEFAULT_CLOCK_SKEW_S,
) -> bool:
    """True when `expires` is present + not passed and any `created` is within age bounds."""
    expires = _as_float(params.get("expires"))
    if expires is None or now > expires + skew_s:
        return False
    created = _as_float(params.get("created"))
    if created is None:
        return True
    return now - max_age_s <= created <= now + skew_s


def _as_float(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class NonceCache:
    """Bounded FIFO nonce cache; `is_replay` records a fresh nonce and flags a reuse."""

    def __init__(self, capacity: int = DEFAULT_NONCE_CACHE_SIZE) -> None:
        self._capacity = max(1, capacity)
        self._seen: OrderedDict[str, None] = OrderedDict()

    def is_replay(self, nonce: str) -> bool:
        if not nonce:
            return False
        if nonce in self._seen:
            return True
        self._seen[nonce] = None
        while len(self._seen) > self._capacity:
            self._seen.popitem(last=False)
        return False
