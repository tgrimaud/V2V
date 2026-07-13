"use strict";

// Gradium web/PCM input contract: mono, 16 kHz, signed 16-bit little-endian.
const TARGET_SAMPLE_RATE = 16000;
const STT_ENDPOINT = "/api/voice/stt";
const TTS_ENDPOINT = "/api/voice/tts";

const recordButton = document.getElementById("record");
const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const metaEl = document.getElementById("meta");

let audioContext = null;
let mediaStream = null;
let workletNode = null;
let sourceNode = null;
let capturedChunks = [];
let recording = false;

// Playback (voice-out) uses its own AudioContext: the capture context is closed
// on teardown, and a single active source is tracked so it can be stopped when a
// new reply arrives or a new recording starts.
let playbackContext = null;
let playbackSource = null;

recordButton.addEventListener("click", () => {
  if (recording) {
    stopRecording();
  } else {
    startRecording();
  }
});

async function startRecording() {
  try {
    stopPlayback();
    setStatus("Requesting microphone…");
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioContext = new AudioContext();
    await audioContext.audioWorklet.addModule("/pcm-worklet.js");

    capturedChunks = [];
    sourceNode = audioContext.createMediaStreamSource(mediaStream);
    workletNode = new AudioWorkletNode(audioContext, "pcm-capture");
    workletNode.port.onmessage = (event) => capturedChunks.push(event.data);
    sourceNode.connect(workletNode);

    recording = true;
    recordButton.textContent = "Stop";
    recordButton.classList.add("recording");
    setStatus("Recording… speak your question.");
  } catch (err) {
    setStatus("Microphone unavailable: " + err.message);
    await teardown();
  }
}

async function stopRecording() {
  recording = false;
  recordButton.disabled = true;
  recordButton.textContent = "Record";
  recordButton.classList.remove("recording");
  setStatus("Transcribing…");

  const sampleRate = audioContext ? audioContext.sampleRate : TARGET_SAMPLE_RATE;
  const samples = mergeChunks(capturedChunks);
  await teardown();

  if (samples.length === 0) {
    renderError("no_audio", "No audio captured.");
    recordButton.disabled = false;
    return;
  }

  const pcm16 = floatToPcm16(downsample(samples, sampleRate, TARGET_SAMPLE_RATE));
  await sendAudio(pcm16.buffer);
  recordButton.disabled = false;
}

async function sendAudio(pcmBuffer) {
  try {
    const response = await fetch(STT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "audio/pcm" },
      body: pcmBuffer,
    });
    const result = await response.json();
    renderResult(result);
  } catch (err) {
    renderError("network_error", "Could not reach the voice runtime: " + err.message);
  }
}

function renderResult(result) {
  if (result && result.outcome === "success" && result.transcript) {
    transcriptEl.className = "transcript";
    transcriptEl.textContent = result.transcript;
    setStatus("Done.");
    metaEl.innerHTML = buildMeta(result);
    // Echo loop: speak the transcript back through the TTS egress route.
    void playEcho(result.transcript, result.correlation_id);
  } else {
    renderError(result.error_code || "stt_error", result.error_reason || "No transcript produced.");
    metaEl.innerHTML = buildMeta(result);
  }
}

function renderError(code, reason) {
  transcriptEl.className = "transcript error";
  transcriptEl.textContent = reason;
  setStatus("Failed.");
  metaEl.innerHTML = "error code: <code>" + escapeHtml(code) + "</code>";
}

function buildMeta(result) {
  if (!result) return "";
  const parts = [];
  if (result.provider) parts.push("provider: <code>" + escapeHtml(result.provider) + "</code>");
  if (typeof result.stt_request_ms === "number") parts.push("stt: <code>" + result.stt_request_ms + " ms</code>");
  if (result.correlation_id) parts.push("corr: <code>" + escapeHtml(result.correlation_id) + "</code>");
  return parts.join(" · ");
}

// Stop and release the currently playing reply, if any. Emptying/replacing the
// buffer is not enough — the AudioBufferSourceNode keeps playing until stop().
function stopPlayback() {
  if (!playbackSource) return;
  try {
    playbackSource.onended = null;
    playbackSource.stop();
  } catch (_e) {
    // already stopped / never started
  }
  try {
    playbackSource.disconnect();
  } catch (_e) {
    // already disconnected
  }
  playbackSource = null;
}

async function playEcho(text, correlationId) {
  stopPlayback();
  setStatus("Synthesizing reply…");
  const started = performance.now();
  let response;
  try {
    const params = new URLSearchParams({ text });
    if (correlationId) params.set("correlation_id", correlationId);
    response = await fetch(TTS_ENDPOINT + "?" + params.toString(), { method: "POST" });
  } catch (err) {
    appendPlaybackError("tts_network_error", "Could not reach the voice runtime: " + err.message);
    return;
  }

  const contentType = response.headers.get("Content-Type") || "";
  if (!response.ok || !contentType.includes("audio/wav")) {
    await appendPlaybackErrorFromResponse(response);
    return;
  }

  try {
    const wav = await response.arrayBuffer();
    if (!playbackContext || playbackContext.state === "closed") {
      playbackContext = new AudioContext();
    }
    if (playbackContext.state === "suspended") await playbackContext.resume();
    const buffer = await playbackContext.decodeAudioData(wav);
    const firstAudioMs = Math.round(performance.now() - started);

    stopPlayback();
    playbackSource = playbackContext.createBufferSource();
    playbackSource.buffer = buffer;
    playbackSource.connect(playbackContext.destination);
    playbackSource.onended = () => {
      if (!recording) setStatus("Reply played.");
    };
    playbackSource.start();
    setStatus("Playing reply…");
    metaEl.innerHTML += " · tts first audio: <code>" + firstAudioMs + " ms</code>";
  } catch (err) {
    appendPlaybackError("tts_decode_error", "Could not play the reply: " + err.message);
  }
}

async function appendPlaybackErrorFromResponse(response) {
  let code = "tts_error";
  let reason = "No audio produced.";
  try {
    const err = await response.json();
    code = err.error_code || code;
    reason = err.error_reason || reason;
  } catch (_e) {
    // non-JSON error body; keep defaults
  }
  appendPlaybackError(code, reason);
}

function appendPlaybackError(code, reason) {
  setStatus("Reply unavailable.");
  metaEl.innerHTML +=
    " · <span class=\"tts-error\">tts: " + escapeHtml(reason) + " (" + escapeHtml(code) + ")</span>";
}

function mergeChunks(chunks) {
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const merged = new Float32Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
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

async function teardown() {
  if (sourceNode) sourceNode.disconnect();
  if (workletNode) workletNode.disconnect();
  if (mediaStream) mediaStream.getTracks().forEach((track) => track.stop());
  if (audioContext && audioContext.state !== "closed") await audioContext.close();
  sourceNode = null;
  workletNode = null;
  mediaStream = null;
  audioContext = null;
}

function setStatus(text) {
  statusEl.textContent = text;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
  });
}
