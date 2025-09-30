import type { GenerationDetails } from '../api/types';

export interface GenerationDetailField {
  key: keyof GenerationDetails;
  label: string;
}

export interface GenerationDetailDisplayValue {
  text: string;
  isMultiline: boolean;
}

export const GENERATION_DETAIL_FIELDS: GenerationDetailField[] = [
  { key: 'total_cost', label: 'Total cost' },
  { key: 'created_at', label: 'Created' },
  { key: 'model', label: 'Model' },
  { key: 'origin', label: 'Origin' },
  { key: 'usage', label: 'Usage' },
  { key: 'is_byok', label: 'Self-hosted' },
  { key: 'cache_discount', label: 'Cache discount' },
  { key: 'upstream_inference_cost', label: 'Upstream inference cost' },
  { key: 'cancelled', label: 'Cancelled' },
  { key: 'provider_name', label: 'Provider' },
  { key: 'latency', label: 'Latency (ms)' },
  { key: 'moderation_latency', label: 'Moderation latency (ms)' },
  { key: 'generation_time', label: 'Generation time (ms)' },
  { key: 'finish_reason', label: 'Finish reason' },
  { key: 'native_finish_reason', label: 'Native finish reason' },
  { key: 'tokens_prompt', label: 'Prompt tokens' },
  { key: 'tokens_completion', label: 'Completion tokens' },
  { key: 'native_tokens_prompt', label: 'Native prompt tokens' },
  { key: 'native_tokens_completion', label: 'Native completion tokens' },
  { key: 'native_tokens_reasoning', label: 'Native reasoning tokens' },
  { key: 'num_media_prompt', label: 'Prompt media' },
  { key: 'num_media_completion', label: 'Completion media' },
  { key: 'num_search_results', label: 'Search results' },
];

export function formatGenerationDetailValue(value: unknown): GenerationDetailDisplayValue {
  if (value === null || value === undefined || value === '') {
    return { text: '—', isMultiline: false };
  }

  if (typeof value === 'boolean') {
    return { text: value ? 'Yes' : 'No', isMultiline: false };
  }

  if (typeof value === 'number') {
    const text = Number.isFinite(value) ? value.toString() : String(value);
    return { text, isMultiline: false };
  }

  if (typeof value === 'object') {
    try {
      const serialized = JSON.stringify(value, null, 2);
      return { text: serialized, isMultiline: serialized.includes('\n') };
    } catch (error) {
      console.warn('Failed to stringify generation detail value', error, value);
      const fallback = String(value);
      return { text: fallback, isMultiline: fallback.includes('\n') };
    }
  }

  const text = String(value);
  return { text, isMultiline: text.includes('\n') };
}
