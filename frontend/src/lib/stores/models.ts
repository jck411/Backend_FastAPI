import { writable } from 'svelte/store';
import { fetchModels } from '../api/client';
import type { ModelListResponse, ModelRecord } from '../api/types';

interface ModelState {
  models: ModelRecord[];
  loading: boolean;
  error: string | null;
}

const initialState: ModelState = {
  models: [],
  loading: false,
  error: null,
};

function createModelStore() {
  const store = writable<ModelState>({ ...initialState });

  async function loadModels(): Promise<ModelListResponse | void> {
    store.update((value) => ({ ...value, loading: true, error: null }));
    try {
      const response = await fetchModels();
      const models = Array.isArray(response.data) ? response.data : [];
      store.set({ models, loading: false, error: null });
      return response;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      store.set({ models: [], loading: false, error: message });
    }
  }

  return {
    subscribe: store.subscribe,
    loadModels,
  };
}

export const modelStore = createModelStore();
