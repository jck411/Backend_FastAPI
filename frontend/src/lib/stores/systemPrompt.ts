import { writable } from 'svelte/store';
import { fetchSystemPrompt, updateSystemPrompt } from '../api/client';
import type { SystemPromptResponse } from '../api/types';

interface SystemPromptState {
  loading: boolean;
  saving: boolean;
  error: string | null;
  saveError: string | null;
  value: string;
  initialValue: string;
  dirty: boolean;
}

const INITIAL_STATE: SystemPromptState = {
  loading: false,
  saving: false,
  error: null,
  saveError: null,
  value: '',
  initialValue: '',
  dirty: false,
};

export function createSystemPromptStore() {
  const store = writable<SystemPromptState>({ ...INITIAL_STATE });

  function computeDirty(value: string, initialValue: string): boolean {
    return value.trim() !== initialValue.trim();
  }

  function normalizeResponse(response: SystemPromptResponse): string {
    return response.system_prompt?.trim() ?? '';
  }

  async function load(): Promise<void> {
    store.set({ ...INITIAL_STATE, loading: true });
    try {
      const response = await fetchSystemPrompt();
      const prompt = normalizeResponse(response);
      store.set({
        loading: false,
        saving: false,
        error: null,
        saveError: null,
        value: prompt,
        initialValue: prompt,
        dirty: false,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load system prompt.';
      store.set({
        ...INITIAL_STATE,
        loading: false,
        error: message,
      });
    }
  }

  function updateValue(value: string): void {
    store.update((state) => {
      const normalized = value;
      return {
        ...state,
        value: normalized,
        dirty: computeDirty(normalized, state.initialValue),
        saveError: null,
      };
    });
  }

  async function save(): Promise<void> {
    let currentValue = '';
    store.update((state) => {
      currentValue = state.value;
      return { ...state, saving: true, saveError: null };
    });

    const payload = {
      system_prompt: currentValue.trim() || null,
    };

    try {
      const response = await updateSystemPrompt(payload);
      const prompt = normalizeResponse(response);
      store.set({
        loading: false,
        saving: false,
        error: null,
        saveError: null,
        value: prompt,
        initialValue: prompt,
        dirty: false,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save system prompt.';
      store.update((state) => ({
        ...state,
        saving: false,
        saveError: message,
      }));
    }
  }

  function reset(): void {
    store.update((state) => ({
      ...state,
      value: state.initialValue,
      dirty: false,
      saveError: null,
    }));
  }

  return {
    subscribe: store.subscribe,
    load,
    save,
    reset,
    updateValue,
  };
}

export type { SystemPromptState };
