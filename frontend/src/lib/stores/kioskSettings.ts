/**
 * Kiosk settings store.
 * Fetches from and persists to the backend API (STT, TTS, UI, and LLM settings).
 * Uses unified /api/clients/kiosk/* endpoints.
 */

import { get, writable } from 'svelte/store';
import {
    type KioskLlmSettings,
    type KioskLlmSettingsUpdate,
    type KioskSttSettings,
    type KioskSttSettingsUpdate,
    type KioskTtsSettings,
    type KioskTtsSettingsUpdate,
    type KioskUiSettings,
    type KioskUiSettingsUpdate,
    fetchKioskLlmSettings,
    fetchKioskSttSettings,
    fetchKioskTtsSettings,
    fetchKioskUiSettings,
    resetKioskLlmSettings,
    resetKioskSttSettings,
    resetKioskTtsSettings,
    updateKioskLlmSettings,
    updateKioskSttSettings,
    updateKioskTtsSettings,
    updateKioskUiSettings,
} from '../api/kiosk';

// Combined settings type for the UI
export interface KioskSettings {
    // STT settings
    stt_mode: 'conversation' | 'command';
    eot_threshold: number;
    eot_timeout_ms: number;
    eager_eot_threshold: number | null;
    keyterms: string[];
    command_model: string;
    // TTS settings (OpenAI)
    enabled: boolean;
    provider: string;  // Always 'openai'
    voice: string;     // OpenAI voice: alloy, echo, fable, onyx, nova, shimmer
    model: string;     // tts-1 or tts-1-hd
    speed: number;     // 0.25 to 4.0
    response_format: string;
    sample_rate: number;
    stream_chunk_bytes: number;
    use_segmentation: boolean;
    delimiters: string[];
    segmentation_logging_enabled: boolean;
    first_phrase_min_chars: number;
    // Buffer settings for audio playback
    buffering_enabled: boolean;
    startup_delay_enabled: boolean;
    low_latency_audio: boolean;
    initial_buffer_sec: number;
    max_ahead_sec: number;
    min_chunk_sec: number;
    // UI settings
    idle_return_delay_ms: number;
    slideshow_max_photos: number;
    // LLM settings
    llm_model: string;
    system_prompt: string | null;
    temperature: number;
    max_tokens: number;
    conversation_mode: boolean;
    conversation_timeout_seconds: number;
}

export interface KioskSettingsUpdate extends Partial<KioskSettings> { }

export const DEFAULT_KIOSK_SETTINGS: KioskSettings = {
    // STT
    stt_mode: 'command',
    eot_threshold: 0.7,
    eot_timeout_ms: 5000,
    eager_eot_threshold: null,
    keyterms: [],
    command_model: 'nova-3',
    // TTS (OpenAI)
    enabled: true,
    provider: 'openai',
    voice: 'alloy',
    model: 'tts-1',
    speed: 1.0,
    response_format: 'pcm',
    sample_rate: 24000,
    stream_chunk_bytes: 4096,
    use_segmentation: true,
    delimiters: ['\n', '. ', '? ', '! ', '* ', ', ', ': '],
    segmentation_logging_enabled: false,
    first_phrase_min_chars: 10,
    // Buffer settings (optimized for low latency)
    buffering_enabled: false,
    startup_delay_enabled: false,
    low_latency_audio: true,
    initial_buffer_sec: 0.0,
    max_ahead_sec: 1.5,
    min_chunk_sec: 0.1,
    // UI
    idle_return_delay_ms: 10000,
    slideshow_max_photos: 30,
    // LLM
    llm_model: 'openai/gpt-4o-mini',
    system_prompt: 'You are a helpful voice assistant who replies succinctly.',
    temperature: 0.7,
    max_tokens: 500,
    conversation_mode: false,
    conversation_timeout_seconds: 10.0,
};

function cloneSettings(value: KioskSettings): KioskSettings {
    return JSON.parse(JSON.stringify(value)) as KioskSettings;
}

export function getDefaultKioskSttSettings(): KioskSettings {
    return cloneSettings(DEFAULT_KIOSK_SETTINGS);
}

function createKioskSettingsStore() {
    const store = writable<KioskSettings>(getDefaultKioskSttSettings());
    let loaded = false;
    let loading = false;

    async function load(): Promise<KioskSettings> {
        if (loading) {
            return get(store);
        }
        loading = true;
        try {
            const [sttSettings, ttsSettings, uiSettings, llmSettings] = await Promise.all([
                fetchKioskSttSettings(),
                fetchKioskTtsSettings(),
                fetchKioskUiSettings(),
                fetchKioskLlmSettings(),
            ]);
            const combined: KioskSettings = {
                // STT
                stt_mode: sttSettings.mode,
                eot_threshold: sttSettings.eot_threshold,
                eot_timeout_ms: sttSettings.eot_timeout_ms,
                eager_eot_threshold: sttSettings.eager_eot_threshold ?? null,
                keyterms: sttSettings.keyterms,
                command_model: sttSettings.command_model,
                // TTS
                enabled: ttsSettings.enabled,
                provider: ttsSettings.provider,
                voice: ttsSettings.voice,
                model: ttsSettings.model,
                speed: ttsSettings.speed,
                response_format: ttsSettings.response_format,
                sample_rate: ttsSettings.sample_rate,
                stream_chunk_bytes: ttsSettings.stream_chunk_bytes,
                use_segmentation: ttsSettings.use_segmentation,
                delimiters: ttsSettings.delimiters,
                segmentation_logging_enabled: ttsSettings.segmentation_logging_enabled,
                first_phrase_min_chars: ttsSettings.first_phrase_min_chars,
                buffering_enabled: ttsSettings.buffering_enabled,
                startup_delay_enabled: ttsSettings.startup_delay_enabled,
                low_latency_audio: ttsSettings.low_latency_audio,
                initial_buffer_sec: ttsSettings.initial_buffer_sec,
                max_ahead_sec: ttsSettings.max_ahead_sec,
                min_chunk_sec: ttsSettings.min_chunk_sec,
                // UI
                idle_return_delay_ms: uiSettings.idle_return_delay_ms,
                slideshow_max_photos: uiSettings.slideshow_max_photos,
                // LLM
                llm_model: llmSettings.model,
                system_prompt: llmSettings.system_prompt,
                temperature: llmSettings.temperature,
                max_tokens: llmSettings.max_tokens,
                conversation_mode: llmSettings.conversation_mode,
                conversation_timeout_seconds: llmSettings.conversation_timeout_seconds,
            };
            store.set(combined);
            loaded = true;
            return combined;
        } catch (error) {
            console.error('Failed to load kiosk settings:', error);
            return get(store);
        } finally {
            loading = false;
        }
    }

    async function save(update: KioskSettingsUpdate): Promise<KioskSettings> {
        try {
            const sttUpdate: KioskSttSettingsUpdate = {};
            const ttsUpdate: KioskTtsSettingsUpdate = {};
            const uiUpdate: KioskUiSettingsUpdate = {};
            const llmUpdate: KioskLlmSettingsUpdate = {};

            // STT fields
            if (update.stt_mode !== undefined) sttUpdate.mode = update.stt_mode;
            if (update.eot_threshold !== undefined) sttUpdate.eot_threshold = update.eot_threshold;
            if (update.eot_timeout_ms !== undefined) sttUpdate.eot_timeout_ms = update.eot_timeout_ms;
            if (update.eager_eot_threshold !== undefined) sttUpdate.eager_eot_threshold = update.eager_eot_threshold;
            if (update.keyterms !== undefined) sttUpdate.keyterms = update.keyterms;
            if (update.command_model !== undefined) sttUpdate.command_model = update.command_model;

            // TTS fields
            if (update.enabled !== undefined) ttsUpdate.enabled = update.enabled;
            if (update.provider !== undefined) ttsUpdate.provider = update.provider;
            if (update.voice !== undefined) ttsUpdate.voice = update.voice;
            if (update.model !== undefined) ttsUpdate.model = update.model;
            if (update.speed !== undefined) ttsUpdate.speed = update.speed;
            if (update.response_format !== undefined) ttsUpdate.response_format = update.response_format;
            if (update.sample_rate !== undefined) ttsUpdate.sample_rate = update.sample_rate;
            if (update.stream_chunk_bytes !== undefined) ttsUpdate.stream_chunk_bytes = update.stream_chunk_bytes;
            if (update.use_segmentation !== undefined) ttsUpdate.use_segmentation = update.use_segmentation;
            if (update.delimiters !== undefined) ttsUpdate.delimiters = update.delimiters;
            if (update.first_phrase_min_chars !== undefined) {
                ttsUpdate.first_phrase_min_chars = update.first_phrase_min_chars;
            }
            if (update.segmentation_logging_enabled !== undefined) {
                ttsUpdate.segmentation_logging_enabled = update.segmentation_logging_enabled;
            }
            if (update.buffering_enabled !== undefined) {
                ttsUpdate.buffering_enabled = update.buffering_enabled;
            }
            if (update.startup_delay_enabled !== undefined) {
                ttsUpdate.startup_delay_enabled = update.startup_delay_enabled;
            }
            if (update.low_latency_audio !== undefined) {
                ttsUpdate.low_latency_audio = update.low_latency_audio;
            }
            if (update.initial_buffer_sec !== undefined) {
                ttsUpdate.initial_buffer_sec = update.initial_buffer_sec;
            }
            if (update.max_ahead_sec !== undefined) {
                ttsUpdate.max_ahead_sec = update.max_ahead_sec;
            }
            if (update.min_chunk_sec !== undefined) {
                ttsUpdate.min_chunk_sec = update.min_chunk_sec;
            }

            // UI fields
            if (update.idle_return_delay_ms !== undefined) uiUpdate.idle_return_delay_ms = update.idle_return_delay_ms;
            if (update.slideshow_max_photos !== undefined) uiUpdate.slideshow_max_photos = update.slideshow_max_photos;

            // LLM fields
            if (update.llm_model !== undefined) llmUpdate.model = update.llm_model;
            if (update.system_prompt !== undefined) llmUpdate.system_prompt = update.system_prompt;
            if (update.temperature !== undefined) llmUpdate.temperature = update.temperature;
            if (update.max_tokens !== undefined) llmUpdate.max_tokens = update.max_tokens;
            if (update.conversation_mode !== undefined) llmUpdate.conversation_mode = update.conversation_mode;
            if (update.conversation_timeout_seconds !== undefined) llmUpdate.conversation_timeout_seconds = update.conversation_timeout_seconds;

            const promises: Promise<unknown>[] = [];

            if (Object.keys(sttUpdate).length > 0) {
                promises.push(updateKioskSttSettings(sttUpdate));
            }
            if (Object.keys(ttsUpdate).length > 0) {
                promises.push(updateKioskTtsSettings(ttsUpdate));
            }
            if (Object.keys(uiUpdate).length > 0) {
                promises.push(updateKioskUiSettings(uiUpdate));
            }
            if (Object.keys(llmUpdate).length > 0) {
                promises.push(updateKioskLlmSettings(llmUpdate));
            }

            await Promise.all(promises);
            return await load();
        } catch (error) {
            console.error('Failed to save kiosk settings:', error);
            throw error;
        }
    }

    async function reset(): Promise<KioskSettings> {
        try {
            const [sttSettings, ttsSettings, llmSettings] = await Promise.all([
                resetKioskSttSettings(),
                resetKioskTtsSettings(),
                resetKioskLlmSettings(),
            ]);
            const current = get(store);
            const combined: KioskSettings = {
                // STT
                stt_mode: sttSettings.mode,
                eot_threshold: sttSettings.eot_threshold,
                eot_timeout_ms: sttSettings.eot_timeout_ms,
                eager_eot_threshold: sttSettings.eager_eot_threshold ?? null,
                keyterms: sttSettings.keyterms,
                command_model: sttSettings.command_model,
                // TTS
                enabled: ttsSettings.enabled,
                provider: ttsSettings.provider,
                voice: ttsSettings.voice,
                model: ttsSettings.model,
                speed: ttsSettings.speed,
                response_format: ttsSettings.response_format,
                sample_rate: ttsSettings.sample_rate,
                stream_chunk_bytes: ttsSettings.stream_chunk_bytes,
                use_segmentation: ttsSettings.use_segmentation,
                delimiters: ttsSettings.delimiters,
                segmentation_logging_enabled: ttsSettings.segmentation_logging_enabled,
                first_phrase_min_chars: ttsSettings.first_phrase_min_chars,
                buffering_enabled: ttsSettings.buffering_enabled,
                startup_delay_enabled: ttsSettings.startup_delay_enabled,
                low_latency_audio: ttsSettings.low_latency_audio,
                initial_buffer_sec: ttsSettings.initial_buffer_sec,
                max_ahead_sec: ttsSettings.max_ahead_sec,
                min_chunk_sec: ttsSettings.min_chunk_sec,
                // UI (keep current)
                idle_return_delay_ms: current.idle_return_delay_ms,
                slideshow_max_photos: current.slideshow_max_photos,
                // LLM
                llm_model: llmSettings.model,
                system_prompt: llmSettings.system_prompt,
                temperature: llmSettings.temperature,
                max_tokens: llmSettings.max_tokens,
                conversation_mode: llmSettings.conversation_mode,
                conversation_timeout_seconds: llmSettings.conversation_timeout_seconds,
            };
            store.set(combined);
            return combined;
        } catch (error) {
            console.error('Failed to reset kiosk settings:', error);
            throw error;
        }
    }

    return {
        subscribe: store.subscribe,
        load,
        save,
        reset,
        get isLoaded(): boolean {
            return loaded;
        },
        get current(): KioskSettings {
            return get(store);
        },
    };
}

export const kioskSettingsStore = createKioskSettingsStore();

// Re-export types for convenience
export type { KioskLlmSettings, KioskLlmSettingsUpdate, KioskSttSettings, KioskSttSettingsUpdate, KioskTtsSettings, KioskTtsSettingsUpdate, KioskUiSettings, KioskUiSettingsUpdate };
