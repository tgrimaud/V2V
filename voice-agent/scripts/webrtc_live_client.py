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
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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


async def run(url: str, audio: str | None) -> int:
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.contrib.media import MediaPlayer
    from aiortc.mediastreams import AudioStreamTrack

    pc = RTCPeerConnection()
    track = MediaPlayer(audio).audio if audio else AudioStreamTrack()
    pc.addTrack(track)
    got_audio = asyncio.Event()

    @pc.on("track")
    def _on_track(t):
        async def _drain():
            while True:
                await t.recv()
                got_audio.set()
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
    try:
        await asyncio.wait_for(got_audio.wait(), timeout=8)
        print("received_bot_audio: True")
    except asyncio.TimeoutError:
        print("received_bot_audio: False (no utterance flushed / silent source)")
    await pc.close()
    return 0 if pc.connectionState == "connected" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Live WebRTC evidence client")
    parser.add_argument("--url", default="http://127.0.0.1:8090")
    parser.add_argument("--audio", default=None, help="optional WAV to stream as mic input")
    args = parser.parse_args()
    return asyncio.run(run(args.url, args.audio))


if __name__ == "__main__":
    raise SystemExit(main())
