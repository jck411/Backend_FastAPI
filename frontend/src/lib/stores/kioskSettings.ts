/**
 * Kiosk settings store.
 * Fetches from and persists to the backend API (both STT and UI settings).
 */

import { get, writable } from 'svelte/store';
import {
    type KioskSttSettings,
    type KioskSttSettingsUpdate,
    type KioskUiSettings,
    type KioskUiSettingsUpdate,
    fetchKioskSttSettings,
    fetchKioskUiSettings,
    resetKioskSttSettings,
    updateKioskSttSettings,
    updateKioskUiSettings,
} from '../api/kiosk';

// Combined settings type
export interface KioskSettings extends KioskSttSettings, KioskUiSettings { }
export interface KioskSettingsUpdate extends KioskSttSettingsUpdate, KioskUiSettingsUpdate { }

export const DEFAULT_KIOSK_STT_SETTINGS: KioskSttSettings = {
    eot_threshold: 0.7,
    eot_timeout_ms: 5000,
    eager_eot_threshold: null,
    keyterms: [],
};

export const DEFAULT_KIOSK_UI_SETTINGS: KioskUiSettings = {
    idle_return_delay_ms: 10000,
};

export const DEFAULT_KIOSK_SETTINGS: KioskSettings = {
    ...DEFAULT_KIOSK_STT_SETTINGS,
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
            // Load both STT and UI settings in parallel
            const [sttSettings, uiSettings] = await Promise.all([
                fetchKioskSttSettings(),
                fetchKioskUiSettings(),
            ]);
            const combined: KioskSettings = { ...sttSettings, ...uiSettings };
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
            const uiUpdate: KioskUiSettingsUpdate = {};

            if (update.eot_threshold !== undefined) sttUpdate.eot_threshold = update.eot_threshold;
            if (update.eot_timeout_ms !== undefined) sttUpdate.eot_timeout_ms = update.eot_timeout_ms;
            if (update.eager_eot_threshold !== undefined) sttUpdate.eager_eot_threshold = update.eager_eot_threshold;
            if (update.keyterms !== undefined) sttUpdate.keyterms = update.keyterms;
            if (update.idle_return_delay_ms !== undefined) uiUpdate.idle_return_delay_ms = update.idle_return_delay_ms;

            const promises: Promise<unknown>[] = [];

            if (Object.keys(sttUpdate).length > 0) {
                promises.push(updateKioskSttSettings(sttUpdate));
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
            // Reset STT settings (UI settings don't have a reset endpoint yet)
            const sttSettings = await resetKioskSttSettings();
            const current = get(store);
            const combined: KioskSettings = { ...sttSettings, idle_return_delay_ms: current.idle_return_delay_ms };
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
export type { KioskSttSettings, KioskSttSettingsUpdate, KioskUiSettings, KioskUiSettingsUpdate };
