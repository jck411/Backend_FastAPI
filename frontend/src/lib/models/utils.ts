import type { ModelPricing, ModelRecord } from '../api/types';

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
  return asNumeric(pricing.prompt ?? pricing.request ?? pricing.completion ?? pricing.image ?? null);
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
