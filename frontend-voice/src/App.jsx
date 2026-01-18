import { useCallback, useEffect, useRef, useState } from 'react';
import useWebSocket from 'react-use-websocket';
import './App.css';
import useAudioCapture from './hooks/useAudioCapture';

// Version for debugging
console.log('🔧 App.jsx v3 loaded');

const clientId = `voice_${crypto.randomUUID()}`;
const TIMEOUT_COUNTDOWN_SECONDS = 5;

const deriveAppState = (mode, backend) => {
  if (backend === 'PROCESSING' || backend === 'SPEAKING') return backend;
  if (mode === 'PAUSED') return 'PAUSED';
  if (mode === 'FRESH') return 'FRESH';
  return 'LISTENING';
};

function App() {
  const [messages, setMessages] = useState([]);
  const [currentTranscript, setCurrentTranscript] = useState('');
  const [currentResponse, setCurrentResponse] = useState('');
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

  // UI modes: FRESH (never started), ACTIVE (listening/processing/speaking), PAUSED (user paused)
  const [uiMode, setUiModeState] = useState('FRESH');
  const uiModeRef = useRef('FRESH');

  // Backend states: IDLE, LISTENING, PROCESSING, SPEAKING
  const [backendState, setBackendStateState] = useState('IDLE');
  const backendStateRef = useRef('IDLE');

  // STT session tracking (local only)
  const sttStatusRef = useRef('idle'); // idle | starting | ready | paused

  const responseRef = useRef('');
  const fadeTimeoutRef = useRef(null);
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

  // Inactivity timeout refs
  const pauseTimeoutRef = useRef(null);
  const listenTimeoutRef = useRef(null);
  const sttDraftRef = useRef(sttDraft);  // Keep ref in sync for use in callbacks

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
    const ctx = audioContextRef.current;
    if (!ctx || !hasTtsPlaybackStartedRef.current) {
      return;
    }

    const remaining = Math.max(0, nextPlayTimeRef.current - ctx.currentTime);
    if (ttsEndTimeoutRef.current) clearTimeout(ttsEndTimeoutRef.current);
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
      source.start(startTime);
      scheduledSourcesRef.current.push(source);

      nextPlayTimeRef.current = startTime + audioBuffer.duration;

      if (!hasTtsPlaybackStartedRef.current) {
        hasTtsPlaybackStartedRef.current = true;
        sendMessage(JSON.stringify({ type: 'tts_playback_start' }));
      }
    } catch (err) {
      console.error('Failed to play audio chunk:', err);
    }
  }, [getAudioContext, sendMessage]);

  const appState = deriveAppState(uiMode, backendState);

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
    fadeTimeoutRef.current = setTimeout(() => setTextVisible(false), 5000);
  }, []);

  // Keep sttDraftRef in sync with sttDraft state
  useEffect(() => {
    sttDraftRef.current = sttDraft;
  }, [sttDraft]);

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
    setCurrentResponse('');

    if (clearMessages) {
      setMessages([]);
      setLatestExchange(null);
    }

    if (fadeText) {
      scheduleFade();
    } else {
      setTextVisible(false);
    }
  }, [clearInactivityTimeouts, readyState, releaseMic, sendMessage, stopTtsPlayback, scheduleFade]);

  // Handle inactivity timeout - close session but preserve context
  const handleInactivityTimeout = useCallback(() => {
    console.log('⏰ Inactivity timeout triggered');
    resetSession({ fadeText: true });
  }, [resetSession]);

  // Schedule listen timeout (when listening with no speech)
  const scheduleListenTimeout = useCallback((options = {}) => {
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
        stopTtsPlayback();
      }

      if (msg.type === 'tts_audio_start') {
        const sampleRate = Number(msg.sample_rate) || 24000;
        ttsSampleRateRef.current = sampleRate;
        resetTtsPlayback();
      }

      if (msg.type === 'tts_audio_chunk') {
        if (msg.data) {
          playTtsChunk(msg.data);
        }
        if (msg.is_last) {
          scheduleTtsPlaybackEnd();
        }
      }

      if (msg.type === 'tts_audio') {
        if (msg.data) {
          playTtsChunk(msg.data);
        }
      }

      if (msg.type === 'state') {
        const s = msg.state;
        const previousBackendState = backendStateRef.current;
        const currentAppState = deriveAppState(uiModeRef.current, backendStateRef.current);
        console.log('Backend state:', s, '| appState:', currentAppState);
        setBackendState(s);

        if (s === 'LISTENING') {
          // Only update UI if not paused
          if (uiModeRef.current !== 'PAUSED') {
            if (uiModeRef.current === 'FRESH') {
              setUiMode('ACTIVE');
            }
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
          scheduleFade();
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
          setLatestExchange(prev => ({ ...prev, user: msg.text, assistant: '' }));
          setCurrentTranscript('');
        }
      }

      if (msg.type === 'assistant_response_start') {
        responseRef.current = '';
        setCurrentResponse('');
        setTextVisible(true);
      } else if (msg.type === 'assistant_response_chunk') {
        responseRef.current += (msg.text || '');
        setCurrentResponse(responseRef.current);
      } else if (msg.type === 'assistant_response_end') {
        const finalText = responseRef.current || msg.text || '';
        if (finalText) {
          setMessages(prev => [...prev, { role: 'assistant', content: finalText }]);
          setLatestExchange(prev => ({ ...prev, assistant: finalText }));
        }
        responseRef.current = '';
        setCurrentResponse('');
      }

    } catch (e) {
      console.error('Parse error:', e);
    }
  }, [clearInactivityTimeouts, handleSessionReady, lastMessage, playTtsChunk, resetTtsPlayback, scheduleListenTimeout, scheduleTtsPlaybackEnd, stopTtsPlayback]);

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
    const currentAppState = deriveAppState(uiModeRef.current, backendStateRef.current);

    if (currentAppState === 'LISTENING') {
      console.log('🎤 TAP: PAUSE');
      clearInactivityTimeouts();
      setUiMode('PAUSED');
      const paused = pauseListening();
      if (paused) setSttStatus('paused');
      scheduleFade();
      // Schedule pause timeout
      schedulePauseTimeout();
    } else if (currentAppState === 'PAUSED') {
      console.log('🎤 TAP: RESUME');
      clearInactivityTimeouts();
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
    // Don't do anything for PROCESSING or SPEAKING states
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
          <button className="settings-button" onClick={handleOpenSettings}>S</button>
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

        <div className={`floating-text ${textVisible ? 'visible' : ''}`}>
          {currentTranscript && <p className="user-text">{currentTranscript}</p>}
          {!currentTranscript && latestExchange?.user && <p className="user-text">{latestExchange.user}</p>}
          {(currentResponse || latestExchange?.assistant) && (
            <p className="assistant-text">{currentResponse || latestExchange?.assistant}</p>
          )}
        </div>
      </div>

      <div className="bottom-controls">
        {(appState === 'PAUSED' || (messages.length > 0 && appState !== 'LISTENING')) && (
          <button className="new-button" onClick={handleClear}>New</button>
        )}
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
              <button onClick={handleCloseSettings}>Done</button>
            </div>

            {settingsError && <div className="settings-error">{settingsError}</div>}

            {settingsLoading ? (
              <div className="settings-loading">Loading...</div>
            ) : (
              <>
                <div className="settings-row">
                  <div className="settings-label">Text to speech</div>
                  <button
                    className={`settings-toggle ${ttsDraft.enabled ? 'on' : ''}`}
                    onClick={handleToggleTts}
                    disabled={settingsSaving}
                  >
                    {ttsDraft.enabled ? 'On' : 'Off'}
                  </button>
                </div>

                <div className="settings-row">
                  <div className="settings-label">End of turn timeout</div>
                  <div className="settings-value">{sttDraft.eot_timeout_ms} ms</div>
                  <input
                    className="settings-slider"
                    type="range"
                    min="100"
                    max="30000"
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
                    max="600"
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
                    max="600"
                    step="5"
                    value={sttDraft.listen_timeout_seconds}
                    onChange={(e) => setSttDraft(prev => ({
                      ...prev,
                      listen_timeout_seconds: Number(e.target.value),
                    }))}
                  />
                </div>
              </>
            )}

            <div className="settings-actions">
              <button
                className="settings-default"
                onClick={handleResetDefaults}
                disabled={settingsLoading || settingsSaving}
              >
                Default
              </button>
              <button
                className="settings-save"
                onClick={handleSaveSettings}
                disabled={settingsLoading || settingsSaving}
              >
                {settingsSaving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default App;
