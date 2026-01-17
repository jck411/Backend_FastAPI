import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useMemo, useRef, useState } from 'react';
import useWebSocket, { ReadyState } from 'react-use-websocket';
import AlarmOverlay from './components/AlarmOverlay';
import CalendarScreen from './components/CalendarScreen';
import Clock from './components/Clock';
import TranscriptionScreen from './components/TranscriptionScreen';
import { useConfig } from './context/ConfigContext';

/**
 * Generate a unique client ID for this frontend instance.
 * Uses crypto.randomUUID() with a fallback for older browsers.
 */
function generateClientId() {
    const uuid = typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    return `kiosk_${uuid}`;
}

export default function App() {
    // 0 = Clock, 1 = Chat, 2 = Calendar
    const [currentScreen, setCurrentScreen] = useState(0);
    const SCREEN_COUNT = 3;

    // Get config from context (includes display timezone, idle delay, etc.)
    const { idleReturnDelayMs } = useConfig();

    // Generate a unique client ID for this frontend instance (stable across re-renders)
    const clientId = useMemo(() => generateClientId(), []);

    // WebSocket Connection - connects to backend with unique client ID
    const wsUrl = `ws://${window.location.hostname}:8000/api/voice/connect?client_id=${clientId}`;

    const [messages, setMessages] = useState([]);
    const [liveTranscript, setLiveTranscript] = useState("");
    const [agentState, setAgentState] = useState("IDLE");
    const [toolStatus, setToolStatus] = useState(null);  // { name: string, status: 'started' | 'finished' | 'error' }
    const [activeAlarm, setActiveAlarm] = useState(null); // Currently firing alarm
    const messagesEndRef = useRef(null);

    // Web Audio API for streaming TTS playback
    // Using refs to persist across re-renders without triggering updates
    const audioContextRef = useRef(null);
    const nextPlayTimeRef = useRef(0);
    const ttsSampleRateRef = useRef(24000); // Default to 24kHz (OpenAI default)
    const isPlayingRef = useRef(false);
    const hasStartedRef = useRef(false);
    const scheduledSourcesRef = useRef([]); // Track scheduled audio sources for cancellation

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

    /**
     * Initialize or get the AudioContext.
     * Must be called after user interaction (e.g., on first audio chunk).
     */
    const getAudioContext = () => {
        if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
            audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: ttsSampleRateRef.current
            });
            console.log(`Created AudioContext with sample rate: ${ttsSampleRateRef.current}`);
        }
        // Resume if suspended (required after user interaction in some browsers)
        if (audioContextRef.current.state === 'suspended') {
            audioContextRef.current.resume();
        }
        return audioContextRef.current;
    };

    /**
     * Play a PCM audio chunk immediately using Web Audio API.
     * Schedules the audio buffer for gapless playback.
     */
    const playAudioChunk = (base64Audio) => {
        try {
            const ctx = getAudioContext();

            // Decode base64 to binary
            const binaryString = atob(base64Audio);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            // Convert 16-bit PCM to Float32 for Web Audio API
            const samples = new Int16Array(bytes.buffer);
            const floatSamples = new Float32Array(samples.length);
            for (let i = 0; i < samples.length; i++) {
                floatSamples[i] = samples[i] / 32768.0; // Normalize to [-1, 1]
            }

            // Create audio buffer
            const audioBuffer = ctx.createBuffer(1, floatSamples.length, ttsSampleRateRef.current);
            audioBuffer.getChannelData(0).set(floatSamples);

            // Create source node
            const source = ctx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(ctx.destination);

            // Calculate when to play this chunk (gapless scheduling)
            const currentTime = ctx.currentTime;
            const startTime = Math.max(nextPlayTimeRef.current, currentTime);

            // Schedule playback
            source.start(startTime);
            scheduledSourcesRef.current.push(source);

            // Update next play time for gapless playback
            nextPlayTimeRef.current = startTime + audioBuffer.duration;

            // Send playback start event on first chunk
            if (!hasStartedRef.current) {
                hasStartedRef.current = true;
                isPlayingRef.current = true;
                console.log("🎵 Audio playback started (streaming)");
                sendMessage(JSON.stringify({ type: "tts_playback_start" }));
            }
        } catch (e) {
            console.error("Failed to play audio chunk:", e);
        }
    };

    /**
     * Stop all audio playback immediately (for barge-in).
     * Stops all scheduled sources and resets state.
     */
    const stopAudio = () => {
        console.log("🛑 Stopping TTS audio (barge-in)");

        // Stop all scheduled audio sources
        for (const source of scheduledSourcesRef.current) {
            try {
                source.stop();
            } catch (e) {
                // Source may have already finished
            }
        }
        scheduledSourcesRef.current = [];

        // Close and recreate audio context for clean slate
        if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
            audioContextRef.current.close();
            audioContextRef.current = null;
        }

        // Reset playback state
        nextPlayTimeRef.current = 0;

        // Only send end event if we were playing
        if (isPlayingRef.current || hasStartedRef.current) {
            sendMessage(JSON.stringify({ type: "tts_playback_end" }));
            isPlayingRef.current = false;
            hasStartedRef.current = false;
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
                } else if (data.type === 'assistant_response') {
                    // Legacy: full response at once (backward compatibility)
                    console.log('Received assistant_response:', data.text);
                    setMessages(prev => [...prev, { role: 'assistant', text: data.text }]);
                } else if (data.type === 'interrupt_tts') {
                    // Barge-in: stop TTS immediately
                    console.log('🛑 Received interrupt_tts - stopping audio playback');
                    stopAudio();
                } else if (data.type === 'tts_audio_start') {
                    // Start of TTS audio stream - reset state and store sample rate
                    console.log('🎵 TTS stream starting, sample_rate:', data.sample_rate);

                    // Reset state for new audio stream
                    nextPlayTimeRef.current = 0;
                    hasStartedRef.current = false;
                    isPlayingRef.current = false;
                    scheduledSourcesRef.current = [];

                    // Store sample rate for AudioContext creation
                    ttsSampleRateRef.current = data.sample_rate || 24000;

                    // Close existing context if sample rate changed
                    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
                        audioContextRef.current.close();
                        audioContextRef.current = null;
                    }
                } else if (data.type === 'tts_audio_chunk') {
                    // Play audio chunk IMMEDIATELY using Web Audio API
                    playAudioChunk(data.data);
                } else if (data.type === 'tts_audio_end') {
                    // Audio stream complete - send playback end after all scheduled audio finishes
                    console.log('TTS stream complete');

                    // Calculate when all audio will finish
                    if (audioContextRef.current && hasStartedRef.current) {
                        const timeUntilDone = Math.max(0, nextPlayTimeRef.current - audioContextRef.current.currentTime);
                        console.log(`All audio scheduled, will complete in ${(timeUntilDone * 1000).toFixed(0)}ms`);

                        // Send playback end event after all audio finishes
                        setTimeout(() => {
                            console.log("Audio playback finished");
                            sendMessage(JSON.stringify({ type: "tts_playback_end" }));
                            isPlayingRef.current = false;
                            hasStartedRef.current = false;
                            scheduledSourcesRef.current = [];
                        }, timeUntilDone * 1000 + 100); // +100ms buffer
                    }
                } else if (data.type === 'tts_audio_cancelled') {
                    // TTS was cancelled on backend - clean up
                    console.log('TTS cancelled by backend');
                    stopAudio();
                } else if (data.type === 'tts_audio') {
                    // Legacy: single audio message (backward compatibility)
                    // Play it as a single chunk
                    console.log('Received TTS audio (legacy), playing immediately');
                    playAudioChunk(data.data);
                } else if (data.type === 'state') {
                    setAgentState(data.state);

                    if (data.state === 'LISTENING' || data.state === 'THINKING' || data.state === 'SPEAKING') {
                        setCurrentScreen(1); // Auto-jump to chat screen
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
                } else if (data.type === 'alarm_trigger') {
                    // Alarm is firing!
                    console.log('🔔 Alarm trigger received:', data);
                    setActiveAlarm({
                        alarm_id: data.alarm_id,
                        label: data.label,
                        alarm_time: data.alarm_time
                    });
                } else if (data.type === 'alarm_acknowledged') {
                    // Alarm was acknowledged (confirmation from backend)
                    console.log('✓ Alarm acknowledged:', data.alarm_id);
                    if (activeAlarm && activeAlarm.alarm_id === data.alarm_id) {
                        setActiveAlarm(null);
                    }
                } else if (data.type === 'alarm_snoozed') {
                    // Alarm was snoozed (confirmation from backend)
                    console.log('💤 Alarm snoozed:', data.original_alarm_id, '-> new:', data.new_alarm?.alarm_id);
                    if (activeAlarm && activeAlarm.alarm_id === data.original_alarm_id) {
                        setActiveAlarm(null);
                    }
                }
            } catch (e) {
                console.error("Failed to parse WS message", e);
            }
        }
    }, [lastMessage, activeAlarm]);

    // Idle Timeout Logic - Return to clock after delay
    useEffect(() => {
        if (agentState === 'IDLE') {
            const timer = setTimeout(() => {
                setCurrentScreen(0);
                setMessages([]);
            }, idleReturnDelayMs);

            // Cleanup: cancel timer if state changes before delay completes
            return () => clearTimeout(timer);
        }
    }, [agentState, idleReturnDelayMs]);

    const handleSwipe = (direction) => {
        setCurrentScreen((prev) => {
            if (direction > 0) {
                // Swipe right -> previous screen (wrap to last)
                return prev === 0 ? SCREEN_COUNT - 1 : prev - 1;
            } else {
                // Swipe left -> next screen (wrap to first)
                return (prev + 1) % SCREEN_COUNT;
            }
        });
    };

    /**
     * Manually activate listening mode (simulates wake word detection).
     * Sends a wakeword_detected event to the backend to start STT processing.
     */
    const handleActivateListening = () => {
        if (readyState === ReadyState.OPEN) {
            console.log('Manual activation - sending wakeword_detected');
            sendMessage(JSON.stringify({
                type: "wakeword_detected",
                confidence: 1.0,
                manual: true
            }));
        } else {
            console.warn('Cannot activate listening - WebSocket not connected');
        }
    };

    /**
     * Dismiss a firing alarm.
     */
    const handleAlarmDismiss = (alarmId) => {
        if (readyState === ReadyState.OPEN) {
            console.log('Dismissing alarm:', alarmId);
            sendMessage(JSON.stringify({
                type: "alarm_acknowledge",
                alarm_id: alarmId
            }));
            // Optimistically clear the alarm (backend will confirm)
            setActiveAlarm(null);
        }
    };

    /**
     * Snooze a firing alarm.
     */
    const handleAlarmSnooze = (alarmId, minutes = 5) => {
        if (readyState === ReadyState.OPEN) {
            console.log('Snoozing alarm:', alarmId, 'for', minutes, 'minutes');
            sendMessage(JSON.stringify({
                type: "alarm_snooze",
                alarm_id: alarmId,
                snooze_minutes: minutes
            }));
            // Optimistically clear the alarm (backend will confirm)
            setActiveAlarm(null);
        }
    };

    const screens = [
        <Clock key="clock" />,
        <TranscriptionScreen
            key="chat"
            messages={messages}
            liveTranscript={liveTranscript}
            isListening={agentState === 'LISTENING'}
            agentState={agentState}
            toolStatus={toolStatus}
            messagesEndRef={messagesEndRef}
            onActivateListening={handleActivateListening}
        />,
        <CalendarScreen key="calendar" />
    ];

    return (
        <div className="w-screen h-screen bg-black overflow-hidden relative font-sans text-white select-none">
            {/* Web Audio API is used for TTS playback - no HTML audio element needed */}

            {/* Alarm Overlay - appears on top of everything when alarm fires */}
            <AlarmOverlay
                alarm={activeAlarm}
                onDismiss={handleAlarmDismiss}
                onSnooze={handleAlarmSnooze}
                snoozeMinutes={5}
            />

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
                    dragElastic={0.3}
                    onDragEnd={(event, info) => {
                        const threshold = 30; // Lower threshold for easier swipe
                        if (info.offset.x < -threshold) {
                            handleSwipe(-1);  // Swipe left -> next screen
                        } else if (info.offset.x > threshold) {
                            handleSwipe(1); // Swipe right -> previous screen
                        }
                    }}
                >
                    {screens[currentScreen]}
                </motion.div>
            </AnimatePresence>

            {/* Tap zones for navigation - right side only (left reserved for Fully Kiosk menu) */}
            {/* Tap right edge to go forward */}
            <div
                className="absolute right-0 top-0 w-16 h-full z-40 cursor-pointer"
                onClick={() => handleSwipe(-1)}
                style={{ touchAction: 'manipulation' }}
            />
            {/* Tap left-center area to go back (avoiding left edge for Fully Kiosk) */}
            <div
                className="absolute left-20 top-0 w-16 h-full z-40 cursor-pointer"
                onClick={() => handleSwipe(1)}
                style={{ touchAction: 'manipulation' }}
            />

            {/* Page Indicators - subtle but tappable */}
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex space-x-4 z-50">
                {Array.from({ length: SCREEN_COUNT }, (_, i) => (
                    <div
                        key={i}
                        onClick={() => setCurrentScreen(i)}
                        className={`w-4 h-4 rounded-full transition-all duration-300 cursor-pointer ${i === currentScreen
                            ? 'bg-white/50'
                            : 'bg-white/15'
                            }`}
                        style={{ touchAction: 'manipulation' }}
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
