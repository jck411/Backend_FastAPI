const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const startButton = document.getElementById("startButton");
const armKeywordButton = document.getElementById("armKeyword");
const stopButton = document.getElementById("stopButton");

let ws;
let audioContext;
let stream;
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

async function startAudioPipeline() {
  stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioContext = new AudioContext({ sampleRate: 16000 });
  source = audioContext.createMediaStreamSource(stream);
  processor = audioContext.createScriptProcessor(4096, 1, 1);

  processor.onaudioprocess = (event) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const channelData = event.inputBuffer.getChannelData(0);
    ws.send(floatTo16BitPCM(channelData));
  };

  source.connect(processor);
  processor.connect(audioContext.destination);
}

async function stopAudioPipeline() {
  if (processor) processor.disconnect();
  if (source) source.disconnect();
  if (audioContext) await audioContext.close();
  if (stream) stream.getTracks().forEach((t) => t.stop());
  processor = null;
  source = null;
  audioContext = null;
  stream = null;
}

async function openSession(mode) {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  finalLines = [];
  partialText = "";
  renderTranscript();

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${protocol}://${location.host}/api/azure-stt/stream`);
  ws.binaryType = "arraybuffer";

  ws.onopen = async () => {
    ws.send(JSON.stringify({ mode }));
    await startAudioPipeline();
    startButton.disabled = true;
    armKeywordButton.disabled = true;
    stopButton.disabled = false;
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "partial") {
      partialText = data.text;
      renderTranscript();
    } else if (data.type === "final") {
      partialText = "";
      finalLines.push(data.text);
      renderTranscript();
    } else if (data.type === "armed") {
      setStatus("Keyword mode armed. Say your Azure keyword to start transcription.");
    } else if (data.type === "keyword_detected") {
      setStatus("Keyword detected ✅ Starting live transcription…");
    } else if (data.type === "started") {
      setStatus("Transcribing now. Speak naturally.");
    } else if (data.type === "error") {
      setStatus(`Error: ${data.message}`);
    }
  };

  ws.onclose = async () => {
    await stopAudioPipeline();
    startButton.disabled = false;
    armKeywordButton.disabled = false;
    stopButton.disabled = true;
    setStatus("Session stopped.");
  };
}

async function stopSession() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "stop" }));
    ws.close();
  }
  await stopAudioPipeline();
}

startButton.addEventListener("click", () => openSession("button"));
armKeywordButton.addEventListener("click", () => openSession("keyword"));
stopButton.addEventListener("click", stopSession);

fetch("/api/azure-stt/status")
  .then((r) => r.json())
  .then((s) => {
    if (!s.configured) {
      setStatus("Azure Speech is not configured. Add AZURE_SPEECH_KEY and AZURE_SPEECH_REGION in .env.");
      startButton.disabled = true;
      armKeywordButton.disabled = true;
      return;
    }
    setStatus(
      s.keyword_model_available
        ? `Ready. Language: ${s.language}. You can start by button or Azure keyword.`
        : `Ready for button mode (${s.language}). Keyword model missing.`
    );
  })
  .catch((e) => setStatus(`Failed to load status: ${e.message}`));
