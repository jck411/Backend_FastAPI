import { useCallback, useEffect, useRef, useState } from 'react';
import { ReadyState } from 'react-use-websocket';

// Version marker
console.log('🔧 useAudioCapture v3 loaded');

export default function useAudioCapture(sendMessage, readyState) {
    const [error, setError] = useState(null);

    const audioContextRef = useRef(null);
    const processorRef = useRef(null);
    const streamRef = useRef(null);
    const sessionReadyRef = useRef(false);
    const pendingBuffersRef = useRef([]);
    const pausedRef = useRef(false);
    const readyStateRef = useRef(readyState);

    useEffect(() => {
        readyStateRef.current = readyState;
    }, [readyState]);

    // Release microphone completely
    const releaseMic = useCallback(() => {
        console.log('🎤 releaseMic called');
        sessionReadyRef.current = false;
        pausedRef.current = false;
        pendingBuffersRef.current = [];

        if (processorRef.current) {
            processorRef.current.disconnect();
            processorRef.current = null;
        }
        if (audioContextRef.current) {
            audioContextRef.current.close();
            audioContextRef.current = null;
        }
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(t => t.stop());
            streamRef.current = null;
        }
    }, []);

    // Initialize microphone - just get audio context and stream ready
    const initMic = useCallback(async () => {
        console.log('🎤 initMic called');
        setError(null);

        // Already have mic access?
        if (streamRef.current && audioContextRef.current) {
            const hasLiveTrack = streamRef.current
                .getTracks()
                .some(track => track.readyState === 'live');
            const audioContext = audioContextRef.current;

            if (audioContext.state === 'suspended') {
                try {
                    await audioContext.resume();
                } catch (err) {
                    console.warn('🎤 Failed to resume audio context:', err);
                }
            }

            if (audioContext.state !== 'closed' && hasLiveTrack) {
                console.log('🎤 Mic already initialized');
                return true;
            }

            // Something got torn down, reset and re-init.
            releaseMic();
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: 16000,
                    echoCancellation: true,
                    noiseSuppression: true,
                },
                video: false,
            });

            const audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
            const source = audioContext.createMediaStreamSource(stream);
            const processor = audioContext.createScriptProcessor(4096, 1, 1);

            processor.onaudioprocess = (e) => {
                const float32 = e.inputBuffer.getChannelData(0);
                const int16 = new Int16Array(float32.length);
                for (let i = 0; i < float32.length; i++) {
                    int16[i] = Math.max(-32768, Math.min(32767, Math.floor(float32[i] * 32768)));
                }
                const b64 = btoa(String.fromCharCode(...new Uint8Array(int16.buffer)));

                if (pausedRef.current) {
                    return;
                }

                if (sessionReadyRef.current && readyStateRef.current === ReadyState.OPEN) {
                    sendMessage(JSON.stringify({ type: 'audio_chunk', data: { audio: b64 } }));
                } else {
                    pendingBuffersRef.current.push(b64);
                    if (pendingBuffersRef.current.length > 100) pendingBuffersRef.current.shift();
                }
            };

            source.connect(processor);
            processor.connect(audioContext.destination);

            streamRef.current = stream;
            audioContextRef.current = audioContext;
            processorRef.current = processor;

            console.log('🎤 Mic initialized successfully');
            return true;
        } catch (err) {
            console.error('🎤 Mic init failed:', err);
            setError('Microphone access denied');
            return false;
        }
    }, [sendMessage, releaseMic]);

    // Start a NEW conversation (clears history on backend)
    const startNewConversation = useCallback(() => {
        console.log('🎤 startNewConversation called');
        console.trace('🎤 startNewConversation stack trace');

        if (readyStateRef.current !== ReadyState.OPEN) {
            console.log('🎤 WebSocket not ready, skipping');
            return;
        }

        sessionReadyRef.current = false;
        pausedRef.current = false;
        pendingBuffersRef.current = [];

        // This tells backend to clear history and start fresh STT session
        sendMessage(JSON.stringify({ type: 'wakeword_detected', confidence: 1.0 }));
    }, [sendMessage]);

    // Resume listening (keeps history on backend)
    const resumeListening = useCallback(() => {
        console.log('🎤 resumeListening called');

        if (readyStateRef.current !== ReadyState.OPEN) {
            console.log('🎤 WebSocket not ready, skipping');
            return;
        }

        pausedRef.current = false;
        sessionReadyRef.current = false;

        // Resume existing session without clearing history
        sendMessage(JSON.stringify({ type: 'resume_listening' }));
    }, [sendMessage]);

    // Pause listening (keeps session alive on backend with KeepAlive)
    const pauseListening = useCallback(() => {
        console.log('🎤 pauseListening called');

        if (readyStateRef.current !== ReadyState.OPEN) {
            console.log('🎤 WebSocket not ready, skipping');
            return;
        }

        pausedRef.current = true;
        sessionReadyRef.current = false;
        pendingBuffersRef.current = [];
        sendMessage(JSON.stringify({ type: 'pause_listening' }));
    }, [sendMessage]);

    // Backend signals STT session is ready
    const handleSessionReady = useCallback(() => {
        if (pausedRef.current) {
            console.log('🎤 Session ready while paused, waiting for resume');
            return;
        }

        console.log('🎤 Session ready, flushing', pendingBuffersRef.current.length, 'pending buffers');
        sessionReadyRef.current = true;

        // Flush pending buffers
        while (pendingBuffersRef.current.length > 0 && readyStateRef.current === ReadyState.OPEN) {
            const b64 = pendingBuffersRef.current.shift();
            sendMessage(JSON.stringify({ type: 'audio_chunk', data: { audio: b64 } }));
        }
    }, [sendMessage]);

    return {
        error,
        initMic,
        releaseMic,
        startNewConversation,
        resumeListening,
        pauseListening,
        handleSessionReady,
    };
}
