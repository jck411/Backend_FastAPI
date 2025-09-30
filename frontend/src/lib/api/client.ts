import { resolveApiPath } from './config';
import { parseSsePayload } from './sse';
import type {
  ChatCompletionChunk,
  ChatCompletionRequest,
  DeepgramTokenResponse,
  GenerationDetailsResponse,
  ActiveModelSettingsPayload,
  ActiveModelSettingsResponse,
  ModelListResponse,
  SystemPromptPayload,
  SystemPromptResponse,
  McpServersResponse,
  McpServerUpdatePayload,
  McpServersCollectionPayload,
  SseEvent,
} from './types';

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function requestJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...init?.headers,
    },
    ...init,
  });

  if (!response.ok) {
    let message = response.statusText;
    try {
      const data = await response.json();
      message = data.detail || data.message || JSON.stringify(data);
    } catch (err) {
      // ignore JSON parse errors
    }
    throw new ApiError(response.status, message);
  }

  return (await response.json()) as T;
}

async function requestVoid(input: RequestInfo, init?: RequestInit): Promise<void> {
  const response = await fetch(input, {
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...init?.headers,
    },
    ...init,
  });

  if (!response.ok) {
    let message = response.statusText;
    try {
      const data = await response.json();
      message = data.detail || data.message || JSON.stringify(data);
    } catch (err) {
      // ignore JSON parse errors
    }
    throw new ApiError(response.status, message);
  }
}

export async function fetchModels(): Promise<ModelListResponse> {
  return requestJson<ModelListResponse>(resolveApiPath('/api/models'));
}

export async function requestDeepgramToken(): Promise<DeepgramTokenResponse> {
  return requestJson<DeepgramTokenResponse>(resolveApiPath('/api/stt/deepgram/token'), {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export async function fetchGenerationDetails(
  generationId: string,
): Promise<GenerationDetailsResponse> {
  const path = `/api/chat/generation/${encodeURIComponent(generationId)}`;
  return requestJson<GenerationDetailsResponse>(resolveApiPath(path));
}

export async function deleteChatMessage(
  sessionId: string,
  clientMessageId: string,
): Promise<void> {
  const path = `/api/chat/session/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(clientMessageId)}`;
  await requestVoid(resolveApiPath(path), {
    method: 'DELETE',
  });
}

export async function fetchModelSettings(): Promise<ActiveModelSettingsResponse> {
  return requestJson<ActiveModelSettingsResponse>(resolveApiPath('/api/settings/model'));
}

export async function updateModelSettings(
  payload: ActiveModelSettingsPayload,
): Promise<ActiveModelSettingsResponse> {
  return requestJson<ActiveModelSettingsResponse>(resolveApiPath('/api/settings/model'), {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function fetchSystemPrompt(): Promise<SystemPromptResponse> {
  return requestJson<SystemPromptResponse>(resolveApiPath('/api/settings/system-prompt'));
}

export async function updateSystemPrompt(
  payload: SystemPromptPayload,
): Promise<SystemPromptResponse> {
  return requestJson<SystemPromptResponse>(resolveApiPath('/api/settings/system-prompt'), {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function fetchMcpServers(): Promise<McpServersResponse> {
  return requestJson<McpServersResponse>(resolveApiPath('/api/mcp/servers/'));
}

export async function replaceMcpServers(
  payload: McpServersCollectionPayload,
): Promise<McpServersResponse> {
  return requestJson<McpServersResponse>(resolveApiPath('/api/mcp/servers/'), {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function patchMcpServer(
  serverId: string,
  payload: McpServerUpdatePayload,
): Promise<McpServersResponse> {
  const path = `/api/mcp/servers/${encodeURIComponent(serverId)}`;
  return requestJson<McpServersResponse>(resolveApiPath(path), {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function refreshMcpServers(): Promise<McpServersResponse> {
  return requestJson<McpServersResponse>(resolveApiPath('/api/mcp/servers/refresh'), {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export interface ChatStreamCallbacks {
  onSession?: (sessionId: string) => void;
  onChunk?: (chunk: ChatCompletionChunk, rawEvent: SseEvent) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
}

export interface ChatStreamOptions extends ChatStreamCallbacks {
  signal?: AbortSignal;
}

const NEWLINE_BUFFER = /\n\n|\r\r|\r\n\r\n/;

export async function streamChat(
  payload: ChatCompletionRequest,
  { onChunk, onDone, onError, onSession, signal }: ChatStreamOptions = {},
): Promise<void> {
  const response = await fetch(resolveApiPath('/api/chat/stream'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok || !response.body) {
    const message = response.statusText || 'Failed to connect to chat stream';
    const error = new ApiError(response.status || 0, message);
    onError?.(error);
    throw error;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split(NEWLINE_BUFFER);
      // keep the last partial chunk in the buffer
      buffer = parts.pop() ?? '';

      for (const part of parts) {
        const events = parseSsePayload(part);
        for (const event of events) {
          if (event.event === 'session' && event.data) {
            try {
              const sessionPayload = JSON.parse(event.data) as { session_id?: string };
              if (sessionPayload.session_id) {
                onSession?.(sessionPayload.session_id);
              }
            } catch (err) {
              console.warn('Failed to parse session payload', err);
            }
            continue;
          }

          if (event.event !== 'message') {
            onChunk?.({
              choices: [],
              object: 'event',
              meta: { event: event.event, data: event.data },
            }, event);
            continue;
          }

          if (event.data === '[DONE]') {
            onDone?.();
            return;
          }

          if (!event.data) {
            continue;
          }

          try {
            const chunk = JSON.parse(event.data) as ChatCompletionChunk;
            onChunk?.(chunk, event);
          } catch (err) {
            console.warn('Failed to parse SSE chunk', err, event.data);
          }
        }
      }
    }

    // Flush remaining buffered data.
    if (buffer.trim()) {
      const events = parseSsePayload(buffer);
      for (const event of events) {
        if (event.event === 'session' && event.data) {
          try {
            const sessionPayload = JSON.parse(event.data) as { session_id?: string };
            if (sessionPayload.session_id) {
              onSession?.(sessionPayload.session_id);
            }
          } catch (err) {
            console.warn('Failed to parse session payload', err);
          }
        } else if (event.event === 'message') {
          if (event.data === '[DONE]') {
            onDone?.();
          } else if (event.data) {
            try {
              const chunk = JSON.parse(event.data) as ChatCompletionChunk;
              onChunk?.(chunk, event);
            } catch (err) {
              console.warn('Failed to parse SSE chunk', err, event.data);
            }
          }
        }
      }
    }

    onDone?.();
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      return;
    }
    const error = err instanceof Error ? err : new Error(String(err));
    onError?.(error);
    throw error;
  } finally {
    reader.releaseLock();
  }
}

export { ApiError };
