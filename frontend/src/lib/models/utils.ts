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

const TOKENS_PER_MILLION = 1_000_000;
const ITEMS_PER_THOUSAND = 1_000;
const MILLION_DECIMALS = 6;
const THOUSAND_DECIMALS = 4;

const INPUT_TOKEN_PER_MILLION_KEYS = [
  'prompt_price_per_million',
  'input_price_per_million',
  'input_token_price_per_million',
];
const INPUT_TOKEN_PER_UNIT_KEYS = ['prompt_price', 'input_price', 'input_token_price'];
const INPUT_TOKEN_PRICING_KEYS = ['prompt', 'input', 'input_tokens', 'prompt_tokens'];

const OUTPUT_TOKEN_PER_MILLION_KEYS = [
  'completion_price_per_million',
  'output_price_per_million',
  'output_token_price_per_million',
];
const OUTPUT_TOKEN_PER_UNIT_KEYS = ['completion_price', 'output_price', 'output_token_price'];
const OUTPUT_TOKEN_PRICING_KEYS = ['completion', 'output', 'output_tokens', 'completion_tokens'];

const INPUT_IMAGE_PER_THOUSAND_KEYS = [
  'input_image_price_per_thousand',
  'vision_input_price_per_thousand',
  'image_price_per_thousand',
];
const INPUT_IMAGE_PER_UNIT_KEYS = [
  'input_image_price',
  'vision_input_price',
  'input_image',
  'image',
];
const INPUT_IMAGE_PRICING_KEYS = [
  'input_image',
  'image_input',
  'vision_input',
  'input_images',
  'vision',
  'image',
];

const OUTPUT_IMAGE_PER_THOUSAND_KEYS = [
  'output_image_price_per_thousand',
  'image_price_per_thousand',
  'vision_output_price_per_thousand',
];
const OUTPUT_IMAGE_PER_UNIT_KEYS = [
  'output_image_price',
  'image_price',
  'vision_output_price',
  'output_image',
];
const OUTPUT_IMAGE_PRICING_KEYS = [
  'output_image',
  'image',
  'image_output',
  'vision_output',
];

const REQUEST_PER_THOUSAND_KEYS = [
  'request_price_per_thousand',
  'requests_price_per_thousand',
];
const REQUEST_PER_UNIT_KEYS = ['request_price', 'requests_price', 'request'];
const REQUEST_PRICING_KEYS = ['request', 'requests'];

const WEB_SEARCH_PER_UNIT_KEYS = ['web_search', 'web-search', 'search'];
const WEB_SEARCH_PRICING_KEYS = ['web_search', 'web-search', 'search'];

const REASONING_PER_MILLION_KEYS = [
  'internal_reasoning_price_per_million',
  'reasoning_price_per_million',
  'reasoning_tokens_price_per_million',
];
const REASONING_PER_UNIT_KEYS = [
  'internal_reasoning',
  'reasoning',
  'reasoning_tokens',
  'internal_reasoning_token',
  'reasoning_token',
];
const REASONING_PRICING_KEYS = ['internal_reasoning', 'reasoning', 'reasoning_tokens'];

const CACHE_READ_PER_MILLION_KEYS = [
  'input_cache_read_price_per_million',
  'cache_read_price_per_million',
  'cache_hit_price_per_million',
];
const CACHE_READ_PER_UNIT_KEYS = [
  'input_cache_read',
  'cache_read',
  'cache_hit',
  'cache_read_token',
  'cache_hit_token',
];
const CACHE_READ_PRICING_KEYS = ['input_cache_read', 'cache_read', 'cache_hit'];

const CACHE_WRITE_PER_MILLION_KEYS = [
  'input_cache_write_price_per_million',
  'cache_write_price_per_million',
  'cache_refresh_price_per_million',
];
const CACHE_WRITE_PER_UNIT_KEYS = [
  'input_cache_write',
  'cache_write',
  'cache_refresh',
  'cache_write_token',
  'cache_refresh_token',
];
const CACHE_WRITE_PRICING_KEYS = ['input_cache_write', 'cache_write', 'cache_refresh'];

function normalizePrice(value: number | null, decimals: number): number | null {
  if (value === null) return null;
  if (!Number.isFinite(value)) return null;
  if (value < 0) return null;
  if (value === 0) return 0;
  return Number(value.toFixed(decimals));
}

function scalePrice(value: number | null, multiplier: number, decimals: number): number | null {
  if (value === null) return null;
  if (!Number.isFinite(value)) return null;
  if (value < 0) return null;
  if (value === 0) return 0;
  return Number((value * multiplier).toFixed(decimals));
}

function readRecordNumeric(record: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    if (!(key in record)) continue;
    const numeric = asNumeric(record[key]);
    if (numeric !== null) {
      return numeric;
    }
  }
  return null;
}

function gatherPricingSources(model: ModelRecord): ModelPricing[] {
  const sources: ModelPricing[] = [];
  const push = (candidate: unknown) => {
    if (candidate && typeof candidate === 'object') {
      sources.push(candidate as ModelPricing);
    }
  };
  push(model.pricing);
  if (model.provider && typeof model.provider === 'object') {
    push(model.provider.pricing);
  }
  const topProvider = (model as Record<string, unknown>).top_provider;
  if (topProvider && typeof topProvider === 'object') {
    push((topProvider as Record<string, unknown>).pricing);
  }
  return sources;
}

function extractPriceFromRecord(
  record: Record<string, unknown>,
  perMillionKeys: string[],
  perUnitKeys: string[],
  multiplier: number,
  decimals: number,
): number | null {
  const perMillion = readRecordNumeric(record, perMillionKeys);
  const normalizedPerMillion = normalizePrice(perMillion, decimals);
  if (normalizedPerMillion !== null) {
    return normalizedPerMillion;
  }

  const perUnit = readRecordNumeric(record, perUnitKeys);
  const scaledPerUnit = scalePrice(perUnit, multiplier, decimals);
  if (scaledPerUnit !== null) {
    return scaledPerUnit;
  }

  return null;
}

function extractPriceFromPricing(
  pricing: ModelPricing | null | undefined,
  perMillionKeys: string[],
  perUnitKeys: string[],
  multiplier: number,
  decimals: number,
): number | null {
  if (!pricing) return null;
  const record = pricing as Record<string, unknown>;

  const perMillion = readRecordNumeric(record, perMillionKeys);
  const normalizedPerMillion = normalizePrice(perMillion, decimals);
  if (normalizedPerMillion !== null) {
    return normalizedPerMillion;
  }

  const perUnit = readRecordNumeric(record, perUnitKeys);
  const scaledPerUnit = scalePrice(perUnit, multiplier, decimals);
  if (scaledPerUnit !== null) {
    return scaledPerUnit;
  }

  return null;
}

function deriveScaledPrice(
  model: ModelRecord,
  perMillionKeys: string[],
  perUnitKeys: string[],
  pricingKeys: string[],
  multiplier: number,
  decimals: number,
): number | null {
  const record = model as Record<string, unknown>;
  const direct = extractPriceFromRecord(record, perMillionKeys, perUnitKeys, multiplier, decimals);
  if (direct !== null) {
    return direct;
  }

  const pricingUnitKeys = [...pricingKeys, ...perUnitKeys];
  for (const pricing of gatherPricingSources(model)) {
    const value = extractPriceFromPricing(pricing, perMillionKeys, pricingUnitKeys, multiplier, decimals);
    if (value !== null) {
      return value;
    }
  }

  return null;
}

export function extractPromptPrice(pricing?: ModelPricing | null): number | null {
  return extractPriceFromPricing(
    pricing ?? null,
    INPUT_TOKEN_PER_MILLION_KEYS,
    [...INPUT_TOKEN_PRICING_KEYS, ...INPUT_TOKEN_PER_UNIT_KEYS],
    TOKENS_PER_MILLION,
    MILLION_DECIMALS,
  );
}

export function deriveInputTokenPrice(model: ModelRecord): number | null {
  return deriveScaledPrice(
    model,
    INPUT_TOKEN_PER_MILLION_KEYS,
    INPUT_TOKEN_PER_UNIT_KEYS,
    INPUT_TOKEN_PRICING_KEYS,
    TOKENS_PER_MILLION,
    MILLION_DECIMALS,
  );
}

export function deriveOutputTokenPrice(model: ModelRecord): number | null {
  return deriveScaledPrice(
    model,
    OUTPUT_TOKEN_PER_MILLION_KEYS,
    OUTPUT_TOKEN_PER_UNIT_KEYS,
    OUTPUT_TOKEN_PRICING_KEYS,
    TOKENS_PER_MILLION,
    MILLION_DECIMALS,
  );
}

export function deriveInputImagePrice(model: ModelRecord): number | null {
  return deriveScaledPrice(
    model,
    INPUT_IMAGE_PER_THOUSAND_KEYS,
    INPUT_IMAGE_PER_UNIT_KEYS,
    INPUT_IMAGE_PRICING_KEYS,
    ITEMS_PER_THOUSAND,
    THOUSAND_DECIMALS,
  );
}

export function deriveOutputImagePrice(model: ModelRecord): number | null {
  return deriveScaledPrice(
    model,
    OUTPUT_IMAGE_PER_THOUSAND_KEYS,
    OUTPUT_IMAGE_PER_UNIT_KEYS,
    OUTPUT_IMAGE_PRICING_KEYS,
    ITEMS_PER_THOUSAND,
    THOUSAND_DECIMALS,
  );
}

export function deriveRequestPrice(model: ModelRecord): number | null {
  return deriveScaledPrice(
    model,
    REQUEST_PER_THOUSAND_KEYS,
    REQUEST_PER_UNIT_KEYS,
    REQUEST_PRICING_KEYS,
    ITEMS_PER_THOUSAND,
    THOUSAND_DECIMALS,
  );
}

export function deriveWebSearchPrice(model: ModelRecord): number | null {
  return deriveScaledPrice(
    model,
    [],
    WEB_SEARCH_PER_UNIT_KEYS,
    WEB_SEARCH_PRICING_KEYS,
    1,
    THOUSAND_DECIMALS,
  );
}

export function deriveInternalReasoningPrice(model: ModelRecord): number | null {
  return deriveScaledPrice(
    model,
    REASONING_PER_MILLION_KEYS,
    REASONING_PER_UNIT_KEYS,
    REASONING_PRICING_KEYS,
    TOKENS_PER_MILLION,
    MILLION_DECIMALS,
  );
}

export function deriveCacheReadPrice(model: ModelRecord): number | null {
  return deriveScaledPrice(
    model,
    CACHE_READ_PER_MILLION_KEYS,
    CACHE_READ_PER_UNIT_KEYS,
    CACHE_READ_PRICING_KEYS,
    TOKENS_PER_MILLION,
    MILLION_DECIMALS,
  );
}

export function deriveCacheWritePrice(model: ModelRecord): number | null {
  return deriveScaledPrice(
    model,
    CACHE_WRITE_PER_MILLION_KEYS,
    CACHE_WRITE_PER_UNIT_KEYS,
    CACHE_WRITE_PRICING_KEYS,
    TOKENS_PER_MILLION,
    MILLION_DECIMALS,
  );
}

export function derivePromptPrice(model: ModelRecord): number | null {
  return deriveInputTokenPrice(model);
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
  if (value === 0) return 'FREE';
  if (value >= 100) return `$${value.toFixed(0)}`;
  if (value >= 10) return `$${value.toFixed(1)}`;
  if (value >= 1) return `$${value.toFixed(2)}`;
  if (value >= 0.1) return `$${value.toFixed(2)}`;
  return `$${value.toFixed(3)}`;
}

export function formatContext(value: number | null): string {
  if (value === null) return 'Unknown';
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}k tokens`;
  }
  return `${value} tokens`;
}

export function formatContextMillions(value: number | null): string {
  if (value === null) return '—';
  const millions = value / TOKENS_PER_MILLION;
  const roundedMillions = (() => {
    if (millions >= 10) return millions.toFixed(0);
    if (millions >= 1) return millions.toFixed(1);
    if (millions >= 0.1) return millions.toFixed(2);
    return millions.toFixed(3);
  })().replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1');

  const contextLabel = (() => {
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
    if (value >= 1000) return `${Math.round(value / 1000)}K`;
    return `${value}`;
  })();

  return `${roundedMillions}M (~${contextLabel})`;
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
