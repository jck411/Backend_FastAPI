/**
 * AudioWorklet processor for low-latency audio capture.
 * This runs on a separate audio thread for smooth, uninterrupted audio processing.
 */
class VoiceAudioCaptureProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.isPaused = false;
        this.port.onmessage = (event) => {
            const data = event.data || {};
            if (data.type === 'pause') {
                this.isPaused = Boolean(data.value);
            }
        };
    }

    process(inputs) {
        if (this.isPaused) return true;
        const input = inputs[0];
        if (!input || !input[0] || input[0].length === 0) {
            return true;
        }
        const samples = new Float32Array(input[0]);
        this.port.postMessage(samples, [samples.buffer]);
        return true;
    }
}

registerProcessor('kiosk-audio-capture', VoiceAudioCaptureProcessor);
