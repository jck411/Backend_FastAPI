import { get, writable } from 'svelte/store';
import {
    applyPreset,
    createPreset,
    deletePreset,
    fetchDefaultPreset,
    fetchPresets,
    savePresetSnapshot,
    setDefaultPreset,
} from '../api/client';
import type { PresetConfig, PresetCreatePayload, PresetListItem, PresetSaveSnapshotPayload } from '../api/types';
import { modelStore } from './models';

interface PresetsState {
    loading: boolean;
    saving: boolean;
    applying: string | null;
    deleting: string | null;
    creating: boolean;
    settingDefault: string | null;
    error: string | null;
    items: PresetListItem[];
    lastApplied: string | null;
    lastResult: PresetConfig | null;
}

const INITIAL_STATE: PresetsState = {
    loading: false,
    saving: false,
    applying: null,
    deleting: null,
    creating: false,
    settingDefault: null,
    error: null,
    items: [],
    lastApplied: null,
    lastResult: null,
};

export function createPresetsStore() {
    const store = writable<PresetsState>({ ...INITIAL_STATE });

    async function load(): Promise<void> {
        store.update((s) => ({ ...s, loading: true, error: null }));
        try {
            const items = await fetchPresets();
            store.update((s) => ({
                ...s,
                loading: false,
                error: null,
                items,
            }));
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to load presets.';
            store.update((s) => ({
                ...s,
                loading: false,
                error: message,
            }));
        }
    }

    async function create(name: string): Promise<PresetConfig | null> {
        const payload: PresetCreatePayload = {
            name: name.trim(),
            model_filters: modelStore.getFilters()
        };
        if (!payload.name) {
            store.update((s) => ({ ...s, error: 'Preset name is required.' }));
            return null;
        }
        store.update((s) => ({ ...s, creating: true, error: null, lastResult: null }));
        try {
            const result = await createPreset(payload);
            // Refresh list to reflect timestamps and ordering
            const items = await fetchPresets();
            store.update((s) => ({
                ...s,
                creating: false,
                error: null,
                items,
                lastResult: result,
            }));
            return result;
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to create preset.';
            store.update((s) => ({ ...s, creating: false, error: message }));
            return null;
        }
    }

    async function saveSnapshot(name: string, payload?: PresetSaveSnapshotPayload | null): Promise<PresetConfig | null> {
        store.update((s) => ({ ...s, saving: true, error: null, lastResult: null }));
        try {
            const snapshotPayload = {
                ...payload,
                model_filters: modelStore.getFilters()
            };
            const result = await savePresetSnapshot(name, snapshotPayload);
            const items = await fetchPresets();
            store.update((s) => ({
                ...s,
                saving: false,
                error: null,
                items,
                lastResult: result,
            }));
            return result;
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to save snapshot.';
            store.update((s) => ({ ...s, saving: false, error: message }));
            return null;
        }
    }

    async function remove(name: string): Promise<boolean> {
        store.update((s) => ({ ...s, deleting: name, error: null }));
        try {
            const result = await deletePreset(name);
            const items = await fetchPresets();
            store.update((s) => ({
                ...s,
                deleting: null,
                items,
            }));
            return Boolean(result?.deleted);
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to delete preset.';
            store.update((s) => ({ ...s, deleting: null, error: message }));
            return false;
        }
    }

    async function apply(name: string): Promise<PresetConfig | null> {
        store.update((s) => ({ ...s, applying: name, error: null, lastApplied: null, lastResult: null }));
        try {
            // Check if the preset has filters from cached items to avoid extra fetch
            const currentState = get(store);
            const presetItem = currentState.items.find((item) => item.name === name);
            const hasFilters = presetItem?.has_filters ?? true; // Default to true if unknown

            const result = await applyPreset(name, hasFilters);
            // Always apply model filters from preset: set them if present, reset if absent
            if (result?.model_filters) {
                modelStore.setFilters(result.model_filters);
            } else {
                modelStore.resetFilters();
            }
            // Do not reload here; timestamps in list aren't critical on apply.
            store.update((s) => ({
                ...s,
                applying: null,
                lastApplied: name,
                lastResult: result,
            }));
            return result;
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to apply preset.';
            store.update((s) => ({ ...s, applying: null, error: message }));
            return null;
        }
    }

    async function setDefault(name: string): Promise<PresetConfig | null> {
        store.update((s) => ({ ...s, settingDefault: name, error: null }));
        try {
            const result = await setDefaultPreset(name);
            // Refresh list to reflect is_default changes
            const items = await fetchPresets();
            store.update((s) => ({
                ...s,
                settingDefault: null,
                items,
                lastResult: result,
            }));
            return result;
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to set default preset.';
            store.update((s) => ({ ...s, settingDefault: null, error: message }));
            return null;
        }
    }

    async function loadDefault(): Promise<PresetConfig | null> {
        try {
            return await fetchDefaultPreset();
        } catch (error) {
            console.error('Failed to load default preset:', error);
            return null;
        }
    }

    function clearError(): void {
        store.update((s) => ({ ...s, error: null }));
    }

    function clearLastApplied(): void {
        store.update((s) => ({ ...s, lastApplied: null, lastResult: null }));
    }

    return {
        subscribe: store.subscribe,
        load,
        create,
        saveSnapshot,
        remove,
        apply,
        setDefault,
        loadDefault,
        clearError,
        clearLastApplied,
    };
}

export const presetsStore = createPresetsStore();
