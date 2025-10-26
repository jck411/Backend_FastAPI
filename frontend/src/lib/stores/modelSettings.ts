import { get, writable } from 'svelte/store';
import { fetchModelSettings, updateModelSettings } from '../api/client';
import type {
  ActiveModelSettingsPayload,
  ActiveModelSettingsResponse,
  ModelHyperparameters,
} from '../api/types';

interface ModelSettingsState {
  loading: boolean;
  saving: boolean;
  error: string | null;
  saveError: string | null;
  dirty: boolean;
  data: ActiveModelSettingsResponse | null;
  lastSyncedModel: string | null;
  lastSavedAt: number | null;
  version: number;
}

const INITIAL_STATE: ModelSettingsState = {
  loading: false,
  saving: false,
  error: null,
  saveError: null,
  dirty: false,
  data: null,
  lastSyncedModel: null,
  lastSavedAt: null,
  version: 0,
};

function sanitizeParameters(
  parameters: ModelHyperparameters | null | undefined,
): ModelHyperparameters | undefined {
  if (!parameters) {
    return undefined;
  }

  const sanitized: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(parameters)) {
    if (value === undefined || value === null) {
      continue;
    }
    if (typeof value === 'string' && value.trim() === '') {
      continue;
    }
    if (Array.isArray(value)) {
      if (value.length === 0) {
        continue;
      }
      sanitized[key] = value;
      continue;
    }
    if (typeof value === 'object') {
      const entries = Object.entries(value as Record<string, unknown>);
      if (entries.length === 0) {
        continue;
      }
      sanitized[key] = value;
      continue;
    }
    sanitized[key] = value;
  }

  return Object.keys(sanitized).length > 0 ? (sanitized as ModelHyperparameters) : undefined;
}

export function createModelSettingsStore() {
  const store = writable<ModelSettingsState>({ ...INITIAL_STATE });
  let loadSequence = 0;

  async function flushSave(): Promise<boolean> {
    const snapshot = get(store);
    if (!snapshot.dirty || !snapshot.data) {
      if (snapshot.dirty) {
        store.update((state) => ({ ...state, dirty: false }));
      }
      return true;
    }

    const version = snapshot.version;
    const payload: ActiveModelSettingsPayload = {
      model: snapshot.data.model,
      provider: snapshot.data.provider ?? null,
    };
    if ('supports_tools' in snapshot.data) {
      payload.supports_tools =
        snapshot.data.supports_tools === undefined
          ? null
          : snapshot.data.supports_tools;
    }
    const sanitized = sanitizeParameters(snapshot.data.parameters);
    if (sanitized) {
      payload.parameters = sanitized;
    } else {
      payload.parameters = null;
    }

    store.update((state) => ({ ...state, saving: true, saveError: null }));

    try {
      const response = await updateModelSettings(payload);
      store.update((state) => {
        const now = Date.now();
        if (state.version !== version) {
          return {
            ...state,
            saving: false,
            saveError: null,
            lastSavedAt: now,
            lastSyncedModel: response.model,
          };
        }
        return {
          ...state,
          saving: false,
          saveError: null,
          dirty: false,
          data: response,
          lastSyncedModel: response.model,
          lastSavedAt: now,
        };
      });
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save model settings.';
      store.update((state) => ({ ...state, saving: false, saveError: message }));
      return false;
    }
  }

  async function load(selectedModel: string): Promise<void> {
    const sequence = ++loadSequence;
    store.set({ ...INITIAL_STATE, loading: true });

    try {
      const response = await fetchModelSettings();
      let data = response;
      if (selectedModel && response.model !== selectedModel) {
        data = await updateModelSettings({ model: selectedModel, parameters: null, provider: null });
      }
      if (sequence !== loadSequence) {
        return;
      }
      store.set({
        loading: false,
        saving: false,
        error: null,
        saveError: null,
        dirty: false,
        data,
        lastSyncedModel: data.model,
        lastSavedAt: Date.now(),
        version: 0,
      });
    } catch (error) {
      if (sequence !== loadSequence) {
        return;
      }
      const message = error instanceof Error ? error.message : 'Failed to load model settings.';
      store.set({
        ...INITIAL_STATE,
        error: message,
      });
    }
  }

  function updateParameter<Key extends keyof ModelHyperparameters>(
    key: Key,
    value: ModelHyperparameters[Key] | null,
  ): void {
    store.update((state) => {
      if (!state.data) {
        return state;
      }
      const nextParameters = { ...(state.data.parameters ?? {}) } as ModelHyperparameters;
      if (value === null || value === undefined) {
        delete (nextParameters as Record<string, unknown>)[key as string];
      } else {
        (nextParameters as Record<string, unknown>)[key as string] = value;
      }
      const data: ActiveModelSettingsResponse = {
        ...state.data,
        parameters: Object.keys(nextParameters).length > 0 ? nextParameters : null,
      };
      return {
        ...state,
        data,
        dirty: true,
        saveError: null,
        version: state.version + 1,
      };
    });
  }

  function setModel(model: string): void {
    store.update((state) => {
      if (!state.data || state.data.model === model) {
        return state;
      }
      const data: ActiveModelSettingsResponse = {
        ...state.data,
        model,
      };
      return {
        ...state,
        data,
        dirty: true,
        saveError: null,
        version: state.version + 1,
      };
    });
  }

  function resetToDefaults(): void {
    store.update((state) => {
      if (!state.data) {
        return state;
      }
      const data: ActiveModelSettingsResponse = {
        ...state.data,
        parameters: null,
      };
      return {
        ...state,
        data,
        dirty: true,
        saveError: null,
        version: state.version + 1,
      };
    });
  }

  function clearErrors(): void {
    store.update((state) => ({ ...state, error: null, saveError: null }));
  }

  return {
    subscribe: store.subscribe,
    load,
    updateParameter,
    setModel,
    resetToDefaults,
    clearErrors,
    flushSave,
  };
}

export const modelSettingsStore = createModelSettingsStore();
