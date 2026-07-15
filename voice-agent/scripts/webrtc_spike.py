"""WebRTC transport spike (Sprint 6 / TASK-WEB-007).

Locks the `SmallWebRTCTransport` dependency + signaling surface and, when the
`pipecat-ai[webrtc]` extra is installed, runs an in-process SDP offer/answer smoke
(two `aiortc` peer connections, no network) to prove the handshake end to end.

This script is deliberately tolerant of a missing extra: `SmallWebRTCTransport`
hard-imports `aiortc`/`av`/`cv2`, which may be unavailable (offline index, or no
Python 3.14 wheel yet). In that case it prints the resolved API + the install hint
instead of failing, so the spike still documents the contract. See
`docs/qa/webrtc-transport-spike.md`.

Run: `.venv/bin/python scripts/webrtc_spike.py`
"""

import asyncio
import sys
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from web_voice.webrtc_support import probe_webrtc_support  # noqa: E402


def report_support() -> bool:
    support = probe_webrtc_support()
    print("=== WebRTC transport support probe ===")
    print("available :", support.available)
    if not support.available:
        print("missing   :", support.missing)
        print("install   :", support.install_hint)
    return support.available


async def in_process_offer_answer_smoke() -> None:
    """Two aiortc peers negotiate an audio-only session in-process (no network)."""
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.mediastreams import AudioStreamTrack

    caller = RTCPeerConnection()
    callee = RTCPeerConnection()
    try:
        caller.addTrack(AudioStreamTrack())
        offer = await caller.createOffer()
        await caller.setLocalDescription(offer)
        await callee.setRemoteDescription(
            RTCSessionDescription(sdp=caller.localDescription.sdp, type="offer")
        )
        answer = await callee.createAnswer()
        await callee.setLocalDescription(answer)
        print("=== in-process offer/answer smoke ===")
        print("offer type   :", caller.localDescription.type)
        print("answer type  :", callee.localDescription.type)
        print("answer has audio m-line:", "m=audio" in callee.localDescription.sdp)
        print("SMOKE OK" if callee.localDescription.type == "answer" else "SMOKE FAIL")
    finally:
        await caller.close()
        await callee.close()


def report_signaling_contract() -> None:
    print("=== signaling contract (HTTP, media plane = WebRTC) ===")
    print("POST  /api/voice/webrtc/offer  {sdp,type,pc_id?,restart_pc?,requestData?}")
    print("      -> {sdp,type:'answer',pc_id}")
    print("PATCH /api/voice/webrtc/ice    {pc_id,candidates:[{candidate,sdp_mid,sdp_mline_index}]}")
    print("handler: SmallWebRTCRequestHandler.handle_web_request / handle_patch_request")
    print("STUN required for NAT; TURN required for symmetric/corporate NAT (coturn).")


def main() -> None:
    available = report_support()
    report_signaling_contract()
    if available:
        asyncio.run(in_process_offer_answer_smoke())
    else:
        print("Skipping live handshake smoke: install the extra to run it.")


if __name__ == "__main__":
    main()
