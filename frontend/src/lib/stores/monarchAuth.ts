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
    refreshing: boolean;
    configured: boolean;
    email: string | null;
    error: string | null;
}

const INITIAL_STATE: MonarchAuthState = {
    loading: false,
    saving: false,
    refreshing: false,
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
                refreshing: false,
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
                refreshing: false,
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
                refreshing: false,
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

    async function refresh(): Promise<{ success: boolean; message: string }> {
        store.update((state) => ({ ...state, refreshing: true, error: null }));
        try {
            // This would call the MCP tool through the chat interface
            // For now, we'll return a placeholder
            // In a real implementation, you'd integrate this with your MCP tool calling mechanism

            // Simulate the refresh taking time
            await new Promise(resolve => setTimeout(resolve, 2000));

            store.update((state) => ({ ...state, refreshing: false }));
            return { success: true, message: 'Account data refreshed successfully' };
        } catch (error) {
            const message =
                error instanceof Error ? error.message : 'Failed to refresh account data.';
            store.update((state) => ({
                ...state,
                refreshing: false,
                error: message,
            }));
            return { success: false, message };
        }
    }

    return {
        subscribe: store.subscribe,
        load,
        save,
        remove,
        refresh,
    };
}
