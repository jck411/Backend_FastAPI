/**
 * Voice configuration for frontend-kiosk.
 * Mirrors the configuration from frontend-voice for consistency.
 */

const toNumber = (value, fallback) => {
    if (value === undefined || value === null || value === '') {
        return fallback;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
};

const toBoolean = (value, fallback) => {
    if (value === undefined || value === null || value === '') {
        return fallback;
    }
    if (typeof value === 'boolean') {
        return value;
    }
    const normalized = String(value).trim().toLowerCase();
    if (normalized === 'true') return true;
    if (normalized === 'false') return false;
    return fallback;
};

const toString = (value) => {
    if (value === undefined || value === null) return '';
    return String(value).trim();
};

const normalizePath = (value, fallback) => {
    const resolved = value ? value.trim() : '';
    if (!resolved) return fallback;
    return resolved.startsWith('/') ? resolved : `/${resolved}`;
};

const appendQueryParam = (url, key, value) => {
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
};

const resolveDefaultPort = () => {
    if (typeof window === 'undefined') return '';
    if (import.meta.env.DEV) return '8000';
    return window.location.port || '';
};

export const VOICE_CONFIG = {
    ws: {
        url: toString(import.meta.env.VITE_VOICE_WS_URL),
        protocol: toString(import.meta.env.VITE_VOICE_WS_PROTOCOL),
        host: toString(import.meta.env.VITE_VOICE_WS_HOST),
        port: toString(import.meta.env.VITE_VOICE_WS_PORT),
        path: normalizePath(
            toString(import.meta.env.VITE_VOICE_WS_PATH),
            '/api/voice/connect',
        ),
    },
    audio: {
        targetSampleRate: toNumber(import.meta.env.VITE_VOICE_AUDIO_SAMPLE_RATE, 16000),
        processorBufferSize: toNumber(import.meta.env.VITE_VOICE_AUDIO_BUFFER_SIZE, 4096),
        maxPendingBuffers: toNumber(import.meta.env.VITE_VOICE_AUDIO_MAX_PENDING, 100),
        useAudioWorklet: toBoolean(import.meta.env.VITE_VOICE_AUDIO_WORKLET, true),
        resampleToTarget: toBoolean(import.meta.env.VITE_VOICE_AUDIO_RESAMPLE, true),
        includeSampleRate: toBoolean(import.meta.env.VITE_VOICE_AUDIO_INCLUDE_SAMPLE_RATE, false),
    },
    tts: {
        defaultSampleRate: toNumber(import.meta.env.VITE_VOICE_TTS_SAMPLE_RATE, 24000),
        initialBufferSec: 0.2,
        minChunkSec: 0.08,
        maxAheadSec: 1.5,
        startupDelaySec: 0.06,
        micResumeDelayMs: toNumber(import.meta.env.VITE_VOICE_TTS_MIC_RESUME_DELAY_MS, 800),
    },
    ui: {
        idleReturnDelayMs: toNumber(import.meta.env.VITE_KIOSK_IDLE_RETURN_MS, 10000),
    },
};

export const createClientId = () => {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return `kiosk_${crypto.randomUUID()}`;
    }
    return `kiosk_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
};

export const buildVoiceWsUrl = (clientId, config = VOICE_CONFIG) => {
    const explicitUrl = config.ws.url;
    if (explicitUrl) {
        return appendQueryParam(explicitUrl, 'client_id', clientId);
    }
    if (typeof window === 'undefined') return '';
    const protocol = config.ws.protocol || (window.location.protocol === 'https:' ? 'wss:' : 'ws:');
    const host = config.ws.host || window.location.hostname;
    const port = config.ws.port || resolveDefaultPort();
    const portSegment = port ? `:${port}` : '';
    const path = config.ws.path || '/api/voice/connect';
    return `${protocol}//${host}${portSegment}${path}?client_id=${encodeURIComponent(clientId)}`;
};
