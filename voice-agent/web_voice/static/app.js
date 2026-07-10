"use strict";

// Gradium web/PCM input contract: mono, 16 kHz, signed 16-bit little-endian.
const TARGET_SAMPLE_RATE = 16000;
const STT_ENDPOINT = "/api/voice/stt";

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

recordButton.addEventListener("click", () => {
  if (recording) {
    stopRecording();
  } else {
    startRecording();
  }
});

async function startRecording() {
  try {
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
  } else {
    renderError(result.error_code || "stt_error", result.error_reason || "No transcript produced.");
  }
  metaEl.innerHTML = buildMeta(result);
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
