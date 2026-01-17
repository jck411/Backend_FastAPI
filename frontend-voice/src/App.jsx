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

  // Handle touch/click interaction
  const handleInteractionStart = (e) => {
    e.preventDefault();
    setTranscription('');
    setResponse('');
    setIsRecording(true);
    startRecording();
  };

  const handleInteractionEnd = (e) => {
    e.preventDefault();
    setIsRecording(false);
    stopRecording();
  };

  return (
    <div className="app">
      {/* Connection status pill */}
      <div className={`status-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
        {isConnected ? 'Connected' : 'Connecting...'}
      </div>

      {/* Main interaction area - tap/hold to speak */}
      <div
        className="interaction-area"
        onMouseDown={handleInteractionStart}
        onMouseUp={handleInteractionEnd}
        onMouseLeave={handleInteractionEnd}
        onTouchStart={handleInteractionStart}
        onTouchEnd={handleInteractionEnd}
      >
        <div className="orb-container">
          <div className={`orb ${isRecording ? 'recording' : 'idle'}`} />
          <div className="ripple-ring" />
          <div className="ripple-ring" />
          <div className="ripple-ring" />
        </div>

        <div className={`status-text ${isRecording ? 'active' : ''}`}>
          {isRecording ? 'Listening...' : 'Hold to speak'}
        </div>
      </div>

      {/* Messages display */}
      <div className="content">
        {error && <div className="error">{error}</div>}

        {transcription && (
          <div className="message-card user">
            <div className="message-label">You</div>
            <p className="message-text">{transcription}</p>
          </div>
        )}

        {response && (
          <div className="message-card assistant">
            <div className="message-label">Assistant</div>
            <p className="message-text">{response}</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
