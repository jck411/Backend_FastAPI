import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useRef, useState } from 'react';
import useWebSocket, { ReadyState } from 'react-use-websocket';
import Clock from './components/Clock';
import PhotoFrame from './components/PhotoFrame';
import TranscriptionScreen from './components/TranscriptionScreen';

export default function App() {
    // 0 = Clock, 1 = Photos, 2 = Transcription
    const [currentScreen, setCurrentScreen] = useState(0);

    // WebSocket Connection - connects to backend
    const wsUrl = `ws://${window.location.hostname}:8000/api/voice/connect?client_id=frontend_gui`;

    const [messages, setMessages] = useState([]);
    const [liveTranscript, setLiveTranscript] = useState("");
    const [agentState, setAgentState] = useState("IDLE");
    const [idleReturnDelay, setIdleReturnDelay] = useState(10000); // Default 10s
    const audioRef = useRef(null);
    const messagesEndRef = useRef(null);

    // Fetch UI settings on mount
    useEffect(() => {
        const fetchSettings = async () => {
            try {
                const response = await fetch(`http://${window.location.hostname}:8000/api/kiosk/ui/settings`);
                if (response.ok) {
                    const data = await response.json();
                    setIdleReturnDelay(data.idle_return_delay_ms);
                }
            } catch (e) {
                console.error("Failed to fetch UI settings", e);
            }
        };
        fetchSettings();
    }, []);

    const {
        sendMessage,
        lastMessage,
        readyState
    } = useWebSocket(wsUrl, {
        onOpen: () => console.log('WebSocket Connected'),
        shouldReconnect: () => true,
        reconnectAttempts: 10,
        reconnectInterval: 3000,
    });

    // Play TTS audio
    const playAudio = (base64Audio) => {
        try {
            // Convert base64 to audio blob (PCM 16-bit, 16kHz mono)
            const binaryString = atob(base64Audio);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            // Create WAV header for PCM data
            const sampleRate = 16000;
            const numChannels = 1;
            const bitsPerSample = 16;
            const byteRate = sampleRate * numChannels * bitsPerSample / 8;
            const blockAlign = numChannels * bitsPerSample / 8;
            const dataSize = bytes.length;
            const fileSize = 44 + dataSize;

            const wavBuffer = new ArrayBuffer(fileSize);
            const view = new DataView(wavBuffer);

            // RIFF header
            view.setUint32(0, 0x52494646, false); // "RIFF"
            view.setUint32(4, fileSize - 8, true);
            view.setUint32(8, 0x57415645, false); // "WAVE"

            // fmt chunk
            view.setUint32(12, 0x666d7420, false); // "fmt "
            view.setUint32(16, 16, true); // chunk size
            view.setUint16(20, 1, true); // audio format (PCM)
            view.setUint16(22, numChannels, true);
            view.setUint32(24, sampleRate, true);
            view.setUint32(28, byteRate, true);
            view.setUint16(32, blockAlign, true);
            view.setUint16(34, bitsPerSample, true);

            // data chunk
            view.setUint32(36, 0x64617461, false); // "data"
            view.setUint32(40, dataSize, true);

            // Copy PCM data
            const wavBytes = new Uint8Array(wavBuffer);
            wavBytes.set(bytes, 44);

            const blob = new Blob([wavBytes], { type: 'audio/wav' });
            const url = URL.createObjectURL(blob);

            if (audioRef.current) {
                audioRef.current.src = url;
                audioRef.current.play().catch(e => console.error("Audio play failed:", e));
            }
        } catch (e) {
            console.error("Failed to play audio:", e);
        }
    };

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, liveTranscript]);

    useEffect(() => {
        if (lastMessage !== null) {
            try {
                const data = JSON.parse(lastMessage.data);
                if (data.type === 'transcript') {
                    if (data.is_final) {
                        setMessages(prev => [...prev, { role: 'user', text: data.text }]);
                        setLiveTranscript("");
                    } else {
                        setLiveTranscript(data.text);
                    }
                } else if (data.type === 'assistant_response') {
                    console.log('Received assistant_response:', data.text);
                    setMessages(prev => [...prev, { role: 'assistant', text: data.text }]);
                } else if (data.type === 'tts_audio') {
                    console.log('Received TTS audio, length:', data.data?.length);
                    playAudio(data.data);
                } else if (data.type === 'state') {
                    setAgentState(data.state);
                    if (data.state === 'LISTENING' || data.state === 'THINKING') {
                        setCurrentScreen(2); // Auto-jump to transcription screen
                        // Do NOT clear messages
                    }
                    if (data.state === 'IDLE') {
                        setTimeout(() => {
                            setCurrentScreen(0);
                            setMessages([]); // Optional: clear on idle return
                        }, idleReturnDelay);
                    }
                }
            } catch (e) {
                console.error("Failed to parse WS message", e);
            }
        }
    }, [lastMessage, idleReturnDelay]);

    const handleSwipe = (direction) => {
        if (direction > 0) {
            setCurrentScreen((prev) => (prev + 1) % 3);
        } else {
            setCurrentScreen((prev) => (prev === 0 ? 2 : prev - 1));
        }
    };

    const screens = [
        <Clock key="clock" />,
        <PhotoFrame key="photos" />,
        <TranscriptionScreen
            key="transcription"
            messages={messages}
            liveTranscript={liveTranscript}
            isListening={agentState === 'LISTENING'}
            agentState={agentState}
            messagesEndRef={messagesEndRef}
        />
    ];

    return (
        <div className="w-screen h-screen bg-black overflow-hidden relative font-sans text-white select-none">
            {/* Hidden audio element for TTS playback */}
            <audio ref={audioRef} />

            <AnimatePresence mode="popLayout" initial={false}>
                <motion.div
                    key={currentScreen}
                    className="absolute inset-0 w-full h-full"
                    initial={{ x: 300, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    exit={{ x: -300, opacity: 0 }}
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    drag="x"
                    dragConstraints={{ left: 0, right: 0 }}
                    dragElastic={0.2}
                    onDragEnd={(e, { offset }) => {
                        if (offset.x < -100) handleSwipe(1);
                        else if (offset.x > 100) handleSwipe(-1);
                    }}
                >
                    {screens[currentScreen]}
                </motion.div>
            </AnimatePresence>

            {/* Page Indicators */}
            <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex space-x-3 z-50">
                {[0, 1, 2].map((i) => (
                    <div
                        key={i}
                        className={`h-1.5 rounded-full transition-all duration-300 ${i === currentScreen ? 'bg-white w-8' : 'bg-white/40 w-1.5'
                            }`}
                    />
                ))}
            </div>

            {/* Connection Indicator */}
            <div
                className="fixed top-2 right-2 w-2 h-2 rounded-full z-50 transition-colors"
                style={{ backgroundColor: readyState === ReadyState.OPEN ? '#00ADB5' : '#FF4136' }}
            />
        </div>
    );
}
