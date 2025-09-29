import { derived, get, writable } from 'svelte/store';
import {
  DEFAULT_WEB_SEARCH_SETTINGS,
  normalizeWebSearchSettings,
  type WebSearchSettings,
} from './webSearch';

function createWebSearchStore(initial: WebSearchSettings = DEFAULT_WEB_SEARCH_SETTINGS) {
  const settings = writable<WebSearchSettings>({ ...initial });

  function update(settingsPatch: Partial<WebSearchSettings>): void {
    settings.update((current) => normalizeWebSearchSettings(settingsPatch, current));
  }

  function setEnabled(enabled: boolean): void {
    settings.update((current) => normalizeWebSearchSettings({ enabled }, current));
  }

  function reset(): void {
    settings.set({ ...DEFAULT_WEB_SEARCH_SETTINGS });
  }

  const isEnabled = derived(settings, ($settings) => $settings.enabled);

  return {
    subscribe: settings.subscribe,
    get current(): WebSearchSettings {
      return get(settings);
    },
    update,
    setEnabled,
    reset,
    isEnabled,
  };
}

export type WebSearchStore = ReturnType<typeof createWebSearchStore>;

export const webSearchStore = createWebSearchStore();
