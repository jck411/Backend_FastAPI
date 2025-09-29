import type { ModelRecord } from '../../../api/types';
import { normalizeToken } from './fields';

export const REASONING_TOKENS = [
  'reasoning',
  'reasoning_effort',
  'reasoning_max_tokens',
  'reasoning_exclude',
  'reasoning_enabled',
  'include_reasoning',
];

export const REASONING_SCHEMA_KEYS = {
  effort: ['reasoning.effort', 'reasoning_effort'] as const,
  maxTokens: ['reasoning.max_tokens', 'reasoning_max_tokens', 'thinking_budget'] as const,
  exclude: ['reasoning.exclude', 'reasoning_exclude', 'include_reasoning'] as const,
  enabled: ['reasoning.enabled', 'reasoning_enabled'] as const,
};

export function hasReasoningEffortSupport(modelRecord: ModelRecord | null): boolean {
  if (!modelRecord) {
    return false;
  }

  const keywords = ['openai/o1', 'openai/o3', 'openai/gpt-5', 'gpt-5', '/grok', 'grok-'];
  const tokens: string[] = [];

  const pushToken = (value: unknown) => {
    if (typeof value !== 'string') {
      return;
    }
    const normalized = value.trim().toLowerCase();
    if (normalized) {
      tokens.push(normalized);
    }
  };

  pushToken(modelRecord.id);
  pushToken(modelRecord.name);

  if (Array.isArray(modelRecord.tags)) {
    for (const tag of modelRecord.tags) {
      pushToken(tag);
    }
  }

  const record = modelRecord as Record<string, unknown>;
  pushToken(record.series);
  pushToken(record.family);

  return tokens.some((token) => keywords.some((keyword) => token.includes(keyword)));
}

export function normalizeSchemaKeys(keys: readonly string[]): string[] {
  const result: string[] = [];
  for (const key of keys) {
    const normalized = normalizeToken(key);
    if (normalized) {
      result.push(normalized);
    }
  }
  return result;
}
