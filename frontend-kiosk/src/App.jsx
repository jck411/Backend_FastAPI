import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import useWebSocket, { ReadyState } from 'react-use-websocket';
import AlarmOverlay from './components/AlarmOverlay';
import Clock from './components/Clock';
import MicButton from './components/MicButton';
import TranscriptionOverlay from './components/TranscriptionOverlay';
import { useConfig } from './context/ConfigContext';
import useAudioCapture from './hooks/useAudioCapture';
import { buildVoiceWsUrl, createClientId, VOICE_CONFIG } from './voice/config';

// TTS buffering defaults (can be overridden by backend settings via tts_audio_start message)
const TTS_STARTUP_DELAY_SEC = VOICE_CONFIG.tts.startupDelaySec;
// Delay before resuming mic after TTS ends to avoid capturing speaker echo/reverb
const TTS_MIC_RESUME_DELAY_MS = VOICE_CONFIG.tts.micResumeDelayMs;

/**
 * Derive the UI application state from backend state and response status.
 * This ensures consistent state handling across the app.
 */
const deriveAppState = (backendState, isPlayingTts = false) => {
    if (isPlayingTts) return 'SPEAKING';
    if (backendState === 'PROCESSING' || backendState === 'SPEAKING') return 'SPEAKING';
    if (backendState === 'LISTENING') return 'LISTENING';
    return 'IDLE';
};

export default function App() {
    // Get config from context (includes display timezone, idle delay, etc.)
    const { idleReturnDelayMs } = useConfig();

    // Generate a unique client ID for this frontend instance (stable across re-renders)
    const clientId = useMemo(() => createClientId(), []);
    const wsUrl = useMemo(() => buildVoiceWsUrl(clientId), [clientId]);

    // UI State
    const [messages, setMessages] = useState([]);
    const [liveTranscript, setLiveTranscript] = useState("");
    const [backendState, setBackendState] = useState("IDLE");
    const [toolStatus, setToolStatus] = useState(null);
    const [activeAlarm, setActiveAlarm] = useState(null);
    const [showTranscription, setShowTranscription] = useState(false);
    const messagesEndRef = useRef(null);

    // Refs for state machine (to avoid stale closures)
    const backendStateRef = useRef("IDLE");
    const isPlayingTtsRef = useRef(false);

    // TTS mic lock - prevents mic from resuming until TTS playback is truly complete
    // This overrides backend state and is the authoritative signal for mic control
    const ttsMicLockedRef = useRef(false);

    // Web Audio API for streaming TTS playback
    const audioContextRef = useRef(null);
    const nextPlayTimeRef = useRef(0);
    const ttsSampleRateRef = useRef(VOICE_CONFIG.tts.defaultSampleRate);
    // Dynamic buffer settings (updated from backend via tts_audio_start message)
    const ttsInitialBufferSecRef = useRef(VOICE_CONFIG.tts.initialBufferSec);
    const ttsMaxAheadSecRef = useRef(VOICE_CONFIG.tts.maxAheadSec);
    const ttsMinChunkSecRef = useRef(VOICE_CONFIG.tts.minChunkSec);
    const hasStartedRef = useRef(false);
    const scheduledSourcesRef = useRef([]);
    const pendingChunksRef = useRef([]);
    const pendingSampleCountRef = useRef(0);
    const ttsStreamEndedRef = useRef(false);
    // Track the last scheduled audio source for onended callback
    const lastScheduledSourceRef = useRef(null);
    const ttsMicResumeTimeoutRef = useRef(null);
    const ttsPlaybackTokenRef = useRef(0);

    // WebSocket connection
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

    // Audio capture hook - use new pattern with session readiness
    const {
        isCapturing,
        error: audioError,
        initMic,
        releaseMic,
        handleSessionReady,
        pauseCapture,
        resumeCapture,
    } = useAudioCapture(sendMessage, readyState, VOICE_CONFIG.audio);

    /**
     * Update backend state and ref together.
     */
    const updateBackendState = useCallback((newState) => {
        backendStateRef.current = newState;
        setBackendState(newState);
    }, []);

    /**
     * Initialize or get the AudioContext.
     * Must be called after user interaction (e.g., on first audio chunk).
     */
    const getAudioContext = () => {
        if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
            audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: ttsSampleRateRef.current,
                latencyHint: 'playback'  // Prioritize smooth playback over low latency
            });
            console.log(`Created AudioContext with sample rate: ${ttsSampleRateRef.current}, latencyHint: playback`);
        }
        // Resume if suspended (required after user interaction in some browsers)
        if (audioContextRef.current.state === 'suspended') {
            audioContextRef.current.resume();
        }
        return audioContextRef.current;
    };

    const decodeBase64Pcm = (base64Audio) => {
        const binaryString = atob(base64Audio);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        const samples = new Int16Array(bytes.buffer);
        const floatSamples = new Float32Array(samples.length);
        for (let i = 0; i < samples.length; i++) {
            floatSamples[i] = samples[i] / 32768.0;
        }

        return floatSamples;
    };

    const consumePendingSamples = (sampleCount) => {
        const output = new Float32Array(sampleCount);
        let offset = 0;

        while (offset < sampleCount && pendingChunksRef.current.length > 0) {
            const chunk = pendingChunksRef.current[0];
            const remaining = sampleCount - offset;

            if (chunk.length <= remaining) {
                output.set(chunk, offset);
                offset += chunk.length;
                pendingChunksRef.current.shift();
            } else {
                output.set(chunk.subarray(0, remaining), offset);
                pendingChunksRef.current[0] = chunk.subarray(remaining);
                offset += remaining;
            }
        }

        pendingSampleCountRef.current = Math.max(0, pendingSampleCountRef.current - sampleCount);
        return output;
    };

    const schedulePcmSamples = (floatSamples, ctx) => {
        const audioBuffer = ctx.createBuffer(1, floatSamples.length, ttsSampleRateRef.current);
        audioBuffer.getChannelData(0).set(floatSamples);

        const source = ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(ctx.destination);

        const currentTime = ctx.currentTime;
        const startupDelay = hasStartedRef.current ? 0 : TTS_STARTUP_DELAY_SEC;
        const startTime = Math.max(nextPlayTimeRef.current, currentTime + startupDelay);

        source.start(startTime);
        scheduledSourcesRef.current.push(source);
        lastScheduledSourceRef.current = source;
        nextPlayTimeRef.current = startTime + audioBuffer.duration;

        if (!hasStartedRef.current) {
            hasStartedRef.current = true;
            isPlayingTtsRef.current = true;
            ttsMicLockedRef.current = true; // Lock mic during TTS
            console.log("🎵 Audio playback started (streaming), mic locked");
            // Pause mic capture during TTS to prevent self-transcription
            pauseCapture();
            sendMessage(JSON.stringify({ type: "tts_playback_start" }));
        }
    };

    const getOutputLatencyMs = (ctx) => {
        if (!ctx) return 0;
        const latencySeconds = typeof ctx.outputLatency === 'number'
            ? ctx.outputLatency
            : typeof ctx.baseLatency === 'number'
                ? ctx.baseLatency
                : 0;
        if (!Number.isFinite(latencySeconds)) return 0;
        return Math.max(0, Math.round(latencySeconds * 1000));
    };

    const clearTtsMicResumeTimeout = useCallback(() => {
        if (ttsMicResumeTimeoutRef.current) {
            clearTimeout(ttsMicResumeTimeoutRef.current);
            ttsMicResumeTimeoutRef.current = null;
        }
    }, []);

    const resumeCaptureIfListening = useCallback(() => {
        if (backendStateRef.current === 'LISTENING') {
            resumeCapture();
        }
    }, [resumeCapture]);

    /**
     * Set up onended callback on the last scheduled source to detect true playback completion.
     * This replaces timer-based detection for more accurate TTS completion.
     */
    const setupTtsCompletionCallback = (playbackToken) => {
        const lastSource = lastScheduledSourceRef.current;
        if (!lastSource) {
            console.warn("No last source to attach onended callback");
            return;
        }

        lastSource.onended = () => {
            if (playbackToken !== ttsPlaybackTokenRef.current) {
                return;
            }
            console.log("🔊 Last audio source ended (onended event)");
            // Clear state
            sendMessage(JSON.stringify({ type: "tts_playback_end" }));
            isPlayingTtsRef.current = false;
            hasStartedRef.current = false;
            scheduledSourcesRef.current = [];
            lastScheduledSourceRef.current = null;

            // Resume mic after delay to avoid capturing any speaker echo
            clearTtsMicResumeTimeout();
            const outputLatencyMs = getOutputLatencyMs(audioContextRef.current);
            const resumeDelayMs = Math.max(0, TTS_MIC_RESUME_DELAY_MS + outputLatencyMs);
            ttsMicResumeTimeoutRef.current = setTimeout(() => {
                if (playbackToken !== ttsPlaybackTokenRef.current) {
                    return;
                }
                console.log("🎤 Unlocking mic after TTS completion delay");
                ttsMicLockedRef.current = false;
                resumeCaptureIfListening();
            }, resumeDelayMs);
        };
    };

    const drainPendingAudio = (force = false) => {
        const pendingSamples = pendingSampleCountRef.current;
        if (!pendingSamples) {
            return;
        }

        const sampleRate = ttsSampleRateRef.current;
        const minInitialSamples = Math.floor(sampleRate * ttsInitialBufferSecRef.current);
        const minChunkSamples = Math.floor(sampleRate * ttsMinChunkSecRef.current);

        if (!hasStartedRef.current && !force && pendingSamples < minInitialSamples) {
            return;
        }

        const ctx = getAudioContext();

        while (pendingSampleCountRef.current > 0) {
            if (hasStartedRef.current) {
                const aheadSeconds = nextPlayTimeRef.current - ctx.currentTime;
                if (!force && aheadSeconds > ttsMaxAheadSecRef.current) {
                    break;
                }
            }

            const targetSamples = (ttsStreamEndedRef.current || force)
                ? pendingSampleCountRef.current
                : Math.min(pendingSampleCountRef.current, minChunkSamples);

            if (!force && targetSamples < minChunkSamples && !ttsStreamEndedRef.current) {
                break;
            }

            if (targetSamples <= 0) {
                break;
            }

            schedulePcmSamples(consumePendingSamples(targetSamples), ctx);
        }
    };

    const enqueueAudioChunk = (base64Audio, force = false) => {
        try {
            const floatSamples = decodeBase64Pcm(base64Audio);
            if (!floatSamples.length) {
                return;
            }

            pendingChunksRef.current.push(floatSamples);
            pendingSampleCountRef.current += floatSamples.length;
            drainPendingAudio(force);
        } catch (e) {
            console.error("Failed to queue audio chunk:", e);
        }
    };

    /**
     * Stop all audio playback immediately (for barge-in).
     * Stops all scheduled sources, resets state, and notifies backend.
     */
    const stopAudio = useCallback(() => {
        console.log("🛑 Stopping TTS audio (barge-in)");
        ttsPlaybackTokenRef.current += 1;
        clearTtsMicResumeTimeout();

        // Stop all scheduled audio sources
        for (const source of scheduledSourcesRef.current) {
            try {
                source.stop();
            } catch (e) {
                // Source may have already finished
            }
        }
        scheduledSourcesRef.current = [];
        lastScheduledSourceRef.current = null;
        pendingChunksRef.current = [];
        pendingSampleCountRef.current = 0;
        ttsStreamEndedRef.current = false;

        // Close and recreate audio context for clean slate
        if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
            audioContextRef.current.close();
            audioContextRef.current = null;
        }

        // Reset playback state
        nextPlayTimeRef.current = 0;
        ttsMicLockedRef.current = false; // Unlock mic on barge-in

        // Only send end event if we were playing
        if (isPlayingTtsRef.current || hasStartedRef.current) {
            sendMessage(JSON.stringify({ type: "tts_playback_end" }));
            isPlayingTtsRef.current = false;
            hasStartedRef.current = false;
        }
    }, [clearTtsMicResumeTimeout, sendMessage]);

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

                // Handle STT session ready - flush buffered audio
                if (data.type === 'stt_session_ready') {
                    console.log('🎤 STT session ready');
                    handleSessionReady();
                }

                // Handle STT session error
                if (data.type === 'stt_session_error') {
                    console.warn('STT session error:', data.error);
                }

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
                    // Barge-in: stop TTS immediately and resume mic
                    console.log('🛑 Received interrupt_tts - stopping audio playback');
                    stopAudio();
                    resumeCapture();
                } else if (data.type === 'tts_audio_start') {
                    // Start of TTS audio stream - reset state and store sample rate
                    console.log('🎵 TTS stream starting, sample_rate:', data.sample_rate);

                    // Pause mic capture during TTS to prevent self-transcription
                    pauseCapture();
                    ttsPlaybackTokenRef.current += 1;
                    clearTtsMicResumeTimeout();
                    ttsMicLockedRef.current = true;

                    // Reset state for new audio stream
                    nextPlayTimeRef.current = 0;
                    hasStartedRef.current = false;
                    isPlayingTtsRef.current = false;
                    scheduledSourcesRef.current = [];
                    pendingChunksRef.current = [];
                    pendingSampleCountRef.current = 0;
                    ttsStreamEndedRef.current = false;

                    // Store sample rate for AudioContext creation
                    ttsSampleRateRef.current = data.sample_rate || VOICE_CONFIG.tts.defaultSampleRate;

                    // Update buffer settings from backend (allows runtime tuning)
                    if (data.initial_buffer_sec !== undefined) {
                        ttsInitialBufferSecRef.current = data.initial_buffer_sec;
                    }
                    if (data.max_ahead_sec !== undefined) {
                        ttsMaxAheadSecRef.current = data.max_ahead_sec;
                    }
                    if (data.min_chunk_sec !== undefined) {
                        ttsMinChunkSecRef.current = data.min_chunk_sec;
                    }

                    // Close existing context if sample rate changed
                    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
                        audioContextRef.current.close();
                        audioContextRef.current = null;
                    }
                } else if (data.type === 'tts_audio_chunk') {
                    // Play audio chunk IMMEDIATELY using Web Audio API
                    if (data.data) {
                        enqueueAudioChunk(data.data);
                    }
                    // Check for last chunk - schedule playback end when all audio finishes
                    if (data.is_last) {
                        console.log('TTS stream complete (is_last received)');
                        ttsStreamEndedRef.current = true;
                        drainPendingAudio(true);

                        // Use onended callback on last source for accurate completion detection
                        if (lastScheduledSourceRef.current) {
                            setupTtsCompletionCallback(ttsPlaybackTokenRef.current);
                        } else {
                            // No audio was played (maybe TTS was empty or failed)
                            console.log("No audio was played, sending tts_playback_end immediately");
                            sendMessage(JSON.stringify({ type: "tts_playback_end" }));
                            isPlayingTtsRef.current = false;
                            hasStartedRef.current = false;
                            ttsMicLockedRef.current = false;
                            resumeCaptureIfListening();
                        }
                    }
                } else if (data.type === 'tts_audio_end') {
                    // Legacy: explicit end message (backward compatibility)
                    console.log('TTS stream complete (tts_audio_end)');
                    ttsStreamEndedRef.current = true;
                    drainPendingAudio(true);

                    // Use onended callback on last source for accurate completion detection
                    if (lastScheduledSourceRef.current) {
                        setupTtsCompletionCallback(ttsPlaybackTokenRef.current);
                    } else {
                        // No audio was played (maybe TTS was empty or failed)
                        console.log("No audio was played, sending tts_playback_end immediately");
                        sendMessage(JSON.stringify({ type: "tts_playback_end" }));
                        isPlayingTtsRef.current = false;
                        hasStartedRef.current = false;
                        ttsMicLockedRef.current = false;
                        resumeCaptureIfListening();
                    }
                } else if (data.type === 'tts_audio_cancelled') {
                    // TTS was cancelled on backend - clean up
                    console.log('TTS cancelled by backend');
                    stopAudio();
                    resumeCapture();
                } else if (data.type === 'tts_audio') {
                    // Legacy: single audio message (backward compatibility)
                    console.log('Received TTS audio (legacy), playing immediately');
                    pauseCapture();
                    enqueueAudioChunk(data.data, true);
                } else if (data.type === 'state') {
                    const newState = data.state;
                    const prevState = backendStateRef.current;
                    updateBackendState(newState);

                    // Show transcription overlay when active
                    if (newState === 'LISTENING' || newState === 'THINKING' || newState === 'SPEAKING') {
                        setShowTranscription(true);
                    }

                    // Handle state transitions for mic control
                    if (newState === 'LISTENING' && prevState !== 'LISTENING') {
                        // Backend ready to receive audio - resume capture if NOT locked by TTS
                        if (ttsMicLockedRef.current) {
                            console.log('Backend listening - but mic locked by TTS, will resume after playback');
                        } else {
                            console.log('Backend listening - resuming audio capture');
                            resumeCapture();
                        }
                    } else if (newState === 'IDLE') {
                        // Conversation ended - release mic
                        console.log('Backend idle - releasing microphone');
                        releaseMic();
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
    }, [lastMessage, activeAlarm, clearTtsMicResumeTimeout, handleSessionReady, pauseCapture, resumeCapture, resumeCaptureIfListening, releaseMic, stopAudio, updateBackendState, sendMessage]);

    // Idle Timeout Logic - Close transcription overlay after delay
    useEffect(() => {
        if (backendState === 'IDLE' && showTranscription) {
            const timer = setTimeout(() => {
                setShowTranscription(false);
                setMessages([]);
            }, idleReturnDelayMs);

            // Cleanup: cancel timer if state changes before delay completes
            return () => clearTimeout(timer);
        }
    }, [backendState, showTranscription, idleReturnDelayMs]);

    /**
     * Start a new voice interaction.
     * Initializes mic and sends wakeword to backend.
     */
    const handleStartListening = useCallback(async () => {
        if (readyState !== ReadyState.OPEN) {
            console.warn('Cannot start listening - WebSocket not connected');
            return;
        }

        console.log('Starting voice interaction');
        setShowTranscription(true);
        setLiveTranscript("");

        // Initialize mic first
        const micReady = await initMic();
        if (!micReady) {
            console.error('Failed to initialize microphone');
            return;
        }

        // Send wakeword to trigger backend STT session
        sendMessage(JSON.stringify({
            type: "wakeword_detected",
            confidence: 1.0,
            manual: true
        }));
    }, [readyState, initMic, sendMessage]);

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

    /**
     * Close transcription overlay and abort current process.
     */
    const handleCloseTranscription = useCallback(() => {
        console.log('Closing transcription overlay - aborting process');

        // Stop TTS audio playback
        stopAudio();

        // Release microphone
        releaseMic();

        // Clear backend session (stops LLM, TTS, etc.)
        if (readyState === ReadyState.OPEN) {
            sendMessage(JSON.stringify({ type: "clear_session" }));
        }

        // Reset UI state
        setShowTranscription(false);
        setMessages([]);
        setLiveTranscript("");
        setToolStatus(null);
    }, [stopAudio, releaseMic, readyState, sendMessage]);

    // Derive app state for UI display
    const appState = deriveAppState(backendState, isPlayingTtsRef.current);

    return (
        <div className="w-screen h-screen bg-black overflow-hidden relative font-sans text-white select-none">
            {/* Web Audio API is used for TTS playback - no HTML audio element needed */}

            {/* Main Screen: Clock with weather and photo slideshow */}
            <Clock />

            {/* Microphone Button - hidden when overlay is showing */}
            {!showTranscription && (
                <MicButton
                    isRecording={isCapturing}
                    onStart={handleStartListening}
                    onStop={releaseMic}
                    disabled={readyState !== ReadyState.OPEN || backendState === 'PROCESSING'}
                    error={audioError}
                />
            )}

            {/* Transcription Overlay - appears when mic is tapped */}
            {showTranscription && (
                <TranscriptionOverlay
                    messages={messages}
                    liveTranscript={liveTranscript}
                    isListening={backendState === 'LISTENING'}
                    agentState={appState}
                    toolStatus={toolStatus}
                    messagesEndRef={messagesEndRef}
                    onClose={handleCloseTranscription}
                />
            )}

            {/* Alarm Overlay - appears on top of everything when alarm fires */}
            <AlarmOverlay
                alarm={activeAlarm}
                onDismiss={handleAlarmDismiss}
                onSnooze={handleAlarmSnooze}
                snoozeMinutes={5}
            />

            {/* Connection Indicator */}
            <div
                className="fixed top-2 right-2 w-2 h-2 rounded-full z-50 transition-colors"
                style={{ backgroundColor: readyState === ReadyState.OPEN ? '#00ADB5' : '#FF4136' }}
            />
        </div>
    );
}
