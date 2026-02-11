/**
 * Speech Settings Store
 *
 * Manages frontend-only speech behavior settings.
 * Note: Deepgram/STT parameters are now configured server-side via /api/clients/svelte/stt
 * This store only handles frontend behavior like auto-submit timing.
 */
import { get, writable } from 'svelte/store';

export const SPEECH_SETTINGS_STORAGE_KEY = 'speech.settings.v2';

export interface SpeechSttSettings {
  /** Whether to auto-submit after speech ends */
  autoSubmit: boolean;
  /** Delay in ms before auto-submitting (0 = immediate) */
  autoSubmitDelayMs: number;
}

export interface SpeechSettings {
  stt: SpeechSttSettings;
  updatedAt: string | null;
}

export type SpeechTimingPresetKey = 'fast' | 'normal' | 'slow';

export interface SpeechTimingPreset {
  label: string;
  autoSubmitDelayMs: number;
}

export const SPEECH_TIMING_PRESETS: Record<SpeechTimingPresetKey, SpeechTimingPreset> = {
  fast: {
    label: 'Fast',
    autoSubmitDelayMs: 0,
  },
  normal: {
    label: 'Normal',
    autoSubmitDelayMs: 300,
  },
  slow: {
    label: 'Slow',
    autoSubmitDelayMs: 800,
  },
};

const DEFAULT_SPEECH_SETTINGS: SpeechSettings = {
  stt: {
    autoSubmit: true,
    autoSubmitDelayMs: 0,
  },
  updatedAt: null,
};

function cloneSettings(value: SpeechSettings): SpeechSettings {
  return JSON.parse(JSON.stringify(value)) as SpeechSettings;
}

export function getDefaultSpeechSettings(): SpeechSettings {
  return cloneSettings(DEFAULT_SPEECH_SETTINGS);
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(Math.max(Math.round(value), min), max);
}

function toBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function readNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function sanitizeSpeechSettings(input: unknown): SpeechSettings {
  const defaults = getDefaultSpeechSettings();
  const result: SpeechSettings = {
    stt: { ...defaults.stt },
    updatedAt: defaults.updatedAt,
  };

  if (!input || typeof input !== 'object') {
    return result;
  }

  const data = input as Record<string, unknown>;

  const sttRaw = data.stt ?? data['stt'];
  if (sttRaw && typeof sttRaw === 'object') {
    const stt = sttRaw as Record<string, unknown>;

    result.stt.autoSubmit = toBoolean(stt.autoSubmit ?? stt['auto_submit'], defaults.stt.autoSubmit);
    const autoSubmitDelay = readNumber(stt.autoSubmitDelayMs ?? stt['auto_submit_delay_ms']);
    if (autoSubmitDelay !== null) {
      result.stt.autoSubmitDelayMs = clampNumber(autoSubmitDelay, 0, 10000);
    }
  }

  const updatedAtRaw = data.updatedAt ?? data['updated_at'];
  result.updatedAt = typeof updatedAtRaw === 'string' && updatedAtRaw ? updatedAtRaw : null;

  return result;
}

function readFromStorage(): SpeechSettings {
  if (typeof window === 'undefined' || !window.localStorage) {
    return getDefaultSpeechSettings();
  }
  try {
    const raw = window.localStorage.getItem(SPEECH_SETTINGS_STORAGE_KEY);
    if (!raw) {
      return getDefaultSpeechSettings();
    }
    const parsed = JSON.parse(raw);
    return sanitizeSpeechSettings(parsed);
  } catch (error) {
    console.warn('Failed to read speech settings from storage', error);
    return getDefaultSpeechSettings();
  }
}

function persistToStorage(settings: SpeechSettings): void {
  if (typeof window === 'undefined' || !window.localStorage) {
    return;
  }
  try {
    window.localStorage.setItem(SPEECH_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch (error) {
    console.warn('Failed to persist speech settings', error);
  }
}

function createSpeechSettingsStore() {
  const initial = readFromStorage();
  const store = writable<SpeechSettings>(initial);

  function save(next: SpeechSettings): SpeechSettings {
    const sanitized = sanitizeSpeechSettings(next);
    const withTimestamp: SpeechSettings = {
      ...sanitized,
      stt: { ...sanitized.stt },
      updatedAt: new Date().toISOString(),
    };
    store.set(withTimestamp);
    persistToStorage(withTimestamp);
    return withTimestamp;
  }

  function updateSettings(partial: Partial<SpeechSettings>): SpeechSettings {
    const current = get(store);
    const merged: SpeechSettings = {
      ...current,
      stt: { ...current.stt },
      updatedAt: current.updatedAt,
    };

    if (partial.stt) {
      merged.stt = { ...merged.stt, ...partial.stt };
    }
    if (partial.updatedAt !== undefined) {
      merged.updatedAt = partial.updatedAt;
    }

    return save(merged);
  }

  function reset(): SpeechSettings {
    return save(getDefaultSpeechSettings());
  }

  function refreshFromStorage(): void {
    const fresh = readFromStorage();
    store.set(fresh);
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('storage', (event) => {
      if (event.key === SPEECH_SETTINGS_STORAGE_KEY) {
        try {
          const value = event.newValue ? JSON.parse(event.newValue) : null;
          const sanitized = sanitizeSpeechSettings(value);
          store.set(sanitized);
        } catch (error) {
          console.warn('Failed to synchronize speech settings from storage', error);
        }
      }
    });
  }

  return {
    subscribe: store.subscribe,
    save,
    update: updateSettings,
    reset,
    refresh: refreshFromStorage,
    get current(): SpeechSettings {
      return get(store);
    },
  };
}

export const speechSettingsStore = createSpeechSettingsStore();
