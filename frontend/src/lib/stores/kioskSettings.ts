/**
 * Kiosk settings store.
 * Fetches from and persists to the backend API (STT, TTS, UI, and LLM settings).
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

// Combined settings type (note: TTS model and LLM model have different names to avoid conflicts)
export interface KioskSettings extends KioskSttSettings, Omit<KioskTtsSettings, 'model'>, KioskUiSettings, Omit<KioskLlmSettings, 'model'> {
    tts_model: string;  // TTS voice model (renamed from TTS settings)
    llm_model: string;  // LLM model (renamed from LLM settings)
}
export interface KioskSettingsUpdate extends KioskSttSettingsUpdate, Omit<KioskTtsSettingsUpdate, 'model'>, KioskUiSettingsUpdate, Omit<KioskLlmSettingsUpdate, 'model'> {
    tts_model?: string;
    llm_model?: string;
}

export const DEFAULT_KIOSK_STT_SETTINGS: KioskSttSettings = {
    eot_threshold: 0.7,
    eot_timeout_ms: 5000,
    eager_eot_threshold: null,
    keyterms: [],
};

export const DEFAULT_KIOSK_TTS_SETTINGS: KioskTtsSettings = {
    enabled: true,
    provider: 'deepgram',
    model: 'aura-asteria-en',
    sample_rate: 16000,
};

export const DEFAULT_KIOSK_UI_SETTINGS: KioskUiSettings = {
    idle_return_delay_ms: 10000,
};

export const DEFAULT_KIOSK_LLM_SETTINGS = {
    llm_model: 'openai/gpt-4o-mini',
    system_prompt: 'You are a helpful voice assistant who replies succinctly.',
    temperature: 0.7,
    max_tokens: 500,
    conversation_mode: false,
    conversation_timeout_seconds: 10.0,
};

export const DEFAULT_KIOSK_SETTINGS: KioskSettings = {
    ...DEFAULT_KIOSK_STT_SETTINGS,
    ...{ enabled: DEFAULT_KIOSK_TTS_SETTINGS.enabled, provider: DEFAULT_KIOSK_TTS_SETTINGS.provider, tts_model: DEFAULT_KIOSK_TTS_SETTINGS.model, sample_rate: DEFAULT_KIOSK_TTS_SETTINGS.sample_rate },
    ...DEFAULT_KIOSK_UI_SETTINGS,
    ...DEFAULT_KIOSK_LLM_SETTINGS,
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
            // Return current value while loading
            return get(store);
        }
        loading = true;
        try {
            // Load STT, TTS, UI, and LLM settings in parallel
            const [sttSettings, ttsSettings, uiSettings, llmSettings] = await Promise.all([
                fetchKioskSttSettings(),
                fetchKioskTtsSettings(),
                fetchKioskUiSettings(),
                fetchKioskLlmSettings(),
            ]);
            const combined: KioskSettings = {
                ...sttSettings,
                enabled: ttsSettings.enabled,
                provider: ttsSettings.provider,
                tts_model: ttsSettings.model,
                sample_rate: ttsSettings.sample_rate,
                ...uiSettings,
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
            // Determine which APIs need to be called
            const sttUpdate: KioskSttSettingsUpdate = {};
            const ttsUpdate: KioskTtsSettingsUpdate = {};
            const uiUpdate: KioskUiSettingsUpdate = {};

            // STT fields
            if (update.eot_threshold !== undefined) sttUpdate.eot_threshold = update.eot_threshold;
            if (update.eot_timeout_ms !== undefined) sttUpdate.eot_timeout_ms = update.eot_timeout_ms;
            if (update.eager_eot_threshold !== undefined) sttUpdate.eager_eot_threshold = update.eager_eot_threshold;
            if (update.keyterms !== undefined) sttUpdate.keyterms = update.keyterms;

            // TTS fields
            if (update.enabled !== undefined) ttsUpdate.enabled = update.enabled;
            if (update.provider !== undefined) ttsUpdate.provider = update.provider;
            if (update.tts_model !== undefined) ttsUpdate.model = update.tts_model;
            if (update.sample_rate !== undefined) ttsUpdate.sample_rate = update.sample_rate;

            // UI fields
            if (update.idle_return_delay_ms !== undefined) uiUpdate.idle_return_delay_ms = update.idle_return_delay_ms;

            // LLM fields
            const llmUpdate: KioskLlmSettingsUpdate = {};
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

            // Reload to get the combined state
            return await load();
        } catch (error) {
            console.error('Failed to save kiosk settings:', error);
            throw error;
        }
    }

    async function reset(): Promise<KioskSettings> {
        try {
            // Reset STT, TTS, and LLM settings in parallel
            const [sttSettings, ttsSettings, llmSettings] = await Promise.all([
                resetKioskSttSettings(),
                resetKioskTtsSettings(),
                resetKioskLlmSettings(),
            ]);
            const current = get(store);
            const combined: KioskSettings = {
                ...sttSettings,
                enabled: ttsSettings.enabled,
                provider: ttsSettings.provider,
                tts_model: ttsSettings.model,
                sample_rate: ttsSettings.sample_rate,
                idle_return_delay_ms: current.idle_return_delay_ms,
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

