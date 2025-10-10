import { get, writable } from 'svelte/store';
import { requestDeepgramToken } from '../api/client';
import { speechSettingsStore } from '../stores/speechSettings';

type SpeechMode = 'idle' | 'dictation';

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
};

const state = writable<SpeechStoreState>({ ...initialState });

let mediaStream: MediaStream | null = null;
let mediaRecorder: MediaRecorder | null = null;
let ws: WebSocket | null = null;

let currentSession = 0;
let accumulatedTranscript = '';
let lastInterim = '';
let speechFinalReceived = false;
let utteranceEndTimer: ReturnType<typeof setTimeout> | null = null;
let autoSubmitTimer: ReturnType<typeof setTimeout> | null = null;
let autoSubmitSequence = 0;

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

function resetPromptTracking(): void {
  accumulatedTranscript = '';
  lastInterim = '';
  speechFinalReceived = false;
}

function clearUtteranceTimer(): void {
  if (utteranceEndTimer) {
    clearTimeout(utteranceEndTimer);
    utteranceEndTimer = null;
  }
}

function ensureSocketClosed(): void {
  if (ws) {
    try {
      ws.close();
    } catch (error) {
      console.warn('Failed to close Deepgram socket', error);
    }
  }
  ws = null;
}

function ensureMediaStopped(): void {
  if (mediaRecorder) {
    try {
      mediaRecorder.stop();
    } catch (error) {
      // ignore
    }
  }
  mediaRecorder = null;

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
  ensureMediaStopped();
  ensureSocketClosed();
  clearUtteranceTimer();

  state.update((value) => ({
    ...value,
    recording: false,
    connecting: false,
    keepPromptSynced: false,
    pendingSubmit: options.submitText ? { text: options.submitText } : null,
    mode: 'idle',
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

async function startListening(mode: SpeechMode): Promise<void> {
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

  const sessionId = ++currentSession;

  resetPromptTracking();

  state.set({
    ...current,
    mode,
    connecting: true,
    recording: false,
    error: null,
    keepPromptSynced: true,
    pendingSubmit: null,
  });

  let token: string;
  try {
    const response = await requestDeepgramToken();
    token = response.access_token;
    if (!token) {
      throw new Error('Missing Deepgram token');
    }
  } catch (error) {
    if (sessionId !== currentSession) {
      return;
    }
    stopListening();
    const message = error instanceof Error ? error.message : 'Failed to get Deepgram token';
    setError(message);
    return;
  }

  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  } catch (error) {
    if (sessionId !== currentSession) {
      return;
    }
    stopListening();
    const message = error instanceof Error ? error.message : 'Microphone access denied';
    setError(message);
    return;
  }

  const recorderMimeCandidates = ['audio/ogg;codecs=opus', 'audio/webm;codecs=opus', 'audio/webm'];
  const selectedMime = recorderMimeCandidates.find((type) => {
    try {
      return MediaRecorder.isTypeSupported(type);
    } catch (error) {
      return false;
    }
  });

  const encoding = 'opus';

  const stt = settings.stt;

  const params = new URLSearchParams({
    model: stt.model,
    interim_results: String(stt.interimResults !== false),
    vad_events: String(stt.vadEvents !== false),
    smart_format: String(stt.smartFormat !== false),
    punctuate: String(stt.punctuate !== false),
    numerals: String(stt.numerals !== false),
    filler_words: String(stt.fillerWords === true),
    profanity_filter: String(stt.profanityFilter === true),
    utterance_end_ms: String(Math.max(stt.utteranceEndMs, 1000)),
    endpointing: String(Math.max(stt.endpointing, 800)),
    encoding,
    no_delay: 'false',
    multichannel: 'false',
    alternatives: '1',
  });

  const socketUrl = `wss://api.deepgram.com/v1/listen?${params.toString()}`;
  const isJwt = token.includes('.') && token.split('.').length >= 3;
  const protocols = isJwt ? ['Bearer', token] as const : ['token', token] as const;

  const dgSocket = new WebSocket(socketUrl, protocols as unknown as string | string[]);
  ws = dgSocket;
  mediaStream = stream;

  dgSocket.addEventListener('open', () => {
    if (sessionId !== currentSession) {
      return;
    }

    state.update((value) => ({
      ...value,
      connecting: false,
      recording: true,
      error: null,
      keepPromptSynced: true,
    }));

    try {
      mediaRecorder = new MediaRecorder(stream, selectedMime ? { mimeType: selectedMime } : undefined);
    } catch (error) {
      setError('MediaRecorder not supported');
      stopListening();
      return;
    }

    mediaRecorder.addEventListener('dataavailable', async (event) => {
      if (!event.data || event.data.size === 0) {
        return;
      }
      try {
        const buffer = await event.data.arrayBuffer();
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(buffer);
        }
      } catch (error) {
        console.warn('Failed to send audio chunk', error);
      }
    });

    mediaRecorder.addEventListener('stop', () => {
      try {
        ws?.send(new Uint8Array());
      } catch (error) {
        // ignore
      }
    });

    mediaRecorder.start(250);
  });

  dgSocket.addEventListener('message', (event) => {
    if (sessionId !== currentSession) {
      return;
    }
    if (typeof event.data !== 'string') {
      return;
    }

    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(event.data) as Record<string, unknown>;
    } catch (error) {
      return;
    }

    handleDeepgramMessage(payload, mode, sessionId);
  });

  dgSocket.addEventListener('error', (event) => {
    console.warn('Deepgram socket error', event);
    if (sessionId !== currentSession) {
      return;
    }
    setError('Deepgram connection error');
    stopListening();
  });

  dgSocket.addEventListener('close', () => {
    if (sessionId !== currentSession) {
      return;
    }
    ensureMediaStopped();
    state.update((value) => ({ ...value, recording: false, connecting: false, keepPromptSynced: false }));
  });
}

interface DeepgramMessage {
  type?: string;
  is_final?: boolean;
  speech_final?: boolean;
  channel?: {
    alternatives?: Array<{
      transcript?: string;
    }>;
  };
}

function handleDeepgramMessage(raw: Record<string, unknown>, mode: SpeechMode, sessionId: number): void {
  const message = raw as DeepgramMessage;

  if (message.type === 'UtteranceEnd') {
    if (!speechFinalReceived) {
      handleSpeechEnd(accumulatedTranscript || lastInterim);
    }
    clearUtteranceTimer();
    utteranceEndTimer = setTimeout(() => {
      speechFinalReceived = false;
    }, 1000);
    return;
  }

  if (message.type !== 'Results') {
    return;
  }

  const alternative = message.channel?.alternatives?.[0];
  const transcriptRaw = alternative?.transcript ?? '';
  const transcript = transcriptRaw.trim();

  if (transcript) {
    const interimCombined = accumulatedTranscript
      ? `${accumulatedTranscript} ${transcript}`.trim()
      : transcript;
    lastInterim = interimCombined;
    updatePrompt(interimCombined, true);
  }

  const isFinal = message.is_final === true;
  if (isFinal && transcript) {
    accumulatedTranscript = accumulatedTranscript
      ? `${accumulatedTranscript} ${transcript}`.trim()
      : transcript;
    updatePrompt(accumulatedTranscript, true);
  }

  const speechFinal = message.speech_final === true;
  if (speechFinal) {
    speechFinalReceived = true;
    clearUtteranceTimer();
    handleSpeechEnd(accumulatedTranscript || lastInterim || transcript);
  }
}

export async function startDictation(): Promise<void> {
  clearAutoSubmitTimer();
  const current = get(state);
  const activeDictation = current.mode === 'dictation' && (current.recording || current.connecting);
  if (activeDictation) {
    stopListening();
    state.update((value) => ({ ...value, mode: 'idle', keepPromptSynced: false }));
    return;
  }

  state.update((value) => ({ ...value, mode: 'dictation' }));
  await startListening('dictation');
}

export function stopSpeech(): void {
  clearAutoSubmitTimer();
  stopListening();
  state.update((value) => ({ ...value, mode: 'idle' }));
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
