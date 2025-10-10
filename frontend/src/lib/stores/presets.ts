import { writable } from 'svelte/store';
import {
    applyPreset,
    createPreset,
    deletePreset,
    fetchPresets,
    savePresetSnapshot,
} from '../api/client';
import type { PresetConfig, PresetCreatePayload, PresetListItem, PresetSaveSnapshotPayload } from '../api/types';

interface PresetsState {
    loading: boolean;
    saving: boolean;
    applying: string | null;
    deleting: string | null;
    creating: boolean;
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
    error: null,
    items: [],
    lastApplied: null,
    lastResult: null,
};

export function createPresetsStore() {
    const store = writable<PresetsState>({ ...INITIAL_STATE });

    async function load(): Promise<void> {
        store.set({ ...INITIAL_STATE, loading: true });
        try {
            const items = await fetchPresets();
            store.set({
                ...INITIAL_STATE,
                loading: false,
                items,
            });
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to load presets.';
            store.set({
                ...INITIAL_STATE,
                loading: false,
                error: message,
            });
        }
    }

    async function create(name: string): Promise<PresetConfig | null> {
        const payload: PresetCreatePayload = { name: name.trim() };
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
            const result = await savePresetSnapshot(name, payload ?? undefined);
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
            const result = await applyPreset(name);
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

    function clearError(): void {
        store.update((s) => ({ ...s, error: null }));
    }

    return {
        subscribe: store.subscribe,
        load,
        create,
        saveSnapshot,
        remove,
        apply,
        clearError,
    };
}

export const presetsStore = createPresetsStore();
