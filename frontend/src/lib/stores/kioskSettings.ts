/**
 * Kiosk STT settings store.
 * Fetches from and persists to the backend API.
 */

import { get, writable } from 'svelte/store';
import {
    type KioskSttSettings,
    type KioskSttSettingsUpdate,
    fetchKioskSttSettings,
    resetKioskSttSettings,
    updateKioskSttSettings,
} from '../api/kiosk';

export const DEFAULT_KIOSK_STT_SETTINGS: KioskSttSettings = {
    eot_threshold: 0.7,
    eot_timeout_ms: 5000,
    eager_eot_threshold: null,
    keyterms: [],
};

function cloneSettings(value: KioskSttSettings): KioskSttSettings {
    return JSON.parse(JSON.stringify(value)) as KioskSttSettings;
}

export function getDefaultKioskSttSettings(): KioskSttSettings {
    return cloneSettings(DEFAULT_KIOSK_STT_SETTINGS);
}

function createKioskSettingsStore() {
    const store = writable<KioskSttSettings>(getDefaultKioskSttSettings());
    let loaded = false;
    let loading = false;

    async function load(): Promise<KioskSttSettings> {
        if (loading) {
            // Return current value while loading
            return get(store);
        }
        loading = true;
        try {
            const settings = await fetchKioskSttSettings();
            store.set(settings);
            loaded = true;
            return settings;
        } catch (error) {
            console.error('Failed to load kiosk STT settings:', error);
            return get(store);
        } finally {
            loading = false;
        }
    }

    async function save(update: KioskSttSettingsUpdate): Promise<KioskSttSettings> {
        try {
            const settings = await updateKioskSttSettings(update);
            store.set(settings);
            return settings;
        } catch (error) {
            console.error('Failed to save kiosk STT settings:', error);
            throw error;
        }
    }

    async function reset(): Promise<KioskSttSettings> {
        try {
            const settings = await resetKioskSttSettings();
            store.set(settings);
            return settings;
        } catch (error) {
            console.error('Failed to reset kiosk STT settings:', error);
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
        get current(): KioskSttSettings {
            return get(store);
        },
    };
}

export const kioskSettingsStore = createKioskSettingsStore();

// Re-export types for convenience
export type { KioskSttSettings, KioskSttSettingsUpdate };
