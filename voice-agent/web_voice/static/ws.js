"use strict";

// Browser WebSocket voice client (TASK-WEB-028, ADR-0043; single routed port per ADR-0047).
//
// Full-duplex over ONE `wss` connection (no TURN): the mic is captured, downsampled to
// 16 kHz PCM16 and streamed as binary frames; the bot's answer arrives as binary PCM16
// frames and JSON control frames (`opened`, `barge_in`, `call_end`, `pong`). The framing
// mirrors the server serializer (web_voice/websocket_framing.py) and the Genesys AudioHook
// shape. The socket rides the SAME origin as the page at `/ws` (TASK-WEB-038). A connection
// past the server's per-bridge session ceiling is refused with WS close 1013, which we
// surface as a "busy, try again" message.

const TARGET_SAMPLE_RATE = 16000; // Gradium PCM contract: mono, 16 kHz, s16le.
const USER_ON = 0.02; // mic RMS above this = user speaking
const USER_OFF = 0.012; // mic RMS below this = user silent
const SILENCE_HANGOVER_MS = 500; // sustained silence before a turn is "ended"

const connectBtn = document.getElementById("connect");
const disconnectBtn = document.getElementById("disconnect");
const languageEl = document.getElementById("language");
const statusEl = document.getElementById("status");
const statusText = document.getElementById("statusText");
const corrEl = document.getElementById("corr");
const wsUrlEl = document.getElementById("wsurl");
const latencyEl = document.getElementById("latency");
const latencyStatsEl = document.getElementById("latencyStats");

// Browser AEC is mandatory here for the same reason as WebRTC (TASK-WEB-008): without it
// the bot's speaker output re-enters the mic and the server VAD self-interrupts the bot.
const AUDIO_CONSTRAINTS = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };

let ws = null;
let micStream = null;
let captureCtx = null;
let workletNode = null;
let sourceNode = null;
let playbackCtx = null;
let nextStartTime = 0;
const activeSources = [];
let closedByUser = false;

// Perceived per-turn latency: gap between the end of the user's speech and the first bot
// audio frame (there is no per-turn HTTP response on a streaming socket).
let userWasSpeaking = false;
let lastLoudTs = 0;
let awaitingBot = false;
let userEndTs = 0;
const latencies = [];

function setStatus(text, cls) {
  statusText.textContent = text;
  statusEl.className = "status" + (cls ? " " + cls : "");
}

function selectedLanguage() {
  return languageEl && languageEl.value ? languageEl.value : "fr";
}

function wsUrl() {
  const params = new URLSearchParams(window.location.search);
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const lang = encodeURIComponent(selectedLanguage());
  const override = params.get("wsport");
  // Single routed port (ADR-0047 / TASK-WEB-038): the live socket rides the SAME origin as
  // the page at `/ws` — one port carries the page, the REST API and the socket. Behind the
  // TLS edge HAProxy routes the `Upgrade: websocket` request to the bridge on the existing
  // backend (no edge special-case, no TURN/UDP); over plain HTTP (local dev) it is the same
  // host:port the page came from. `?wsport=<n>` forces a direct host:port/ws for dev against
  // a specific bridge (bypassing the VIP), e.g. `?wsport=8090` straight at one node.
  if (override) {
    return `${scheme}://${window.location.hostname || "127.0.0.1"}:${override}/ws?language=${lang}`;
  }
  return `${scheme}://${window.location.host}/ws?language=${lang}`;
}

async function connect() {
  connectBtn.disabled = true;
  if (languageEl) languageEl.disabled = true;
  closedByUser = false;
  setStatus("Requesting microphone…");
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: AUDIO_CONSTRAINTS });
    await startCapture();
    openSocket();
  } catch (err) {
    setStatus("Microphone unavailable: " + err.message, "error");
    await teardown();
  }
}

async function startCapture() {
  captureCtx = new AudioContext();
  await captureCtx.audioWorklet.addModule("/pcm-worklet.js");
  sourceNode = captureCtx.createMediaStreamSource(micStream);
  workletNode = new AudioWorkletNode(captureCtx, "pcm-capture");
  workletNode.port.onmessage = (event) => onCaptureFrame(event.data);
  sourceNode.connect(workletNode);
  resetTurnState();
}

function openSocket() {
  const url = wsUrl();
  wsUrlEl.textContent = url;
  setStatus("Connecting…");
  ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => {
    ws.send(JSON.stringify({ type: "open", language: selectedLanguage() }));
    setStatus("Live — speak now", "live");
    disconnectBtn.disabled = false;
  };
  ws.onmessage = (event) => onSocketMessage(event.data);
  ws.onerror = () => setStatus("Connection error", "error");
  ws.onclose = (event) => onSocketClose(event);
}

// Mic frame: measure energy for the latency envelope, then stream as 16 kHz PCM16.
function onCaptureFrame(samples) {
  trackUserTurn(rms(samples), performance.now());
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const rate = captureCtx ? captureCtx.sampleRate : TARGET_SAMPLE_RATE;
  const pcm16 = floatToPcm16(downsample(samples, rate, TARGET_SAMPLE_RATE));
  ws.send(pcm16.buffer);
}

function onSocketMessage(data) {
  if (data instanceof ArrayBuffer) {
    onBotAudio(new Int16Array(data));
    return;
  }
  let message = null;
  try {
    message = JSON.parse(data);
  } catch (_e) {
    return; // ignore non-JSON text
  }
  handleControl(message);
}

function handleControl(message) {
  const type = message && message.type;
  if (type === "opened") setStatus("Live — speak now", "live");
  else if (type === "barge_in") stopPlayback(); // server interrupted the bot → drop queued audio
  else if (type === "call_end") endCall();
}

function onBotAudio(int16) {
  if (awaitingBot) {
    reportLatency(Math.round(performance.now() - userEndTs));
    awaitingBot = false;
    setStatus("Bot answering…", "live");
  }
  playPcm16(int16);
}

// Schedule each 16 kHz PCM16 chunk back-to-back; the AudioContext resamples to its own
// rate on playback, so no client-side upsampling worklet is needed.
function playPcm16(int16) {
  if (!playbackCtx || playbackCtx.state === "closed") {
    playbackCtx = new AudioContext();
    nextStartTime = 0;
  }
  if (playbackCtx.state === "suspended") playbackCtx.resume();
  const floats = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) floats[i] = int16[i] / 0x8000;
  const buffer = playbackCtx.createBuffer(1, floats.length, TARGET_SAMPLE_RATE);
  buffer.getChannelData(0).set(floats);
  const src = playbackCtx.createBufferSource();
  src.buffer = buffer;
  src.connect(playbackCtx.destination);
  const startAt = Math.max(playbackCtx.currentTime, nextStartTime);
  src.onended = () => {
    const idx = activeSources.indexOf(src);
    if (idx !== -1) activeSources.splice(idx, 1);
  };
  src.start(startAt);
  nextStartTime = startAt + buffer.duration;
  activeSources.push(src);
}

function stopPlayback() {
  while (activeSources.length) {
    const src = activeSources.pop();
    try {
      src.onended = null;
      src.stop();
      src.disconnect();
    } catch (_e) {
      // already stopped / disconnected
    }
  }
  nextStartTime = playbackCtx ? playbackCtx.currentTime : 0;
}

function trackUserTurn(micRms, now) {
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

function reportLatency(ms) {
  latencyEl.textContent = ms + " ms";
  latencies.push(ms);
  const avg = Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length);
  latencyStatsEl.textContent =
    " · avg " + avg + " ms · " + latencies.length + " turn" + (latencies.length > 1 ? "s" : "");
}

function resetTurnState() {
  userWasSpeaking = false;
  awaitingBot = false;
  lastLoudTs = performance.now();
  userEndTs = 0;
}

function onSocketClose(event) {
  disconnectBtn.disabled = true;
  connectBtn.disabled = false;
  if (languageEl) languageEl.disabled = false;
  if (closedByUser) {
    setStatus("Disconnected");
  } else if (event.code === 1013) {
    // The server refuses a connection past its per-bridge session ceiling with 1013
    // (VOICE_MAX_WS_SESSIONS, ADR-0047; the legacy stdlib path used 1 client).
    setStatus("Server busy — please try again shortly.", "busy");
  } else if (event.code === 1000) {
    setStatus("Call ended");
  } else {
    setStatus("Connection closed (code " + event.code + ")", "error");
  }
  cleanupAudio();
}

function endCall() {
  closedByUser = true;
  setStatus("Call ended");
  if (ws && ws.readyState === WebSocket.OPEN) ws.close(1000);
}

async function disconnect() {
  closedByUser = true;
  if (ws && ws.readyState <= WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({ type: "close" }));
    } catch (_e) {
      // socket already gone
    }
    ws.close(1000);
  }
  await teardown();
}

function cleanupAudio() {
  stopPlayback();
  if (sourceNode) sourceNode.disconnect();
  if (workletNode) workletNode.disconnect();
  if (micStream) micStream.getTracks().forEach((track) => track.stop());
  if (captureCtx && captureCtx.state !== "closed") captureCtx.close();
  sourceNode = null;
  workletNode = null;
  micStream = null;
  captureCtx = null;
}

async function teardown() {
  cleanupAudio();
  disconnectBtn.disabled = true;
  connectBtn.disabled = false;
  if (languageEl) languageEl.disabled = false;
}

function rms(samples) {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return samples.length ? Math.sqrt(sum / samples.length) : 0;
}

function downsample(samples, fromRate, toRate) {
  if (fromRate === toRate) return samples;
  const ratio = fromRate / toRate;
  const outLength = Math.floor(samples.length / ratio);
  const out = new Float32Array(outLength);
  for (let i = 0; i < outLength; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.floor((i + 1) * ratio), samples.length);
    let sum = 0;
    for (let j = start; j < end; j++) sum += samples[j];
    out[i] = end > start ? sum / (end - start) : 0;
  }
  return out;
}

function floatToPcm16(samples) {
  const pcm = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    pcm[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return pcm;
}

connectBtn.addEventListener("click", connect);
disconnectBtn.addEventListener("click", disconnect);
