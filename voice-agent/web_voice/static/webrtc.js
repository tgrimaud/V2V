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
const latencyEl = document.getElementById("latency");
const latencyStatsEl = document.getElementById("latencyStats");

let pc = null;
let micStream = null;

// ---- Per-turn response-time measurement (client-side, perceived latency) ----
// WebRTC playback is a continuous media stream, so there is no per-turn HTTP
// response to time (unlike index.html). Instead we watch two energy envelopes —
// the mic (user) and the remote track (bot) — and report the gap between the end
// of the user's speech and the first bot audio. That is the latency the caller
// actually perceives. Thresholds are RMS on [-1,1] float samples.
const USER_ON = 0.02;      // mic RMS above this = user is speaking
const USER_OFF = 0.012;    // mic RMS below this = user is silent
const BOT_ON = 0.015;      // remote RMS above this = bot started answering
const SILENCE_HANGOVER_MS = 500; // sustained silence before a turn is "ended"
const POLL_MS = 40;

let analysisCtx = null;
let micAnalyser = null;
let botAnalyser = null;
let pollTimer = null;

let userWasSpeaking = false;
let lastLoudTs = 0;        // last time mic was above USER_OFF
let awaitingBot = false;   // user finished, waiting for the bot to start
let userEndTs = 0;
const latencies = [];

function setStatus(text, cls) {
  statusText.textContent = text;
  statusEl.className = "status" + (cls ? " " + cls : "");
}

function rms(analyser, buf) {
  analyser.getFloatTimeDomainData(buf);
  let sum = 0;
  for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
  return Math.sqrt(sum / buf.length);
}

function makeAnalyser(stream) {
  const src = analysisCtx.createMediaStreamSource(stream);
  const analyser = analysisCtx.createAnalyser();
  analyser.fftSize = 1024;
  src.connect(analyser); // analysis only — not connected to destination
  return analyser;
}

function startLatencyPolling() {
  const micBuf = new Float32Array(micAnalyser.fftSize);
  const botBuf = new Float32Array(1024);
  resetTurnState();
  pollTimer = setInterval(() => {
    const now = performance.now();
    const micRms = rms(micAnalyser, micBuf);
    const botRms = botAnalyser ? rms(botAnalyser, botBuf) : 0;
    trackUserTurn(micRms, botRms, now);
    detectBotOnset(botRms, now);
  }, POLL_MS);
}

// Ignore mic energy while the bot is speaking so its speaker->mic echo is not
// mistaken for a new user turn (echoCancellation reduces but never removes it).
function trackUserTurn(micRms, botRms, now) {
  if (botRms > BOT_ON) return;
  if (micRms > USER_OFF) lastLoudTs = now;
  if (micRms > USER_ON) {
    if (!userWasSpeaking) setStatus("Listening…", "live");
    userWasSpeaking = true;
    awaitingBot = false;
  } else if (userWasSpeaking && now - lastLoudTs > SILENCE_HANGOVER_MS) {
    userWasSpeaking = false;
    awaitingBot = true;
    userEndTs = lastLoudTs;
    setStatus("Thinking…", "live");
  }
}

function detectBotOnset(botRms, now) {
  if (!awaitingBot || botRms <= BOT_ON) return;
  awaitingBot = false;
  reportLatency(Math.round(now - userEndTs));
  setStatus("Bot answering…", "live");
}

function reportLatency(ms) {
  latencyEl.textContent = ms + " ms";
  latencies.push(ms);
  const avg = Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length);
  latencyStatsEl.textContent = " · avg " + avg + " ms · " + latencies.length + " turn" + (latencies.length > 1 ? "s" : "");
}

function resetTurnState() {
  userWasSpeaking = false;
  awaitingBot = false;
  lastLoudTs = performance.now();
  userEndTs = 0;
}

function stopLatencyPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
  micAnalyser = null;
  botAnalyser = null;
  if (analysisCtx && analysisCtx.state !== "closed") analysisCtx.close();
  analysisCtx = null;
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
    analysisCtx = new AudioContext();
    micAnalyser = makeAnalyser(micStream);
    pc = new RTCPeerConnection();
    pc.addEventListener("track", (event) => {
      remoteAudio.srcObject = event.streams[0];
      botAnalyser = makeAnalyser(event.streams[0]);
      startLatencyPolling();
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
  stopLatencyPolling();
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
