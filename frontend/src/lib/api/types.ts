export type ChatRole = 'system' | 'user' | 'assistant' | 'tool';

export type ChatContentFragment =
  | { type: 'text'; text: string }
  | {
      type: 'image_url';
      image_url: {
        url: string;
        detail?: 'auto' | 'low' | 'high';
        [key: string]: unknown;
      };
      metadata?: Record<string, unknown>;
      [key: string]: unknown;
    }
  | { type: string; [key: string]: unknown };

export type ChatMessageContent = string | ChatContentFragment[];

export interface ChatMessage {
  role: ChatRole;
  content: ChatMessageContent;
  name?: string;
  tool_call_id?: string;
  client_message_id?: string;
  // Allow additional provider-specific metadata without breaking type safety.
  [key: string]: unknown;
}

export interface ChatCompletionRequest {
  model?: string;
  session_id?: string;
  messages: ChatMessage[];
  plugins?: Array<Record<string, unknown>>;
  web_search_options?: Record<string, unknown>;
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

export interface AttachmentResource {
  id: string;
  sessionId: string;
  mimeType: string;
  sizeBytes: number;
  displayUrl: string;
  deliveryUrl: string;
  uploadedAt: string;
  expiresAt: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface AttachmentUploadResponse {
  attachment: AttachmentResource;
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
  categories?: string[];
  categories_normalized?: string[];
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

export interface GenerationDetails {
  id?: string;
  total_cost?: number | null;
  created_at?: string | null;
  model?: string | null;
  origin?: string | null;
  usage?: number | null;
  is_byok?: boolean | null;
  upstream_id?: string | null;
  cache_discount?: number | null;
  upstream_inference_cost?: number | null;
  app_id?: number | null;
  streamed?: boolean | null;
  cancelled?: boolean | null;
  provider_name?: string | null;
  latency?: number | null;
  moderation_latency?: number | null;
  generation_time?: number | null;
  finish_reason?: string | null;
  native_finish_reason?: string | null;
  tokens_prompt?: number | null;
  tokens_completion?: number | null;
  native_tokens_prompt?: number | null;
  native_tokens_completion?: number | null;
  native_tokens_reasoning?: number | null;
  num_media_prompt?: number | null;
  num_media_completion?: number | null;
  num_search_results?: number | null;
  [key: string]: unknown;
}

export interface GenerationDetailsResponse {
  data: GenerationDetails;
  [key: string]: unknown;
}

export interface ProviderMaxPrice {
  prompt?: number | string | null;
  completion?: number | string | null;
  image?: number | string | null;
  audio?: number | string | null;
  request?: number | string | null;
  [key: string]: unknown;
}

export interface ProviderPreferences {
  allow_fallbacks?: boolean | null;
  require_parameters?: boolean | null;
  data_collection?: 'allow' | 'deny' | null;
  zdr?: boolean | null;
  order?: string[] | null;
  only?: string[] | null;
  ignore?: string[] | null;
  quantizations?: string[] | null;
  sort?: 'price' | 'throughput' | 'latency' | null;
  max_price?: ProviderMaxPrice | null;
  experimental?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export type ReasoningEffort = 'low' | 'medium' | 'high';

export interface ReasoningConfig {
  effort?: ReasoningEffort | null;
  max_tokens?: number | null;
  exclude?: boolean | null;
  enabled?: boolean | null;
  [key: string]: unknown;
}

export interface ModelHyperparameters {
  temperature?: number | null;
  top_p?: number | null;
  top_k?: number | null;
  min_p?: number | null;
  top_a?: number | null;
  max_tokens?: number | null;
  frequency_penalty?: number | null;
  presence_penalty?: number | null;
  repetition_penalty?: number | null;
  seed?: number | null;
  logit_bias?: Record<string, number> | null;
  stop?: string | string[] | null;
  top_logprobs?: number | null;
  parallel_tool_calls?: boolean | null;
  tool_choice?: string | Record<string, unknown> | null;
  response_format?: Record<string, unknown> | null;
  structured_outputs?: boolean | null;
  reasoning?: ReasoningConfig | null;
  safe_prompt?: boolean | null;
  raw_mode?: boolean | null;
  [key: string]: unknown;
}

export interface ActiveModelSettingsPayload {
  model: string;
  provider?: ProviderPreferences | null;
  parameters?: ModelHyperparameters | null;
}

export interface ActiveModelSettingsResponse extends ActiveModelSettingsPayload {
  updated_at: string;
}

export interface SystemPromptResponse {
  system_prompt: string | null;
}

export type SystemPromptPayload = SystemPromptResponse;

export interface McpServerToolStatus {
  name: string;
  qualified_name: string;
  enabled: boolean;
}

export interface McpServerStatus {
  id: string;
  enabled: boolean;
  connected: boolean;
  module?: string | null;
  command?: string[] | null;
  cwd?: string | null;
  env?: Record<string, string>;
  tool_prefix?: string | null;
  disabled_tools: string[];
  tool_count: number;
  tools: McpServerToolStatus[];
}

export interface McpServersResponse {
  servers: McpServerStatus[];
  updated_at?: string | null;
}

export interface McpServerDefinition {
  id: string;
  enabled?: boolean;
  module?: string | null;
  command?: string[] | null;
  cwd?: string | null;
  env?: Record<string, string>;
  tool_prefix?: string | null;
  disabled_tools?: string[];
}

export interface McpServersCollectionPayload {
  servers: McpServerDefinition[];
}

export interface McpServerUpdatePayload {
  enabled?: boolean;
  disabled_tools?: string[];
  module?: string | null;
  command?: string[] | null;
  cwd?: string | null;
  env?: Record<string, string> | null;
  tool_prefix?: string | null;
}
