import { get, writable } from 'svelte/store';
import { streamChat } from '../api/client';
import type { ChatCompletionRequest } from '../api/types';

export type ConversationRole = 'user' | 'assistant' | 'system' | 'tool';

export interface ReasoningSegment {
  text: string;
  type?: string;
}

export type ReasoningStatus = 'streaming' | 'complete';

export type WebSearchEngine = 'native' | 'exa';
export type WebSearchContextSize = 'low' | 'medium' | 'high';

export interface WebSearchSettings {
  enabled: boolean;
  engine: WebSearchEngine | null;
  maxResults: number | null;
  searchPrompt: string;
  contextSize: WebSearchContextSize | null;
}

function toReasoningSegments(value: unknown): ReasoningSegment[] {
  if (value == null) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((entry) => toReasoningSegments(entry));
  }
  if (typeof value === 'string') {
    return value.length > 0 ? [{ text: value }] : [];
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const text = record.text;
    const type = record.type;
    const segments: ReasoningSegment[] = [];

    if (typeof text === 'string' && text.length > 0) {
      const segment: ReasoningSegment = { text };
      if (typeof type === 'string' && type.length > 0) {
        segment.type = type;
      }
      segments.push(segment);
    }

    const nestedKeys = [
      'segments',
      'segment',
      'messages',
      'message',
      'content',
      'contents',
      'parts',
      'steps',
      'items',
    ];

    for (const key of nestedKeys) {
      const nested = record[key];
      if (nested !== undefined) {
        segments.push(...toReasoningSegments(nested));
      }
    }

    return segments;
  }

  return [];
}

function collectReasoningSegmentsFromChunk(chunk: unknown): {
  segments: ReasoningSegment[];
  hasPayload: boolean;
} {
  if (!chunk || typeof chunk !== 'object') {
    return { segments: [], hasPayload: false };
  }
  const choices = (chunk as { choices?: Array<Record<string, unknown>> }).choices;
  if (!Array.isArray(choices)) {
    return { segments: [], hasPayload: false };
  }
  const segments: ReasoningSegment[] = [];
  let hasPayload = false;
  for (const choice of choices) {
    if (!choice || typeof choice !== 'object') {
      continue;
    }
    const delta = (choice as { delta?: unknown }).delta;
    if (!delta || typeof delta !== 'object') {
      continue;
    }
    if ('reasoning' in (delta as Record<string, unknown>)) {
      hasPayload = true;
      const reasoning = (delta as { reasoning?: unknown }).reasoning;
      segments.push(...toReasoningSegments(reasoning));
    }
  }
  return { segments, hasPayload };
}

function mergeReasoningSegments(
  existing: ReasoningSegment[] | undefined,
  incoming: ReasoningSegment[],
): ReasoningSegment[] {
  const sanitizedIncoming = incoming.filter((segment) => segment.text.length > 0);
  if (sanitizedIncoming.length === 0) {
    return existing ?? [];
  }
  if (!existing || existing.length === 0) {
    return sanitizedIncoming;
  }

  const existingText = existing.map((segment) => segment.text).join('');
  const incomingText = sanitizedIncoming.map((segment) => segment.text).join('');

  if (incomingText.startsWith(existingText)) {
    const suffix = incomingText.slice(existingText.length);
    if (suffix.length === 0) {
      return existing;
    }
    const merged = [...existing];
    const lastIndex = merged.length - 1;
    const lastIncoming = sanitizedIncoming[sanitizedIncoming.length - 1];
    merged[lastIndex] = {
      text: `${merged[lastIndex].text}${suffix}`,
      type: lastIncoming.type ?? merged[lastIndex].type,
    };
    return merged;
  }

  const merged = [...existing];
  for (const segment of sanitizedIncoming) {
    const alreadyPresent = merged.some(
      (existingSegment) =>
        existingSegment.text === segment.text && existingSegment.type === segment.type,
    );
    if (alreadyPresent) {
      continue;
    }
    merged.push(segment);
  }
  return merged;
}

function reasoningTextLength(segments: ReasoningSegment[] | undefined | null): number {
  return segments?.reduce((total, segment) => total + segment.text.length, 0) ?? 0;
}

const DEFAULT_WEB_SEARCH_SETTINGS: WebSearchSettings = {
  enabled: false,
  engine: null,
  maxResults: 5,
  searchPrompt: '',
  contextSize: null,
};

function normalizeWebSearchSettings(
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

interface ConversationMessageDetails {
  model?: string | null;
  finishReason?: string | null;
  reasoning?: ReasoningSegment[];
  reasoningStatus?: ReasoningStatus | null;
  usage?: Record<string, unknown> | null;
  routing?: Record<string, unknown> | null;
  toolCalls?: Array<Record<string, unknown>> | null;
  generationId?: string | null;
  toolName?: string | null;
  toolStatus?: string | null;
  toolResult?: string | null;
}

export interface ConversationMessage {
  id: string;
  role: ConversationRole;
  content: string;
  pending?: boolean;
  details?: ConversationMessageDetails;
}

interface ChatState {
  messages: ConversationMessage[];
  sessionId: string | null;
  isStreaming: boolean;
  error: string | null;
  selectedModel: string;
  webSearch: WebSearchSettings;
}

const initialState: ChatState = {
  messages: [],
  sessionId: null,
  isStreaming: false,
  error: null,
  selectedModel: 'openrouter/auto',
  webSearch: { ...DEFAULT_WEB_SEARCH_SETTINGS },
};

function createId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function toChatPayload(state: ChatState, prompt: string): ChatCompletionRequest {
  const payload: ChatCompletionRequest = {
    model: state.selectedModel,
    session_id: state.sessionId ?? undefined,
    messages: [
      {
        role: 'user',
        content: prompt,
      },
    ],
  };

  if (state.webSearch.enabled) {
    const plugin: Record<string, unknown> = { id: 'web' };
    if (state.webSearch.engine) {
      plugin.engine = state.webSearch.engine;
    }
    if (state.webSearch.maxResults !== null && state.webSearch.maxResults !== undefined) {
      plugin.max_results = state.webSearch.maxResults;
    }
    const trimmedPrompt = state.webSearch.searchPrompt.trim();
    if (trimmedPrompt) {
      plugin.search_prompt = trimmedPrompt;
    }
    payload.plugins = [plugin];

    if (state.webSearch.contextSize) {
      payload.web_search_options = { search_context_size: state.webSearch.contextSize };
    }
  }

  return payload;
}

function createChatStore() {
  const store = writable<ChatState>({ ...initialState });
  let currentAbort: AbortController | null = null;

  async function sendMessage(prompt: string): Promise<void> {
    if (!prompt.trim()) {
      return;
    }

    const state = get(store);
    if (state.isStreaming) {
      currentAbort?.abort();
    }

    const userMessageId = createId('user');
    const assistantMessageId = createId('assistant');

    const payload = toChatPayload(state, prompt);
    
    store.update((value) => ({
      ...value,
      messages: [
        ...value.messages,
        { id: userMessageId, role: 'user', content: prompt },
        { id: assistantMessageId, role: 'assistant', content: '', pending: true },
      ],
      isStreaming: true,
      error: null,
    }));

    const abortController = new AbortController();
    currentAbort = abortController;
    const toolMessageIds = new Map<string, string>();

    try {
      await streamChat(payload, {
        signal: abortController.signal,
        onSession(sessionId) {
          store.update((value) => ({ ...value, sessionId }));
        },
        onChunk(chunk, rawEvent) {
          const eventType = rawEvent?.event ?? 'message';

          if (eventType === 'message') {
            const deltaText =
              chunk.choices?.map((choice) => choice.delta?.content ?? '').join('') ?? '';
            const { segments: reasoningSegments, hasPayload: hasReasoningPayload } =
              collectReasoningSegmentsFromChunk(chunk);

            if (!deltaText && reasoningSegments.length === 0 && !hasReasoningPayload) {
              return;
            }

            store.update((value) => {
              const messages = value.messages.map((message) => {
                if (message.id !== assistantMessageId) {
                  return message;
                }
                const updatedMessage: ConversationMessage = {
                  ...message,
                  content: deltaText ? `${message.content}${deltaText}` : message.content,
                };

                if (reasoningSegments.length > 0 || hasReasoningPayload) {
                  const existingDetails: ConversationMessageDetails = message.details ?? {};
                  const nextDetails: ConversationMessageDetails = {
                    ...existingDetails,
                    reasoningStatus: 'streaming',
                  };
                  if (reasoningSegments.length > 0) {
                    nextDetails.reasoning = mergeReasoningSegments(
                      existingDetails.reasoning,
                      reasoningSegments,
                    );
                  }
                  updatedMessage.details = nextDetails;
                }

                return updatedMessage;
              });
              return { ...value, messages };
            });
            return;
          }

          if (eventType === 'metadata' && rawEvent?.data) {
            try {
              const metadata = JSON.parse(rawEvent.data) as Record<string, unknown>;
              store.update((value) => {
                const messages = value.messages.map((message) => {
                  if (message.id !== assistantMessageId) {
                    return message;
                  }
                  const existingDetails: ConversationMessageDetails = message.details ?? {};
                  const nextReasoningSegments = toReasoningSegments(metadata.reasoning);
                  const hasIncomingReasoning = nextReasoningSegments.length > 0;
                  let reasoning = existingDetails.reasoning;
                  if (hasIncomingReasoning) {
                    reasoning =
                      reasoningTextLength(nextReasoningSegments) >=
                      reasoningTextLength(existingDetails.reasoning)
                        ? nextReasoningSegments
                        : existingDetails.reasoning ?? nextReasoningSegments;
                  }
                  const reasoningStatus = hasIncomingReasoning
                    ? message.pending
                      ? 'streaming'
                      : 'complete'
                    : existingDetails.reasoningStatus ?? null;
                  return {
                    ...message,
                    details: {
                      ...existingDetails,
                      model:
                        typeof metadata.model === 'string'
                          ? metadata.model
                          : existingDetails.model ?? null,
                      finishReason:
                        typeof metadata.finish_reason === 'string'
                          ? metadata.finish_reason
                          : existingDetails.finishReason ?? null,
                      reasoning,
                      reasoningStatus,
                      usage:
                        metadata.usage && typeof metadata.usage === 'object'
                          ? (metadata.usage as Record<string, unknown>)
                          : existingDetails.usage ?? null,
                      routing:
                        metadata.routing && typeof metadata.routing === 'object'
                          ? (metadata.routing as Record<string, unknown>)
                          : existingDetails.routing ?? null,
                      toolCalls:
                        Array.isArray(metadata.tool_calls)
                          ? (metadata.tool_calls as Array<Record<string, unknown>>)
                          : existingDetails.toolCalls ?? null,
                      generationId:
                        typeof metadata.generation_id === 'string'
                          ? metadata.generation_id
                          : existingDetails.generationId ?? null,
                    },
                  };
                });
                return { ...value, messages };
              });
            } catch (error) {
              console.warn('Failed to parse metadata payload', error, rawEvent.data);
            }
            return;
          }

          if (eventType === 'tool' && rawEvent?.data) {
            try {
              const payload = JSON.parse(rawEvent.data) as Record<string, unknown>;
              const callId = typeof payload.call_id === 'string' ? payload.call_id : createId('tool');
              const status = typeof payload.status === 'string' ? payload.status : 'started';
              const toolName = typeof payload.name === 'string' ? payload.name : 'tool';
              const result = payload.result;
              const toolResult =
                typeof result === 'string'
                  ? result
                  : result && typeof result === 'object'
                    ? JSON.stringify(result)
                    : null;

              let messageId = toolMessageIds.get(callId);
              if (!messageId) {
                messageId = createId('tool');
                toolMessageIds.set(callId, messageId);
                store.update((value) => ({
                  ...value,
                  messages: [
                    ...value.messages,
                    {
                      id: messageId as string,
                      role: 'tool',
                      content: status === 'started'
                        ? `Running ${toolName}…`
                        : toolResult ?? `Tool ${toolName} responded.`,
                      pending: status === 'started',
                      details: {
                        toolName,
                        toolStatus: status,
                        toolResult: toolResult ?? null,
                      },
                    },
                  ],
                }));
              } else {
                store.update((value) => {
                  const messages = value.messages.map((message) => {
                    if (message.id !== messageId) {
                      return message;
                    }
                    const details = {
                      ...(message.details ?? {}),
                      toolName,
                      toolStatus: status,
                      toolResult: toolResult ?? (message.details?.toolResult ?? null),
                    };
                    return {
                      ...message,
                      content:
                        toolResult ??
                        (status === 'started'
                          ? `Running ${toolName}…`
                          : `Tool ${toolName} ${status}.`),
                      pending: status === 'started',
                      details,
                    };
                  });
                  return { ...value, messages };
                });
              }
            } catch (error) {
              console.warn('Failed to parse tool payload', error, rawEvent.data);
            }
          }
        },
        onDone() {
          store.update((value) => ({
            ...value,
            isStreaming: false,
            messages: value.messages.map((message) => {
              if (message.id !== assistantMessageId) {
                return message;
              }
              const details = message.details
                ? {
                    ...message.details,
                    reasoningStatus: message.details.reasoning
                      ? 'complete'
                      : message.details.reasoningStatus ?? null,
                  }
                : undefined;
              return {
                ...message,
                pending: false,
                details,
              };
            }),
          }));
        },
        onError(error) {
          console.error('Chat stream error', error);
          store.update((value) => ({
            ...value,
            isStreaming: false,
            error: error.message ?? 'Unknown error',
            messages: value.messages.filter(
              (message) =>
                message.id !== assistantMessageId && !(message.role === 'tool' && message.pending),
            ),
          }));
        },
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        // Aborted by user; no additional handling.
        return;
      }
      const message = error instanceof Error ? error.message : String(error);
      store.update((value) => ({
        ...value,
        isStreaming: false,
        error: message,
        messages: value.messages.filter(
          (msg) => msg.id !== assistantMessageId && !(msg.role === 'tool' && msg.pending),
        ),
      }));
    } finally {
      currentAbort = null;
    }
  }

  function cancelStream(): void {
    if (currentAbort) {
      currentAbort.abort();
      currentAbort = null;
      store.update((value) => ({
        ...value,
        isStreaming: false,
        messages: value.messages.filter(
          (message) =>
            !(
              (message.role === 'assistant' && message.pending && !message.content) ||
              (message.role === 'tool' && message.pending)
            ),
        ),
      }));
    }
  }

  function clearConversation(): void {
    currentAbort?.abort();
    currentAbort = null;
    store.update((value) => ({
      ...initialState,
      selectedModel: value.selectedModel,
      webSearch: { ...value.webSearch },
    }));
  }

  function setModel(model: string): void {
    store.update((value) => ({ ...value, selectedModel: model }));
  }

  function updateWebSearch(settings: Partial<WebSearchSettings>): void {
    if (!settings || typeof settings !== 'object') {
      return;
    }
    store.update((value) => ({
      ...value,
      webSearch: normalizeWebSearchSettings(settings, value.webSearch),
    }));
  }

  return {
    subscribe: store.subscribe,
    sendMessage,
    cancelStream,
    clearConversation,
    setModel,
    updateWebSearch,
  };
}

export const chatStore = createChatStore();
