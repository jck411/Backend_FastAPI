import { get, writable } from 'svelte/store';

export const SPEECH_SETTINGS_STORAGE_KEY = 'speech.settings.v1';

export interface SpeechSttSettings {
  provider: 'deepgram';
  model: string;
  interimResults: boolean;
  vadEvents: boolean;
  utteranceEndMs: number;
  endpointing: number;
  autoSubmit: boolean;
  smartFormat: boolean;
  punctuate: boolean;
  numerals: boolean;
  fillerWords: boolean;
  profanityFilter: boolean;
}

export interface SpeechConversationSettings {
  timeoutMs: number;
}

export interface SpeechSettings {
  stt: SpeechSttSettings;
  conversation: SpeechConversationSettings;
  updatedAt: string | null;
}

export type SpeechTimingPresetKey = 'fast' | 'normal' | 'slow';

export interface SpeechTimingPreset {
  label: string;
  stt: Pick<SpeechSttSettings, 'utteranceEndMs' | 'endpointing'>;
  conversation: Pick<SpeechConversationSettings, 'timeoutMs'>;
}

export const SPEECH_TIMING_PRESETS: Record<SpeechTimingPresetKey, SpeechTimingPreset> = {
  fast: {
    label: 'Fast speech',
    stt: {
      utteranceEndMs: 1000,
      endpointing: 800,
    },
    conversation: {
      timeoutMs: 5000,
    },
  },
  normal: {
    label: 'Normal speech',
    stt: {
      utteranceEndMs: 1500,
      endpointing: 1200,
    },
    conversation: {
      timeoutMs: 6000,
    },
  },
  slow: {
    label: 'Slow speech',
    stt: {
      utteranceEndMs: 2500,
      endpointing: 2000,
    },
    conversation: {
      timeoutMs: 8000,
    },
  },
};

export const DEEPGRAM_MODEL_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'nova-3-general', label: 'Nova-3 General' },
  { value: 'nova-3-medical', label: 'Nova-3 Medical' },
  { value: 'nova-2-finance', label: 'Nova-2 Finance' },
  { value: 'nova-2-conversationalai', label: 'Nova-2 Conversational AI' },
];

const DEFAULT_SPEECH_SETTINGS: SpeechSettings = {
  stt: {
    provider: 'deepgram',
    model: 'nova-3',
    interimResults: true,
    vadEvents: true,
    utteranceEndMs: 1500,
    endpointing: 1200,
    autoSubmit: true,
    smartFormat: true,
    punctuate: true,
    numerals: true,
    fillerWords: false,
    profanityFilter: false,
  },
  conversation: {
    timeoutMs: 6000,
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
    conversation: { ...defaults.conversation },
    updatedAt: defaults.updatedAt,
  };

  if (!input || typeof input !== 'object') {
    return result;
  }

  const data = input as Record<string, unknown>;

  const sttRaw = data.stt ?? data['stt'];
  if (sttRaw && typeof sttRaw === 'object') {
    const stt = sttRaw as Record<string, unknown>;
    const model = typeof stt.model === 'string' && stt.model.trim()
      ? stt.model.trim()
      : typeof stt.model === 'string'
        ? stt.model
        : typeof stt['model'] === 'string' && stt['model'].trim()
          ? (stt['model'] as string).trim()
          : defaults.stt.model;
    result.stt.provider = 'deepgram';
    result.stt.model = model;
    result.stt.interimResults = toBoolean(stt.interimResults ?? stt['interim_results'], defaults.stt.interimResults);
    result.stt.vadEvents = toBoolean(stt.vadEvents ?? stt['vad_events'], defaults.stt.vadEvents);

    const utterance = readNumber(stt.utteranceEndMs ?? stt['utterance_end_ms']);
    if (utterance !== null) {
      result.stt.utteranceEndMs = clampNumber(utterance, 500, 5000);
    }

    const endpointing = readNumber(stt.endpointing);
    if (endpointing !== null) {
      result.stt.endpointing = clampNumber(endpointing, 300, 5000);
    }

    result.stt.autoSubmit = toBoolean(stt.autoSubmit ?? stt['auto_submit'], defaults.stt.autoSubmit);
    result.stt.smartFormat = toBoolean(stt.smartFormat ?? stt['smart_format'], defaults.stt.smartFormat);
    result.stt.punctuate = toBoolean(stt.punctuate, defaults.stt.punctuate);
    result.stt.numerals = toBoolean(stt.numerals, defaults.stt.numerals);
    result.stt.fillerWords = toBoolean(stt.fillerWords ?? stt['filler_words'], defaults.stt.fillerWords);
    result.stt.profanityFilter = toBoolean(
      stt.profanityFilter ?? stt['profanity_filter'],
      defaults.stt.profanityFilter,
    );
  }

  const conversationRaw = data.conversation ?? data['conversation'];
  if (conversationRaw && typeof conversationRaw === 'object') {
    const conversation = conversationRaw as Record<string, unknown>;
    const timeout = readNumber(conversation.timeoutMs ?? conversation['timeout_ms']);
    if (timeout !== null) {
      result.conversation.timeoutMs = clampNumber(timeout, 3000, 120000);
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
      conversation: { ...sanitized.conversation },
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
      conversation: { ...current.conversation },
      updatedAt: current.updatedAt,
    };

    if (partial.stt) {
      merged.stt = { ...merged.stt, ...partial.stt };
    }
    if (partial.conversation) {
      merged.conversation = { ...merged.conversation, ...partial.conversation };
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
