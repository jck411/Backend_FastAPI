/**
 * Speech Controller - Server-side STT via Backend WebSocket
 *
 * This connects to the backend's /api/stt/stream WebSocket endpoint,
 * which handles Deepgram STT server-side. This avoids the need for
 * Deepgram token generation permissions.
 *
 * Supports two modes:
 * - Conversation (Flux): AI turn detection, auto-resumes listening after AI responds
 * - Command (Nova): Silence-based detection, stops after each utterance
 */
import { get, writable } from 'svelte/store';
import { fetchSttSettings } from '../api/client';
import { API_BASE_URL } from '../api/config';
import type { SttSettings } from '../api/types';
import { speechSettingsStore } from '../stores/speechSettings';

// Audio configuration
const TARGET_SAMPLE_RATE = 16000;
const PROCESSOR_BUFFER_SIZE = 4096;
const WORKLET_PROCESSOR_NAME = 'audio-capture';
const WORKLET_MODULE_URL = new URL('./audioCaptureWorklet.js', import.meta.url);

type SpeechMode = 'idle' | 'dictation';
type SttEngineMode = 'conversation' | 'command';

interface PendingSubmit {
  text: string;
}

interface SpeechStoreState {
  mode: SpeechMode;
  recording: boolean;
  connecting: boolean;
  error: string | null;
  promptText: string;
  promptVersion: number;
  keepPromptSynced: boolean;
  pendingSubmit: PendingSubmit | null;
  /** Server-side STT engine mode (conversation/command) */
  sttMode: SttEngineMode;
  /** True if listening was triggered from conversation mode auto-resume */
  conversationActive: boolean;
}

const initialState: SpeechStoreState = {
  mode: 'idle',
  recording: false,
  connecting: false,
  error: null,
  promptText: '',
  promptVersion: 0,
  keepPromptSynced: false,
  pendingSubmit: null,
  sttMode: 'command',
  conversationActive: false,
};

const state = writable<SpeechStoreState>({ ...initialState });

// Audio resources
let mediaStream: MediaStream | null = null;
let audioContext: AudioContext | null = null;
let audioProcessor: AudioWorkletNode | ScriptProcessorNode | null = null;
let ws: WebSocket | null = null;

// Session state
let currentSession = 0;
let accumulatedTranscript = '';
let autoSubmitTimer: ReturnType<typeof setTimeout> | null = null;
let autoSubmitSequence = 0;

// =============================================================================
// Helper Functions
// =============================================================================

function clearAutoSubmitTimer(): void {
  if (autoSubmitTimer) {
    clearTimeout(autoSubmitTimer);
    autoSubmitTimer = null;
  }
  autoSubmitSequence++;
}

function updatePrompt(text: string, keepSynced: boolean): void {
  state.update((value) => ({
    ...value,
    promptText: text,
    promptVersion: value.promptVersion + 1,
    keepPromptSynced: keepSynced ? true : value.keepPromptSynced,
  }));
}

function setError(message: string): void {
  state.update((value) => ({
    ...value,
    error: message,
    recording: false,
    connecting: false,
    keepPromptSynced: false,
    mode: 'idle',
  }));
}

function getWebSocketUrl(): string {
  // Convert HTTP(S) URL to WS(S)
  let base = API_BASE_URL || window.location.origin;
  base = base.replace(/^http/, 'ws');
  return `${base}/api/stt/stream`;
}

// Resample audio from source rate to target rate
function resampleFloat32(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (!input || input.length === 0) return input;
  if (!fromRate || !toRate || fromRate === toRate) return input;

  const ratio = fromRate / toRate;
  const outputLength = Math.max(1, Math.round(input.length / ratio));
  const output = new Float32Array(outputLength);

  for (let i = 0; i < outputLength; i++) {
    const position = i * ratio;
    const left = Math.floor(position);
    const right = Math.min(left + 1, input.length - 1);
    const weight = position - left;
    output[i] = input[left] + (input[right] - input[left]) * weight;
  }
  return output;
}

// Convert Float32 samples to base64-encoded Int16
function float32ToBase64(float32: Float32Array): string {
  const int16 = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    int16[i] = Math.max(-32768, Math.min(32767, Math.floor(float32[i] * 32768)));
  }

  // Convert to binary string
  const bytes = new Uint8Array(int16.buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

// =============================================================================
// Audio Processing
// =============================================================================

function processAudioFrame(samples: Float32Array, inputSampleRate: number): void {
  if (!samples || samples.length === 0) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  // Resample if needed
  const resampled =
    inputSampleRate !== TARGET_SAMPLE_RATE
      ? resampleFloat32(samples, inputSampleRate, TARGET_SAMPLE_RATE)
      : samples;

  // Convert to base64 and send
  const b64 = float32ToBase64(resampled);
  ws.send(JSON.stringify({
    type: 'audio_chunk',
    data: { audio: b64 },
  }));
}

// =============================================================================
// Cleanup Functions
// =============================================================================

function ensureSocketClosed(): void {
  if (ws) {
    try {
      ws.close();
    } catch (error) {
      console.warn('Failed to close WebSocket', error);
    }
  }
  ws = null;
}

function ensureAudioStopped(): void {
  if (audioProcessor) {
    try {
      audioProcessor.disconnect();
      if ('port' in audioProcessor) {
        audioProcessor.port.onmessage = null;
      }
    } catch (error) {
      // ignore
    }
  }
  audioProcessor = null;

  if (audioContext) {
    try {
      audioContext.close();
    } catch (error) {
      // ignore
    }
  }
  audioContext = null;

  if (mediaStream) {
    try {
      mediaStream.getTracks().forEach((track) => track.stop());
    } catch (error) {
      // ignore
    }
  }
  mediaStream = null;
}

interface StopOptions {
  submitText?: string | null;
}

function stopListening(options: StopOptions = {}): void {
  ensureAudioStopped();
  ensureSocketClosed();
  clearAutoSubmitTimer();

  state.update((value) => ({
    ...value,
    recording: false,
    connecting: false,
    keepPromptSynced: false,
    pendingSubmit: options.submitText ? { text: options.submitText } : null,
    mode: 'idle',
  }));
}

// =============================================================================
// Speech End Handling
// =============================================================================

function handleSpeechEnd(finalText: string): void {
  const trimmed = finalText.trim();
  const settings = speechSettingsStore.current;
  const autoSubmit = settings?.stt.autoSubmit ?? true;
  const autoSubmitDelay = Math.max(settings?.stt.autoSubmitDelayMs ?? 0, 0);

  clearAutoSubmitTimer();

  if (!trimmed) {
    stopListening({ submitText: null });
    return;
  }

  if (autoSubmit) {
    if (autoSubmitDelay <= 0) {
      stopListening({ submitText: trimmed });
      return;
    }

    // Stop recording but wait before submitting
    stopListening();
    updatePrompt(trimmed, false);
    const token = ++autoSubmitSequence;
    autoSubmitTimer = setTimeout(() => {
      if (token !== autoSubmitSequence) {
        return;
      }
      state.update((value) => ({
        ...value,
        pendingSubmit: { text: trimmed },
      }));
    }, autoSubmitDelay);
  } else {
    stopListening();
    updatePrompt(trimmed, false);
  }
}

// =============================================================================
// Audio Processing Setup
// =============================================================================

async function setupAudioProcessing(
  context: AudioContext,
  source: MediaStreamAudioSourceNode,
  inputSampleRate: number,
  sessionId: number,
): Promise<void> {
  let processor: AudioWorkletNode | ScriptProcessorNode | null = null;

  // Try AudioWorklet first (better performance)
  if (context.audioWorklet) {
    try {
      await context.audioWorklet.addModule(WORKLET_MODULE_URL);
      const workletNode = new AudioWorkletNode(context, WORKLET_PROCESSOR_NAME);
      workletNode.port.onmessage = (event) => {
        if (sessionId !== currentSession) return;
        const data = event.data;
        const samples = data && data.samples ? data.samples : data;
        if (samples instanceof Float32Array) {
          processAudioFrame(samples, inputSampleRate);
        } else if (samples instanceof ArrayBuffer) {
          processAudioFrame(new Float32Array(samples), inputSampleRate);
        }
      };
      processor = workletNode;
    } catch (error) {
      console.warn('AudioWorklet unavailable, falling back to ScriptProcessor:', error);
    }
  }

  // Fallback to ScriptProcessor
  if (!processor) {
    const scriptNode = context.createScriptProcessor(PROCESSOR_BUFFER_SIZE, 1, 1);
    scriptNode.onaudioprocess = (e) => {
      if (sessionId !== currentSession) return;
      processAudioFrame(e.inputBuffer.getChannelData(0), inputSampleRate);
    };
    processor = scriptNode;
  }

  source.connect(processor);
  processor.connect(context.destination);
  audioProcessor = processor;
}

// =============================================================================
// Main STT Functions
// =============================================================================

// Cached server STT settings
let cachedSttSettings: SttSettings | null = null;
let sttSettingsLoading = false;

async function loadServerSttSettings(): Promise<SttSettings | null> {
  if (cachedSttSettings) {
    return cachedSttSettings;
  }
  if (sttSettingsLoading) {
    // Wait for the in-flight request
    await new Promise((resolve) => setTimeout(resolve, 100));
    return cachedSttSettings;
  }

  sttSettingsLoading = true;
  try {
    cachedSttSettings = await fetchSttSettings();
    return cachedSttSettings;
  } catch (error) {
    console.warn('Failed to fetch server STT settings', error);
    return null;
  } finally {
    sttSettingsLoading = false;
  }
}

/** Clear the cached STT settings so they are re-fetched on next listen */
export function invalidateSttSettingsCache(): void {
  cachedSttSettings = null;
}

async function startListening(mode: SpeechMode, isConversationResume = false): Promise<void> {
  const current = get(state);
  if (current.connecting || current.recording) {
    stopListening();
  }
  clearAutoSubmitTimer();

  const settings = speechSettingsStore.current;
  if (!settings) {
    setError('Speech settings unavailable');
    return;
  }

  // Fetch server STT settings to determine mode
  const serverSttSettings = await loadServerSttSettings();
  const sttMode: SttEngineMode = serverSttSettings?.mode === 'conversation' ? 'conversation' : 'command';
  const isConversationMode = sttMode === 'conversation';

  const sessionId = ++currentSession;
  accumulatedTranscript = '';

  state.set({
    ...current,
    mode,
    connecting: true,
    recording: false,
    error: null,
    keepPromptSynced: true,
    pendingSubmit: null,
    sttMode,
    conversationActive: isConversationMode || isConversationResume,
  });

  // 1. Get microphone access
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: TARGET_SAMPLE_RATE,
        echoCancellation: true,
        noiseSuppression: true,
      },
      video: false,
    });
  } catch (error) {
    if (sessionId !== currentSession) return;
    stopListening();
    const message = error instanceof Error ? error.message : 'Microphone access denied';
    setError(message);
    return;
  }

  if (sessionId !== currentSession) {
    stream.getTracks().forEach((t) => t.stop());
    return;
  }

  mediaStream = stream;

  // 2. Create audio context
  const context = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
  audioContext = context;
  const inputSampleRate = context.sampleRate;
  const source = context.createMediaStreamSource(stream);

  // 3. Connect to backend WebSocket
  const wsUrl = getWebSocketUrl();
  const socket = new WebSocket(wsUrl);
  ws = socket;

  socket.addEventListener('open', () => {
    if (sessionId !== currentSession) return;
    // Wait for stt_session_ready message before starting audio
  });

  socket.addEventListener('message', (event) => {
    if (sessionId !== currentSession) return;
    if (typeof event.data !== 'string') return;

    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(event.data) as Record<string, unknown>;
    } catch (error) {
      return;
    }

    const eventType = payload.type as string;

    if (eventType === 'stt_session_ready') {
      // Backend STT session is ready - start audio processing
      void setupAudioProcessing(context, source, inputSampleRate, sessionId);

      state.update((value) => ({
        ...value,
        connecting: false,
        recording: true,
        error: null,
        keepPromptSynced: true,
      }));
    } else if (eventType === 'transcript') {
      const text = String(payload.text ?? '');
      const isFinal = payload.is_final === true;

      if (text) {
        if (isFinal) {
          // Accumulate final transcripts
          accumulatedTranscript = accumulatedTranscript
            ? `${accumulatedTranscript} ${text}`.trim()
            : text;
          updatePrompt(accumulatedTranscript, true);
          // When speech is final, handle the end
          handleSpeechEnd(accumulatedTranscript);
        } else {
          // Interim transcript - show accumulated + current interim
          const combined = accumulatedTranscript
            ? `${accumulatedTranscript} ${text}`.trim()
            : text;
          updatePrompt(combined, true);
        }
      }
    } else if (eventType === 'error') {
      const message = String(payload.message ?? 'STT error');
      console.error('STT error:', message);
      setError(message);
      stopListening();
    }
  });

  socket.addEventListener('error', (event) => {
    console.warn('WebSocket error', event);
    if (sessionId !== currentSession) return;
    setError('Connection error');
    stopListening();
  });

  socket.addEventListener('close', () => {
    if (sessionId !== currentSession) return;
    ensureAudioStopped();
    state.update((value) => ({
      ...value,
      recording: false,
      connecting: false,
      keepPromptSynced: false,
    }));
  });
}

// =============================================================================
// Public API
// =============================================================================

export async function startDictation(): Promise<void> {
  clearAutoSubmitTimer();
  const current = get(state);
  const activeDictation = current.mode === 'dictation' && (current.recording || current.connecting);
  if (activeDictation) {
    stopListening();
    state.update((value) => ({ ...value, mode: 'idle', keepPromptSynced: false, conversationActive: false }));
    return;
  }

  state.update((value) => ({ ...value, mode: 'dictation' }));
  await startListening('dictation');
}

/**
 * Resume listening after AI response in conversation mode.
 * Called automatically by App.svelte when streaming ends and conversation mode is active.
 */
export async function resumeConversation(): Promise<void> {
  const current = get(state);

  // Only resume if we were in conversation mode
  if (!current.conversationActive) {
    return;
  }

  // If already recording/connecting, don't restart
  if (current.recording || current.connecting) {
    return;
  }

  // Resume listening in dictation mode (conversation continues)
  state.update((value) => ({ ...value, mode: 'dictation' }));
  await startListening('dictation', true);
}

/**
 * End the conversation session and return to idle.
 * Called when user manually stops or when conversation times out.
 */
export function endConversation(): void {
  clearAutoSubmitTimer();
  stopListening();
  state.update((value) => ({
    ...value,
    mode: 'idle',
    conversationActive: false,
  }));
}

export function stopSpeech(): void {
  clearAutoSubmitTimer();
  stopListening();
  state.update((value) => ({ ...value, mode: 'idle', conversationActive: false }));
}

export function clearPendingSubmit(): PendingSubmit | null {
  const current = get(state);
  if (!current.pendingSubmit) {
    return null;
  }
  const submission = current.pendingSubmit;
  state.update((value) => ({ ...value, pendingSubmit: null }));
  return submission;
}

export const speechState = { subscribe: state.subscribe };
