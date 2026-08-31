"""Headless Genesys AudioHook client — test the `/genesys/audiohook` endpoint WITHOUT Genesys.

TASK-WEB-047. Everything the Genesys entry point owns at the transport boundary is
Genesys-independent, so it can be driven from a local environment: the connection-auth
handshake (X-API-KEY + IETF HTTP Message Signatures HMAC-SHA256, TASK-INFRA-012), the
AudioHook-shaped control channel (`open`/`opened`, `close`/`closed`, ADR-0043), the
PCMU/L16 <-> PCM16/16 kHz codec (`web_voice/genesys_codec.py`) and the session lifecycle.
This client points at a **local bridge** or the **deployed endpoint**, signs the handshake
exactly as `GenesysConnectionAuthenticator` rebuilds it, streams audio (a real PCM16/16 kHz
WAV transcoded to the wire codec, or synthetic non-PII noise — DEC-014), then saves the bot
answer WAV and prints a per-turn summary.

What still needs the live Genesys org (stay `measured=false` for the runbook): the cloud
legs (ingress / Architect fork / egress), the negotiated codec, native barge-in/EOT events
and the Architect degraded branch — see `docs/operations/genesys-live-measurement-runbook.md`.

Signature scheme (must match `web_voice/genesys_signature.py` byte-for-byte): the base is
each covered component on its own line as `"name": value`, then a final
`"@signature-params": <the exact Signature-Input value>` line, joined with `\\n`, HMAC-SHA256
keyed by the base64-decoded shared secret.

Usage — start the endpoint (local), then drive one turn:

    cd voice-agent
    set -a; . ../.env; set +a
    export GENESYS_AUDIOHOOK_API_KEY=local-dev-key
    export GENESYS_AUDIOHOOK_SECRET=$(python3 -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())")
    .venv/bin/python -m web_voice.server --genesys on --backend http \\
        --stt-mode streaming --tts-mode streaming &

    # credentials come from the env (same vars as the server) — never on argv (visible in `ps`)
    .venv/bin/python scripts/genesys_local_client.py \\
        --url ws://127.0.0.1:8090/genesys/audiohook \\
        --audio fixtures/long/billing-question.wav --codec L16 --out /tmp/genesys-answer.wav

    # deployed endpoint (export the vault-rendered GENESYS_AUDIOHOOK_SECRET first; edge overrides):
    export GENESYS_AUDIOHOOK_API_KEY=... GENESYS_AUDIOHOOK_SECRET=...   # base64 secret
    .venv/bin/python scripts/genesys_local_client.py \\
        --url wss://vip-ai4cc-voice-t01.prod.lan/genesys/audiohook --insecure \\
        --authority vip-ai4cc-voice-t01.prod.lan --audio speech.wav
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import math
import os
import random
import struct
import sys
import time
import uuid
import wave
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_voice import genesys_codec  # noqa: E402
from web_voice.genesys_auth import DEFAULT_API_KEY_HEADER  # noqa: E402
from web_voice.websocket_framing import ControlType  # noqa: E402

INTERNAL_SAMPLE_RATE = 16000
DEFAULT_FRAME_MS = 20
# Covered components + their fixed order (must mirror what the server parses/rebuilds).
COVERED_COMPONENTS = (
    "@request-target",
    "@authority",
    "audiohook-organization-id",
    "audiohook-session-id",
    "audiohook-correlation-id",
    "x-api-key",
)
# RMS above which a decoded bot frame counts as real speech (separates the first audible
# answer frame from silence/keepalive), same scale as the WS live client.
AUDIBLE_RMS_THRESHOLD = 200.0
# Trailing near-silence appended after the clip so the server end-of-turn detector flushes
# the utterance (raw PCM over WS transmits every frame, unlike Opus/DTX — zeros are fine).
TRAILING_SILENCE_MS = 800
# A far-enough default signature validity window (server rejects once now > expires + skew).
DEFAULT_EXPIRES_WINDOW_S = 300


def build_signed_headers(
    *,
    request_target: str,
    authority: str,
    api_key: str,
    secret: bytes,
    org_id: str,
    session_id: str,
    correlation_id: str,
    created: int,
    expires: int,
    nonce: str,
    key_id: str,
    api_key_header: str = DEFAULT_API_KEY_HEADER,
    label: str = "sig1",
) -> dict[str, str]:
    """Build the AudioHook connection-auth headers the server's authenticator accepts."""
    covered = " ".join(f'"{name}"' for name in COVERED_COMPONENTS)
    raw_params = (
        f"({covered});keyid=\"{key_id}\";nonce=\"{nonce}\";"
        f"alg=\"hmac-sha256\";created={created};expires={expires}"
    )
    values = {
        "@request-target": request_target,
        "@authority": authority,
        "audiohook-organization-id": org_id,
        "audiohook-session-id": session_id,
        "audiohook-correlation-id": correlation_id,
        "x-api-key": api_key,
    }
    base_lines = [f'"{name}": {values[name]}' for name in COVERED_COMPONENTS]
    base_lines.append(f'"@signature-params": {raw_params}')
    signature = hmac.new(secret, "\n".join(base_lines).encode("utf-8"), hashlib.sha256).digest()
    return {
        api_key_header: api_key,
        "Audiohook-Organization-Id": org_id,
        "Audiohook-Session-Id": session_id,
        "Audiohook-Correlation-Id": correlation_id,
        "Signature-Input": f"{label}={raw_params}",
        "Signature": f"{label}=:{base64.b64encode(signature).decode('ascii')}:",
    }


def decode_secret(raw: str) -> bytes:
    """Base64-decode the shared secret (same padding-tolerant scheme as the server)."""
    stripped = raw.strip()
    return base64.b64decode(stripped + "=" * ((-len(stripped)) % 4))


def load_pcm16_16k(path: str) -> bytes:
    """Load raw PCM16 mono 16 kHz bytes from a `.wav` (header stripped) or raw `.pcm` file."""
    if path.lower().endswith(".wav"):
        with wave.open(path, "rb") as handle:
            _require_pcm16_mono_16k(handle, path)
            return handle.readframes(handle.getnframes())
    return Path(path).read_bytes()


def _require_pcm16_mono_16k(handle: wave.Wave_read, path: str) -> None:
    if (handle.getsampwidth(), handle.getnchannels(), handle.getframerate()) != (2, 1, 16000):
        raise SystemExit(
            f"{path}: expected PCM16 mono 16 kHz "
            f"(got {handle.getsampwidth() * 8}-bit, {handle.getnchannels()}ch, "
            f"{handle.getframerate()} Hz). Convert first, e.g. "
            f"say -o out.wav --data-format=LEI16@16000 --file-format=WAVE 'texte'."
        )


def synthetic_pcm16_16k(duration_ms: int, *, seed: int = 1) -> bytes:
    """Deterministic low-amplitude non-PII noise (DEC-014); peak << the STT onset threshold."""
    rng = random.Random(seed)
    count = INTERNAL_SAMPLE_RATE * duration_ms // 1000
    return struct.pack(f"<{count}h", *(rng.randint(-300, 300) for _ in range(count)))


def iter_internal_frames(pcm16_16k: bytes, chunk: int) -> Iterator[bytes]:
    """Yield fixed-size PCM16/16 kHz frames; a trailing short frame is zero-padded."""
    for start in range(0, len(pcm16_16k), chunk):
        frame = pcm16_16k[start : start + chunk]
        if len(frame) < chunk:
            frame = frame + b"\x00" * (chunk - len(frame))
        yield frame


def frame_rms(pcm16: bytes) -> float:
    """RMS amplitude of a little-endian PCM16 buffer (0.0 for an empty/odd buffer)."""
    n = len(pcm16) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", pcm16[: n * 2])
    return math.sqrt(sum(s * s for s in samples) / n)


def write_wav(path: str, pcm16_16k: bytes) -> None:
    """Save decoded bot audio as a PCM16 mono 16 kHz WAV."""
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(INTERNAL_SAMPLE_RATE)
        handle.writeframes(pcm16_16k)


class _TurnState:
    """Collects bot audio + control frames received during one turn."""

    def __init__(self) -> None:
        self.bot_pcm16 = bytearray()
        self.control: list[dict] = []
        self.first_audible_at: float | None = None
        self.closed = False


async def _receive(ws, codec: str, state: _TurnState) -> None:
    """Drain server frames: binary -> decode wire audio; text -> control (print + record)."""
    async for message in ws:
        if message.type.name in ("CLOSE", "CLOSING", "CLOSED", "ERROR"):
            break
        if message.type.name == "BINARY":
            pcm16 = genesys_codec.to_internal_pcm16(message.data, codec)
            state.bot_pcm16.extend(pcm16)
            if state.first_audible_at is None and frame_rms(pcm16) >= AUDIBLE_RMS_THRESHOLD:
                state.first_audible_at = time.monotonic()
        elif message.type.name == "TEXT":
            _on_control(message.data, state)


def _on_control(data: str, state: _TurnState) -> None:
    try:
        frame = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return
    state.control.append(frame)
    print("control <-", frame)
    if frame.get("type") in (ControlType.CLOSED, ControlType.CALL_END):
        state.closed = True


def _load_input_audio(args) -> bytes:
    if args.audio:
        return load_pcm16_16k(args.audio)
    return synthetic_pcm16_16k(args.synthetic_ms)


def _connect_targets(args) -> tuple[str, str, str]:
    """Resolve (full_url, signed @request-target, signed @authority) from the args + URL.

    The query is OWNED here (built from --conversation-id) so the signed @request-target
    always matches the server's raw_path; any query in --url is ignored.
    """
    parts = urlsplit(args.url)
    query = f"conversationId={args.conversation_id}"
    full_url = f"{parts.scheme}://{parts.netloc}{parts.path}?{query}"
    request_target = args.request_target or f"{parts.path}?{query}"
    authority = args.authority or parts.netloc
    return full_url, request_target, authority


def _resolve_credentials(args) -> tuple[str, bytes]:
    """Resolve the API key + shared secret, preferring env over argv (argv leaks via `ps`).

    Defaults to the server's own env vars (`GENESYS_AUDIOHOOK_API_KEY` /
    `GENESYS_AUDIOHOOK_SECRET`); the flags stay as optional dev-only overrides.
    """
    api_key = args.api_key or os.environ.get("GENESYS_AUDIOHOOK_API_KEY") or ""
    raw_secret = args.secret or os.environ.get("GENESYS_AUDIOHOOK_SECRET") or ""
    if not api_key or not raw_secret:
        raise SystemExit(
            "missing credentials: set GENESYS_AUDIOHOOK_API_KEY + GENESYS_AUDIOHOOK_SECRET "
            "(base64) in the environment, or pass --api-key/--secret (argv is visible in `ps`)."
        )
    return api_key, decode_secret(raw_secret)


async def run(args) -> int:
    import aiohttp

    api_key, secret = _resolve_credentials(args)
    full_url, request_target, authority = _connect_targets(args)
    now = int(time.time())
    headers = build_signed_headers(
        request_target=request_target,
        authority=authority,
        api_key=api_key,
        secret=secret,
        org_id=args.org_id,
        session_id=args.session_id,
        correlation_id=args.conversation_id,
        created=now,
        expires=now + args.expires_window,
        nonce=uuid.uuid4().hex,
        key_id=args.key_id,
        api_key_header=args.api_key_header,
    )
    ssl_arg = False if (full_url.startswith("wss://") and args.insecure) else None
    if ssl_arg is False:
        print("WARNING: --insecure disables TLS verification (self-signed edge only).", file=sys.stderr)
    chunk = INTERNAL_SAMPLE_RATE * args.frame_ms // 1000 * 2
    clip = list(iter_internal_frames(_load_input_audio(args), chunk))
    trailing = [b"\x00" * chunk] * max(1, TRAILING_SILENCE_MS // args.frame_ms)
    state = _TurnState()

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(full_url, headers=headers, ssl=ssl_arg, max_msg_size=0) as ws:
            receiver = asyncio.ensure_future(_receive(ws, args.codec, state))
            await ws.send_str(json.dumps({"type": ControlType.OPEN, "language": args.language}))
            stop_speaking_at = await _stream(ws, clip, trailing, args.codec, args.frame_ms)
            await asyncio.sleep(args.hold)
            await ws.send_str(json.dumps({"type": ControlType.CLOSE}))
            await asyncio.sleep(0.2)
            receiver.cancel()
    _report(args, state, stop_speaking_at)
    return 0


async def _stream(ws, clip, trailing, codec: str, frame_ms: int) -> float:
    """Send the clip then the trailing silence at ~real-time cadence; return the stop time."""
    for frame in clip:
        await ws.send_bytes(genesys_codec.from_internal_pcm16(frame, codec))
        await asyncio.sleep(frame_ms / 1000)
    stop_speaking_at = time.monotonic()
    for frame in trailing:
        await ws.send_bytes(genesys_codec.from_internal_pcm16(frame, codec))
        await asyncio.sleep(frame_ms / 1000)
    return stop_speaking_at


def _report(args, state: _TurnState, stop_speaking_at: float) -> None:
    if state.bot_pcm16 and args.out:
        write_wav(args.out, bytes(state.bot_pcm16))
    control_types = [frame.get("type") for frame in state.control]
    print("---- turn summary ----")
    print("control frames:", control_types or "(none)")
    print("bot audio bytes (pcm16/16k):", len(state.bot_pcm16))
    if state.first_audible_at is not None:
        print("time_to_first_bot_audio_ms:", round((state.first_audible_at - stop_speaking_at) * 1000, 1))
    else:
        print("time_to_first_bot_audio_ms: none (no above-threshold bot frame received)")
    if args.out and state.bot_pcm16:
        print("answer WAV:", args.out)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Headless Genesys AudioHook client (no live Genesys)")
    parser.add_argument("--url", default="ws://127.0.0.1:8090/genesys/audiohook")
    parser.add_argument(
        "--api-key",
        help="API key (dev override; prefer env GENESYS_AUDIOHOOK_API_KEY — argv is visible in `ps`)",
    )
    parser.add_argument(
        "--secret",
        help="base64 shared secret (dev override; prefer env GENESYS_AUDIOHOOK_SECRET — argv leaks via `ps`)",
    )
    parser.add_argument("--codec", default=genesys_codec.DEFAULT_CODEC, choices=genesys_codec.SUPPORTED_CODECS)
    parser.add_argument("--audio", help="PCM16 mono 16 kHz .wav/.pcm to stream (real speech)")
    parser.add_argument("--synthetic-ms", type=int, default=1200, help="synthetic non-PII noise if no --audio")
    parser.add_argument("--out", help="save the decoded bot answer as a PCM16/16k WAV")
    parser.add_argument("--conversation-id", default=f"local-{uuid.uuid4().hex[:8]}")
    parser.add_argument("--session-id", default=f"sess-{uuid.uuid4().hex[:8]}")
    parser.add_argument("--org-id", default="local-test-org")
    parser.add_argument("--key-id", default="voice-support-pilot")
    parser.add_argument("--api-key-header", default=DEFAULT_API_KEY_HEADER)
    parser.add_argument("--authority", help="override signed @authority (deployed edge / GENESYS_AUDIOHOOK_AUTHORITY)")
    parser.add_argument("--request-target", help="override signed @request-target (HAProxy edge rewrite)")
    parser.add_argument("--expires-window", type=int, default=DEFAULT_EXPIRES_WINDOW_S)
    parser.add_argument("--language", default="fr")
    parser.add_argument("--frame-ms", type=int, default=DEFAULT_FRAME_MS)
    parser.add_argument("--hold", type=float, default=12.0, help="seconds to keep the call open for the answer")
    parser.add_argument("--insecure", action="store_true", help="skip TLS verify for a self-signed wss:// edge")
    return parser


def main() -> int:
    return asyncio.run(run(_build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
