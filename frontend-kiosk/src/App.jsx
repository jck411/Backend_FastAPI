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
    const [toolStatus, setToolStatus] = useState(null);  // { name: string, status: 'started' | 'finished' | 'error' }
    const [idleReturnDelay, setIdleReturnDelay] = useState(10000); // Default 10s
    const audioRef = useRef(null);
    const messagesEndRef = useRef(null);

    // Web Audio API for streaming playback (plays chunks immediately as they arrive)
    const audioContextRef = useRef(null);
    const audioQueueRef = useRef([]);  // Queue of audio buffers waiting to play
    const isPlayingRef = useRef(false);
    const nextPlayTimeRef = useRef(0);
    const ttsSampleRateRef = useRef(24000);  // Store sample rate from backend (default to OpenAI's 24kHz)

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

    // Initialize AudioContext lazily
    const getAudioContext = () => {
        if (!audioContextRef.current) {
            audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: ttsSampleRateRef.current
            });
            nextPlayTimeRef.current = 0;
        }
        if (audioContextRef.current.state === 'suspended') {
            audioContextRef.current.resume();
        }
        return audioContextRef.current;
    };

    // Schedule audio chunk for immediate playback
    const scheduleAudioChunk = async (base64Audio) => {
        try {
            const ctx = getAudioContext();

            // Decode base64 to binary
            const binaryString = atob(base64Audio);
            const len = binaryString.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            // Create AudioBuffer from raw PCM 16-bit
            // Note: decodeAudioData expects WAV/MP3 container usually, or we manually build AudioBuffer for PCM.
            // Since backend is sending raw PCM, we must manually create AudioBuffer.
            const float32Data = new Float32Array(len / 2);
            const dataView = new DataView(bytes.buffer);

            for (let i = 0; i < len / 2; i++) {
                // Convert int16 to float32 (-1.0 to 1.0)
                const int16 = dataView.getInt16(i * 2, true); // little-endian
                float32Data[i] = int16 < 0 ? int16 / 0x8000 : int16 / 0x7FFF;
            }

            const audioBuffer = ctx.createBuffer(1, float32Data.length, ttsSampleRateRef.current);
            audioBuffer.copyToChannel(float32Data, 0);

            // Access check: Ensure nextPlayTime is at least current time to avoid drift
            // Add a tiny buffer (50ms) to first chunk to ensure smooth start if needed,
            // but for low latency we want aggressive scheduling.
            const currentTime = ctx.currentTime;

            if (nextPlayTimeRef.current < currentTime) {
                nextPlayTimeRef.current = currentTime;
            }

            const source = ctx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(ctx.destination);
            source.start(nextPlayTimeRef.current);

            // Keep track of sources to stop them if interrupted
            audioQueueRef.current.push(source);

            // Clean up source from queue when done
            source.onended = () => {
                arr_remove(audioQueueRef.current, source);
                // If queue is empty, we could signal playback end, but we usually wait for backend event
            };

            // Advance time
            nextPlayTimeRef.current += audioBuffer.duration;

        } catch (e) {
            console.error("Failed to schedule audio chunk:", e);
        }
    };

    const arr_remove = (arr, value) => {
        const index = arr.indexOf(value);
        if (index > -1) {
            arr.splice(index, 1);
        }
        return arr;
    };

    const stopAudio = () => {
        console.log("🛑 Stopping TTS audio (barge-in)");
        // Stop all scheduled sources
        if (audioQueueRef.current) {
            audioQueueRef.current.forEach(source => {
                try { source.stop(); } catch (e) { /* ignore */ }
            });
            audioQueueRef.current = [];
        }

        // Reset time
        if (audioContextRef.current) {
            nextPlayTimeRef.current = audioContextRef.current.currentTime;
        }

        // Legacy fallback
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current.currentTime = 0;
            audioRef.current.src = '';
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
                } else if (data.type === 'assistant_response_start') {
                    // Start of streaming response - add pending message
                    console.log('Streaming response starting');
                    setMessages(prev => [...prev, { role: 'assistant', text: '', pending: true }]);
                } else if (data.type === 'assistant_response_chunk') {
                    // Streaming text chunk - append to last assistant message
                    setMessages(prev => {
                        const updated = [...prev];
                        const lastIdx = updated.length - 1;
                        if (lastIdx >= 0 && updated[lastIdx]?.role === 'assistant') {
                            updated[lastIdx] = {
                                ...updated[lastIdx],
                                text: updated[lastIdx].text + data.text
                            };
                        }
                        return updated;
                    });
                } else if (data.type === 'assistant_response_end') {
                    // End of streaming - mark message as complete
                    console.log('Streaming response complete');
                    setMessages(prev => {
                        const updated = [...prev];
                        const lastIdx = updated.length - 1;
                        if (lastIdx >= 0 && updated[lastIdx]?.role === 'assistant') {
                            updated[lastIdx] = {
                                ...updated[lastIdx],
                                pending: false
                            };
                        }
                        return updated;
                    });
                } else if (data.type === 'interrupt_tts') {
                    // Barge-in: stop TTS immediately
                    console.log('🛑 Received interrupt_tts - stopping audio playback');
                    stopAudio();
                } else if (data.type === 'tts_audio_start') {
                    // Start of chunked TTS audio
                    console.log('TTS audio stream starting:', data.sample_rate, 'Hz sample rate');
                    stopAudio(); // Clear previous
                    if (data.sample_rate) {
                        ttsSampleRateRef.current = data.sample_rate;
                    }
                    // Initialize context ensures it's ready
                    getAudioContext();

                } else if (data.type === 'tts_audio_chunk') {
                    // Play chunk immediately
                    if (data.data) {
                        scheduleAudioChunk(data.data);
                    }
                } else if (data.type === 'tts_audio_end') {
                    console.log('TTS audio stream complete signal received');
                } else if (data.type === 'tts_audio') {
                    // Legacy: single audio message
                    if (data.data) {
                        scheduleAudioChunk(data.data);
                    }
                } else if (data.type === 'state') {
                    setAgentState(data.state);

                    if (data.state === 'LISTENING' || data.state === 'THINKING' || data.state === 'SPEAKING') {
                        setCurrentScreen(2); // Auto-jump to transcription screen
                        // Do NOT clear messages
                    }

                    // Clear tool status when transitioning to IDLE
                    if (data.state === 'IDLE') {
                        setToolStatus(null);
                    }
                } else if (data.type === 'tool_status') {
                    // Handle tool status updates
                    console.log('Tool status:', data.status, data.name);
                    setToolStatus({ name: data.name, status: data.status });

                    // Auto-clear after tool finishes (with small delay for visibility)
                    if (data.status === 'finished' || data.status === 'error') {
                        setTimeout(() => setToolStatus(null), 2000);
                    }
                }
            } catch (e) {
                console.error("Failed to parse WS message", e);
            }
        }
    }, [lastMessage]);

    // Idle Timeout Logic - Return to clock after delay
    useEffect(() => {
        if (agentState === 'IDLE') {
            const timer = setTimeout(() => {
                setCurrentScreen(0);
                setMessages([]);
            }, idleReturnDelay);

            // Cleanup: cancel timer if state changes before delay completes
            return () => clearTimeout(timer);
        }
    }, [agentState, idleReturnDelay]);

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
            toolStatus={toolStatus}
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
