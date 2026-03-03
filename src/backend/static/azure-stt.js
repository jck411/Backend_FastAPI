const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const startButton = document.getElementById("startButton");
const armKeywordButton = document.getElementById("armKeyword");
const stopButton = document.getElementById("stopButton");

let keywordWs;   // keyword-detection WebSocket
let transcribeWs; // transcription WebSocket (Azure STT for now, swappable)
let audioContext;
let stream;       // MediaStream from getUserMedia
let source;
let processor;
let finalLines = [];
let partialText = "";

const setStatus = (text) => (statusEl.textContent = text);
const renderTranscript = () => {
  const stable = finalLines.join("\n");
  transcriptEl.innerHTML = stable + (partialText ? `\n<span class="partial">${partialText}</span>` : "");
};

const floatTo16BitPCM = (float32Array) => {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);
  let offset = 0;
  for (let i = 0; i < float32Array.length; i += 1) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }
  return buffer;
};

// ── Shared microphone pipeline ──────────────────────────────────

async function ensureMic() {
  if (audioContext) return;
  stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioContext = new AudioContext({ sampleRate: 16000 });
  source = audioContext.createMediaStreamSource(stream);
  processor = audioContext.createScriptProcessor(4096, 1, 1);

  processor.onaudioprocess = (event) => {
    const pcm = floatTo16BitPCM(event.inputBuffer.getChannelData(0));
    if (keywordWs && keywordWs.readyState === WebSocket.OPEN) keywordWs.send(pcm);
    if (transcribeWs && transcribeWs.readyState === WebSocket.OPEN) transcribeWs.send(pcm);
  };

  source.connect(processor);
  processor.connect(audioContext.destination);
}

async function releaseMic() {
  if (processor) processor.disconnect();
  if (source) source.disconnect();
  if (audioContext) await audioContext.close();
  if (stream) stream.getTracks().forEach((t) => t.stop());
  processor = null;
  source = null;
  audioContext = null;
  stream = null;
}

// ── Transcription session (service-agnostic interface) ──────────

function openTranscription() {
  if (transcribeWs && transcribeWs.readyState === WebSocket.OPEN) return;

  finalLines = [];
  partialText = "";
  renderTranscript();

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  transcribeWs = new WebSocket(`${protocol}://${location.host}/api/azure-stt/stream`);
  transcribeWs.binaryType = "arraybuffer";

  transcribeWs.onopen = () => {
    setStatus("Transcribing now. Speak naturally.");
    stopButton.disabled = false;
  };

  transcribeWs.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "partial") {
      partialText = data.text;
      renderTranscript();
    } else if (data.type === "final") {
      partialText = "";
      finalLines.push(data.text);
      renderTranscript();
    } else if (data.type === "started") {
      setStatus("Transcribing now. Speak naturally.");
    } else if (data.type === "error") {
      setStatus(`Error: ${data.message}`);
    }
  };

  transcribeWs.onclose = () => {
    transcribeWs = null;
    if (!keywordWs || keywordWs.readyState !== WebSocket.OPEN) {
      fullStop();
    }
  };
}

function closeTranscription() {
  if (transcribeWs && transcribeWs.readyState === WebSocket.OPEN) {
    transcribeWs.send(JSON.stringify({ type: "stop" }));
    transcribeWs.close();
  }
  transcribeWs = null;
}

// ── Keyword listener ────────────────────────────────────────────

async function armKeyword() {
  startButton.disabled = true;
  armKeywordButton.disabled = true;
  stopButton.disabled = false;

  await ensureMic();

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  keywordWs = new WebSocket(`${protocol}://${location.host}/api/keyword/listen`);
  keywordWs.binaryType = "arraybuffer";

  keywordWs.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "armed") {
      setStatus('Keyword armed. Say "computer" to start transcription.');
    } else if (data.type === "keyword_detected") {
      setStatus("Keyword detected \u2705 Starting transcription\u2026");
      openTranscription();
      closeKeyword();
    } else if (data.type === "error") {
      setStatus(`Keyword error: ${data.message}`);
    }
  };

  keywordWs.onclose = () => {
    keywordWs = null;
    if (!transcribeWs || transcribeWs.readyState !== WebSocket.OPEN) {
      fullStop();
    }
  };
}

function closeKeyword() {
  if (keywordWs) {
    keywordWs.onclose = null; // prevent onclose from triggering fullStop during handoff
    if (keywordWs.readyState === WebSocket.OPEN) {
      keywordWs.send(JSON.stringify({ type: "stop" }));
      keywordWs.close();
    }
  }
  keywordWs = null;
}

// ── Button-triggered transcription ──────────────────────────────

async function startDirect() {
  startButton.disabled = true;
  armKeywordButton.disabled = true;
  stopButton.disabled = false;

  await ensureMic();
  openTranscription();
}

// ── Full stop ───────────────────────────────────────────────────

async function fullStop() {
  closeKeyword();
  closeTranscription();
  await releaseMic();
  startButton.disabled = false;
  armKeywordButton.disabled = false;
  stopButton.disabled = true;
  setStatus("Stopped.");
}

// ── Wire up buttons ─────────────────────────────────────────────

startButton.addEventListener("click", startDirect);
armKeywordButton.addEventListener("click", armKeyword);
stopButton.addEventListener("click", fullStop);

// ── Initial status check ────────────────────────────────────────

Promise.all([
  fetch("/api/azure-stt/status").then((r) => r.json()),
  fetch("/api/keyword/status").then((r) => r.json()),
])
  .then(([stt, kw]) => {
    if (!stt.configured) {
      setStatus("Azure Speech not configured. Add AZURE_SPEECH_KEY and AZURE_SPEECH_REGION in .env.");
      startButton.disabled = true;
      armKeywordButton.disabled = true;
      return;
    }
    armKeywordButton.disabled = !kw.available;
    setStatus(
      kw.available
        ? `Ready. Language: ${stt.language}. Start by button or say "computer".`
        : `Ready for button mode (${stt.language}). Keyword model missing.`
    );
  })
  .catch((e) => setStatus(`Failed to load status: ${e.message}`));
