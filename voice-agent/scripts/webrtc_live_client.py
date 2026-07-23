"""Live WebRTC client for TASK-WEB-007 evidence.

Connects to a running voice server, negotiates a real WebRTC session against the
`/api/voice/webrtc/offer` route (same path the browser uses), and reports the
correlation id + whether the media plane reaches `connected`. Optionally streams a
speech WAV in as the mic track so the full STT->answer->TTS loop runs over WebRTC.

Run (server must be up):
  .venv/bin/python scripts/webrtc_live_client.py --url http://127.0.0.1:8090 [--audio file.wav]
"""

import argparse
import asyncio
import json
import sys
import time
import urllib.request
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Received-audio RMS above which a bot frame counts as real speech (int16 scale). The
# WebRTC output track sends digital-silence keepalive (RMS ~0) before the answer, so a
# small threshold cleanly separates the first *audible* frame from the keepalive.
_AUDIBLE_RMS_THRESHOLD = 200.0


def _clip_duration_s(audio: str | None) -> float | None:
    """Duration of the mic WAV clip, used to place the 'customer stops speaking' mark.

    Best-effort: only WAV is readable here; any other container -> None (the client
    then reports first-audible relative to connect, and labels the gap honestly)."""
    if not audio:
        return None
    try:
        with wave.open(audio, "rb") as handle:
            rate = handle.getframerate()
            return handle.getnframes() / float(rate) if rate else None
    except Exception:  # noqa: BLE001 - non-WAV / unreadable clip -> no clip mark
        return None


def _frame_rms(frame: object) -> float:
    """RMS amplitude of an aiortc AudioFrame (int16), 0.0 if it cannot be read."""
    try:
        import numpy as np

        samples = frame.to_ndarray().astype("float64")  # type: ignore[attr-defined]
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples * samples)))
    except Exception:  # noqa: BLE001 - defensive: never crash the drain loop on a frame
        return 0.0


async def _wait_ice(peer) -> None:
    if peer.iceGatheringState == "complete":
        return
    done = asyncio.Event()
    peer.on(
        "icegatheringstatechange",
        lambda: done.set() if peer.iceGatheringState == "complete" else None,
    )
    await asyncio.wait_for(done.wait(), timeout=10)


def _post_offer(url: str, sdp: str, sdp_type: str) -> dict:
    body = json.dumps({"sdp": sdp, "type": sdp_type}).encode("utf-8")
    req = urllib.request.Request(
        url + "/api/voice/webrtc/offer", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


async def run(url: str, audio: str | None, hold: float = 12.0) -> int:
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.contrib.media import MediaPlayer
    from aiortc.mediastreams import AudioStreamTrack

    pc = RTCPeerConnection()
    track = MediaPlayer(audio).audio if audio else AudioStreamTrack()
    pc.addTrack(track)
    got_audio = asyncio.Event()
    # Wall-clock (monotonic) of the first *audible* bot frame received, so the client
    # can log a true browser-received mouth-to-ear proxy for TASK-WEB-014 — the
    # server-side composite ends at "first frame emitted by the runtime"; this closes
    # the residual network + jitter-buffer + playout gap end to end.
    first_audible = {"at": None}

    @pc.on("track")
    def _on_track(t):
        async def _drain():
            while True:
                frame = await t.recv()
                got_audio.set()
                if first_audible["at"] is None and _frame_rms(frame) >= _AUDIBLE_RMS_THRESHOLD:
                    first_audible["at"] = time.monotonic()
        asyncio.ensure_future(_drain())

    await pc.setLocalDescription(await pc.createOffer())
    await _wait_ice(pc)
    answer = await asyncio.to_thread(
        _post_offer, url, pc.localDescription.sdp, pc.localDescription.type
    )
    print("correlation_id:", answer.get("correlation_id"))
    await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))

    for _ in range(100):
        if pc.connectionState == "connected":
            break
        await asyncio.sleep(0.1)
    print("connection_state:", pc.connectionState)
    # The mic clip starts streaming once the media plane is connected; place the
    # "customer stops speaking" mark at connect + clip duration (approximate: the
    # client cannot see the server's end-of-turn hold, which the server-side composite
    # folds in separately).
    connected_at = time.monotonic()
    clip_s = _clip_duration_s(audio)
    # Hold the session open so the whole clip streams, the aggregator flushes the
    # utterance, and STT->answer->TTS completes before we hang up. (The bot output
    # track sends silence keepalive immediately, so we cannot gate the close on
    # "first bot frame"; we hold for a fixed window instead.)
    await asyncio.sleep(hold)
    print("received_bot_audio:", got_audio.is_set())
    _report_first_audible(first_audible["at"], connected_at, clip_s)
    await pc.close()
    return 0 if pc.connectionState == "connected" else 1


def _report_first_audible(
    first_audible_at: float | None, connected_at: float, clip_s: float | None
) -> None:
    """Log the client-observed first-audible proxy (browser-received, TASK-WEB-014)."""
    if first_audible_at is None:
        print("first_audible_bot_audio: none (only silence keepalive received)")
        return
    from_connect_ms = round((first_audible_at - connected_at) * 1000, 1)
    print("first_audible_from_connect_ms:", from_connect_ms)
    if clip_s is not None:
        # Mouth-to-ear proxy: from the mic clip's end (customer stops speaking) to the
        # first audible bot frame. Includes the server end-of-turn hold + STT + backend
        # + TTS + full channel egress (network + jitter + playout) — the true perceived
        # latency the server-side runtime composite cannot see past its own egress.
        mouth_to_ear_ms = round((first_audible_at - (connected_at + clip_s)) * 1000, 1)
        print("mouth_to_ear_proxy_ms:", mouth_to_ear_ms, f"(clip {round(clip_s, 3)}s)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Live WebRTC evidence client")
    parser.add_argument("--url", default="http://127.0.0.1:8090")
    parser.add_argument("--audio", default=None, help="optional WAV to stream as mic input")
    parser.add_argument("--hold", type=float, default=12.0, help="seconds to keep the call open")
    args = parser.parse_args()
    return asyncio.run(run(args.url, args.audio, args.hold))


if __name__ == "__main__":
    raise SystemExit(main())
