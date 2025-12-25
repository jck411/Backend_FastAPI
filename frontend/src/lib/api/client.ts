import { resolveApiPath } from './config';
import { parseSsePayload } from './sse';
import type {
  ActiveModelSettingsPayload,
  ActiveModelSettingsResponse,
  AttachmentUploadResponse,
  ChatCompletionChunk,
  ChatCompletionRequest,
  DeepgramTokenResponse,
  GenerationDetailsResponse,
  GoogleAuthAuthorizeRequest,
  GoogleAuthAuthorizeResponse,
  GoogleAuthStatusResponse,
  McpServersCollectionPayload,
  McpServersResponse,
  McpServerUpdatePayload,
  ModelListResponse,
  MonarchCredentials,
  MonarchStatusResponse,
  PresetConfig,
  PresetCreatePayload,
  // Presets
  PresetListItem,
  PresetSaveSnapshotPayload,
  SpotifyAuthAuthorizeRequest,
  SpotifyAuthAuthorizeResponse,
  SpotifyAuthStatusResponse,
  SseEvent,
  SystemPromptPayload,
  SystemPromptResponse,
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
  return requestJson<ActiveModelSettingsResponse>(resolveApiPath('/api/clients/svelte/llm'));
}

export async function updateModelSettings(
  payload: ActiveModelSettingsPayload,
): Promise<ActiveModelSettingsResponse> {
  return requestJson<ActiveModelSettingsResponse>(resolveApiPath('/api/clients/svelte/llm'), {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function fetchSystemPrompt(): Promise<SystemPromptResponse> {
  // System prompt is part of LLM settings in the per-client API
  const llm = await requestJson<{ system_prompt: string | null }>(resolveApiPath('/api/clients/svelte/llm'));
  return { system_prompt: llm.system_prompt };
}

export async function updateSystemPrompt(
  payload: SystemPromptPayload,
): Promise<SystemPromptResponse> {
  // Update via LLM settings endpoint
  const updated = await requestJson<{ system_prompt: string | null }>(resolveApiPath('/api/clients/svelte/llm'), {
    method: 'PUT',
    body: JSON.stringify({ system_prompt: payload.system_prompt }),
  });
  return { system_prompt: updated.system_prompt };
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

export async function setMcpServerClientEnabled(
  serverId: string,
  clientId: string,
  enabled: boolean,
): Promise<McpServersResponse> {
  const path = `/api/mcp/servers/${encodeURIComponent(serverId)}/clients/${encodeURIComponent(clientId)}?enabled=${enabled}`;
  return requestJson<McpServersResponse>(resolveApiPath(path), {
    method: 'PATCH',
  });
}

export async function fetchGoogleAuthStatus(): Promise<GoogleAuthStatusResponse> {
  return requestJson<GoogleAuthStatusResponse>(resolveApiPath('/api/google-auth/status'));
}

export async function startGoogleAuthorization(
  payload: GoogleAuthAuthorizeRequest,
): Promise<GoogleAuthAuthorizeResponse> {
  return requestJson<GoogleAuthAuthorizeResponse>(resolveApiPath('/api/google-auth/authorize'), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchMonarchStatus(): Promise<MonarchStatusResponse> {
  return requestJson<MonarchStatusResponse>(resolveApiPath('/api/monarch-auth/status'));
}

export async function saveMonarchCredentials(
  creds: MonarchCredentials,
): Promise<MonarchStatusResponse> {
  return requestJson<MonarchStatusResponse>(resolveApiPath('/api/monarch-auth/credentials'), {
    method: 'POST',
    body: JSON.stringify(creds),
  });
}

export async function deleteMonarchCredentials(): Promise<MonarchStatusResponse> {
  return requestJson<MonarchStatusResponse>(resolveApiPath('/api/monarch-auth/credentials'), {
    method: 'DELETE',
  });
}

export async function fetchSpotifyAuthStatus(): Promise<SpotifyAuthStatusResponse> {
  return requestJson<SpotifyAuthStatusResponse>(resolveApiPath('/api/spotify-auth/status'));
}

export async function startSpotifyAuthorization(
  payload: SpotifyAuthAuthorizeRequest,
): Promise<SpotifyAuthAuthorizeResponse> {
  return requestJson<SpotifyAuthAuthorizeResponse>(resolveApiPath('/api/spotify-auth/authorize'), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function uploadAttachment(
  file: File,
  sessionId: string,
): Promise<AttachmentUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('session_id', sessionId);

  const response = await fetch(resolveApiPath('/api/uploads'), {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    let message = response.statusText || 'Upload failed';
    try {
      const data = await response.json();
      message = (data?.detail as string) ?? message;
    } catch (error) {
      // ignore parse errors
    }
    throw new ApiError(response.status || 0, message);
  }

  return (await response.json()) as AttachmentUploadResponse;
}

export interface ChatStreamCallbacks {
  onSession?: (sessionId: string) => void;
  onChunk?: (chunk: ChatCompletionChunk, rawEvent: SseEvent) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
  onNotice?: (payload: Record<string, unknown>) => void;
}

export interface ChatStreamOptions extends ChatStreamCallbacks {
  signal?: AbortSignal;
}

const NEWLINE_BUFFER = /\n\n|\r\r|\r\n\r\n/;

export async function streamChat(
  payload: ChatCompletionRequest,
  { onChunk, onDone, onError, onSession, onNotice, signal }: ChatStreamOptions = {},
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

          if (event.event === 'notice') {
            if (event.data) {
              try {
                const payload = JSON.parse(event.data) as Record<string, unknown>;
                onNotice?.(payload);
              } catch (err) {
                console.warn('Failed to parse notice payload', err, event.data);
              }
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
        } else if (event.event === 'notice') {
          if (event.data) {
            try {
              const payload = JSON.parse(event.data) as Record<string, unknown>;
              onNotice?.(payload);
            } catch (err) {
              console.warn('Failed to parse notice payload', err, event.data);
            }
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

/* Preset API - using per-client svelte presets */

export async function fetchPresets(): Promise<PresetListItem[]> {
  interface BackendPreset {
    name: string;
    llm?: { model?: string;[key: string]: unknown };
    model_filters?: PresetModelFilters | null;
    created_at?: string | null;
    updated_at?: string | null;
    [key: string]: unknown;
  }

  const response = await requestJson<{ presets: BackendPreset[]; active_index: number | null }>(
    resolveApiPath('/api/clients/svelte/presets')
  );

  return response.presets.map((preset, index) => ({
    name: preset.name,
    model: preset.llm?.model ?? 'unknown',
    is_default: index === response.active_index,
    has_filters: Boolean(preset.model_filters),
    created_at: preset.created_at ?? new Date().toISOString(),
    updated_at: preset.updated_at ?? new Date().toISOString(),
  }));
}


export async function fetchPreset(name: string): Promise<PresetConfig> {
  interface BackendPreset {
    name: string;
    llm?: {
      model?: string;
      system_prompt?: string | null;
      [key: string]: unknown
    };
    model_filters?: PresetModelFilters | null;
    created_at?: string | null;
    updated_at?: string | null;
    [key: string]: unknown;
  }

  const response = await requestJson<{ presets: BackendPreset[]; active_index: number | null }>(
    resolveApiPath('/api/clients/svelte/presets')
  );
  const preset = response.presets.find(p => p.name === name);
  if (!preset) throw new ApiError(404, `Preset not found: ${name}`);

  const index = response.presets.indexOf(preset);
  return {
    name: preset.name,
    model: preset.llm?.model ?? 'unknown',
    system_prompt: preset.llm?.system_prompt ?? null,
    model_filters: preset.model_filters ?? null,
    is_default: index === response.active_index,
    created_at: preset.created_at ?? new Date().toISOString(),
    updated_at: preset.updated_at ?? new Date().toISOString(),
  };
}


export async function createPreset(payload: PresetCreatePayload): Promise<PresetConfig> {
  // Get current LLM settings (includes model and system_prompt)
  const currentLlm = await requestJson<Record<string, unknown>>(resolveApiPath('/api/clients/svelte/llm'));

  // Create preset via POST with LLM settings only (MCP is separate)
  const presetPayload = {
    name: payload.name,
    llm: currentLlm,
    model_filters: payload.model_filters,
  };

  const result = await requestJson<{ presets: PresetConfig[]; active_index: number | null }>(
    resolveApiPath('/api/clients/svelte/presets'),
    {
      method: 'POST',
      body: JSON.stringify(presetPayload),
    }
  );

  // Return the newly created preset (last in list)
  const newPreset = result.presets.find(p => p.name === payload.name);
  if (!newPreset) throw new ApiError(500, 'Failed to create preset');
  return newPreset;
}



export async function savePresetSnapshot(
  name: string,
  _payload?: PresetSaveSnapshotPayload | null,
): Promise<PresetConfig> {
  // Get current presets to find the index
  const presets = await requestJson<{ presets: PresetConfig[]; active_index: number | null }>(
    resolveApiPath('/api/clients/svelte/presets')
  );

  const index = presets.presets.findIndex(p => p.name === name);
  if (index === -1) throw new ApiError(404, `Preset not found: ${name}`);

  // Get current LLM settings (includes model and system_prompt)
  const currentLlm = await requestJson<Record<string, unknown>>(resolveApiPath('/api/clients/svelte/llm'));

  // Update preset at index with current LLM settings only (MCP is separate)
  const result = await requestJson<{ presets: PresetConfig[]; active_index: number | null }>(
    resolveApiPath(`/api/clients/svelte/presets/${index}`),
    {
      method: 'PUT',
      body: JSON.stringify({
        llm: currentLlm,
        model_filters: _payload?.model_filters ?? null,
      }),
    }
  );

  const updatedPreset = result.presets[index];
  if (!updatedPreset) throw new ApiError(500, 'Failed to save preset snapshot');
  return updatedPreset;
}




export async function deletePreset(name: string): Promise<{ deleted: boolean }> {
  // Delete preset by name
  await requestVoid(resolveApiPath(`/api/clients/svelte/presets/by-name/${encodeURIComponent(name)}`), {
    method: 'DELETE',
  });
  return { deleted: true };
}

export async function applyPreset(name: string): Promise<PresetConfig> {
  // Apply preset by name
  const path = `/api/clients/svelte/presets/by-name/${encodeURIComponent(name)}/apply`;
  const result = await requestJson<{ llm: PresetConfig }>(resolveApiPath(path), {
    method: 'POST',
    body: JSON.stringify({}),
  });
  // The apply endpoint returns ClientSettings, extract LLM as the preset config
  return result.llm as PresetConfig;
}

export async function setDefaultPreset(name: string): Promise<PresetConfig> {
  // Set preset as active by name
  const path = `/api/clients/svelte/presets/by-name/${encodeURIComponent(name)}/set-active`;
  const result = await requestJson<{ presets: PresetConfig[]; active_index: number | null }>(resolveApiPath(path), {
    method: 'POST',
    body: JSON.stringify({}),
  });
  // Return the preset that was made active
  const preset = result.presets.find(p => p.name === name);
  if (!preset) throw new ApiError(404, `Preset not found: ${name}`);
  return preset;
}


export async function fetchDefaultPreset(): Promise<PresetConfig | null> {
  const response = await requestJson<{ presets: PresetConfig[]; active_index: number | null }>(resolveApiPath('/api/clients/svelte/presets'));
  if (response.active_index !== null && response.presets[response.active_index]) {
    return response.presets[response.active_index];
  }
  return null;
}


export { ApiError };
