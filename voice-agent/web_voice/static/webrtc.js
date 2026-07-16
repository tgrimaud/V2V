// WebRTC streaming client (Sprint 6 / TASK-WEB-007).
//
// Minimal full-duplex client: capture the mic, negotiate one audio-only WebRTC
// session with the voice runtime, and play the bot's answer over the same channel.
// Non-trickle ICE: we wait for gathering to complete so the single POSTed offer
// carries the host candidates (enough for localhost / LAN; TURN handles the rest).

const OFFER_URL = "/api/voice/webrtc/offer";

const startBtn = document.getElementById("start");
const stopBtn = document.getElementById("stop");
const statusEl = document.getElementById("status");
const statusText = document.getElementById("statusText");
const corrEl = document.getElementById("corr");
const remoteAudio = document.getElementById("remote");

let pc = null;
let micStream = null;

function setStatus(text, cls) {
  statusText.textContent = text;
  statusEl.className = "status" + (cls ? " " + cls : "");
}

async function waitForIceGathering(peer) {
  if (peer.iceGatheringState === "complete") return;
  await new Promise((resolve) => {
    const check = () => {
      if (peer.iceGatheringState === "complete") {
        peer.removeEventListener("icegatheringstatechange", check);
        resolve();
      }
    };
    peer.addEventListener("icegatheringstatechange", check);
  });
}

// Browser audio processing is mandatory for barge-in (TASK-WEB-008): without echo
// cancellation the bot's own answer is played out the speaker, re-enters the mic, and
// the energy VAD treats it as speech -> the bot interrupts itself. noiseSuppression +
// autoGainControl further reduce false onsets from ambient noise / gain swings.
const AUDIO_CONSTRAINTS = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
};

async function startCall() {
  startBtn.disabled = true;
  setStatus("Requesting microphone…");
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: AUDIO_CONSTRAINTS });
    pc = new RTCPeerConnection();
    pc.addEventListener("track", (event) => {
      remoteAudio.srcObject = event.streams[0];
    });
    pc.addEventListener("connectionstatechange", () => {
      if (pc.connectionState === "connected") setStatus("Live — speak now", "live");
      if (["failed", "disconnected", "closed"].includes(pc.connectionState)) stopCall();
    });
    micStream.getTracks().forEach((track) => pc.addTrack(track, micStream));

    const offer = await pc.createOffer({ offerToReceiveAudio: true });
    await pc.setLocalDescription(offer);
    setStatus("Gathering ICE…");
    await waitForIceGathering(pc);

    setStatus("Negotiating…");
    const res = await fetch(OFFER_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type }),
    });
    if (!res.ok) throw new Error("signaling failed: " + res.status);
    const answer = await res.json();
    corrEl.textContent = answer.correlation_id || "—";
    await pc.setRemoteDescription({ sdp: answer.sdp, type: answer.type });
    stopBtn.disabled = false;
  } catch (err) {
    setStatus("Error: " + err.message, "error");
    stopCall();
  }
}

function stopCall() {
  stopBtn.disabled = true;
  startBtn.disabled = false;
  if (pc) {
    pc.close();
    pc = null;
  }
  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop());
    micStream = null;
  }
  if (statusEl.className.indexOf("error") === -1) setStatus("Idle");
}

startBtn.addEventListener("click", startCall);
stopBtn.addEventListener("click", stopCall);
