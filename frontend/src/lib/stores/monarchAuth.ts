import { writable } from 'svelte/store';
import {
    deleteMonarchCredentials,
    fetchMonarchStatus,
    saveMonarchCredentials,
} from '../api/client';
import type { MonarchCredentials } from '../api/types';

interface MonarchAuthState {
    loading: boolean;
    saving: boolean;
    configured: boolean;
    email: string | null;
    error: string | null;
}

const INITIAL_STATE: MonarchAuthState = {
    loading: false,
    saving: false,
    configured: false,
    email: null,
    error: null,
};

export function createMonarchAuthStore() {
    const store = writable<MonarchAuthState>({ ...INITIAL_STATE });

    async function load(): Promise<void> {
        store.update((state) => ({ ...state, loading: true, error: null }));
        try {
            const response = await fetchMonarchStatus();
            store.set({
                loading: false,
                saving: false,
                configured: response.configured,
                email: response.email,
                error: null,
            });
        } catch (error) {
            const message =
                error instanceof Error ? error.message : 'Failed to check Monarch status.';
            store.set({
                ...INITIAL_STATE,
                loading: false,
                error: message,
            });
        }
    }

    async function save(creds: MonarchCredentials): Promise<boolean> {
        store.update((state) => ({ ...state, saving: true, error: null }));
        try {
            const response = await saveMonarchCredentials(creds);
            store.set({
                loading: false,
                saving: false,
                configured: response.configured,
                email: response.email,
                error: null,
            });
            return true;
        } catch (error) {
            const message =
                error instanceof Error ? error.message : 'Failed to save Monarch credentials.';
            store.update((state) => ({
                ...state,
                saving: false,
                error: message,
            }));
            return false;
        }
    }

    async function remove(): Promise<boolean> {
        store.update((state) => ({ ...state, saving: true, error: null }));
        try {
            const response = await deleteMonarchCredentials();
            store.set({
                loading: false,
                saving: false,
                configured: response.configured,
                email: response.email,
                error: null,
            });
            return true;
        } catch (error) {
            const message =
                error instanceof Error ? error.message : 'Failed to remove Monarch credentials.';
            store.update((state) => ({
                ...state,
                saving: false,
                error: message,
            }));
            return false;
        }
    }

    return {
        subscribe: store.subscribe,
        load,
        save,
        remove,
    };
}
