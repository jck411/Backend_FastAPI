import { useEffect, useRef, useState } from 'react';
import useWebSocket from 'react-use-websocket';
import './App.css';
import useAudioCapture from './hooks/useAudioCapture';

// Version for debugging
console.log('🔧 App.jsx v3 loaded');

const clientId = `voice_${crypto.randomUUID()}`;

function App() {
  const [messages, setMessages] = useState([]);
  const [currentTranscript, setCurrentTranscript] = useState('');
  const [currentResponse, setCurrentResponse] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [latestExchange, setLatestExchange] = useState(null);
  const [textVisible, setTextVisible] = useState(false);

  // States: FRESH, LISTENING, PAUSED, PROCESSING, SPEAKING
  const [appState, setAppState] = useState('FRESH');
  const appStateRef = useRef('FRESH');  // Ref to avoid stale closures

  const responseRef = useRef('');
  const fadeTimeoutRef = useRef(null);
  const hasAutoStartedRef = useRef(false);

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

  // Keep appStateRef in sync
  useEffect(() => {
    appStateRef.current = appState;
  }, [appState]);

  // Auto-start on first connect - run only ONCE
  useEffect(() => {
    if (readyState === 1 && !hasAutoStartedRef.current) {
      hasAutoStartedRef.current = true;
      console.log('🎤 Auto-starting (one-time)...');
      initMic().then(ok => {
        if (ok) {
          appStateRef.current = 'LISTENING';
          setAppState('LISTENING');
          setTextVisible(true);
          startNewConversation();
        }
      });
    }
    // Intentionally minimal deps - this should only run once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readyState]);

  const scheduleFade = () => {
    if (fadeTimeoutRef.current) clearTimeout(fadeTimeoutRef.current);
    fadeTimeoutRef.current = setTimeout(() => setTextVisible(false), 5000);
  };

  // Handle backend messages
  useEffect(() => {
    if (!lastMessage?.data) return;

    try {
      const msg = JSON.parse(lastMessage.data);

      if (msg.type === 'stt_session_ready') {
        handleSessionReady();
      }

      if (msg.type === 'state') {
        const s = msg.state;
        const currentAppState = appStateRef.current;
        console.log('Backend state:', s, '| appState:', currentAppState);

        if (s === 'LISTENING') {
          // Only update UI if not paused
          if (currentAppState !== 'PAUSED') {
            setAppState('LISTENING');
            setTextVisible(true);
          }
          // DON'T send any messages to backend - just update UI
        } else if (s === 'PROCESSING') {
          setAppState('PROCESSING');
        } else if (s === 'SPEAKING') {
          setAppState('SPEAKING');
        } else if (s === 'IDLE') {
          // Just update UI, don't try to auto-resume
          if (currentAppState !== 'PAUSED') {
            setAppState('LISTENING');  // Stay in listening mode for UI
          }
          scheduleFade();
        }
      }

      if (msg.type === 'transcript') {
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
  }, [lastMessage, handleSessionReady]);

  // Handle tap - pause/resume
  const handleTap = (e) => {
    if (showHistory) return;
    const currentAppState = appStateRef.current;

    if (currentAppState === 'LISTENING') {
      console.log('🎤 TAP: PAUSE');
      appStateRef.current = 'PAUSED';
      setAppState('PAUSED');
      pauseListening();
      scheduleFade();
    } else if (currentAppState === 'PAUSED') {
      console.log('🎤 TAP: RESUME');
      appStateRef.current = 'LISTENING';
      setAppState('LISTENING');
      setTextVisible(true);
      initMic().then(ok => {
        if (ok) {
          resumeListening();
        }
      });
    } else if (currentAppState === 'FRESH') {
      console.log('🎤 TAP: FIRST START');
      appStateRef.current = 'LISTENING';
      setTextVisible(true);
      initMic().then(ok => {
        if (ok) {
          setAppState('LISTENING');
          startNewConversation();
        }
      });
    }
    // Don't do anything for PROCESSING or SPEAKING states
  };

  // Clear session
  const handleClear = (e) => {
    e.stopPropagation();
    pauseListening();
    releaseMic();
    hasAutoStartedRef.current = false;
    appStateRef.current = 'FRESH';
    setAppState('FRESH');
    setMessages([]);
    setLatestExchange(null);
    setCurrentTranscript('');
    setCurrentResponse('');
    setTextVisible(false);
  };

  const handlePullUp = (e) => {
    e.stopPropagation();
    setShowHistory(true);
  };

  const handleCloseHistory = () => setShowHistory(false);

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
      <div className={`connection-dot ${isConnected ? 'connected' : ''}`} />

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
    </div>
  );
}

export default App;
