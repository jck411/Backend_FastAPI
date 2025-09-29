export type WebSearchEngine = 'native' | 'exa';
export type WebSearchContextSize = 'low' | 'medium' | 'high';

export interface WebSearchSettings {
  enabled: boolean;
  engine: WebSearchEngine | null;
  maxResults: number | null;
  searchPrompt: string;
  contextSize: WebSearchContextSize | null;
}

export const DEFAULT_WEB_SEARCH_SETTINGS: WebSearchSettings = {
  enabled: false,
  engine: null,
  maxResults: 5,
  searchPrompt: '',
  contextSize: null,
};

export function normalizeWebSearchSettings(
  update: Partial<WebSearchSettings>,
  current: WebSearchSettings,
): WebSearchSettings {
  const next: WebSearchSettings = { ...current };

  if (Object.prototype.hasOwnProperty.call(update, 'enabled')) {
    next.enabled = Boolean(update.enabled);
  }

  if (Object.prototype.hasOwnProperty.call(update, 'engine')) {
    const value = update.engine;
    next.engine = value === 'native' || value === 'exa' ? value : null;
  }

  if (Object.prototype.hasOwnProperty.call(update, 'maxResults')) {
    const raw = update.maxResults;
    if (raw === null || raw === undefined) {
      next.maxResults = null;
    } else {
      const numeric = Number(raw);
      if (Number.isFinite(numeric) && numeric > 0) {
        next.maxResults = Math.min(Math.round(numeric), 25);
      } else {
        next.maxResults = current.maxResults;
      }
    }
  }

  if (Object.prototype.hasOwnProperty.call(update, 'searchPrompt')) {
    const value = update.searchPrompt;
    next.searchPrompt = typeof value === 'string' ? value : current.searchPrompt;
  }

  if (Object.prototype.hasOwnProperty.call(update, 'contextSize')) {
    const value = update.contextSize;
    next.contextSize = value === 'low' || value === 'medium' || value === 'high' ? value : null;
  }

  return next;
}
