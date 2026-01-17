import { useCallback, useRef, useState } from 'react';
import { ReadyState } from 'react-use-websocket';

/**
 * Custom hook for browser-based audio capture.
 * Uses Web Audio API to capture microphone audio and stream it via WebSocket.
 *
 * Audio format: 16-bit PCM, 16kHz, mono (matches backend STT expectations)
 */
export function useAudioCapture(sendMessage, readyState) {
    const [isRecording, setIsRecording] = useState(false);
    const [error, setError] = useState(null);

    // Refs for audio processing
    const mediaStreamRef = useRef(null);
    const audioContextRef = useRef(null);
    const workletNodeRef = useRef(null);
    const scriptProcessorRef = useRef(null); // Fallback for older browsers

    const SAMPLE_RATE = 16000;
    const CHUNK_DURATION_MS = 100; // Send audio every 100ms

    /**
     * Convert Float32Array to Int16 PCM and encode as base64
     */
    const float32ToBase64PCM = useCallback((float32Array) => {
        const int16Array = new Int16Array(float32Array.length);
        for (let i = 0; i < float32Array.length; i++) {
            // Clamp to [-1, 1] and convert to 16-bit
            const s = Math.max(-1, Math.min(1, float32Array[i]));
            int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        // Convert to base64
        const uint8Array = new Uint8Array(int16Array.buffer);
        let binary = '';
        for (let i = 0; i < uint8Array.length; i++) {
            binary += String.fromCharCode(uint8Array[i]);
        }
        return btoa(binary);
    }, []);

    /**
     * Send audio chunk via WebSocket
     */
    const sendAudioChunk = useCallback((audioData) => {
        if (readyState !== ReadyState.OPEN) return;

        const base64Audio = float32ToBase64PCM(audioData);
        sendMessage(JSON.stringify({
            type: 'audio_chunk',
            data: { audio: base64Audio }
        }));
    }, [sendMessage, readyState, float32ToBase64PCM]);

    /**
     * Start recording audio from microphone
     */
    const startRecording = useCallback(async () => {
        if (isRecording) return;
        if (readyState !== ReadyState.OPEN) {
            setError('WebSocket not connected');
            return;
        }

        setError(null);

        try {
            // Request microphone access
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: SAMPLE_RATE,
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            mediaStreamRef.current = stream;

            // Create audio context
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            const audioContext = new AudioContextClass({ sampleRate: SAMPLE_RATE });
            audioContextRef.current = audioContext;

            // Resume if suspended (needed for some browsers)
            if (audioContext.state === 'suspended') {
                await audioContext.resume();
            }

            const source = audioContext.createMediaStreamSource(stream);

            // Try AudioWorklet first (modern browsers), fallback to ScriptProcessor
            try {
                // For AudioWorklet, we'd need to load a separate processor file
                // Using ScriptProcessor for simplicity and broader compatibility
                throw new Error('Use ScriptProcessor for simplicity');
            } catch {
                // Fallback: ScriptProcessor (deprecated but widely supported)
                const bufferSize = Math.floor(SAMPLE_RATE * CHUNK_DURATION_MS / 1000);
                const processor = audioContext.createScriptProcessor(
                    bufferSize > 16384 ? 16384 : bufferSize < 256 ? 256 :
                        Math.pow(2, Math.ceil(Math.log2(bufferSize))), // Must be power of 2
                    1, // Input channels
                    1  // Output channels
                );

                processor.onaudioprocess = (e) => {
                    const inputData = e.inputBuffer.getChannelData(0);
                    // Clone the data since it's reused
                    const audioData = new Float32Array(inputData);
                    sendAudioChunk(audioData);
                };

                source.connect(processor);
                processor.connect(audioContext.destination); // Required for processing
                scriptProcessorRef.current = processor;
            }

            // Send wake word event to start STT session
            sendMessage(JSON.stringify({
                type: 'wakeword_detected',
                confidence: 1.0,
                manual: true
            }));

            setIsRecording(true);
            console.log('🎤 Audio capture started');

        } catch (err) {
            console.error('Failed to start audio capture:', err);
            if (err.name === 'NotAllowedError') {
                // Check if this might be due to insecure context (HTTP on mobile)
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
                setError(`Mic error: ${err.name || 'unknown'}`);
            }
        }
    }, [isRecording, readyState, sendMessage, sendAudioChunk, SAMPLE_RATE, CHUNK_DURATION_MS]);

    /**
     * Stop recording and cleanup
     */
    const stopRecording = useCallback(() => {
        if (!isRecording) return;

        console.log('🎤 Stopping audio capture');

        // Stop script processor
        if (scriptProcessorRef.current) {
            scriptProcessorRef.current.disconnect();
            scriptProcessorRef.current = null;
        }

        // Stop worklet node
        if (workletNodeRef.current) {
            workletNodeRef.current.disconnect();
            workletNodeRef.current = null;
        }

        // Close audio context
        if (audioContextRef.current) {
            audioContextRef.current.close();
            audioContextRef.current = null;
        }

        // Stop media stream
        if (mediaStreamRef.current) {
            mediaStreamRef.current.getTracks().forEach(track => track.stop());
            mediaStreamRef.current = null;
        }

        setIsRecording(false);
    }, [isRecording]);

    return {
        isRecording,
        startRecording,
        stopRecording,
        error
    };
}

export default useAudioCapture;
