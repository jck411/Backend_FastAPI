import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import useWebSocket from 'react-use-websocket';
import './App.css';
import ScrollFadeText from './components/ScrollFadeText';
import useAudioCapture from './hooks/useAudioCapture';

// Version for debugging
console.log('🔧 App.jsx v3 loaded');

const clientId = `voice_${crypto.randomUUID()}`;
const TIMEOUT_COUNTDOWN_SECONDS = 5;
const STREAM_SPEED_STORAGE_KEY = 'voice_stream_speed_cps';
const SYNC_TO_TTS_STORAGE_KEY = 'voice_sync_to_tts';
const DEFAULT_STREAM_SPEED_CPS = 45;
const STREAM_SPEED_MIN = 20;
const STREAM_SPEED_MAX = 120;
const STREAM_SPEED_STEP = 5;
const DEFAULT_TTS_SYNC_CPS = 15;
const TTS_SYNC_CPS_MIN = 8;
const TTS_SYNC_CPS_MAX = 30;

const deriveAppState = (mode, backend, responseActive = false) => {
  if (responseActive) return 'SPEAKING';
  if (backend === 'PROCESSING' || backend === 'SPEAKING') return backend;
  if (mode === 'PAUSED') return 'PAUSED';
  if (mode === 'FRESH') return 'FRESH';
  return 'LISTENING';
};

function App() {
  const [messages, setMessages] = useState([]);
  const [currentTranscript, setCurrentTranscript] = useState('');
  const [currentResponse, setCurrentResponse] = useState('');
  const [isResponseActive, setIsResponseActiveState] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [latestExchange, setLatestExchange] = useState(null);
  const [textVisible, setTextVisible] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [sttDraft, setSttDraft] = useState({
    eot_timeout_ms: 5000,
    eot_threshold: 0.7,
    pause_timeout_seconds: 30,
    listen_timeout_seconds: 15,
  });
  const [ttsDraft, setTtsDraft] = useState({
    enabled: false,
  });
  const [settingsError, setSettingsError] = useState(null);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [timeoutCountdown, setTimeoutCountdown] = useState(null);
  const [streamSpeedCps, setStreamSpeedCps] = useState(() => {
    if (typeof window === 'undefined') return DEFAULT_STREAM_SPEED_CPS;
    try {
      const saved = Number(window.localStorage.getItem(STREAM_SPEED_STORAGE_KEY));
      if (Number.isFinite(saved) && saved > 0) {
        return Math.min(STREAM_SPEED_MAX, Math.max(STREAM_SPEED_MIN, saved));
      }
    } catch {
      // Fall back to default when storage is unavailable.
    }
    return DEFAULT_STREAM_SPEED_CPS;
  });
  const [syncToTts, setSyncToTts] = useState(() => {
    if (typeof window === 'undefined') return false;
    try {
      return window.localStorage.getItem(SYNC_TO_TTS_STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  });

  // UI modes: FRESH (never started), ACTIVE (listening/processing/speaking), PAUSED (user paused)
  const [uiMode, setUiModeState] = useState('FRESH');
  const uiModeRef = useRef('FRESH');

  // Backend states: IDLE, LISTENING, PROCESSING, SPEAKING
  const [backendState, setBackendStateState] = useState('IDLE');
  const backendStateRef = useRef('IDLE');

  // STT session tracking (local only)
  const sttStatusRef = useRef('idle'); // idle | starting | ready | paused

  const responseRef = useRef('');
  const displayedResponseRef = useRef('');
  const responseInterruptedRef = useRef(false);
  const responseCompleteRef = useRef(false);
  const responseActiveRef = useRef(false);
  const responseActivePrevRef = useRef(false);
  const streamAnimationRef = useRef(null);
  const streamLastTickRef = useRef(0);
  const streamCarryRef = useRef(0);
  const fadeTimeoutRef = useRef(null);
  const pendingFadeRef = useRef(false);
  const hasAutoStartedRef = useRef(false);
  const audioContextRef = useRef(null);
  const nextPlayTimeRef = useRef(0);
  const ttsSampleRateRef = useRef(24000);
  const hasTtsPlaybackStartedRef = useRef(false);
  const ttsEndTimeoutRef = useRef(null);
  const scheduledSourcesRef = useRef([]);
  const countdownTimeoutRef = useRef(null);
  const countdownIntervalRef = useRef(null);
  const backgroundedRef = useRef(false);
  const floatingTextRef = useRef(null);
  const autoScrollRef = useRef(true);

  // Inactivity timeout refs
  const pauseTimeoutRef = useRef(null);
  const listenTimeoutRef = useRef(null);
  const sttDraftRef = useRef(sttDraft);  // Keep ref in sync for use in callbacks
  const streamSpeedRef = useRef(streamSpeedCps);
  const syncToTtsRef = useRef(syncToTts);
  const ttsTextLengthRef = useRef(0);  // Track response text length for TTS sync
  const ttsAudioStartTimeRef = useRef(null);  // Track when TTS audio started playing
  const ttsAudioDurationRef = useRef(0);  // Total buffered audio duration (seconds)
  const ttsAudioCompleteRef = useRef(false);  // Whether we've received the last audio chunk
  const ttsCpsEstimateRef = useRef(DEFAULT_TTS_SYNC_CPS);
  const ttsCpsUpdatedRef = useRef(false);

  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProtocol}//${window.location.hostname}:8000/api/voice/connect?client_id=${clientId}`;

  const { sendMessage, lastMessage, readyState } = useWebSocket(wsUrl, {
    shouldReconnect: () => true,
    reconnectInterval: 3000,
    onOpen: () => setIsConnected(true),
    onClose: () => setIsConnected(false),
  });

  const {
    error,
    initMic,
    releaseMic,
    startNewConversation,
    resumeListening,
    pauseListening,
    handleSessionReady,
  } = useAudioCapture(sendMessage, readyState);

  const setUiMode = (nextMode) => {
    uiModeRef.current = nextMode;
    setUiModeState(nextMode);
  };

  const setBackendState = (nextState) => {
    backendStateRef.current = nextState;
    setBackendStateState(nextState);
  };

  const setSttStatus = (nextStatus) => {
    sttStatusRef.current = nextStatus;
  };

  const setResponseActive = useCallback((nextActive) => {
    responseActiveRef.current = nextActive;
    setIsResponseActiveState(nextActive);
  }, []);

  const latestUserText = latestExchange?.user || '';
  const latestAssistantText = latestExchange?.assistant || '';
  const textItems = useMemo(() => {
    const items = [];
    const userText = currentTranscript || latestUserText;
    const assistantText = currentResponse || latestAssistantText;
    if (userText) {
      items.push({ id: 'user', text: userText, className: 'user-text' });
    }
    if (assistantText) {
      items.push({ id: 'assistant', text: assistantText, className: 'assistant-text' });
    }
    return items;
  }, [currentTranscript, currentResponse, latestAssistantText, latestUserText]);

  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: ttsSampleRateRef.current,
      });
      console.log(`Created AudioContext with sample rate: ${ttsSampleRateRef.current}`);
    }

    if (audioContextRef.current.state === 'suspended') {
      audioContextRef.current.resume();
    }

    return audioContextRef.current;
  }, []);

  const primeAudioContext = useCallback(() => {
    try {
      getAudioContext();
    } catch (err) {
      console.warn('Failed to prime audio context:', err);
    }
  }, [getAudioContext]);

  const updateTtsCpsEstimate = useCallback(() => {
    if (ttsCpsUpdatedRef.current) return;
    if (!ttsAudioCompleteRef.current) return;
    const textLength = ttsTextLengthRef.current;
    const audioDuration = ttsAudioDurationRef.current;
    if (!textLength || !Number.isFinite(audioDuration) || audioDuration <= 0) return;
    const measured = textLength / audioDuration;
    const clamped = Math.max(TTS_SYNC_CPS_MIN, Math.min(TTS_SYNC_CPS_MAX, measured));
    const previous = Number.isFinite(ttsCpsEstimateRef.current)
      ? ttsCpsEstimateRef.current
      : clamped;
    ttsCpsEstimateRef.current = previous * 0.7 + clamped * 0.3;
    ttsCpsUpdatedRef.current = true;
  }, []);

  const resetTtsPlayback = useCallback(() => {
    if (ttsEndTimeoutRef.current) {
      clearTimeout(ttsEndTimeoutRef.current);
      ttsEndTimeoutRef.current = null;
    }

    scheduledSourcesRef.current.forEach(source => {
      try {
        source.stop();
      } catch {
        // Best-effort stop for already-ended sources.
      }
    });
    scheduledSourcesRef.current = [];
    nextPlayTimeRef.current = 0;
    hasTtsPlaybackStartedRef.current = false;
    ttsAudioStartTimeRef.current = null;
    ttsAudioDurationRef.current = 0;
    ttsAudioCompleteRef.current = false;
    ttsCpsUpdatedRef.current = false;
    ttsTextLengthRef.current = 0;

    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close();
    }
    audioContextRef.current = null;
  }, []);

  const stopTtsPlayback = useCallback(() => {
    if (ttsEndTimeoutRef.current) {
      clearTimeout(ttsEndTimeoutRef.current);
      ttsEndTimeoutRef.current = null;
    }

    scheduledSourcesRef.current.forEach(source => {
      try {
        source.stop();
      } catch {
        // Best-effort stop for already-ended sources.
      }
    });
    scheduledSourcesRef.current = [];
    nextPlayTimeRef.current = 0;
    ttsAudioStartTimeRef.current = null;
    ttsAudioDurationRef.current = 0;
    ttsAudioCompleteRef.current = false;
    ttsCpsUpdatedRef.current = false;
    ttsTextLengthRef.current = 0;

    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close();
    }
    audioContextRef.current = null;

    if (hasTtsPlaybackStartedRef.current) {
      sendMessage(JSON.stringify({ type: 'tts_playback_end' }));
    }
    hasTtsPlaybackStartedRef.current = false;
  }, [sendMessage]);

  const scheduleTtsPlaybackEnd = useCallback(() => {
    if (ttsEndTimeoutRef.current) clearTimeout(ttsEndTimeoutRef.current);
    ttsEndTimeoutRef.current = null;

    if (!hasTtsPlaybackStartedRef.current) {
      // No audio was scheduled, but backend still expects a playback end signal.
      sendMessage(JSON.stringify({ type: 'tts_playback_end' }));
      scheduledSourcesRef.current = [];
      nextPlayTimeRef.current = 0;
      return;
    }

    const ctx = audioContextRef.current;
    if (!ctx) {
      sendMessage(JSON.stringify({ type: 'tts_playback_end' }));
      hasTtsPlaybackStartedRef.current = false;
      scheduledSourcesRef.current = [];
      nextPlayTimeRef.current = 0;
      return;
    }

    const remaining = Math.max(0, nextPlayTimeRef.current - ctx.currentTime);
    ttsEndTimeoutRef.current = setTimeout(() => {
      sendMessage(JSON.stringify({ type: 'tts_playback_end' }));
      hasTtsPlaybackStartedRef.current = false;
      scheduledSourcesRef.current = [];
      nextPlayTimeRef.current = 0;
    }, remaining * 1000 + 100);
  }, [sendMessage]);

  const playTtsChunk = useCallback((base64Audio) => {
    try {
      const ctx = getAudioContext();
      const binaryString = atob(base64Audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      const samples = new Int16Array(bytes.buffer);
      const floatSamples = new Float32Array(samples.length);
      for (let i = 0; i < samples.length; i++) {
        floatSamples[i] = samples[i] / 32768;
      }

      const audioBuffer = ctx.createBuffer(1, floatSamples.length, ttsSampleRateRef.current);
      audioBuffer.getChannelData(0).set(floatSamples);

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);

      const currentTime = ctx.currentTime;
      const startTime = Math.max(nextPlayTimeRef.current, currentTime);
      if (ttsAudioStartTimeRef.current === null) {
        ttsAudioStartTimeRef.current = startTime;
      }
      source.start(startTime);
      scheduledSourcesRef.current.push(source);

      nextPlayTimeRef.current = startTime + audioBuffer.duration;
      ttsAudioDurationRef.current += audioBuffer.duration;

      if (!hasTtsPlaybackStartedRef.current) {
        hasTtsPlaybackStartedRef.current = true;
        sendMessage(JSON.stringify({ type: 'tts_playback_start' }));
      }
    } catch (err) {
      console.error('Failed to play audio chunk:', err);
    }
  }, [getAudioContext, sendMessage]);

  const appState = deriveAppState(uiMode, backendState, isResponseActive);

  // Auto-start on first connect - run only ONCE
  useEffect(() => {
    if (document.visibilityState === 'hidden') return;
    if (readyState === 1 && !hasAutoStartedRef.current) {
      hasAutoStartedRef.current = true;
      console.log('🎤 Auto-starting (one-time)...');
      initMic().then(ok => {
        if (ok) {
          setUiMode('ACTIVE');
          setBackendState('IDLE');
          setTextVisible(true);
          const started = startNewConversation();
          if (started) setSttStatus('starting');
        }
      });
    }
    // Intentionally minimal deps - this should only run once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readyState]);

  const scheduleFade = useCallback(() => {
    if (fadeTimeoutRef.current) clearTimeout(fadeTimeoutRef.current);
    // Don't fade if paused - user may want to read the text
    if (uiModeRef.current === 'PAUSED') {
      pendingFadeRef.current = false;
      return;
    }
    const isStreaming = responseRef.current
      && displayedResponseRef.current.length < responseRef.current.length;
    if (isStreaming) {
      pendingFadeRef.current = true;
      return;
    }
    pendingFadeRef.current = false;
    fadeTimeoutRef.current = setTimeout(() => {
      setTextVisible(false);
      // Clear the old exchange data so it doesn't reappear on next transcript
      setLatestExchange(null);
    }, 4000);
  }, []);

  const cancelFade = useCallback(() => {
    if (fadeTimeoutRef.current) {
      clearTimeout(fadeTimeoutRef.current);
      fadeTimeoutRef.current = null;
    }
    pendingFadeRef.current = false;
  }, []);

  const clearTranscriptForListening = useCallback(() => {
    // Only clear the live transcript, NOT the finalized user text in latestExchange
    // This allows the user's question to stay visible while the assistant reply streams
    setCurrentTranscript('');
  }, []);

  const setDisplayedResponse = useCallback((nextText) => {
    displayedResponseRef.current = nextText;
    setCurrentResponse(nextText);
  }, []);

  const stopResponseStreaming = useCallback(() => {
    if (streamAnimationRef.current) {
      cancelAnimationFrame(streamAnimationRef.current);
      streamAnimationRef.current = null;
    }
    streamLastTickRef.current = 0;
    streamCarryRef.current = 0;
  }, []);

  const finalizeStreamingResponse = useCallback(() => {
    const finalText = responseRef.current;
    if (finalText) {
      setMessages(prev => [...prev, { role: 'assistant', content: finalText }]);
      setLatestExchange(prev => ({ ...(prev || {}), assistant: finalText }));
    }
    responseRef.current = '';
    responseCompleteRef.current = false;
    setResponseActive(false);
    setDisplayedResponse('');
    // Always schedule the fade after streaming completes (3 seconds, unless paused)
    pendingFadeRef.current = false;
    scheduleFade();
  }, [scheduleFade, setDisplayedResponse, setLatestExchange, setMessages, setResponseActive]);

  const streamResponseTick = useCallback((timestamp) => {
    const targetText = responseRef.current || '';
    const displayedText = displayedResponseRef.current || '';

    if (responseInterruptedRef.current) {
      stopResponseStreaming();
      return;
    }

    if (!targetText || displayedText.length >= targetText.length) {
      if (responseCompleteRef.current && targetText) {
        finalizeStreamingResponse();
      }
      stopResponseStreaming();
      return;
    }

    if (!streamLastTickRef.current) {
      streamLastTickRef.current = timestamp;
    }

    const deltaMs = Math.max(0, timestamp - streamLastTickRef.current);
    streamLastTickRef.current = timestamp;

    // Calculate speed - use dynamic TTS sync if enabled and audio is playing
    let speed = streamSpeedRef.current;
    if (syncToTtsRef.current && hasTtsPlaybackStartedRef.current && audioContextRef.current) {
      const ctx = audioContextRef.current;
      const startTime = ttsAudioStartTimeRef.current;
      const cpsEstimate = Number.isFinite(ttsCpsEstimateRef.current)
        ? ttsCpsEstimateRef.current
        : DEFAULT_TTS_SYNC_CPS;
      const targetLength = targetText.length;
      if (startTime !== null && targetLength > 0) {
        const elapsedAudioTime = Math.max(0, ctx.currentTime - startTime);
        const scheduledDuration = Math.max(0, nextPlayTimeRef.current - startTime);
        const predictedDuration = targetLength / Math.max(1, cpsEstimate);
        let totalDuration = Math.max(predictedDuration, scheduledDuration);
        if (ttsAudioCompleteRef.current && scheduledDuration > 0) {
          totalDuration = scheduledDuration;
        }
        const remainingAudioTime = Math.max(0.05, totalDuration - elapsedAudioTime);
        const remainingChars = targetLength - displayedText.length;
        const dynamicSpeed = remainingChars / remainingAudioTime;
        // Clamp to reasonable bounds (10-200 chars/sec)
        speed = Math.max(10, Math.min(200, dynamicSpeed));
      }
    }

    const budget = streamCarryRef.current + (speed * deltaMs) / 1000;
    const charsToAdd = Math.floor(budget);

    if (charsToAdd > 0) {
      const nextLength = Math.min(targetText.length, displayedText.length + charsToAdd);
      const nextText = targetText.slice(0, nextLength);
      streamCarryRef.current = budget - charsToAdd;
      if (nextText !== displayedText) {
        setDisplayedResponse(nextText);
      }
    } else {
      streamCarryRef.current = budget;
    }

    streamAnimationRef.current = requestAnimationFrame(streamResponseTick);
  }, [finalizeStreamingResponse, setDisplayedResponse, stopResponseStreaming]);

  const startResponseStreaming = useCallback(() => {
    if (streamAnimationRef.current) return;
    streamLastTickRef.current = 0;
    streamCarryRef.current = 0;
    streamAnimationRef.current = requestAnimationFrame(streamResponseTick);
  }, [streamResponseTick]);

  // Keep sttDraftRef in sync with sttDraft state
  useEffect(() => {
    sttDraftRef.current = sttDraft;
  }, [sttDraft]);

  useEffect(() => {
    streamSpeedRef.current = streamSpeedCps;
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(STREAM_SPEED_STORAGE_KEY, String(streamSpeedCps));
    } catch {
      // Ignore storage errors; speed will reset next load.
    }
  }, [streamSpeedCps]);

  useEffect(() => {
    syncToTtsRef.current = syncToTts;
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(SYNC_TO_TTS_STORAGE_KEY, String(syncToTts));
    } catch {
      // Ignore storage errors.
    }
  }, [syncToTts]);

  useEffect(() => {
    if (!textVisible) return;
    const container = floatingTextRef.current;
    if (!container) return;
    if (!autoScrollRef.current) return;
    // Double RAF to ensure DOM has painted and scrollHeight is accurate
    const frame = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (container) {
          container.scrollTop = container.scrollHeight;
        }
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [currentResponse, currentTranscript, latestExchange, textVisible]);

  useEffect(() => {
    if (!textVisible) return;
    autoScrollRef.current = true;
  }, [textVisible]);


  const handleFloatingScroll = () => {
    const container = floatingTextRef.current;
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    autoScrollRef.current = distanceFromBottom < 12;
  };

  // Clear all inactivity timeouts
  const clearTimeoutCountdown = useCallback(() => {
    if (countdownTimeoutRef.current) {
      clearTimeout(countdownTimeoutRef.current);
      countdownTimeoutRef.current = null;
    }
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current);
      countdownIntervalRef.current = null;
    }
    setTimeoutCountdown(null);
  }, []);

  const clearInactivityTimeouts = useCallback(() => {
    if (pauseTimeoutRef.current) {
      clearTimeout(pauseTimeoutRef.current);
      pauseTimeoutRef.current = null;
    }
    if (listenTimeoutRef.current) {
      clearTimeout(listenTimeoutRef.current);
      listenTimeoutRef.current = null;
    }
    clearTimeoutCountdown();
  }, [clearTimeoutCountdown]);

  const startTimeoutCountdown = useCallback((seconds, mode) => {
    clearTimeoutCountdown();
    const totalSeconds = Number(seconds);
    if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) return;

    const startDelayMs = Math.max(0, (totalSeconds - TIMEOUT_COUNTDOWN_SECONDS) * 1000);
    const startValue = totalSeconds >= TIMEOUT_COUNTDOWN_SECONDS
      ? TIMEOUT_COUNTDOWN_SECONDS
      : Math.max(1, Math.floor(totalSeconds));

    countdownTimeoutRef.current = setTimeout(() => {
      let remaining = startValue;
      setTimeoutCountdown({ remaining, mode });
      countdownIntervalRef.current = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
          clearTimeoutCountdown();
        } else {
          setTimeoutCountdown({ remaining, mode });
        }
      }, 1000);
    }, startDelayMs);
  }, [clearTimeoutCountdown]);

  const finalizePartialResponse = useCallback(() => {
    const partial = displayedResponseRef.current;
    if (partial) {
      setMessages(prev => [...prev, { role: 'assistant', content: partial }]);
      setLatestExchange(prev => ({ ...(prev || {}), assistant: partial }));
    }
    responseRef.current = '';
    responseCompleteRef.current = false;
    setResponseActive(false);
    stopResponseStreaming();
    setDisplayedResponse('');
  }, [setDisplayedResponse, setLatestExchange, setMessages, setResponseActive, stopResponseStreaming]);

  const interruptResponse = useCallback(() => {
    responseInterruptedRef.current = true;
    clearInactivityTimeouts();
    stopTtsPlayback();
    finalizePartialResponse();

    if (readyState === 1) {
      sendMessage(JSON.stringify({ type: 'wakeword_barge_in', manual: true }));
    }
  }, [clearInactivityTimeouts, finalizePartialResponse, readyState, sendMessage, stopTtsPlayback]);

  const resetSession = useCallback((options = {}) => {
    const { clearMessages = false, fadeText = false, resetAutoStart = true } = options;
    clearInactivityTimeouts();

    if (readyState === 1) {
      sendMessage(JSON.stringify({ type: 'clear_session' }));
    }

    stopTtsPlayback();
    releaseMic();
    if (resetAutoStart) {
      hasAutoStartedRef.current = false;
    }

    setUiMode('FRESH');
    setBackendState('IDLE');
    setSttStatus('idle');
    setCurrentTranscript('');
    setDisplayedResponse('');
    responseRef.current = '';
    responseCompleteRef.current = false;
    setResponseActive(false);
    responseInterruptedRef.current = false;
    pendingFadeRef.current = false;
    stopResponseStreaming();

    if (clearMessages) {
      setMessages([]);
      setLatestExchange(null);
    }

    if (fadeText) {
      scheduleFade();
    } else {
      setTextVisible(false);
    }
  }, [
    clearInactivityTimeouts,
    readyState,
    releaseMic,
    sendMessage,
    stopTtsPlayback,
    scheduleFade,
    setDisplayedResponse,
    setResponseActive,
    stopResponseStreaming,
  ]);

  // Handle inactivity timeout - close session but preserve context
  const handleInactivityTimeout = useCallback(() => {
    console.log('⏰ Inactivity timeout triggered');
    resetSession({ fadeText: true });
  }, [resetSession]);

  // Schedule listen timeout (when listening with no speech)
  const scheduleListenTimeout = useCallback((options = {}) => {
    if (responseActiveRef.current) return;
    clearInactivityTimeouts();
    const seconds = sttDraftRef.current.listen_timeout_seconds;
    if (seconds <= 0) return; // Disabled
    const { shouldLog = true } = options;

    if (shouldLog) {
      console.log(`⏱️ Starting listen timeout: ${seconds}s`);
    }
    startTimeoutCountdown(seconds, 'listen');
    listenTimeoutRef.current = setTimeout(() => {
      console.log('⏰ Listen timeout expired');
      handleInactivityTimeout();
    }, seconds * 1000);
  }, [clearInactivityTimeouts, handleInactivityTimeout, startTimeoutCountdown]);

  // Schedule pause timeout (when paused)
  const schedulePauseTimeout = useCallback(() => {
    clearInactivityTimeouts();
    const seconds = sttDraftRef.current.pause_timeout_seconds;
    if (seconds <= 0) return; // Disabled

    console.log(`⏱️ Starting pause timeout: ${seconds}s`);
    startTimeoutCountdown(seconds, 'pause');
    pauseTimeoutRef.current = setTimeout(() => {
      console.log('⏰ Pause timeout expired');
      handleInactivityTimeout();
    }, seconds * 1000);
  }, [clearInactivityTimeouts, handleInactivityTimeout, startTimeoutCountdown]);

  useEffect(() => {
    const wasActive = responseActivePrevRef.current;
    responseActivePrevRef.current = isResponseActive;
    if (!wasActive || isResponseActive) return;
    if (uiModeRef.current !== 'ACTIVE') return;
    const backend = backendStateRef.current;
    if (backend === 'LISTENING' || backend === 'IDLE') {
      scheduleListenTimeout();
    }
  }, [isResponseActive, scheduleListenTimeout]);

  // Handle backend messages
  useEffect(() => {
    if (backgroundedRef.current) return;
    if (!lastMessage?.data) return;

    try {
      const msg = JSON.parse(lastMessage.data);

      if (msg.type === 'stt_session_ready') {
        handleSessionReady();
        if (uiModeRef.current !== 'PAUSED') {
          setSttStatus('ready');
        }
      }

      if (msg.type === 'stt_session_error') {
        console.warn('STT session error:', msg.error);
        setSttStatus('idle');
      }

      if (msg.type === 'interrupt_tts') {
        console.log('TTS interrupted');
        responseInterruptedRef.current = true;
        stopTtsPlayback();
        setResponseActive(false);
      }

      if (msg.type === 'tts_audio_start') {
        responseInterruptedRef.current = false;
        const sampleRate = Number(msg.sample_rate) || 24000;
        ttsSampleRateRef.current = sampleRate;
        resetTtsPlayback();
      }

      if (msg.type === 'tts_audio_chunk') {
        if (!responseInterruptedRef.current) {
          if (msg.data) {
            playTtsChunk(msg.data);
          }
          if (msg.is_last) {
            ttsAudioCompleteRef.current = true;
            updateTtsCpsEstimate();
            scheduleTtsPlaybackEnd();
          }
        }
      }

      if (msg.type === 'tts_audio') {
        if (!responseInterruptedRef.current && msg.data) {
          playTtsChunk(msg.data);
        }
      }

      if (msg.type === 'state') {
        const s = msg.state;
        const previousBackendState = backendStateRef.current;
        const currentAppState = deriveAppState(
          uiModeRef.current,
          backendStateRef.current,
          responseActiveRef.current,
        );
        console.log('Backend state:', s, '| appState:', currentAppState);
        setBackendState(s);

        if (s === 'LISTENING') {
          // Only update UI if not paused
          if (uiModeRef.current !== 'PAUSED') {
            if (uiModeRef.current === 'FRESH') {
              setUiMode('ACTIVE');
            }
            if (previousBackendState !== 'LISTENING') {
              clearTranscriptForListening();
            }
            cancelFade();
            setTextVisible(true);
            scheduleListenTimeout();
          }
          // DON'T send any messages to backend - just update UI
        } else if (s === 'PROCESSING' || s === 'SPEAKING') {
          // Clear timeouts while processing/speaking - don't timeout during activity
          clearInactivityTimeouts();
          if (uiModeRef.current !== 'ACTIVE') {
            setUiMode('ACTIVE');
          }
        } else if (s === 'IDLE') {
          // Keep UI mode as-is; just fade the transcript after idle.
          if (uiModeRef.current !== 'PAUSED') {
            scheduleFade();
          }
          // If ACTIVE (not paused/fresh), schedule listen timeout
          if (uiModeRef.current === 'ACTIVE' && previousBackendState !== 'LISTENING') {
            scheduleListenTimeout();
          }
        }
      }

      if (msg.type === 'transcript') {
        // Reset listen timeout on any transcript (user is speaking)
        if (uiModeRef.current === 'ACTIVE' && backendStateRef.current === 'LISTENING') {
          scheduleListenTimeout({ shouldLog: false });
        }
        setCurrentTranscript(msg.text || '');
        setTextVisible(true);
        if (msg.is_final && msg.text) {
          setMessages(prev => [...prev, { role: 'user', content: msg.text }]);
          // Store finalized user text but keep it displayed (don't clear currentTranscript)
          // The text will remain visible while the assistant reply streams below
          setLatestExchange(prev => ({ ...prev, user: msg.text, assistant: '' }));
        }
      }

      if (msg.type === 'assistant_response_start') {
        responseInterruptedRef.current = false;
        responseCompleteRef.current = false;
        responseRef.current = '';
        ttsTextLengthRef.current = 0;
        ttsCpsUpdatedRef.current = false;
        pendingFadeRef.current = false;
        setResponseActive(true);
        clearInactivityTimeouts();
        stopResponseStreaming();
        setDisplayedResponse('');
        setTextVisible(true);
      } else if (msg.type === 'assistant_response_chunk') {
        if (!responseInterruptedRef.current) {
          responseRef.current += (msg.text || '');
          if (displayedResponseRef.current.length < responseRef.current.length) {
            startResponseStreaming();
          }
        }
      } else if (msg.type === 'assistant_response_end') {
        if (!responseInterruptedRef.current) {
          const candidateText = responseRef.current;
          const finalText = msg.text && msg.text.length > candidateText.length
            ? msg.text
            : candidateText;
          responseRef.current = finalText || '';
          responseCompleteRef.current = Boolean(finalText);
          if (!finalText) {
            setResponseActive(false);
            setDisplayedResponse('');
            return;
          }
          ttsTextLengthRef.current = finalText.length;
          updateTtsCpsEstimate();
          if (displayedResponseRef.current.length >= finalText.length) {
            finalizeStreamingResponse();
          } else {
            startResponseStreaming();
          }
        }
      }

    } catch (e) {
      console.error('Parse error:', e);
    }
  }, [
    clearInactivityTimeouts,
    finalizeStreamingResponse,
    handleSessionReady,
    lastMessage,
    playTtsChunk,
    resetTtsPlayback,
    scheduleFade,
    scheduleListenTimeout,
    scheduleTtsPlaybackEnd,
    setDisplayedResponse,
    setResponseActive,
    startResponseStreaming,
    stopResponseStreaming,
    stopTtsPlayback,
    updateTtsCpsEstimate,
    cancelFade,
    clearTranscriptForListening,
  ]);

  // Load STT settings when opening settings panel
  useEffect(() => {
    if (!showSettings) return;

    let cancelled = false;
    setSettingsLoading(true);
    setSettingsError(null);

    const loadSettings = async () => {
      let hadError = false;

      try {
        const sttResp = await fetch('/api/clients/voice/stt');
        if (!sttResp.ok) {
          hadError = true;
        } else {
          const data = await sttResp.json();
          if (!cancelled) {
            const normalized = {
              eot_timeout_ms: Number(data.eot_timeout_ms ?? 5000),
              eot_threshold: Number(data.eot_threshold ?? 0.7),
              pause_timeout_seconds: Number(data.pause_timeout_seconds ?? 30),
              listen_timeout_seconds: Number(data.listen_timeout_seconds ?? 15),
            };
            setSttDraft(normalized);
          }
        }
      } catch {
        hadError = true;
      }

      try {
        const ttsResp = await fetch('/api/clients/voice/tts');
        if (!ttsResp.ok) {
          hadError = true;
        } else {
          const data = await ttsResp.json();
          if (!cancelled) {
            setTtsDraft({
              enabled: Boolean(data.enabled),
            });
          }
        }
      } catch {
        hadError = true;
      }

      if (!cancelled) {
        if (hadError) {
          setSettingsError('Failed to load settings');
        }
        setSettingsLoading(false);
      }
    };

    loadSettings();

    return () => {
      cancelled = true;
    };
  }, [showSettings]);

  // Handle tap - pause/resume
  const handleTap = () => {
    primeAudioContext();
    if (showHistory || showSettings) return;
    const currentAppState = deriveAppState(
      uiModeRef.current,
      backendStateRef.current,
      responseActiveRef.current,
    );

    if (currentAppState === 'PROCESSING' || currentAppState === 'SPEAKING') {
      console.log('🎤 TAP: INTERRUPT');
      interruptResponse();
      return;
    }

    if (currentAppState === 'LISTENING') {
      console.log('🎤 TAP: PAUSE');
      clearInactivityTimeouts();
      cancelFade();
      setUiMode('PAUSED');
      const paused = pauseListening();
      if (paused) setSttStatus('paused');
      // Schedule pause timeout
      schedulePauseTimeout();
    } else if (currentAppState === 'PAUSED') {
      console.log('🎤 TAP: RESUME');
      clearInactivityTimeouts();
      cancelFade();
      clearTranscriptForListening();
      setUiMode('ACTIVE');
      setBackendState('IDLE');
      setTextVisible(true);
      initMic().then(ok => {
        if (ok) {
          const resumed = resumeListening();
          if (resumed) setSttStatus('starting');
        }
      });
    } else if (currentAppState === 'FRESH') {
      console.log('🎤 TAP: FIRST START');
      clearInactivityTimeouts();
      cancelFade();
      clearTranscriptForListening();
      setUiMode('ACTIVE');
      setBackendState('IDLE');
      setTextVisible(true);
      initMic().then(ok => {
        if (ok) {
          const started = startNewConversation();
          if (started) setSttStatus('starting');
        }
      });
    }
    // Other states are handled above.
  };

  // Clear session
  const handleClear = (e) => {
    e.stopPropagation();
    resetSession({ clearMessages: true });
  };

  const handlePullUp = (e) => {
    e.stopPropagation();
    setShowSettings(false);
    setShowHistory(true);
  };

  const handleCloseHistory = () => setShowHistory(false);

  const handleOpenSettings = (e) => {
    e.stopPropagation();
    setShowHistory(false);
    setShowSettings(true);
    primeAudioContext();
  };

  const handleCloseSettings = (e) => {
    e.stopPropagation();
    setShowSettings(false);
  };

  const handleAppHidden = useCallback(() => {
    if (backgroundedRef.current) return;
    backgroundedRef.current = true;
    setShowHistory(false);
    setShowSettings(false);
    resetSession({ resetAutoStart: false });
  }, [resetSession]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        handleAppHidden();
      } else {
        backgroundedRef.current = false;
      }
    };

    const handlePageHide = () => {
      handleAppHidden();
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('pagehide', handlePageHide);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('pagehide', handlePageHide);
    };
  }, [handleAppHidden]);

  // Community-recommended defaults for Deepgram STT
  const defaultSettings = {
    eot_timeout_ms: 1000,  // 1 second - natural conversation pace
    eot_threshold: 0.7,    // balanced confidence threshold
    pause_timeout_seconds: 30,   // 30 seconds when paused
    listen_timeout_seconds: 15,  // 15 seconds of no speech
  };

  const handleResetDefaults = (e) => {
    e.stopPropagation();
    setSttDraft(defaultSettings);
    setStreamSpeedCps(DEFAULT_STREAM_SPEED_CPS);
    setSyncToTts(false);
  };

  const handleToggleTts = (e) => {
    e.stopPropagation();
    const nextEnabled = !ttsDraft.enabled;
    setTtsDraft({ enabled: nextEnabled });
    if (nextEnabled) {
      primeAudioContext();
    } else {
      stopTtsPlayback();
    }
  };

  const handleSaveSettings = async (e) => {
    e.stopPropagation();
    setSettingsSaving(true);
    setSettingsError(null);

    try {
      const payload = {
        eot_timeout_ms: Number(sttDraft.eot_timeout_ms),
        eot_threshold: Number(sttDraft.eot_threshold),
        pause_timeout_seconds: Number(sttDraft.pause_timeout_seconds),
        listen_timeout_seconds: Number(sttDraft.listen_timeout_seconds),
      };

      const resp = await fetch('/api/clients/voice/stt', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      let hadError = false;

      if (!resp.ok) {
        hadError = true;
      } else {
        const data = await resp.json();
        const normalized = {
          eot_timeout_ms: Number(data.eot_timeout_ms ?? payload.eot_timeout_ms),
          eot_threshold: Number(data.eot_threshold ?? payload.eot_threshold),
          pause_timeout_seconds: Number(data.pause_timeout_seconds ?? payload.pause_timeout_seconds),
          listen_timeout_seconds: Number(data.listen_timeout_seconds ?? payload.listen_timeout_seconds),
        };
        setSttDraft(normalized);
      }

      const ttsPayload = {
        enabled: Boolean(ttsDraft.enabled),
      };

      const ttsResp = await fetch('/api/clients/voice/tts', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(ttsPayload),
      });

      if (!ttsResp.ok) {
        hadError = true;
      } else {
        const data = await ttsResp.json();
        setTtsDraft({
          enabled: Boolean(data.enabled),
        });
      }

      if (hadError) {
        throw new Error('Failed to save settings');
      }

      setShowSettings(false);
    } catch {
      setSettingsError('Failed to save settings');
    } finally {
      setSettingsSaving(false);
    }
  };

  const getOrbClass = () => {
    if (appState === 'LISTENING') return 'listening';
    if (appState === 'PROCESSING') return 'processing';
    if (appState === 'SPEAKING') return 'speaking';
    if (appState === 'PAUSED') return 'paused';
    return 'idle';
  };

  const getStatusText = () => {
    if (!isConnected) return 'Connecting...';
    if (appState === 'LISTENING') return 'Listening...';
    if (appState === 'PROCESSING') return 'Thinking...';
    if (appState === 'SPEAKING') return '';
    if (appState === 'PAUSED') return 'Paused';
    return 'Tap to start';
  };

  return (
    <div className="app" onClick={handleTap}>
      <div className="top-controls">
        <div className="top-left-controls">
          <button
            className="settings-button"
            onClick={handleOpenSettings}
            aria-label="Open settings"
            title="Settings"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true" fill="none">
              <circle cx="12" cy="5" r="1.5" fill="currentColor" />
              <circle cx="12" cy="12" r="1.5" fill="currentColor" />
              <circle cx="12" cy="19" r="1.5" fill="currentColor" />
            </svg>
          </button>
          <button
            className="clear-button"
            onClick={handleClear}
            aria-label="Clear conversation"
            title="Clear"
          >
            Clear
          </button>
        </div>
        <div className="top-right-controls">
          <div className={`connection-dot ${isConnected ? 'connected' : ''}`} />
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="main-content">
        <div className="orb-container">
          <div className={`orb ${getOrbClass()}`} />
          <div className="ripple-ring" />
          <div className="ripple-ring" />
          <div className="ripple-ring" />
        </div>

        <div className={`status-text ${appState !== 'FRESH' ? 'active' : ''}`}>
          {getStatusText()}
        </div>

        <div
          className={`timeout-countdown${timeoutCountdown ? ` visible ${timeoutCountdown.mode}` : ''}`}
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          {timeoutCountdown && (
            <>
              <div className="timeout-banner">
                <span className="timeout-label">
                  {timeoutCountdown.mode === 'pause' ? 'Paused' : 'No speech'}
                </span>
                <span className="timeout-sep">|</span>
                <span className="timeout-text">Session ends in</span>
              </div>
              <div className="timeout-ticker">
                <span key={timeoutCountdown.remaining} className="timeout-digit">
                  {timeoutCountdown.remaining}
                </span>
                <span className="timeout-unit">s</span>
              </div>
            </>
          )}
        </div>

        <ScrollFadeText
          ref={floatingTextRef}
          onScroll={handleFloatingScroll}
          visible={textVisible}
          items={textItems}
        />
      </div>

      <div className="bottom-controls">
        {messages.length > 0 && !showHistory && (
          <div className="pull-indicator" onClick={handlePullUp}>
            <div className="pull-line" />
            <span>History</span>
          </div>
        )}
      </div>

      {showHistory && (
        <div className="history-overlay" onClick={handleCloseHistory}>
          <div className="history-panel" onClick={e => e.stopPropagation()}>
            <div className="history-header">
              <span>Conversation</span>
              <button onClick={handleCloseHistory}>Done</button>
            </div>
            <div className="history-scroll">
              {messages.map((msg, i) => (
                <div key={i} className={`history-message ${msg.role}`}>
                  <span className="history-label">{msg.role === 'user' ? 'You' : 'Assistant'}</span>
                  <p>{msg.content}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {showSettings && (
        <div className="settings-overlay" onClick={handleCloseSettings}>
          <div className="settings-panel" onClick={e => e.stopPropagation()}>
            <div className="settings-header">
              <span>Voice Settings</span>
              <div className="settings-header-actions">
                <button
                  className="settings-header-save"
                  onClick={handleSaveSettings}
                  disabled={settingsLoading || settingsSaving}
                >
                  {settingsSaving ? 'Saving...' : 'Save'}
                </button>
                <button onClick={handleCloseSettings}>Close</button>
              </div>
            </div>

            {settingsError && <div className="settings-error">{settingsError}</div>}

            {settingsLoading ? (
              <div className="settings-loading">Loading...</div>
            ) : (
              <div className="settings-scroll">
                <div className="settings-section">
                  <div className="settings-section-title">Text to Speech</div>

                  <div className="settings-row">
                    <div className="settings-label">Enable TTS</div>
                    <button
                      className={`settings-toggle ${ttsDraft.enabled ? 'on' : ''}`}
                      onClick={handleToggleTts}
                      disabled={settingsSaving}
                    >
                      {ttsDraft.enabled ? 'On' : 'Off'}
                    </button>
                  </div>

                  <div className={`settings-row ${syncToTts && ttsDraft.enabled ? 'disabled' : ''}`}>
                    <div className="settings-row-header">
                      <div className="settings-label">Text stream speed</div>
                      {ttsDraft.enabled && (
                        <button
                          className={`settings-sync-btn ${syncToTts ? 'on' : ''}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            setSyncToTts(!syncToTts);
                          }}
                          disabled={settingsSaving}
                        >
                          Sync
                        </button>
                      )}
                    </div>
                    <div className="settings-value">
                      {syncToTts && ttsDraft.enabled ? 'Synced to TTS' : `${streamSpeedCps} chars/sec`}
                    </div>
                    <input
                      className="settings-slider"
                      type="range"
                      min={STREAM_SPEED_MIN}
                      max={STREAM_SPEED_MAX}
                      step={STREAM_SPEED_STEP}
                      value={streamSpeedCps}
                      onChange={(e) => setStreamSpeedCps(Number(e.target.value))}
                      disabled={syncToTts && ttsDraft.enabled}
                    />
                  </div>
                </div>

                <div className="settings-section">
                  <div className="settings-section-title">Speech Recognition</div>

                  <div className="settings-row">
                    <div className="settings-label">End of turn timeout</div>
                    <div className="settings-value">{sttDraft.eot_timeout_ms} ms</div>
                    <input
                      className="settings-slider"
                      type="range"
                      min="100"
                      max="2000"
                      step="100"
                      value={sttDraft.eot_timeout_ms}
                      onChange={(e) => setSttDraft(prev => ({
                        ...prev,
                        eot_timeout_ms: Number(e.target.value),
                      }))}
                    />
                  </div>

                  <div className="settings-row">
                    <div className="settings-label">End of turn threshold</div>
                    <div className="settings-value">
                      {Number(sttDraft.eot_threshold).toFixed(2)}
                    </div>
                    <input
                      className="settings-slider"
                      type="range"
                      min="0.5"
                      max="0.9"
                      step="0.01"
                      value={sttDraft.eot_threshold}
                      onChange={(e) => setSttDraft(prev => ({
                        ...prev,
                        eot_threshold: Number(e.target.value),
                      }))}
                    />
                  </div>

                  <div className="settings-row">
                    <div className="settings-label">Pause timeout</div>
                    <div className="settings-value">
                      {sttDraft.pause_timeout_seconds === 0 ? 'Disabled' : `${sttDraft.pause_timeout_seconds}s`}
                    </div>
                    <input
                      className="settings-slider"
                      type="range"
                      min="0"
                      max="60"
                      step="5"
                      value={sttDraft.pause_timeout_seconds}
                      onChange={(e) => setSttDraft(prev => ({
                        ...prev,
                        pause_timeout_seconds: Number(e.target.value),
                      }))}
                    />
                  </div>

                  <div className="settings-row">
                    <div className="settings-label">Listen timeout</div>
                    <div className="settings-value">
                      {sttDraft.listen_timeout_seconds === 0 ? 'Disabled' : `${sttDraft.listen_timeout_seconds}s`}
                    </div>
                    <input
                      className="settings-slider"
                      type="range"
                      min="0"
                      max="30"
                      step="1"
                      value={sttDraft.listen_timeout_seconds}
                      onChange={(e) => setSttDraft(prev => ({
                        ...prev,
                        listen_timeout_seconds: Number(e.target.value),
                      }))}
                    />
                  </div>
                </div>
              </div>
            )}

            <div className="settings-actions">
              <button
                className="settings-default"
                onClick={handleResetDefaults}
                disabled={settingsLoading || settingsSaving}
              >
                Default
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default App;
