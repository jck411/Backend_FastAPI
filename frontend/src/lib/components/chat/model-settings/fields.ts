import type { ModelHyperparameters, ModelRecord } from '../../../api/types';
import { extractSupportedParameters } from '../../../models/utils';

type HyperparameterKey = keyof ModelHyperparameters;

export interface NumberFieldConfig {
  key: HyperparameterKey;
  label: string;
  description?: string;
  type: 'number' | 'integer';
  min?: number;
  max?: number;
  step?: number;
}

export interface BooleanFieldConfig {
  key: HyperparameterKey;
  label: string;
  description?: string;
  type: 'boolean';
}

export type FieldConfig = NumberFieldConfig | BooleanFieldConfig;

interface FieldFallbackNumber {
  type: 'number' | 'integer';
  min?: number;
  max?: number;
  step?: number;
}

interface FieldFallbackBoolean {
  type: 'boolean';
}

type FieldFallback = FieldFallbackNumber | FieldFallbackBoolean;

interface ParameterDefinition {
  key: HyperparameterKey;
  aliases: string[];
  label: string;
  description?: string;
  fallback: FieldFallback;
}

export interface ParameterSchema {
  type?: string;
  min?: number;
  max?: number;
  step?: number;
}

const PARAMETER_DEFINITIONS: ParameterDefinition[] = [
  {
    key: 'temperature',
    aliases: ['temperature'],
    label: 'Temperature',
    description: 'Higher values increase randomness.',
    fallback: { type: 'number', min: 0, max: 2, step: 0.1 },
  },
  {
    key: 'top_p',
    aliases: ['top_p'],
    label: 'Top P',
    description: 'Limits sampling to a cumulative probability mass.',
    fallback: { type: 'number', min: 0, max: 1, step: 0.01 },
  },
  {
    key: 'top_k',
    aliases: ['top_k'],
    label: 'Top K',
    description: 'Restrict sampling to the top K tokens.',
    fallback: { type: 'integer', min: 1, max: 400, step: 1 },
  },
  {
    key: 'min_p',
    aliases: ['min_p'],
    label: 'Min P',
    description: 'Nucleus sampling floor; smaller values widen sampling.',
    fallback: { type: 'number', min: 0, max: 1, step: 0.01 },
  },
  {
    key: 'top_a',
    aliases: ['top_a'],
    label: 'Top A',
    description: 'Alternative nucleus control for certain models.',
    fallback: { type: 'number', min: 0, max: 1, step: 0.01 },
  },
  {
    key: 'max_tokens',
    aliases: ['max_tokens', 'max_output_tokens'],
    label: 'Max completion tokens',
    description: 'Upper bound on tokens generated in the response.',
    fallback: { type: 'integer', min: 1, max: 32768, step: 1 },
  },
  {
    key: 'frequency_penalty',
    aliases: ['frequency_penalty'],
    label: 'Frequency penalty',
    description: 'Penalize frequent tokens; useful to reduce repetition.',
    fallback: { type: 'number', min: -2, max: 2, step: 0.05 },
  },
  {
    key: 'presence_penalty',
    aliases: ['presence_penalty'],
    label: 'Presence penalty',
    description: 'Encourage introducing new topics by penalizing seen tokens.',
    fallback: { type: 'number', min: -2, max: 2, step: 0.05 },
  },
  {
    key: 'repetition_penalty',
    aliases: ['repetition_penalty'],
    label: 'Repetition penalty',
    description: 'Higher values push the model away from repeating itself.',
    fallback: { type: 'number', min: 0, max: 2, step: 0.05 },
  },
  {
    key: 'top_logprobs',
    aliases: ['top_logprobs'],
    label: 'Top logprobs',
    description: 'Return log probabilities for the top N tokens per step.',
    fallback: { type: 'integer', min: 0, max: 20, step: 1 },
  },
  {
    key: 'seed',
    aliases: ['seed'],
    label: 'Seed',
    description: 'Deterministic seed (when supported).',
    fallback: { type: 'integer', min: 0, step: 1 },
  },
  {
    key: 'parallel_tool_calls',
    aliases: ['parallel_tool_calls'],
    label: 'Parallel tool calls',
    description: 'Allow the model to invoke multiple tools simultaneously.',
    fallback: { type: 'boolean' },
  },
  {
    key: 'structured_outputs',
    aliases: ['structured_outputs', 'json_schema', 'response_format'],
    label: 'Structured outputs',
    description: 'Favor structured responses when supported by the provider.',
    fallback: { type: 'boolean' },
  },
  {
    key: 'safe_prompt',
    aliases: ['safe_prompt'],
    label: 'Safe prompt',
    description: 'Ask the provider to apply additional safety prompting.',
    fallback: { type: 'boolean' },
  },
  {
    key: 'raw_mode',
    aliases: ['raw_mode'],
    label: 'Raw mode',
    description: 'Bypass guardrails when the provider allows it.',
    fallback: { type: 'boolean' },
  },
];

export function normalizeToken(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const token = value.trim().toLowerCase();
  if (!token) return null;
  return token.replace(/[^a-z0-9_\-]/g, '_');
}

function coerceNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return undefined;
}

export function extractParameterSchemas(modelRecord: ModelRecord | null): Record<string, ParameterSchema> {
  const result: Record<string, ParameterSchema> = {};
  if (!modelRecord || !modelRecord.capabilities) {
    return result;
  }
  const capabilities = modelRecord.capabilities as Record<string, unknown>;
  const rawParameters = capabilities.parameters;
  if (!rawParameters || typeof rawParameters !== 'object') {
    return result;
  }

  function assignSchema(rawKey: string, schemaValue: unknown): void {
    const normalizedKey = normalizeToken(rawKey);
    if (!normalizedKey || !schemaValue || typeof schemaValue !== 'object') {
      return;
    }

    const record = schemaValue as Record<string, unknown>;
    const schema: ParameterSchema = {};
    const rawType = record.type ?? record.datatype ?? record.kind;
    if (typeof rawType === 'string') {
      schema.type = rawType.toLowerCase();
    }

    const min = record.min ?? record.minimum ?? record.lower_bound ?? record.minimum_value;
    const max = record.max ?? record.maximum ?? record.upper_bound ?? record.maximum_value;
    const step = record.step ?? record.increment ?? record.resolution;
    const minNumber = coerceNumber(min);
    const maxNumber = coerceNumber(max);
    const stepNumber = coerceNumber(step);
    if (minNumber !== undefined) schema.min = minNumber;
    if (maxNumber !== undefined) schema.max = maxNumber;
    if (stepNumber !== undefined) schema.step = stepNumber;
    result[normalizedKey] = schema;

    const properties = record.properties;
    if (properties && typeof properties === 'object') {
      for (const [propertyKey, propertySchema] of Object.entries(properties as Record<string, unknown>)) {
        assignSchema(`${rawKey}.${propertyKey}`, propertySchema);
      }
    }
  }

  for (const [key, value] of Object.entries(rawParameters as Record<string, unknown>)) {
    assignSchema(key, value);
  }

  return result;
}

export function collectSupportedParameterTokens(modelRecord: ModelRecord | null): Set<string> {
  const tokens = new Set<string>();
  if (!modelRecord) {
    return tokens;
  }

  const normalized = (modelRecord as Record<string, unknown>).supported_parameters_normalized;
  if (Array.isArray(normalized)) {
    for (const entry of normalized) {
      const token = normalizeToken(entry);
      if (token) tokens.add(token);
    }
  }

  const raw = (modelRecord as Record<string, unknown>).supported_parameters;
  if (Array.isArray(raw)) {
    for (const entry of raw) {
      const token = normalizeToken(entry);
      if (token) tokens.add(token);
    }
  }

  if (tokens.size === 0) {
    for (const entry of extractSupportedParameters(modelRecord)) {
      const token = normalizeToken(entry);
      if (token) tokens.add(token);
    }
  }

  return tokens;
}

function applySchema(definition: ParameterDefinition, schema: ParameterSchema | undefined): FieldConfig {
  const fallback = definition.fallback;
  if (fallback.type === 'boolean') {
    return {
      key: definition.key,
      label: definition.label,
      description: definition.description,
      type: 'boolean',
    };
  }

  const field: NumberFieldConfig = {
    key: definition.key,
    label: definition.label,
    description: definition.description,
    type: fallback.type,
    min: fallback.min,
    max: fallback.max,
    step: fallback.step,
  };

  if (!schema) {
    if (field.type === 'integer' && (!field.step || field.step <= 0)) {
      field.step = 1;
    }
    return field;
  }

  const schemaType = schema.type?.toLowerCase();
  if (schemaType === 'boolean') {
    return {
      key: definition.key,
      label: definition.label,
      description: definition.description,
      type: 'boolean',
    };
  }

  if (schemaType === 'integer' || schemaType === 'int') {
    field.type = 'integer';
  } else if (schemaType === 'number' || schemaType === 'float' || schemaType === 'double') {
    field.type = 'number';
  }

  if (schema.min !== undefined) field.min = schema.min;
  if (schema.max !== undefined) field.max = schema.max;
  if (schema.step !== undefined) field.step = schema.step;

  if (field.type === 'integer' && (!field.step || field.step <= 0)) {
    field.step = 1;
  }

  return field;
}

export function buildFieldConfigs(
  modelRecord: ModelRecord | null,
  parameters: ModelHyperparameters | null,
): FieldConfig[] {
  const available = collectSupportedParameterTokens(modelRecord);
  const activeKeys = new Set(
    parameters ? (Object.keys(parameters) as Array<HyperparameterKey>) : [],
  );
  const schemas = extractParameterSchemas(modelRecord);
  const fields: FieldConfig[] = [];
  const seen = new Set<HyperparameterKey>();

  for (const definition of PARAMETER_DEFINITIONS) {
    const matches = definition.aliases.some((alias) => available.has(alias));
    if (!matches && !activeKeys.has(definition.key)) {
      continue;
    }
    if (seen.has(definition.key)) {
      continue;
    }
    const schema = definition.aliases
      .map((alias) => schemas[alias])
      .find((entry) => entry !== undefined);
    const field = applySchema(definition, schema);
    if ('min' in field && 'max' in field && field.min !== undefined && field.max !== undefined) {
      if (field.min >= field.max) {
        field.min = undefined;
        field.max = undefined;
      }
    }
    fields.push(field);
    seen.add(definition.key);
  }

  return fields;
}

export function parameterNumberValue(
  parameters: ModelHyperparameters | null,
  key: HyperparameterKey,
): number | undefined {
  const value = parameters?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

export function clampToRange(value: number, field: NumberFieldConfig): number {
  let result = value;
  if (field.min !== undefined) {
    result = Math.max(result, field.min);
  }
  if (field.max !== undefined) {
    result = Math.min(result, field.max);
  }
  return result;
}

export function sliderDefaultValue(field: NumberFieldConfig): number {
  const min = field.min ?? 0;
  const max = field.max ?? min;
  if (min <= 0 && max >= 0) {
    return clampToRange(0, field);
  }
  const midpoint = min + (max - min) / 2;
  return clampToRange(midpoint, field);
}

export function sliderCurrentValue(
  field: NumberFieldConfig,
  parameters: ModelHyperparameters | null,
): number {
  const current = parameterNumberValue(parameters, field.key);
  if (current !== undefined) {
    return clampToRange(current, field);
  }
  return sliderDefaultValue(field);
}

export function sliderStepValue(field: NumberFieldConfig): number {
  if (field.step && field.step > 0) {
    return field.step;
  }
  if (field.type === 'integer') {
    return 1;
  }
  const min = field.min ?? 0;
  const max = field.max ?? min + 1;
  const span = max - min;
  if (!Number.isFinite(span) || span <= 0) {
    return 0.01;
  }
  const step = span / 100;
  return step > 0 ? step : 0.01;
}

export function sliderFillPercent(
  field: NumberFieldConfig,
  value: number | undefined,
): string {
  const min = field.min ?? 0;
  const max = field.max ?? min;
  const denominator = max - min;
  if (!Number.isFinite(denominator) || denominator === 0) {
    return '0%';
  }
  const current = clampToRange(value ?? sliderDefaultValue(field), field);
  const percent = ((current - min) / denominator) * 100;
  const bounded = Math.min(100, Math.max(0, percent));
  return `${bounded}%`;
}
