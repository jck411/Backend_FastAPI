import { writable } from 'svelte/store';
import { API_BASE_URL } from '../api/config';
import type { Suggestion, SuggestionsResponse } from '../api/types';

interface SuggestionsState {
    loading: boolean;
    adding: boolean;
    deleting: number | null;
    error: string | null;
    items: Suggestion[];
}

const INITIAL_STATE: SuggestionsState = {
    loading: false,
    adding: false,
    deleting: null,
    error: null,
    items: [],
};

export function createSuggestionsStore() {
    const store = writable<SuggestionsState>({ ...INITIAL_STATE });

    async function load(): Promise<void> {
        store.update((s) => ({ ...s, loading: true, error: null }));
        try {
            const response = await fetch(`${API_BASE_URL}/api/suggestions`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data: SuggestionsResponse = await response.json();
            store.update((s) => ({
                ...s,
                loading: false,
                items: data.suggestions,
            }));
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to load suggestions.';
            store.update((s) => ({ ...s, loading: false, error: message }));
        }
    }

    async function add(label: string, text: string): Promise<Suggestion[] | null> {
        store.update((s) => ({ ...s, adding: true, error: null }));
        try {
            const response = await fetch(`${API_BASE_URL}/api/suggestions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label, text }),
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data: SuggestionsResponse = await response.json();
            store.update((s) => ({
                ...s,
                adding: false,
                items: data.suggestions,
            }));
            return data.suggestions;
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to add suggestion.';
            store.update((s) => ({ ...s, adding: false, error: message }));
            return null;
        }
    }

    async function remove(index: number): Promise<Suggestion[] | null> {
        store.update((s) => ({ ...s, deleting: index, error: null }));
        try {
            const response = await fetch(`${API_BASE_URL}/api/suggestions/${index}`, {
                method: 'DELETE',
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data: SuggestionsResponse = await response.json();
            store.update((s) => ({
                ...s,
                deleting: null,
                items: data.suggestions,
            }));
            return data.suggestions;
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to delete suggestion.';
            store.update((s) => ({ ...s, deleting: null, error: message }));
            return null;
        }
    }

    function clearError(): void {
        store.update((s) => ({ ...s, error: null }));
    }

    return {
        subscribe: store.subscribe,
        load,
        add,
        remove,
        clearError,
    };
}

export const suggestionsStore = createSuggestionsStore();
