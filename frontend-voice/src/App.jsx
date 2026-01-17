import { useEffect, useRef, useState } from 'react';
import useWebSocket from 'react-use-websocket';
import './App.css';
import useAudioCapture from './hooks/useAudioCapture';

const clientId = `voice_${crypto.randomUUID()}`;

function App() {
  const [messages, setMessages] = useState([]);
  const [currentTranscript, setCurrentTranscript] = useState('');
  const [currentResponse, setCurrentResponse] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [latestExchange, setLatestExchange] = useState(null);
  const [textVisible, setTextVisible] = useState(false);

  // Simple states: FRESH, LISTENING, PAUSED, PROCESSING, SPEAKING
  const [appState, setAppState] = useState('FRESH');
  const [isPaused, setIsPaused] = useState(false); // User explicitly paused

  const responseRef = useRef('');
  const fadeTimeoutRef = useRef(null);

  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProtocol}//${window.location.hostname}:8000/api/voice/connect?client_id=${clientId}`;

  const { sendMessage, lastMessage, readyState } = useWebSocket(wsUrl, {
    shouldReconnect: () => true,
    reconnectInterval: 3000,
    onOpen: () => setIsConnected(true),
    onClose: () => setIsConnected(false),
  });

  const { startRecording, stopRecording, isRecording, error } = useAudioCapture(sendMessage, readyState);

  // Auto-start when connected
  useEffect(() => {
    if (readyState === 1 && appState === 'FRESH') {
      setTimeout(() => {
        setAppState('LISTENING');
        startRecording();
        setTextVisible(true);
      }, 300);
    }
  }, [readyState]);

  // Fade text
  const scheduleFade = () => {
    if (fadeTimeoutRef.current) clearTimeout(fadeTimeoutRef.current);
    fadeTimeoutRef.current = setTimeout(() => setTextVisible(false), 5000);
  };

  // Handle backend messages
  useEffect(() => {
    if (!lastMessage?.data) return;

    try {
      const msg = JSON.parse(lastMessage.data);

      if (msg.type === 'state') {
        const s = msg.state;
        console.log('Backend state:', s, '| isPaused:', isPaused);

        if (s === 'LISTENING') {
          // Backend wants us to listen
          if (!isPaused) {
            setAppState('LISTENING');
            if (!isRecording) {
              startRecording();
            }
            setTextVisible(true);
          }
        } else if (s === 'PROCESSING') {
          setAppState('PROCESSING');
        } else if (s === 'SPEAKING') {
          setAppState('SPEAKING');
        } else if (s === 'IDLE') {
          if (isPaused) {
            setAppState('PAUSED');
          } else {
            // After speaking/processing, resume listening
            setAppState('LISTENING');
            if (!isRecording) {
              startRecording();
            }
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
      console.error('Failed to parse message:', e);
    }
  }, [lastMessage, isPaused, isRecording]);

  // Handle tap
  const handleTap = (e) => {
    if (showHistory) return;

    if (appState === 'LISTENING') {
      // Pause
      setIsPaused(true);
      setAppState('PAUSED');
      stopRecording();
      scheduleFade();
    } else if (appState === 'PAUSED' || appState === 'FRESH') {
      // Resume or start - need small delay to ensure cleanup is complete
      setIsPaused(false);
      setAppState('LISTENING');
      setTextVisible(true);
      // Small timeout to ensure previous recording is fully stopped
      setTimeout(() => {
        startRecording();
      }, 100);
    }
  };

  // Clear session
  const handleClear = (e) => {
    e.stopPropagation();
    setIsPaused(false);
    setAppState('FRESH');
    stopRecording();
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
