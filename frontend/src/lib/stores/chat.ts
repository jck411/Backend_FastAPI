import { get, writable } from 'svelte/store';
import { ApiError, deleteChatMessage } from '../api/client';
import type {
  AttachmentResource,
  ChatCompletionRequest,
  ChatMessageContent,
} from '../api/types';
import {
  buildChatContent,
  normalizeMessageContent,
  type MessageContentPart,
} from '../chat/content';
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
import { modelSettingsStore } from './modelSettings';

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

export interface MessageAttachment {
  id: string | null;
  sessionId: string | null;
  mimeType: string | null;
  sizeBytes: number | null;
  displayUrl: string | null;
  deliveryUrl: string | null;
  uploadedAt: string | null;
  expiresAt: string | null;
  metadata?: Record<string, unknown> | null;
  resource?: AttachmentResource | null;
}

export interface ConversationMessage {
  id: string;
  role: ConversationRole;
  content: ChatMessageContent;
  text: string;
  attachments: MessageAttachment[];
  pending?: boolean;
  details?: ConversationMessageDetails;
  createdAt?: string | null;
  createdAtUtc?: string | null;
}

interface OutgoingMessageDraft {
  text: string;
  attachments: AttachmentResource[];
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

function resolveDeletionIdentifiers(message: ConversationMessage): string[] {
  const identifiers: string[] = [];
  const seen = new Set<string>();

  const serverMessageId = message.details?.serverMessageId;
  if (typeof serverMessageId === 'number') {
    const value = String(serverMessageId);
    identifiers.push(value);
    seen.add(value);
  }

  if (message.id && !seen.has(message.id)) {
    identifiers.push(message.id);
  }

  return identifiers;
}

function cloneMessageAttachment(attachment: MessageAttachment): MessageAttachment {
  return {
    ...attachment,
    metadata: attachment.metadata ? { ...attachment.metadata } : attachment.metadata ?? null,
    resource: attachment.resource ? { ...attachment.resource } : attachment.resource ?? null,
  };
}

function attachmentKey(attachment: MessageAttachment): string {
  const id = attachment.id?.trim();
  if (id) {
    return `id:${id}`;
  }
  const delivery = attachment.deliveryUrl?.trim();
  if (delivery) {
    return `delivery:${delivery}`;
  }
  const display = attachment.displayUrl?.trim();
  if (display) {
    return `display:${display}`;
  }
  return `meta:${JSON.stringify({
    display: attachment.displayUrl ?? null,
    delivery: attachment.deliveryUrl ?? null,
  })}`;
}

function mergeMessageAttachments(
  existing: MessageAttachment[],
  incoming: MessageAttachment[],
): MessageAttachment[] {
  if (incoming.length === 0) {
    return existing.map(cloneMessageAttachment);
  }

  const map = new Map<string, MessageAttachment>();
  const order: string[] = [];

  const register = (attachment: MessageAttachment) => {
    const cloned = cloneMessageAttachment(attachment);
    const key = attachmentKey(cloned);
    if (!map.has(key)) {
      order.push(key);
    }
    map.set(key, cloned);
  };

  for (const item of existing) {
    register(item);
  }

  for (const item of incoming) {
    register(item);
  }

  return order.map((key) => map.get(key) as MessageAttachment);
}

type ImageContentPart = Extract<MessageContentPart, { type: 'image' }>;

function toMessageAttachmentFromResource(resource: AttachmentResource): MessageAttachment {
  return {
    id: resource.id ?? null,
    sessionId: resource.sessionId ?? null,
    mimeType: resource.mimeType ?? null,
    sizeBytes: Number.isFinite(resource.sizeBytes) ? resource.sizeBytes : null,
    displayUrl: resource.displayUrl ?? resource.deliveryUrl ?? null,
    deliveryUrl: resource.deliveryUrl ?? resource.displayUrl ?? null,
    uploadedAt: resource.uploadedAt ?? null,
    expiresAt: resource.expiresAt ?? null,
    metadata: resource.metadata ?? null,
    resource: { ...resource },
  };
}

function toMessageAttachmentFromImagePart(part: ImageContentPart): MessageAttachment {
  const deliveryUrl = part.url ?? part.displayUrl ?? null;
  const displayUrl = part.displayUrl ?? part.url ?? null;
  return {
    id: part.attachmentId ?? part.url ?? null,
    sessionId: part.sessionId ?? null,
    mimeType: part.mimeType ?? null,
    sizeBytes: typeof part.sizeBytes === 'number' && Number.isFinite(part.sizeBytes)
      ? part.sizeBytes
      : null,
    displayUrl,
    deliveryUrl,
    uploadedAt: part.uploadedAt ?? null,
    expiresAt: part.expiresAt ?? null,
    metadata: part.metadata ?? null,
    resource: null,
  };
}

function choosePreferredText(current: string, candidate: string): string {
  const trimmedCandidate = candidate.trim();
  if (!trimmedCandidate) {
    return current;
  }
  const trimmedCurrent = current.trim();
  if (!trimmedCurrent) {
    return candidate;
  }
  return trimmedCandidate.length >= trimmedCurrent.length ? candidate : current;
}

interface AssistantContentUpdate {
  deltaText?: string;
  metadataContent?: unknown;
}

function reduceAssistantMessageContent(
  message: ConversationMessage,
  update: AssistantContentUpdate,
): Pick<ConversationMessage, 'content' | 'text' | 'attachments'> {
  let text = message.text ?? '';
  let content: ChatMessageContent = message.content;
  let attachments: MessageAttachment[] = message.attachments ?? [];

  if (update.deltaText) {
    const baseText =
      typeof message.content === 'string'
        ? message.content
        : typeof message.text === 'string'
          ? message.text
          : '';
    const appended = `${baseText}${update.deltaText}`;
    text = appended;
    content = appended;
  }

  if (update.metadataContent !== undefined) {
    const rawContent = update.metadataContent as ChatMessageContent | null | undefined;

    if (rawContent && (typeof rawContent === 'string' || Array.isArray(rawContent))) {
      const normalized = normalizeMessageContent(rawContent);
      if (normalized.text) {
        text = choosePreferredText(text, normalized.text);
      }

      const imageParts = normalized.parts.filter(
        (part): part is ImageContentPart => part.type === 'image',
      );
      if (imageParts.length > 0) {
        const mapped = imageParts.map(toMessageAttachmentFromImagePart);
        attachments = mergeMessageAttachments(attachments, mapped);
      } else {
        attachments = attachments.map(cloneMessageAttachment);
      }

      if (Array.isArray(rawContent)) {
        const hasTextPart = rawContent.some((fragment) => fragment?.type === 'text');
        if (!hasTextPart && text) {
          const fragments = [{ type: 'text', text }, ...rawContent];
          content = fragments as ChatMessageContent;
        } else {
          content = rawContent;
        }
      } else if (typeof rawContent === 'string') {
        content = rawContent;
      }
    } else if (rawContent === null || rawContent === undefined) {
      content = text;
      attachments = attachments.map(cloneMessageAttachment);
    }
  }

  return { text, content, attachments };
}

function extractAttachmentResources(attachments: MessageAttachment[]): AttachmentResource[] {
  const resources: AttachmentResource[] = [];
  for (const attachment of attachments ?? []) {
    if (attachment.resource) {
      resources.push({ ...attachment.resource });
    }
  }
  return resources;
}

function toChatPayload(
  state: ChatState,
  content: ChatMessageContent,
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
        content,
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
    const trimmedSearchPrompt = webSearch.searchPrompt.trim();
    if (trimmedSearchPrompt) {
      plugin.search_prompt = trimmedSearchPrompt;
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

  function coalesceTimestamp(...values: Array<unknown>): string | null {
    for (const value of values) {
      if (typeof value === 'string' && value) {
        return value;
      }
    }
    return null;
  }

  async function sendMessage(draft: OutgoingMessageDraft): Promise<void> {
    const text = draft.text.trim();
    const attachments = draft.attachments ?? [];
    if (!text && attachments.length === 0) {
      return;
    }

    const state = get(store);
    if (state.isStreaming) {
      currentAbort?.abort();
    }

    const userMessageId = createId('user');
    const assistantMessageId = createId('assistant');

    const messageContent = buildChatContent(draft.text, attachments);
    const normalized = normalizeMessageContent(messageContent);
    const userAttachments = attachments.map(toMessageAttachmentFromResource);

    const payload = toChatPayload(
      state,
      messageContent,
      webSearchStore.current,
      userMessageId,
      assistantMessageId,
    );
    const nowIso = new Date().toISOString();

    store.update((value) => ({
      ...value,
      messages: [
        ...value.messages,
        {
          id: userMessageId,
          role: 'user',
          content: messageContent,
          text: normalized.text,
          attachments: userAttachments,
          createdAt: nowIso,
          createdAtUtc: nowIso,
        },
        {
          id: assistantMessageId,
          role: 'assistant',
          content: '',
          text: '',
          attachments: [],
          pending: true,
          createdAt: null,
          createdAtUtc: null,
        },
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
              const merged = reduceAssistantMessageContent(message, { deltaText });
              const updatedMessage: ConversationMessage = {
                ...message,
                ...merged,
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
              const hasContent = Object.prototype.hasOwnProperty.call(metadata, 'content');
              const merged = hasContent
                ? reduceAssistantMessageContent(message, {
                    metadataContent: (metadata as Record<string, unknown>).content,
                  })
                : {
                    text: message.text,
                    content: message.content,
                    attachments: message.attachments.map(cloneMessageAttachment),
                  };
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
              const createdAt = coalesceTimestamp(
                metadata.created_at,
                metadata.created_at_utc,
                message.createdAt ?? null,
              );
              const createdAtUtc = coalesceTimestamp(
                metadata.created_at_utc,
                message.createdAtUtc ?? null,
              );
              return {
                ...message,
                ...merged,
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
                createdAt,
                createdAtUtc,
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
            const fallbackCreatedAt = new Date().toISOString();
            const createdAt = coalesceTimestamp(
              payload.created_at,
              payload.created_at_utc,
              fallbackCreatedAt,
            );
            const createdAtUtc = coalesceTimestamp(
              payload.created_at_utc,
              createdAt ?? fallbackCreatedAt,
            );
            store.update((value) => ({
              ...value,
              messages: [
                ...value.messages,
                {
                  id: messageId as string,
                  role: 'tool',
                  content:
                    status === 'started'
                      ? `Running ${toolName}…`
                      : toolResult ?? `Tool ${toolName} responded.`,
                  text:
                    status === 'started'
                      ? `Running ${toolName}…`
                      : toolResult ?? `Tool ${toolName} responded.`,
                  attachments: [],
                  pending: status === 'started',
                  details: {
                    toolName,
                    toolStatus: status,
                    toolResult: toolResult ?? null,
                    serverMessageId,
                  },
                  createdAt,
                  createdAtUtc,
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
                const nextText =
                  toolResult ??
                  (status === 'started'
                    ? `Running ${toolName}…`
                    : `Tool ${toolName} ${status}.`);
                const nextCreatedAt = coalesceTimestamp(
                  payload.created_at,
                  payload.created_at_utc,
                  message.createdAt ?? null,
                );
                const nextCreatedAtUtc = coalesceTimestamp(
                  payload.created_at_utc,
                  message.createdAtUtc ?? null,
                );
                return {
                  ...message,
                  content: nextText,
                  text: nextText,
                  attachments: (message.attachments ?? []).map(cloneMessageAttachment),
                  pending: status === 'started',
                  details,
                  createdAt: nextCreatedAt,
                  createdAtUtc:
                    nextCreatedAtUtc ?? nextCreatedAt ?? message.createdAtUtc ?? null,
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
              const fallbackIso = new Date().toISOString();
              const finalizedCreatedAt = message.createdAt ?? fallbackIso;
              return {
                ...message,
                pending: false,
                details,
                createdAt: finalizedCreatedAt,
                createdAtUtc: message.createdAtUtc ?? finalizedCreatedAt,
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
              (message.role === 'assistant' && message.pending && !message.text) ||
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

  async function deleteMessagesFromServer(
    sessionId: string,
    messages: ConversationMessage[],
  ): Promise<string | null> {
    let deletionError: string | null = null;
    const attempted = new Set<string>();

    for (const message of messages) {
      if (message.role === 'assistant' || message.role === 'tool') {
        continue;
      }

      const candidates = resolveDeletionIdentifiers(message);
      let deleted = false;

      for (const candidate of candidates) {
        if (!candidate || attempted.has(candidate)) {
          continue;
        }

        attempted.add(candidate);

        try {
          await deleteChatMessage(sessionId, candidate);
          deleted = true;
          break;
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) {
            continue;
          }
          if (!deletionError) {
            deletionError =
              error instanceof Error ? error.message : 'Failed to delete previous message.';
          }
          break;
        }
      }

    }

    return deletionError;
  }

  async function deleteMessage(messageId: string): Promise<void> {
    const state = get(store);
    if (state.isStreaming) {
      return;
    }

    const target = state.messages.find((message) => message.id === messageId);
    if (!target) {
      return;
    }

    if (state.sessionId) {
      const candidates = resolveDeletionIdentifiers(target);
      let deletionError: string | null = null;

      for (const candidate of candidates) {
        try {
          await deleteChatMessage(state.sessionId, candidate);
          deletionError = null;
          break;
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) {
            continue;
          }
          deletionError = error instanceof Error ? error.message : 'Failed to delete message.';
          break;
        }
      }

      if (deletionError) {
        store.update((value) => ({
          ...value,
          error: deletionError,
        }));
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
      const deletionError = await deleteMessagesFromServer(state.sessionId, messagesToRemove);
      if (deletionError) {
        store.update((value) => ({
          ...value,
          error: deletionError,
        }));
      }
    }

    await sendMessage({
      text: target.text,
      attachments: extractAttachmentResources(target.attachments ?? []),
    });
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
      const deletionError = await deleteMessagesFromServer(state.sessionId, messagesToRemove);
      if (deletionError) {
        store.update((value) => ({
          ...value,
          error: deletionError,
        }));
      }
    }

    await sendMessage({
      text: trimmed,
      attachments: extractAttachmentResources(target.attachments ?? []),
    });
  }

  function clearError(): void {
    store.update((value) => ({
      ...value,
      error: null,
    }));
  }

  function setModel(model: string): void {
    // Update the UI-selected model immediately
    store.update((value) => ({ ...value, selectedModel: model }));
    // Persist selection to backend active model settings so presets capture the correct model
    try {
      modelSettingsStore.clearErrors();
      // load() will update backend to selectedModel if it differs
      void modelSettingsStore.load(model);
    } catch {
      // no-op
    }
  }

  function ensureSessionId(): string {
    const state = get(store);
    if (state.sessionId) {
      return state.sessionId;
    }
    const sessionId = createId('session');
    store.update((value) => ({ ...value, sessionId }));
    return sessionId;
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
    ensureSessionId,
  };
}

export const chatStore = createChatStore();
