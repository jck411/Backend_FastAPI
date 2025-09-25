import { get, writable } from 'svelte/store';
import { streamChat } from '../api/client';
import type { ChatCompletionRequest } from '../api/types';

export type ConversationRole = 'user' | 'assistant' | 'system' | 'tool';

export interface ConversationMessage {
  id: string;
  role: ConversationRole;
  content: string;
  pending?: boolean;
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
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function toChatPayload(state: ChatState, prompt: string): ChatCompletionRequest {
  const history = state.messages.map((item) => ({
    role: item.role,
    content: item.content,
  }));

  history.push({ role: 'user', content: prompt });

  const payload: ChatCompletionRequest = {
    model: state.selectedModel,
    session_id: state.sessionId ?? undefined,
    messages: history,
  };

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

    try {
      await streamChat(payload, {
        signal: abortController.signal,
        onSession(sessionId) {
          store.update((value) => ({ ...value, sessionId }));
        },
        onChunk(chunk) {
          const deltaText = chunk.choices?.map((choice) => choice.delta?.content ?? '').join('') ?? '';
          if (!deltaText) return;
          store.update((value) => {
            const messages = value.messages.map((message) => {
              if (message.id === assistantMessageId) {
                return {
                  ...message,
                  content: `${message.content}${deltaText}`,
                };
              }
              return message;
            });
            return { ...value, messages };
          });
        },
        onDone() {
          store.update((value) => ({
            ...value,
            isStreaming: false,
            messages: value.messages.map((message) =>
              message.id === assistantMessageId ? { ...message, pending: false } : message,
            ),
          }));
        },
        onError(error) {
          console.error('Chat stream error', error);
          store.update((value) => ({
            ...value,
            isStreaming: false,
            error: error.message ?? 'Unknown error',
            messages: value.messages.filter((message) => message.id !== assistantMessageId),
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
        messages: value.messages.filter((msg) => msg.id !== assistantMessageId),
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
          (message) => !(message.role === 'assistant' && message.pending && !message.content),
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

  function setModel(model: string): void {
    store.update((value) => ({ ...value, selectedModel: model }));
  }

  return {
    subscribe: store.subscribe,
    sendMessage,
    cancelStream,
    clearConversation,
    setModel,
  };
}

export const chatStore = createChatStore();
