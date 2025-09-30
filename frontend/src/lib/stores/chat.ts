import { get, writable } from 'svelte/store';
import { deleteChatMessage } from '../api/client';
import type { ChatCompletionRequest } from '../api/types';
import {
  mergeReasoningSegments,
  type ReasoningSegment,
  type ReasoningStatus,
  reasoningTextLength,
  toReasoningSegments,
} from '../chat/reasoning';
import { startChatStream } from '../chat/streaming';
import type { WebSearchSettings } from '../chat/webSearch';
import { webSearchStore } from '../chat/webSearchStore';

export type ConversationRole = 'user' | 'assistant' | 'system' | 'tool';

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
  serverMessageId?: number | null;
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
}

const initialState: ChatState = {
  messages: [],
  sessionId: null,
  isStreaming: false,
  error: null,
  selectedModel: 'openrouter/auto',
};

function createId(prefix: string): string {
  let token: string | null = null;

  const cryptoInstance = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined;

  if (cryptoInstance?.randomUUID) {
    try {
      token = cryptoInstance.randomUUID();
    } catch (error) {
      console.warn('Failed to generate UUID via crypto.randomUUID', error);
    }
  }

  if (!token && cryptoInstance?.getRandomValues) {
    const bytes = new Uint32Array(4);
    cryptoInstance.getRandomValues(bytes);
    token = Array.from(bytes, (value) => value.toString(16).padStart(8, '0')).join('');
  }

  if (!token) {
    token = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
  }

  return `${prefix}_${token.replace(/-/g, '')}`;
}

function toChatPayload(
  state: ChatState,
  prompt: string,
  webSearch: WebSearchSettings,
  userMessageId: string,
  assistantMessageId: string,
): ChatCompletionRequest {
  const payload: ChatCompletionRequest = {
    model: state.selectedModel,
    session_id: state.sessionId ?? undefined,
    messages: [
      {
        role: 'user',
        content: prompt,
        client_message_id: userMessageId,
      },
    ],
    metadata: {
      client_assistant_message_id: assistantMessageId,
      client_parent_message_id: userMessageId,
    },
  };

  if (webSearch.enabled) {
    const plugin: Record<string, unknown> = { id: 'web' };
    if (webSearch.engine) {
      plugin.engine = webSearch.engine;
    }
    if (webSearch.maxResults !== null && webSearch.maxResults !== undefined) {
      plugin.max_results = webSearch.maxResults;
    }
    const trimmedPrompt = webSearch.searchPrompt.trim();
    if (trimmedPrompt) {
      plugin.search_prompt = trimmedPrompt;
    }
    payload.plugins = [plugin];

    if (webSearch.contextSize) {
      payload.web_search_options = { search_context_size: webSearch.contextSize };
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

    const payload = toChatPayload(
      state,
      prompt,
      webSearchStore.current,
      userMessageId,
      assistantMessageId,
    );

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
      await startChatStream(payload, {
        signal: abortController.signal,
        onSession(sessionId) {
          store.update((value) => ({ ...value, sessionId }));
        },
        onMessageDelta({ text: deltaText, reasoningSegments, hasReasoningPayload }) {
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
        },
        onMetadata(metadata) {
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
              const serverMessageId =
                typeof metadata.message_id === 'number'
                  ? metadata.message_id
                  : existingDetails.serverMessageId ?? null;
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
                  serverMessageId,
                },
              };
            });
            return { ...value, messages };
          });
        },
        onToolEvent(payload) {
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
          const serverMessageId =
            typeof payload.message_id === 'number' ? payload.message_id : null;

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
                    serverMessageId,
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
                  serverMessageId:
                    serverMessageId ?? message.details?.serverMessageId ?? null,
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
    }));
  }

  function pruneMessages(state: ChatState, messageId: string): ChatState {
    const index = state.messages.findIndex((message) => message.id === messageId);
    if (index === -1) {
      return state;
    }

    const nextMessages = state.messages.slice();
    const target = nextMessages[index];
    nextMessages.splice(index, 1);

    if (target.role === 'assistant') {
      while (index < nextMessages.length && nextMessages[index].role === 'tool') {
        nextMessages.splice(index, 1);
      }
    } else if (target.role === 'user') {
      while (
        index < nextMessages.length &&
        nextMessages[index].role !== 'user' &&
        nextMessages[index].role !== 'system'
      ) {
        nextMessages.splice(index, 1);
      }
    }

    return {
      ...state,
      messages: nextMessages,
    };
  }

  async function deleteMessage(messageId: string): Promise<void> {
    const state = get(store);
    if (state.isStreaming) {
      return;
    }

    if (state.sessionId) {
      try {
        await deleteChatMessage(state.sessionId, messageId);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to delete message.';
        store.update((value) => ({
          ...value,
          error: message,
        }));
        return;
      }
    }

    store.update((value) => pruneMessages(value, messageId));
  }

  async function retryMessage(messageId: string): Promise<void> {
    const state = get(store);
    const index = state.messages.findIndex((message) => message.id === messageId);
    if (index === -1) {
      return;
    }

    const target = state.messages[index];
    if (target.role !== 'user') {
      return;
    }

    if (state.isStreaming) {
      currentAbort?.abort();
      currentAbort = null;
    }

    const messagesToRemove = state.messages.slice(index);
    const preservedMessages = state.messages.slice(0, index);

    store.update((value) => ({
      ...value,
      messages: preservedMessages,
      isStreaming: false,
      error: null,
    }));

    if (state.sessionId) {
      let deletionError: string | null = null;
      for (const message of messagesToRemove) {
        try {
          await deleteChatMessage(state.sessionId, message.id);
        } catch (error) {
          if (!deletionError) {
            deletionError =
              error instanceof Error ? error.message : 'Failed to delete previous message.';
          }
        }
      }

      if (deletionError) {
        store.update((value) => ({
          ...value,
          error: deletionError,
        }));
      }
    }

    if (target.content.trim()) {
      await sendMessage(target.content);
    }
  }

  async function editMessage(messageId: string, nextContent: string): Promise<void> {
    const trimmed = nextContent.trim();
    if (!trimmed) {
      return;
    }

    const state = get(store);
    const index = state.messages.findIndex((message) => message.id === messageId);
    if (index === -1) {
      return;
    }

    const target = state.messages[index];
    if (target.role !== 'user') {
      return;
    }

    if (state.isStreaming) {
      currentAbort?.abort();
      currentAbort = null;
    }

    const messagesToRemove = state.messages.slice(index);
    const preservedMessages = state.messages.slice(0, index);

    store.update((value) => ({
      ...value,
      messages: preservedMessages,
      isStreaming: false,
      error: null,
    }));

    if (state.sessionId) {
      let deletionError: string | null = null;
      for (const message of messagesToRemove) {
        try {
          await deleteChatMessage(state.sessionId, message.id);
        } catch (error) {
          if (!deletionError) {
            deletionError =
              error instanceof Error ? error.message : 'Failed to delete previous message.';
          }
        }
      }

      if (deletionError) {
        store.update((value) => ({
          ...value,
          error: deletionError,
        }));
      }
    }

    await sendMessage(trimmed);
  }

  function clearError(): void {
    store.update((value) => ({
      ...value,
      error: null,
    }));
  }

  function setModel(model: string): void {
    store.update((value) => ({ ...value, selectedModel: model }));
  }

  return {
    subscribe: store.subscribe,
    sendMessage,
    cancelStream,
    clearConversation,
    deleteMessage,
    retryMessage,
    editMessage,
    clearError,
    setModel,
  };
}

export const chatStore = createChatStore();
