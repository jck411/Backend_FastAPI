#!/usr/bin/env node
/**
    Offline Porcupine wake-word listener (using older version without acces    console.log(
        `Listening for wake-word (${useBuiltinKeyword ? 'porcupine' : 'computer'}) — device_index=${deviceIndex}\n` +
        'Press Ctrl-C to quit.',
    );y)
    • Uses your custom model:

/home/jack/REPOS/deepgram_standalone/wakewords/computer_en_linux_v3_0_0.ppn

• Works on Linux, macOS, Windows & Raspberry Pi.

Run:
node wake_word_listener.js \

   --sensitivity 0.65         # optional, default 0.60

       --device_index 2           # optional mic index, default -1 (system default)

    Flags:
    --keyword Overrides the baked-in .ppn path if you need a different model.
    */

const fs = require('fs');
const path = require('path');
const minimist = require('minimist');
const { exit, argv } = require('process');
const Porcupine = require('@picovoice/porcupine-node');
const { PvRecorder } = require('@picovoice/pvrecorder-node');
const http = require('http');
const https = require('https');

(async () => {
    // -------------------------------------------------------------------------
    const DEFAULT_PPN =
        '/home/jack/REPOS/Backend_FastAPI/Test_Frontend/STT/Wakeword/computer_linux_v1.9.0.ppn';

    const args = minimist(argv.slice(2), {
        string: ['keyword', 'backend'],
        default: { keyword: DEFAULT_PPN, sensitivity: 0.6, device_index: -1, use_builtin: false },
    });

    // Backend endpoint to notify on detection
    const backendUrl = typeof args.backend === 'string' && args.backend
        ? args.backend
        : (process.env.BACKEND_URL || 'http://localhost:8000/api/stt/wakeword/detected');

    // Debug: log the raw args
    console.log('Raw args:', args);

    // Convert and validate sensitivity
    const sensitivity = Number(args.sensitivity || 0.6);
    if (isNaN(sensitivity) || sensitivity < 0 || sensitivity > 1) {
        console.error(`Invalid sensitivity: ${args.sensitivity}. Must be a number between 0 and 1.`);
        exit(1);
    }

    // Convert and validate device_index
    const deviceIndex = Number(args.device_index || -1);
    if (isNaN(deviceIndex)) {
        console.error(`Invalid device_index: ${args.device_index}. Must be a number.`);
        exit(1);
    }

    console.log(`Using sensitivity: ${sensitivity}, device_index: ${deviceIndex}`);

    // Check if we should use built-in keyword or custom file
    let useBuiltinKeyword = args.use_builtin || !fs.existsSync(args.keyword);

    if (!useBuiltinKeyword && !fs.existsSync(args.keyword)) {
        console.error(`Keyword file not found:\n  ${args.keyword}`);
        console.log('Falling back to built-in keyword "porcupine" (keyword 0)');
        useBuiltinKeyword = true;
    }

    if (useBuiltinKeyword) {
        console.log('Using built-in keyword "porcupine" (keyword 0)');
        console.log('Available built-in keywords: 0-7 (typically: porcupine, picovoice, grasshopper, bumblebee, etc.)');
    }

    // ----------------------- 1. Create Porcupine engine (without access key) ----------------------
    const sensitivities = [sensitivity];
    console.log('Sensitivities array:', sensitivities);

    // For Porcupine v1.9.2 - older API without access key
    let porcupine;

    try {
        // Choose keyword: built-in (integer) or custom file path
        const keyword = useBuiltinKeyword ? 0 : path.resolve(args.keyword);

        console.log(`Initializing with keyword: ${useBuiltinKeyword ? 'built-in keyword 0 (porcupine)' : keyword}`);

        // Older API: new Porcupine(keywords, sensitivities, modelPath, libraryPath)
        porcupine = new Porcupine(
            [keyword],                     // keywords array (integer for built-in, string for custom)
            sensitivities,                 // sensitivities array
            undefined,                     // modelPath (undefined for default)
            undefined                      // libraryPath (undefined for default)
        );
        console.log('✅ Porcupine initialized successfully without access key');
    } catch (err) {
        console.error('❌ Porcupine initialization failed:', err.message);
        exit(1);
    }

    // ----------------------- 2. Start microphone capture ---------------------
    let recorder;
    try {
        recorder = new PvRecorder(porcupine.frameLength, deviceIndex);
        console.log('🔊  Starting microphone …');
        await recorder.start();
    } catch (err) {
        console.error('❌ Microphone initialization failed:', err.message);
        console.error('\n💡 Possible solutions:');
        console.error('   1. Log out and log back in (to refresh audio group membership)');
        console.error('   2. Restart your computer');
        console.error('   3. Try: sudo node wakewords/wakeword_listiner_no_key.cjs --use_builtin');
        console.error('   4. Or run the simulator: node wake_word_simulator.cjs');

        porcupine.release();
        exit(1);
    }

    console.log(
        `Listening for wake-word (“computer”) — device_index=${deviceIndex}\n` +
        'Press Ctrl-C to quit.',
    );

    // Clean shutdown on SIGINT/SIGTERM
    const shutdown = async () => {
        console.log('\nShutting down …');
        try {
            if (recorder && recorder.stop) {
                await recorder.stop();
            }
            if (recorder && recorder.release) {
                recorder.release();
            }
        } catch (err) {
            console.log('Recorder cleanup error (ignored):', err.message);
        }
        porcupine.release();
        exit(0);
    };
    process.on('SIGINT', shutdown).on('SIGTERM', shutdown);

    // Helper to POST JSON without external deps
    function postJson(urlString, body) {
        return new Promise((resolve, reject) => {
            try {
                const u = new URL(urlString);
                const lib = u.protocol === 'https:' ? https : http;
                const req = lib.request(
                    {
                        hostname: u.hostname,
                        port: u.port || (u.protocol === 'https:' ? 443 : 80),
                        path: u.pathname + (u.search || ''),
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Accept': 'application/json',
                        },
                        timeout: 3000,
                    },
                    (res) => {
                        // Drain response
                        res.on('data', () => { });
                        res.on('end', () => resolve());
                    }
                );
                req.on('error', reject);
                req.write(JSON.stringify(body || {}));
                req.end();
            } catch (err) {
                reject(err);
            }
        });
    }

    // ---------------------------- 3. Main loop -------------------------------
    while (true) {
        const frame = await recorder.read();           // Int16Array
        const keywordIndex = porcupine.process(frame); // returns -1 or keyword idx
        if (keywordIndex >= 0) {
            console.log('✅  Wake-word detected!');
            const phrase = useBuiltinKeyword ? 'porcupine' : 'computer';
            postJson(backendUrl, { phrase, source: 'porcupine' }).catch((err) => {
                console.warn('Wakeword POST failed:', err?.message || err);
            });
        }
    }

})().catch((err) => {
    console.error('Fatal error:', err);
    exit(1);
});
