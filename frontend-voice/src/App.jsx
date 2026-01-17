import { useEffect, useState } from 'react';
import useWebSocket from 'react-use-websocket';
import './App.css';
import useAudioCapture from './hooks/useAudioCapture';

// Generate a unique client ID
const clientId = `voice_${crypto.randomUUID()}`;

function App() {
  const [transcription, setTranscription] = useState('');
  const [response, setResponse] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);

  // WebSocket URL - auto-detect protocol
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProtocol}//${window.location.hostname}:8000/api/voice/connect?client_id=${clientId}`;

  const { sendMessage, lastMessage, readyState } = useWebSocket(wsUrl, {
    shouldReconnect: () => true,
    reconnectInterval: 3000,
    onOpen: () => setIsConnected(true),
    onClose: () => setIsConnected(false),
  });

  // Audio capture hook - passes audio chunks directly via sendMessage
  const { startRecording, stopRecording, isRecording: hookIsRecording, error } = useAudioCapture(sendMessage, readyState);

  // Auto-listen on launch
  const [hasAutoStarted, setHasAutoStarted] = useState(false);
  useEffect(() => {
    if (readyState === 1 && !hasAutoStarted) { // 1 = OPEN
      console.log('Auto-starting microphone on launch...');
      // Simulate button press behavior
      setTranscription('');
      setResponse('');
      setIsRecording(true);
      startRecording();
      setHasAutoStarted(true);
    }
  }, [readyState, startRecording, hasAutoStarted]);

  // Handle incoming messages
  useEffect(() => {
    if (!lastMessage?.data) return;

    try {
      const msg = JSON.parse(lastMessage.data);

      // Handle User Transcription
      if (msg.type === 'transcript') {
        if (msg.is_final) {
          setTranscription(msg.text || '');
        } else {
          setTranscription(msg.text || '');
        }
      }

      // Handle Streaming Assistant Response
      else if (msg.type === 'assistant_response_start') {
        setResponse('');
      } else if (msg.type === 'assistant_response_chunk') {
        setResponse(prev => prev + (msg.text || ''));
      } else if (msg.type === 'assistant_response') {
        // Legacy/Full response
        setResponse(msg.text || '');
      }
    } catch (e) {
      console.error('Failed to parse message:', e);
    }
  }, [lastMessage]);

  // Handle mic button press
  const handleMicDown = () => {
    setTranscription('');
    setResponse('');
    setIsRecording(true);
    // startRecording is async
    startRecording();
  };

  const handleMicUp = () => {
    setIsRecording(false);
    stopRecording();
  };

  return (
    <div className="app">
      {/* Connection indicator */}
      <div className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`} />

      {/* Transcription display */}
      <div className="content">
        {error && <div className="error">{error}</div>}

        {transcription && (
          <div className="transcription">
            <span className="label">You said:</span>
            <p>{transcription}</p>
          </div>
        )}

        {response && (
          <div className="response">
            <span className="label">Assistant:</span>
            <p>{response}</p>
          </div>
        )}

        {!transcription && !response && !error && (
          <div className="placeholder">
            Hold the mic button and speak
          </div>
        )}
      </div>

      {/* Mic button */}
      <button
        className={`mic-button ${isRecording ? 'recording' : ''}`}
        onMouseDown={handleMicDown}
        onMouseUp={handleMicUp}
        onMouseLeave={handleMicUp}
        onTouchStart={handleMicDown}
        onTouchEnd={handleMicUp}
      >
        <svg viewBox="0 0 24 24" fill="currentColor" className="mic-icon">
          <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
          <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
        </svg>
        <span className="mic-label">{isRecording ? 'Listening...' : 'Hold to talk'}</span>
      </button>
    </div>
  );
}

export default App;
