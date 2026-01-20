import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ReadyState } from 'react-use-websocket';

/**
 * Default audio configuration for microphone capture.
 */
const DEFAULT_AUDIO_CONFIG = {
    targetSampleRate: 16000,
    processorBufferSize: 4096,
    maxPendingBuffers: 100,
    useAudioWorklet: true,
    resampleToTarget: true,
    includeSampleRate: false,
};

const WORKLET_PROCESSOR_NAME = 'kiosk-audio-capture';
const WORKLET_MODULE_URL = new URL('../voice/audioCaptureWorklet.js', import.meta.url);

/**
 * Resample Float32Array from one sample rate to another using linear interpolation.
 */
const resampleFloat32 = (input, fromRate, toRate) => {
    if (!input || input.length === 0) return input;
    if (!fromRate || !toRate || fromRate === toRate) return input;
    const ratio = fromRate / toRate;
    const outputLength = Math.max(1, Math.round(input.length / ratio));
    const output = new Float32Array(outputLength);
    for (let i = 0; i < outputLength; i++) {
        const position = i * ratio;
        const left = Math.floor(position);
        const right = Math.min(left + 1, input.length - 1);
        const weight = position - left;
        output[i] = input[left] + (input[right] - input[left]) * weight;
    }
    return output;
};

/**
 * Convert Float32Array to base64-encoded 16-bit PCM.
 */
const float32ToBase64 = (float32) => {
    const int16 = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
        int16[i] = Math.max(-32768, Math.min(32767, Math.floor(float32[i] * 32768)));
    }
    return btoa(String.fromCharCode(...new Uint8Array(int16.buffer)));
};

/**
 * Custom hook for browser-based audio capture with proper state management.
 *
 * Key features:
 * - Buffers audio until STT session is ready (prevents lost audio)
 * - Uses AudioWorklet for low-latency capture when available
 * - Falls back to ScriptProcessor for older browsers
 * - Proper cleanup of all audio resources
 *
 * State machine:
 * 1. initMic() - Request mic permissions and set up audio pipeline
 * 2. Backend sends 'stt_session_ready' -> handleSessionReady() flushes buffered audio
 * 3. Audio streams to backend while session is active
 * 4. releaseMic() - Stop audio capture and cleanup
 */
export default function useAudioCapture(sendMessage, readyState, options = {}) {
    const [error, setError] = useState(null);
    const [isCapturing, setIsCapturing] = useState(false);

    const audioConfig = useMemo(() => ({
        ...DEFAULT_AUDIO_CONFIG,
        ...options,
    }), [options]);

    // Audio processing refs
    const audioContextRef = useRef(null);
    const processorRef = useRef(null);
    const streamRef = useRef(null);
    const inputSampleRateRef = useRef(audioConfig.targetSampleRate);

    // Session management refs
    const sessionReadyRef = useRef(false);
    const pendingBuffersRef = useRef([]);
    const readyStateRef = useRef(readyState);

    // Keep readyState ref current
    useEffect(() => {
        readyStateRef.current = readyState;
    }, [readyState]);

    /**
     * Process a single audio frame - resample if needed and send to backend.
     * Buffers audio until the STT session is ready.
     */
    const processAudioFrame = useCallback((float32) => {
        if (!float32 || float32.length === 0) return;

        const inputSampleRate = inputSampleRateRef.current;
        const targetSampleRate = audioConfig.targetSampleRate;
        const shouldResample = audioConfig.resampleToTarget
            && inputSampleRate
            && targetSampleRate
            && inputSampleRate !== targetSampleRate;

        const samples = shouldResample
            ? resampleFloat32(float32, inputSampleRate, targetSampleRate)
            : float32;

        const b64 = float32ToBase64(samples);
        const payload = { audio: b64 };

        if (audioConfig.includeSampleRate) {
            payload.sample_rate = shouldResample ? targetSampleRate : inputSampleRate;
        }

        // Only send if session is ready, otherwise buffer
        if (sessionReadyRef.current && readyStateRef.current === ReadyState.OPEN) {
            sendMessage(JSON.stringify({ type: 'audio_chunk', data: payload }));
        } else {
            pendingBuffersRef.current.push(payload);
            // Limit buffer size to prevent memory issues
            if (pendingBuffersRef.current.length > audioConfig.maxPendingBuffers) {
                pendingBuffersRef.current.shift();
            }
        }
    }, [audioConfig, sendMessage]);

    /**
     * Release all microphone resources and reset state.
     * Safe to call multiple times.
     */
    const releaseMic = useCallback(() => {
        console.log('🎤 releaseMic called');
        sessionReadyRef.current = false;
        pendingBuffersRef.current = [];
        setIsCapturing(false);

        // Disconnect processor
        if (processorRef.current) {
            if (processorRef.current.port) {
                processorRef.current.port.onmessage = null;
            }
            try {
                processorRef.current.disconnect();
            } catch {
                // Already disconnected
            }
            processorRef.current = null;
        }

        // Close audio context
        if (audioContextRef.current) {
            try {
                audioContextRef.current.close();
            } catch {
                // Already closed
            }
            audioContextRef.current = null;
        }

        // Stop all media tracks
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(t => {
                try {
                    t.stop();
                } catch {
                    // Track already stopped
                }
            });
            streamRef.current = null;
        }
    }, []);

    /**
     * Initialize microphone and set up audio capture pipeline.
     * Returns true if successful, false otherwise.
     *
     * Note: This only sets up the capture - audio won't be sent until
     * handleSessionReady() is called after backend confirms STT session.
     */
    const initMic = useCallback(async () => {
        console.log('🎤 initMic called');
        setError(null);

        // Check if we already have an active capture
        if (streamRef.current && audioContextRef.current) {
            const hasLiveTrack = streamRef.current
                .getTracks()
                .some(track => track.readyState === 'live');
            const audioContext = audioContextRef.current;

            // Resume suspended context
            if (audioContext.state === 'suspended') {
                try {
                    await audioContext.resume();
                } catch (err) {
                    console.warn('🎤 Failed to resume audio context:', err);
                }
            }

            // Already have active capture
            if (audioContext.state !== 'closed' && hasLiveTrack) {
                console.log('🎤 Mic already initialized');
                setIsCapturing(true);
                return true;
            }

            // Resources are stale, clean up and reinitialize
            releaseMic();
        }

        try {
            // Request microphone access
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: audioConfig.targetSampleRate,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                },
                video: false,
            });

            // Create audio context
            const audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: audioConfig.targetSampleRate,
            });

            const source = audioContext.createMediaStreamSource(stream);
            inputSampleRateRef.current = audioContext.sampleRate;

            let processor = null;

            // Try AudioWorklet first (modern, low-latency)
            if (audioConfig.useAudioWorklet && audioContext.audioWorklet) {
                try {
                    await audioContext.audioWorklet.addModule(WORKLET_MODULE_URL);
                    const workletNode = new AudioWorkletNode(audioContext, WORKLET_PROCESSOR_NAME);
                    workletNode.port.onmessage = (event) => {
                        const data = event.data;
                        const samples = data && data.samples ? data.samples : data;
                        if (samples instanceof Float32Array) {
                            processAudioFrame(samples);
                        } else if (samples instanceof ArrayBuffer) {
                            processAudioFrame(new Float32Array(samples));
                        }
                    };
                    processor = workletNode;
                    console.log('🎤 Using AudioWorklet for capture');
                } catch (err) {
                    console.warn('🎤 AudioWorklet unavailable, falling back to ScriptProcessor:', err);
                }
            }

            // Fallback to ScriptProcessor (deprecated but widely supported)
            if (!processor) {
                const createProcessor = audioContext.createScriptProcessor
                    || audioContext.createJavaScriptNode;
                if (!createProcessor) {
                    throw new Error('ScriptProcessor not supported');
                }
                const scriptNode = createProcessor.call(
                    audioContext,
                    audioConfig.processorBufferSize,
                    1, // input channels
                    1, // output channels
                );
                scriptNode.onaudioprocess = (e) => {
                    processAudioFrame(e.inputBuffer.getChannelData(0));
                };
                processor = scriptNode;
                console.log('🎤 Using ScriptProcessor for capture');
            }

            // Connect the audio graph
            source.connect(processor);
            processor.connect(audioContext.destination);

            // Store refs
            streamRef.current = stream;
            audioContextRef.current = audioContext;
            processorRef.current = processor;

            setIsCapturing(true);
            console.log('🎤 Mic initialized successfully');
            return true;

        } catch (err) {
            console.error('🎤 Mic init failed:', err);

            if (err.name === 'NotAllowedError') {
                if (!window.isSecureContext && window.location.protocol !== 'https:') {
                    setError('HTTPS required for mic on mobile');
                } else {
                    setError('Microphone permission denied');
                }
            } else if (err.name === 'NotFoundError') {
                setError('No microphone found');
            } else if (err.name === 'NotSupportedError' || err.name === 'SecurityError') {
                setError('HTTPS required for mic access');
            } else {
                setError(`Mic error: ${err.name || err.message || 'unknown'}`);
            }
            return false;
        }
    }, [audioConfig, processAudioFrame, releaseMic]);

    /**
     * Called when backend signals STT session is ready.
     * Flushes any buffered audio and enables direct streaming.
     */
    const handleSessionReady = useCallback(() => {
        console.log('🎤 Session ready, flushing', pendingBuffersRef.current.length, 'pending buffers');
        sessionReadyRef.current = true;

        // Flush all pending buffers
        while (pendingBuffersRef.current.length > 0 && readyStateRef.current === ReadyState.OPEN) {
            const payload = pendingBuffersRef.current.shift();
            sendMessage(JSON.stringify({ type: 'audio_chunk', data: payload }));
        }
    }, [sendMessage]);

    /**
     * Pause audio capture (keeps mic open but stops sending).
     */
    const pauseCapture = useCallback(() => {
        if (processorRef.current?.port) {
            processorRef.current.port.postMessage({ type: 'pause', value: true });
        }
    }, []);

    /**
     * Resume audio capture after pause.
     */
    const resumeCapture = useCallback(() => {
        if (processorRef.current?.port) {
            processorRef.current.port.postMessage({ type: 'pause', value: false });
        }
    }, []);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            releaseMic();
        };
    }, [releaseMic]);

    return {
        isCapturing,
        error,
        initMic,
        releaseMic,
        handleSessionReady,
        pauseCapture,
        resumeCapture,
    };
}

// Named export for backwards compatibility
export { useAudioCapture };
