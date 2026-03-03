/**
 * Wakeword detection service.
 *
 * Connects to the backend keyword-detection WebSocket (`/api/keyword/listen`)
 * and fires a callback when the keyword is heard. Completely independent from
 * the main speech/transcription pipeline so it can be swapped to any STT
 * service later.
 */
import { get, writable } from 'svelte/store';
import { API_BASE_URL } from '../api/config';

export type WakewordStatus = 'off' | 'starting' | 'armed' | 'detected' | 'error';

interface WakewordState {
    enabled: boolean;
    status: WakewordStatus;
    error: string | null;
}

const STORAGE_KEY = 'wakeword_enabled';

const initialEnabled =
    typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY) === 'true';

const state = writable<WakewordState>({
    enabled: initialEnabled,
    status: initialEnabled ? 'starting' : 'off',
    error: null,
});

export const wakewordState = { subscribe: state.subscribe };

// Audio resources
let mediaStream: MediaStream | null = null;
let audioContext: AudioContext | null = null;
let processor: ScriptProcessorNode | null = null;
let ws: WebSocket | null = null;
let onDetected: (() => void) | null = null;

// ─── Helpers ────────────────────────────────────────────────────

function getWsUrl(): string {
    let base = API_BASE_URL || window.location.origin;
    base = base.replace(/^http/, 'ws');
    return `${base}/api/keyword/listen`;
}

function floatTo16BitPCM(float32: Float32Array): ArrayBuffer {
    const buf = new ArrayBuffer(float32.length * 2);
    const view = new DataView(buf);
    for (let i = 0; i < float32.length; i++) {
        const s = Math.max(-1, Math.min(1, float32[i]));
        view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return buf;
}

// ─── Core lifecycle ─────────────────────────────────────────────

async function startListening(): Promise<void> {
    if (ws) return; // already running

    state.update((v) => ({ ...v, status: 'starting', error: null }));

    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
        state.update((v) => ({ ...v, status: 'error', error: 'Mic access denied' }));
        return;
    }

    audioContext = new AudioContext({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(mediaStream);
    processor = audioContext.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (event) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(floatTo16BitPCM(event.inputBuffer.getChannelData(0)));
        }
    };

    source.connect(processor);
    processor.connect(audioContext.destination);

    ws = new WebSocket(getWsUrl());
    ws.binaryType = 'arraybuffer';

    ws.onmessage = (event) => {
        let data: Record<string, unknown>;
        try {
            data = JSON.parse(event.data as string);
        } catch {
            return;
        }

        if (data.type === 'armed') {
            state.update((v) => ({ ...v, status: 'armed', error: null }));
        } else if (data.type === 'keyword_detected') {
            state.update((v) => ({ ...v, status: 'detected' }));
            // Tear down this session — speech recognition will use its own mic
            teardown();
            onDetected?.();
        } else if (data.type === 'error') {
            state.update((v) => ({ ...v, status: 'error', error: String(data.message ?? 'Unknown') }));
        }
    };

    ws.onclose = () => {
        // Only treat as error if we didn't intentionally close
        const current = get(state);
        if (current.enabled && current.status !== 'detected') {
            teardown();
            state.update((v) => ({ ...v, status: 'error', error: 'Connection closed unexpectedly' }));
        }
    };

    ws.onerror = () => {
        teardown();
        state.update((v) => ({ ...v, status: 'error', error: 'WebSocket error' }));
    };
}

function teardown(): void {
    if (ws) {
        ws.onclose = null;
        ws.onerror = null;
        if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'stop' }));
            ws.close();
        }
        ws = null;
    }
    if (processor) {
        processor.disconnect();
        processor = null;
    }
    if (audioContext) {
        void audioContext.close();
        audioContext = null;
    }
    if (mediaStream) {
        mediaStream.getTracks().forEach((t) => t.stop());
        mediaStream = null;
    }
}

// ─── Public API ─────────────────────────────────────────────────

/** Set the callback invoked when the keyword is detected. */
export function setOnDetected(cb: () => void): void {
    onDetected = cb;
}

/** Re-arm keyword listening (e.g. after transcription completes). */
export function rearm(): void {
    const current = get(state);
    if (!current.enabled) return;
    if (current.status === 'armed' || current.status === 'starting') return;
    // Small delay so the previous mic is fully released
    setTimeout(() => void startListening(), 300);
}

/** Toggle wakeword on/off. */
export function setWakewordEnabled(enabled: boolean): void {
    localStorage.setItem(STORAGE_KEY, String(enabled));

    if (enabled) {
        state.update((v) => ({ ...v, enabled: true }));
        void startListening();
    } else {
        teardown();
        state.set({ enabled: false, status: 'off', error: null });
    }
}

/** Temporarily disarm (e.g. while user is speaking / AI is responding). */
export function disarm(): void {
    const current = get(state);
    if (!current.enabled) return;
    teardown();
    state.update((v) => ({ ...v, status: 'off' }));
}

/** Initialize on app startup — auto-arms if previously enabled. */
export function initWakeword(): void {
    const current = get(state);
    if (current.enabled) {
        void startListening();
    }
}
