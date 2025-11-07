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
  plannerEnabled: boolean;
  initialPlannerEnabled: boolean;
  dirty: boolean;
}

const INITIAL_STATE: SystemPromptState = {
  loading: false,
  saving: false,
  error: null,
  saveError: null,
  value: '',
  initialValue: '',
  plannerEnabled: true,
  initialPlannerEnabled: true,
  dirty: false,
};

export function createSystemPromptStore() {
  const store = writable<SystemPromptState>({ ...INITIAL_STATE });

  function computeDirty(
    value: string,
    plannerEnabled: boolean,
    initialValue: string,
    initialPlannerEnabled: boolean,
  ): boolean {
    return value.trim() !== initialValue.trim() || plannerEnabled !== initialPlannerEnabled;
  }

  function normalizeResponse(response: SystemPromptResponse): {
    prompt: string;
    plannerEnabled: boolean;
  } {
    const prompt = response.system_prompt?.trim() ?? '';
    const plannerEnabled =
      typeof response.llm_planner_enabled === 'boolean'
        ? response.llm_planner_enabled
        : true;
    return { prompt, plannerEnabled };
  }

  async function load(): Promise<void> {
    store.set({ ...INITIAL_STATE, loading: true });
    try {
      const response = await fetchSystemPrompt();
      const { prompt, plannerEnabled } = normalizeResponse(response);
      store.set({
        loading: false,
        saving: false,
        error: null,
        saveError: null,
        value: prompt,
        initialValue: prompt,
        plannerEnabled,
        initialPlannerEnabled: plannerEnabled,
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
        dirty: computeDirty(
          normalized,
          state.plannerEnabled,
          state.initialValue,
          state.initialPlannerEnabled,
        ),
        saveError: null,
      };
    });
  }

  async function save(): Promise<void> {
    let currentValue = '';
    let currentPlannerEnabled = true;
    store.update((state) => {
      currentValue = state.value;
      currentPlannerEnabled = state.plannerEnabled;
      return { ...state, saving: true, saveError: null };
    });

    const payload = {
      system_prompt: currentValue.trim() || null,
      llm_planner_enabled: currentPlannerEnabled,
    };

    try {
      const response = await updateSystemPrompt(payload);
      const { prompt, plannerEnabled } = normalizeResponse(response);
      store.set({
        loading: false,
        saving: false,
        error: null,
        saveError: null,
        value: prompt,
        initialValue: prompt,
        plannerEnabled,
        initialPlannerEnabled: plannerEnabled,
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
      plannerEnabled: state.initialPlannerEnabled,
      dirty: false,
      saveError: null,
    }));
  }

  function setPlannerEnabled(enabled: boolean): void {
    store.update((state) => {
      const plannerEnabled = Boolean(enabled);
      return {
        ...state,
        plannerEnabled,
        dirty: computeDirty(
          state.value,
          plannerEnabled,
          state.initialValue,
          state.initialPlannerEnabled,
        ),
        saveError: null,
      };
    });
  }

  return {
    subscribe: store.subscribe,
    load,
    save,
    reset,
    updateValue,
    setPlannerEnabled,
  };
}

export type { SystemPromptState };
