import type { GenerationDetails } from '../api/types';

export interface GenerationDetailField {
  key: keyof GenerationDetails;
  label: string;
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

export function formatGenerationDetailValue(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value.toString() : String(value);
  }
  return String(value);
}
