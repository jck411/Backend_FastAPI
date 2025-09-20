import dotenv from "dotenv";
import recorder from "node-record-lpcm16";
import WebSocket from "ws";

// Load environment variables
dotenv.config();

// Optimal settings for slow speakers based on Deepgram documentation
const deepgramParams = new URLSearchParams({
    model: 'nova-3',                    // Best accuracy and real-world performance
    interim_results: 'true',            // Get real-time preliminary results
    endpointing: '1000',                // Wait 1000ms for pauses (vs default 10ms) - perfect for slow speakers
    smart_format: 'true',               // Better punctuation and formatting
    vad_events: 'true',                 // Voice activity detection events
    encoding: 'linear16',               // 16-bit PCM audio format
    sample_rate: '16000',               // 16kHz sample rate
    channels: '1'                       // Mono audio
});

const socket = new WebSocket(`wss://api.deepgram.com/v1/listen?${deepgramParams}`, {
    headers: { Authorization: "Token " + process.env.DEEPGRAM_API_KEY }
});

socket.on("open", () => {
    console.log("Connected to Deepgram Nova-3 for STT");
    console.log("🎤 Starting microphone recording...");
    console.log("Speak into your microphone for real-time transcription!");

    // Start recording from microphone (16-bit PCM, 16kHz)
    const recording = recorder.record({
        sampleRateHertz: 16000,
        threshold: 0.5,
        verbose: false,
        recordProgram: 'rec', // Uses SoX
        silence: '1.0',
    });

    // Pipe microphone data directly to Deepgram WebSocket
    recording.stream()
        .on('data', (chunk) => {
            if (socket.readyState === WebSocket.OPEN) {
                socket.send(chunk);
            }
        })
        .on('error', (err) => {
            console.error('Recording error:', err);
        });

    // Handle process termination
    process.on('SIGINT', () => {
        console.log('\n🛑 Stopping recording...');
        recording.stop();
        socket.close();
        process.exit(0);
    });
});

socket.on("message", (msg) => {
    const data = JSON.parse(msg);

    // Handle VAD (Voice Activity Detection) events
    if (data.type === 'SpeechStarted') {
        console.log(`🎙️  Speech detected at ${data.timestamp}s`);
        return;
    }

    // Handle transcription results
    if (data.channel?.alternatives[0]?.transcript) {
        const transcript = data.channel.alternatives[0].transcript;
        const isFinal = data.is_final;
        const speechFinal = data.speech_final;

        // Enhanced display for slow speakers
        if (speechFinal) {
            // End of utterance detected (after endpointing timeout)
            console.log(`\n🏁 UTTERANCE COMPLETE: ${transcript}`);
            console.log('---'); // Visual separator
        } else if (isFinal) {
            // Final result for this audio segment but utterance may continue
            console.log(`\n📝 FINAL SEGMENT: ${transcript}`);
        } else {
            // Interim result - real-time updates
            process.stdout.write(`\r� ${transcript}`);
        }
    }
});

socket.on("error", (error) => {
    console.error("WebSocket error:", error);
});

socket.on("close", (code, reason) => {
    console.log(`WebSocket closed with code ${code}: ${reason}`);
});

// Keep the process alive for testing
console.log("🚀 Starting Deepgram WebSocket client...");
console.log("� OPTIMIZED FOR SLOW SPEAKERS");
console.log("�📋 Requirements: Make sure you have a microphone connected");
console.log("🔧 Note: This requires SoX to be installed (sudo apt install sox on Ubuntu)");
console.log("");
console.log("⚙️  Settings:");
console.log("   • Endpointing: 1000ms (waits longer for pauses)");
console.log("   • Interim results: Enabled (real-time feedback)");
console.log("   • Smart formatting: Enabled (better punctuation)");
console.log("   • VAD events: Enabled (speech detection)");
console.log("");
console.log("⏹️  Press Ctrl+C to exit");
