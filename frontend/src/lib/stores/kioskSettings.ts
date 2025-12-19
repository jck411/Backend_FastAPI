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
    eot_threshold: number;
    eot_timeout_ms: number;
    keyterms: string[];
    // TTS settings (OpenAI)
    enabled: boolean;
    provider: string;  // Always 'openai'
    voice: string;     // OpenAI voice: alloy, echo, fable, onyx, nova, shimmer
    model: string;     // tts-1 or tts-1-hd
    speed: number;     // 0.25 to 4.0
    sample_rate: number;
    // UI settings
    idle_return_delay_ms: number;
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
    eot_threshold: 0.7,
    eot_timeout_ms: 5000,
    keyterms: [],
    // TTS (OpenAI)
    enabled: true,
    provider: 'openai',
    voice: 'alloy',
    model: 'tts-1',
    speed: 1.0,
    sample_rate: 24000,
    // UI
    idle_return_delay_ms: 10000,
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
                eot_threshold: sttSettings.eot_threshold,
                eot_timeout_ms: sttSettings.eot_timeout_ms,
                keyterms: sttSettings.keyterms,
                // TTS
                enabled: ttsSettings.enabled,
                provider: ttsSettings.provider,
                voice: ttsSettings.voice,
                model: ttsSettings.model,
                speed: ttsSettings.speed,
                sample_rate: ttsSettings.sample_rate,
                // UI
                idle_return_delay_ms: uiSettings.idle_return_delay_ms,
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
            if (update.eot_threshold !== undefined) sttUpdate.eot_threshold = update.eot_threshold;
            if (update.eot_timeout_ms !== undefined) sttUpdate.eot_timeout_ms = update.eot_timeout_ms;
            if (update.keyterms !== undefined) sttUpdate.keyterms = update.keyterms;

            // TTS fields
            if (update.enabled !== undefined) ttsUpdate.enabled = update.enabled;
            if (update.provider !== undefined) ttsUpdate.provider = update.provider;
            if (update.voice !== undefined) ttsUpdate.voice = update.voice;
            if (update.model !== undefined) ttsUpdate.model = update.model;
            if (update.speed !== undefined) ttsUpdate.speed = update.speed;
            if (update.sample_rate !== undefined) ttsUpdate.sample_rate = update.sample_rate;

            // UI fields
            if (update.idle_return_delay_ms !== undefined) uiUpdate.idle_return_delay_ms = update.idle_return_delay_ms;

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
                eot_threshold: sttSettings.eot_threshold,
                eot_timeout_ms: sttSettings.eot_timeout_ms,
                keyterms: sttSettings.keyterms,
                // TTS
                enabled: ttsSettings.enabled,
                provider: ttsSettings.provider,
                voice: ttsSettings.voice,
                model: ttsSettings.model,
                speed: ttsSettings.speed,
                sample_rate: ttsSettings.sample_rate,
                // UI (keep current)
                idle_return_delay_ms: current.idle_return_delay_ms,
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
