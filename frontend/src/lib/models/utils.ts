import type { ModelPricing, ModelRecord } from '../api/types';

const SERIES_KEYWORDS: Array<{ label: string; keywords: string[] }> = [
  { label: 'GPT', keywords: ['gpt', 'openai', 'o1', 'o3'] },
  { label: 'Claude', keywords: ['claude'] },
  { label: 'Gemini', keywords: ['gemini', 'palm-2', 'palm2'] },
  { label: 'Grok', keywords: ['grok'] },
  { label: 'Cohere', keywords: ['cohere', 'command'] },
  { label: 'Nova', keywords: ['nova'] },
  { label: 'Qwen', keywords: ['qwen'] },
  { label: 'Yi', keywords: ['yi'] },
  { label: 'DeepSeek', keywords: ['deepseek'] },
  { label: 'Mistral', keywords: ['mistral', 'mixtral'] },
  { label: 'Llama4', keywords: ['llama-4'] },
  { label: 'Llama3', keywords: ['llama-3'] },
  { label: 'Llama2', keywords: ['llama-2'] },
  { label: 'RWKV', keywords: ['rwkv'] },
  { label: 'Router', keywords: ['router'] },
  { label: 'Media', keywords: ['media'] },
  { label: 'Other', keywords: [] },
];

export function asNumeric(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function collectModalities(source: unknown): string[] {
  const values: string[] = [];
  if (Array.isArray(source)) {
    for (const item of source) {
      if (typeof item === 'string' && item.trim()) {
        values.push(item.trim().toLowerCase());
      }
    }
    return values;
  }
  if (typeof source === 'string' && source.trim()) {
    return source
      .split(/[,/]/)
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean);
  }
  if (source && typeof source === 'object') {
    const maybeValues = Object.values(source as Record<string, unknown>);
    for (const value of maybeValues) {
      values.push(...collectModalities(value));
    }
  }
  return values;
}

export function extractInputModalities(model: ModelRecord): string[] {
  const values = new Set<string>();
  const { capabilities, tags } = model;
  if (capabilities && typeof capabilities === 'object') {
    const record = capabilities as Record<string, unknown>;
    for (const key of ['input_modalities', 'input', 'modalities', 'inputs']) {
      addValues(record[key]);
    }
  }
  addValues((model as Record<string, unknown>).input_modalities);
  addValues(tags);
  return Array.from(values);

  function addValues(source: unknown) {
    for (const entry of collectModalities(source)) {
      values.add(entry);
    }
  }
}

export function extractOutputModalities(model: ModelRecord): string[] {
  const values = new Set<string>();
  const { capabilities, tags } = model;
  if (capabilities && typeof capabilities === 'object') {
    const record = capabilities as Record<string, unknown>;
    for (const key of ['output_modalities', 'output', 'outputs']) {
      addValues(record[key]);
    }
    const modalities = record.modalities as Record<string, unknown> | undefined;
    if (modalities) {
      addValues(modalities.output);
      addValues(modalities.outputs);
    }
  }
  addValues((model as Record<string, unknown>).output_modalities);
  addValues(tags);
  return Array.from(values);

  function addValues(source: unknown) {
    for (const entry of collectModalities(source)) {
      values.add(entry);
    }
  }
}

export function extractPromptPrice(pricing?: ModelPricing | null): number | null {
  if (!pricing) return null;
  const value = asNumeric(pricing.prompt ?? pricing.request ?? pricing.completion ?? pricing.image ?? null);
  if (value === null) return null;
  if (value < 0) {
    return null;
  }
  return value;
}

export function extractContextLength(model: ModelRecord): number | null {
  const candidates = [
    (model as Record<string, unknown>).max_context,
    (model as Record<string, unknown>).context_length,
    (model as Record<string, unknown>).context_window,
    (model as Record<string, unknown>).context_tokens,
    (model.stats as Record<string, unknown> | undefined)?.context_length,
  ];
  for (const candidate of candidates) {
    const numeric = asNumeric(candidate);
    if (numeric !== null) {
      return numeric;
    }
  }
  return null;
}

export function formatPrice(value: number | null): string {
  if (value === null) return '—';
  if (value === 0) return 'Free';
  if (value >= 1) return `$${value.toFixed(2)}`;
  if (value >= 0.01) return `$${value.toFixed(3)}`;
  return `$${value.toFixed(4)}`;
}

export function formatContext(value: number | null): string {
  if (value === null) return 'Unknown';
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}k tokens`;
  }
  return `${value} tokens`;
}

export function extractProviderName(model: ModelRecord): string | null {
  const provider = model.provider;
  if (provider && typeof provider === 'object') {
    const record = provider as Record<string, unknown>;
    const display = record.display_name;
    if (typeof display === 'string' && display.trim()) {
      return display.trim();
    }
    const name = record.name ?? record.id ?? record.slug;
    if (typeof name === 'string' && name.trim()) {
      return name.trim();
    }
  }
  if (typeof (model as Record<string, unknown>).provider === 'string') {
    const value = (model as Record<string, unknown>).provider as string;
    return value.trim() || null;
  }
  const parts = model.id?.split('/') ?? [];
  if (parts.length >= 2) {
    return parts[parts.length - 2] ?? null;
  }
  return null;
}

export function extractSeries(model: ModelRecord): string[] {
  const labels = new Set<string>();
  const haystack: string[] = [];

  if (typeof model.id === 'string') {
    haystack.push(model.id.toLowerCase());
  }
  if (typeof model.name === 'string') {
    haystack.push(model.name.toLowerCase());
  }
  if (Array.isArray(model.tags)) {
    haystack.push(...model.tags.map((tag) => String(tag).toLowerCase()));
  }

  const combined = haystack.join(' ');
  for (const entry of SERIES_KEYWORDS) {
    if (entry.label === 'Other') {
      continue;
    }
    if (entry.keywords.some((keyword) => combined.includes(keyword))) {
      labels.add(entry.label);
    }
  }

  if (labels.size === 0) {
    labels.add('Other');
  }

  return Array.from(labels);
}

export function extractSupportedParameters(model: ModelRecord): string[] {
  const values = new Set<string>();
  const candidates: unknown[] = [];
  const record = model as Record<string, unknown>;

  candidates.push(record.parameters, record.supported_parameters);

  if (model.capabilities && typeof model.capabilities === 'object') {
    const capabilities = model.capabilities as Record<string, unknown>;
    candidates.push(capabilities.parameters, capabilities.supports_parameters);
  }

  for (const candidate of candidates) {
    if (!candidate) continue;
    if (Array.isArray(candidate)) {
      for (const item of candidate) {
        const token = normalizeParameter(item);
        if (token) values.add(token);
      }
      continue;
    }
    if (typeof candidate === 'object') {
      for (const key of Object.keys(candidate as Record<string, unknown>)) {
        const token = normalizeParameter(key);
        if (token) values.add(token);
      }
    }
    if (typeof candidate === 'string') {
      const token = normalizeParameter(candidate);
      if (token) values.add(token);
    }
  }

  return Array.from(values);
}

export function extractModeration(model: ModelRecord): string | null {
  const record = model as Record<string, unknown>;
  const capabilities = model.capabilities as Record<string, unknown> | undefined;

  const moderationValues: unknown[] = [];
  moderationValues.push(record.moderation);
  moderationValues.push(record.requires_moderation);
  if (capabilities) {
    moderationValues.push(capabilities.moderation);
    moderationValues.push(capabilities.content_filtering);
  }

  for (const value of moderationValues) {
    if (value === null || value === undefined) {
      continue;
    }
    if (typeof value === 'boolean') {
      return value ? 'moderated' : 'unmoderated';
    }
    if (typeof value === 'string') {
      const token = value.trim().toLowerCase();
      if (!token) continue;
      if (['strict', 'standard', 'moderated', 'safe'].includes(token)) {
        return 'moderated';
      }
      if (['none', 'relaxed', 'unmoderated'].includes(token)) {
        return 'unmoderated';
      }
    }
  }

  return null;
}

function normalizeParameter(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const token = value.trim().toLowerCase();
  if (!token) {
    return null;
  }
  return token.replace(/[^a-z0-9_\-]/g, '_');
}
