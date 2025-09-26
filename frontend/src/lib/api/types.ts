export type ChatRole = 'system' | 'user' | 'assistant' | 'tool';

export interface ChatMessage {
  role: ChatRole;
  content: unknown;
  name?: string;
  tool_call_id?: string;
  // Allow additional provider-specific metadata without breaking type safety.
  [key: string]: unknown;
}

export interface ChatCompletionRequest {
  model?: string;
  session_id?: string;
  messages: ChatMessage[];
  temperature?: number;
  top_p?: number;
  top_k?: number;
  max_tokens?: number;
  min_p?: number;
  top_a?: number;
  presence_penalty?: number;
  frequency_penalty?: number;
  repetition_penalty?: number;
  seed?: number;
  stop?: string | string[];
  tool_choice?: string | Record<string, unknown> | null;
  parallel_tool_calls?: boolean;
  response_format?: Record<string, unknown>;
  structured_outputs?: boolean;
  reasoning?: Record<string, unknown>;
  provider?: Record<string, unknown>;
  models?: string[];
  route?: string;
  transforms?: string[];
  safe_prompt?: boolean;
  raw_mode?: boolean;
  metadata?: Record<string, unknown>;
  stream_options?: Record<string, unknown>;
  user?: string;
  usage?: Record<string, unknown>;
  prediction?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ChatCompletionDelta {
  content?: string;
  tool_calls?: Array<Record<string, unknown>>;
  reasoning?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface ChatCompletionChoice {
  delta: ChatCompletionDelta;
  finish_reason?: string | null;
  index?: number;
  [key: string]: unknown;
}

export interface ChatCompletionChunk {
  id?: string;
  object?: string;
  created?: number;
  model?: string;
  choices?: ChatCompletionChoice[];
  usage?: Record<string, unknown> | null;
  meta?: Record<string, unknown> | null;
  message?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface SseEvent {
  event: string;
  data?: string;
  id?: string;
}

type ModelPriceValue = number | string | null | undefined;

export interface ModelPricing {
  prompt?: ModelPriceValue;
  completion?: ModelPriceValue;
  request?: ModelPriceValue;
  image?: ModelPriceValue;
  web_search?: ModelPriceValue;
  internal_reasoning?: ModelPriceValue;
  input_cache_read?: ModelPriceValue;
  input_cache_write?: ModelPriceValue;
  [key: string]: ModelPriceValue;
}

export interface ModelProviderInfo {
  display_name?: string;
  slug?: string;
  provider_id?: string;
  endpoint_id?: string;
  region?: string;
  pricing?: ModelPricing;
  summary?: string;
  [key: string]: unknown;
}

export interface ModelRecord {
  id: string;
  name?: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
  max_context?: number | null;
  pricing?: ModelPricing;
  capabilities?: Record<string, unknown>;
  provider?: ModelProviderInfo | null;
  supports_tools?: boolean;
  tags?: string[];
  [key: string]: unknown;
}

export interface ModelListMetadata {
  total?: number;
  base_count?: number;
  count?: number;
  [key: string]: unknown;
}

export interface ModelListResponse {
  data: ModelRecord[];
  metadata?: ModelListMetadata;
  [key: string]: unknown;
}

export interface DeepgramTokenResponse {
  access_token: string;
  expires_in?: number | null;
}
