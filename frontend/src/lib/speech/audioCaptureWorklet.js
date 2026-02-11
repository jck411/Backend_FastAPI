/**
 * AudioWorklet processor for capturing microphone audio.
 * Sends Float32Array samples to the main thread for processing.
 */
class AudioCaptureProcessor extends AudioWorkletProcessor {
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
        // Copy samples and transfer buffer to main thread
        const samples = new Float32Array(input[0]);
        this.port.postMessage(samples, [samples.buffer]);
        return true;
    }
}

registerProcessor('audio-capture', AudioCaptureProcessor);
