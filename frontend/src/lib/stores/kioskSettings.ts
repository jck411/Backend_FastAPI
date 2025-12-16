/**
 * Kiosk settings store.
 * Fetches from and persists to the backend API (STT, TTS, and UI settings).
 */

import { get, writable } from 'svelte/store';
import {
    type KioskSttSettings,
    type KioskSttSettingsUpdate,
    type KioskTtsSettings,
    type KioskTtsSettingsUpdate,
    type KioskUiSettings,
    type KioskUiSettingsUpdate,
    fetchKioskSttSettings,
    fetchKioskTtsSettings,
    fetchKioskUiSettings,
    resetKioskSttSettings,
    resetKioskTtsSettings,
    updateKioskSttSettings,
    updateKioskTtsSettings,
    updateKioskUiSettings,
} from '../api/kiosk';

// Combined settings type
export interface KioskSettings extends KioskSttSettings, KioskTtsSettings, KioskUiSettings { }
export interface KioskSettingsUpdate extends KioskSttSettingsUpdate, KioskTtsSettingsUpdate, KioskUiSettingsUpdate { }

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

export const DEFAULT_KIOSK_SETTINGS: KioskSettings = {
    ...DEFAULT_KIOSK_STT_SETTINGS,
    ...DEFAULT_KIOSK_TTS_SETTINGS,
    ...DEFAULT_KIOSK_UI_SETTINGS,
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
            // Load STT, TTS, and UI settings in parallel
            const [sttSettings, ttsSettings, uiSettings] = await Promise.all([
                fetchKioskSttSettings(),
                fetchKioskTtsSettings(),
                fetchKioskUiSettings(),
            ]);
            const combined: KioskSettings = { ...sttSettings, ...ttsSettings, ...uiSettings };
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
            if (update.model !== undefined) ttsUpdate.model = update.model;
            if (update.sample_rate !== undefined) ttsUpdate.sample_rate = update.sample_rate;

            // UI fields
            if (update.idle_return_delay_ms !== undefined) uiUpdate.idle_return_delay_ms = update.idle_return_delay_ms;

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
            // Reset STT and TTS settings in parallel
            const [sttSettings, ttsSettings] = await Promise.all([
                resetKioskSttSettings(),
                resetKioskTtsSettings(),
            ]);
            const current = get(store);
            const combined: KioskSettings = {
                ...sttSettings,
                ...ttsSettings,
                idle_return_delay_ms: current.idle_return_delay_ms,
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
export type { KioskSttSettings, KioskSttSettingsUpdate, KioskTtsSettings, KioskTtsSettingsUpdate, KioskUiSettings, KioskUiSettingsUpdate };
