import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ReadyState } from 'react-use-websocket';

const DEFAULT_AUDIO_CONFIG = {
    targetSampleRate: 16000,
    processorBufferSize: 4096,
    maxPendingBuffers: 100,
    useAudioWorklet: true,
    resampleToTarget: true,
    includeSampleRate: false,
};

const WORKLET_PROCESSOR_NAME = 'voice-audio-capture';
const WORKLET_MODULE_URL = new URL('../voice/audioCaptureWorklet.js', import.meta.url);

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

const float32ToBase64 = (float32) => {
    const int16 = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
        int16[i] = Math.max(-32768, Math.min(32767, Math.floor(float32[i] * 32768)));
    }
    return btoa(String.fromCharCode(...new Uint8Array(int16.buffer)));
};

export default function useAudioCapture(sendMessage, readyState, options = {}) {
    const [error, setError] = useState(null);

    const audioConfig = useMemo(() => ({
        ...DEFAULT_AUDIO_CONFIG,
        ...options,
    }), [options]);

    const audioContextRef = useRef(null);
    const processorRef = useRef(null);
    const streamRef = useRef(null);
    const inputSampleRateRef = useRef(audioConfig.targetSampleRate);
    const sessionReadyRef = useRef(false);
    const pendingBuffersRef = useRef([]);
    const readyStateRef = useRef(readyState);

    useEffect(() => {
        readyStateRef.current = readyState;
    }, [readyState]);

    // Release microphone completely
    const releaseMic = useCallback(() => {
        console.log('🎤 releaseMic called');
        sessionReadyRef.current = false;
        pendingBuffersRef.current = [];

        if (processorRef.current) {
            if (processorRef.current.port) {
                processorRef.current.port.onmessage = null;
            }
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

        if (sessionReadyRef.current && readyStateRef.current === ReadyState.OPEN) {
            sendMessage(JSON.stringify({ type: 'audio_chunk', data: payload }));
        } else {
            pendingBuffersRef.current.push(payload);
            if (pendingBuffersRef.current.length > audioConfig.maxPendingBuffers) {
                pendingBuffersRef.current.shift();
            }
        }
    }, [audioConfig, sendMessage]);

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
                    sampleRate: audioConfig.targetSampleRate,
                    echoCancellation: true,
                    noiseSuppression: true,
                },
                video: false,
            });

            const audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: audioConfig.targetSampleRate,
            });
            const source = audioContext.createMediaStreamSource(stream);
            let processor;
            inputSampleRateRef.current = audioContext.sampleRate;

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
                } catch (err) {
                    console.warn('🎤 AudioWorklet unavailable, falling back to ScriptProcessor:', err);
                }
            }

            if (!processor) {
                const createProcessor = audioContext.createScriptProcessor
                    || audioContext.createJavaScriptNode;
                if (!createProcessor) {
                    throw new Error('ScriptProcessor not supported');
                }
                const scriptNode = createProcessor.call(
                    audioContext,
                    audioConfig.processorBufferSize,
                    1,
                    1,
                );
                scriptNode.onaudioprocess = (e) => {
                    processAudioFrame(e.inputBuffer.getChannelData(0));
                };
                processor = scriptNode;
            }

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
    }, [audioConfig, processAudioFrame, releaseMic]);

    // Backend signals STT session is ready
    const handleSessionReady = useCallback(() => {
        console.log('🎤 Session ready, flushing', pendingBuffersRef.current.length, 'pending buffers');
        sessionReadyRef.current = true;

        // Flush pending buffers
        while (pendingBuffersRef.current.length > 0 && readyStateRef.current === ReadyState.OPEN) {
            const payload = pendingBuffersRef.current.shift();
            sendMessage(JSON.stringify({ type: 'audio_chunk', data: payload }));
        }
    }, [sendMessage]);

    return {
        error,
        initMic,
        releaseMic,
        handleSessionReady,
    };
}
