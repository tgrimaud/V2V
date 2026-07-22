"use strict";

// Gradium web/PCM input contract: mono, 16 kHz, signed 16-bit little-endian.
const TARGET_SAMPLE_RATE = 16000;
// Full server-side loop: audio in -> STT -> backend answer -> TTS -> WAV out.
// The transcript and spoken answer come back as X-Voice-* response headers.
const TURN_ENDPOINT = "/api/voice/turn";

const recordButton = document.getElementById("record");
const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const metaEl = document.getElementById("meta");
const languageEl = document.getElementById("language");

// US-042: the UI-selected language is forwarded to the runtime (query param), which
// forces the backend answer language instead of auto-detecting it.
function selectedLanguage() {
  return languageEl && languageEl.value ? languageEl.value : "";
}

function turnUrl() {
  const lang = selectedLanguage();
  return lang ? TURN_ENDPOINT + "?language=" + encodeURIComponent(lang) : TURN_ENDPOINT;
}

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
  setStatus("Thinking…");
  const started = performance.now();
  let response;
  try {
    response = await fetch(turnUrl(), {
      method: "POST",
      headers: { "Content-Type": "audio/pcm" },
      body: pcmBuffer,
    });
  } catch (err) {
    renderError("network_error", "Could not reach the voice runtime: " + err.message);
    return;
  }

  const contentType = response.headers.get("Content-Type") || "";
  if (!response.ok || !contentType.includes("audio/wav")) {
    await renderTurnError(response);
    return;
  }

  renderTurnMeta(response.headers);
  await playReply(await response.arrayBuffer(), started);
}

// The /turn reply carries the transcript and the spoken answer as headers so the
// page can show both alongside playing the answer audio.
function renderTurnMeta(headers) {
  const transcript = decodeHeader(headers.get("X-Voice-Transcript"));
  const answer = decodeHeader(headers.get("X-Voice-Answer"));
  transcriptEl.className = "transcript";
  transcriptEl.textContent = transcript || "(no transcript)";
  const parts = [];
  if (answer) parts.push("answer: <code>" + escapeHtml(answer) + "</code>");
  const provider = headers.get("X-Answer-Provider");
  if (provider) parts.push("backend: <code>" + escapeHtml(provider) + "</code>");
  // A degraded turn still speaks a safe fallback; flag it so the user knows the
  // backend could not answer confidently (TASK-WEB-003-F).
  if ((headers.get("X-Answer-Outcome") || "") === "degraded") {
    const reason = headers.get("X-Answer-Degraded-Reason") || "degraded";
    parts.push("<span class=\"degraded\">degraded: " + escapeHtml(reason) + "</span>");
  }
  const corr = headers.get("X-Correlation-Id");
  if (corr) parts.push("corr: <code>" + escapeHtml(corr) + "</code>");
  metaEl.innerHTML = parts.join(" · ");
}

async function renderTurnError(response) {
  let code = "turn_error";
  let reason = "No answer produced.";
  try {
    const err = await response.json();
    code = err.error_code || err.error || code;
    // TASK-WEB-006 (RF-013): the 502 body now carries a generic, client-safe
    // `message`; `error_reason` is kept only as a fallback for older responses.
    reason = err.message || err.error_reason || reason;
  } catch (_e) {
    // non-JSON error body; keep defaults
  }
  renderError(code, reason);
}

function renderError(code, reason) {
  transcriptEl.className = "transcript error";
  transcriptEl.textContent = reason;
  setStatus("Failed.");
  metaEl.innerHTML = "error code: <code>" + escapeHtml(code) + "</code>";
}

function decodeHeader(value) {
  if (!value) return "";
  try {
    return decodeURIComponent(value);
  } catch (_e) {
    return value;
  }
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

async function playReply(wav, started) {
  try {
    if (!playbackContext || playbackContext.state === "closed") {
      playbackContext = new AudioContext();
    }
    if (playbackContext.state === "suspended") await playbackContext.resume();
    const buffer = await playbackContext.decodeAudioData(wav);
    const replyMs = Math.round(performance.now() - started);

    stopPlayback();
    playbackSource = playbackContext.createBufferSource();
    playbackSource.buffer = buffer;
    playbackSource.connect(playbackContext.destination);
    playbackSource.onended = () => {
      if (!recording) setStatus("Reply played.");
    };
    playbackSource.start();
    setStatus("Playing reply…");
    metaEl.innerHTML += " · reply: <code>" + replyMs + " ms</code>";
  } catch (err) {
    appendPlaybackError("reply_decode_error", "Could not play the reply: " + err.message);
  }
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
