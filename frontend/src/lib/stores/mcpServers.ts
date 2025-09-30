import { get, writable } from 'svelte/store';
import {
  fetchMcpServers,
  patchMcpServer,
  refreshMcpServers,
} from '../api/client';
import type {
  McpServerStatus,
  McpServerUpdatePayload,
  McpServersResponse,
} from '../api/types';

interface McpServersState {
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  saveError: string | null;
  servers: McpServerStatus[];
  updatedAt: string | null;
  pending: Record<string, boolean>;
}

const INITIAL_STATE: McpServersState = {
  loading: false,
  refreshing: false,
  error: null,
  saveError: null,
  servers: [],
  updatedAt: null,
  pending: {},
};

function mergeResponse(state: McpServersState, payload: McpServersResponse): McpServersState {
  return {
    ...state,
    servers: payload.servers ?? [],
    updatedAt: payload.updated_at ?? null,
    error: null,
    saveError: null,
  };
}

export function createMcpServersStore() {
  const store = writable<McpServersState>({ ...INITIAL_STATE });

  async function load(): Promise<void> {
    store.set({ ...INITIAL_STATE, loading: true });
    try {
      const response = await fetchMcpServers();
      store.set({
        ...INITIAL_STATE,
        servers: response.servers,
        updatedAt: response.updated_at ?? null,
        loading: false,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load MCP servers.';
      store.set({
        ...INITIAL_STATE,
        loading: false,
        error: message,
      });
    }
  }

  async function applyPatch(serverId: string, payload: McpServerUpdatePayload): Promise<void> {
    store.update((state) => ({
      ...state,
      pending: { ...state.pending, [serverId]: true },
      saveError: null,
    }));
    try {
      const response = await patchMcpServer(serverId, payload);
      store.update((state) => {
        const nextPending = { ...state.pending };
        delete nextPending[serverId];
        return {
          ...mergeResponse(state, response),
          pending: nextPending,
        };
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update MCP server.';
      store.update((state) => {
        const nextPending = { ...state.pending };
        delete nextPending[serverId];
        return {
          ...state,
          pending: nextPending,
          saveError: message,
        };
      });
    }
  }

  async function setServerEnabled(serverId: string, enabled: boolean): Promise<void> {
    await applyPatch(serverId, { enabled });
  }

  async function setToolEnabled(serverId: string, tool: string, enabled: boolean): Promise<void> {
    const snapshot = get(store);
    const target = snapshot.servers.find((item) => item.id === serverId);
    if (!target) {
      return;
    }
    const disabled = new Set(target.disabled_tools ?? []);
    if (enabled) {
      disabled.delete(tool);
    } else {
      disabled.add(tool);
    }
    await applyPatch(serverId, { disabled_tools: Array.from(disabled).sort() });
  }

  async function refresh(): Promise<void> {
    store.update((state) => ({
      ...state,
      refreshing: true,
      error: null,
    }));
    try {
      const response = await refreshMcpServers();
      store.update((state) => ({
        ...mergeResponse(state, response),
        refreshing: false,
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to refresh MCP servers.';
      store.update((state) => ({
        ...state,
        refreshing: false,
        saveError: message,
      }));
    }
  }

  function getServer(serverId: string): McpServerStatus | undefined {
    const snapshot = get(store);
    return snapshot.servers.find((item) => item.id === serverId);
  }

  function isPending(serverId: string): boolean {
    const snapshot = get(store);
    return Boolean(snapshot.pending[serverId]);
  }

  return {
    subscribe: store.subscribe,
    load,
    refresh,
    setServerEnabled,
    setToolEnabled,
    applyPatch,
    getServer,
    isPending,
  };
}

export type { McpServersState };
