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
  saving: boolean;
  dirty: boolean;
  error: string | null;
  saveError: string | null;
  servers: McpServerStatus[];
  updatedAt: string | null;
  pending: Record<string, boolean>;
  pendingChanges: Record<string, McpServerUpdatePayload>;
}

const INITIAL_STATE: McpServersState = {
  loading: false,
  refreshing: false,
  saving: false,
  dirty: false,
  error: null,
  saveError: null,
  servers: [],
  updatedAt: null,
  pending: {},
  pendingChanges: {},
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

  function setServerEnabled(serverId: string, enabled: boolean): void {
    store.update((state) => {
      const servers = state.servers.map((server) =>
        server.id === serverId ? { ...server, enabled } : server,
      );
      const pendingChanges = {
        ...state.pendingChanges,
        [serverId]: {
          ...(state.pendingChanges[serverId] ?? {}),
          enabled,
        },
      };
      return {
        ...state,
        servers,
        dirty: true,
        saveError: null,
        pendingChanges,
      };
    });
  }

  function setToolEnabled(serverId: string, tool: string, enabled: boolean): void {
    store.update((state) => {
      const target = state.servers.find((item) => item.id === serverId);
      if (!target) {
        return state;
      }

      const disabled = new Set(target.disabled_tools ?? []);
      if (enabled) {
        disabled.delete(tool);
      } else {
        disabled.add(tool);
      }
      const disabledList = Array.from(disabled).sort();

      const servers = state.servers.map((server) => {
        if (server.id !== serverId) {
          return server;
        }
        return {
          ...server,
          disabled_tools: disabledList,
          tools: server.tools.map((item) =>
            item.name === tool ? { ...item, enabled } : item,
          ),
        };
      });

      const pendingChanges = {
        ...state.pendingChanges,
        [serverId]: {
          ...(state.pendingChanges[serverId] ?? {}),
          disabled_tools: disabledList,
        },
      };

      return {
        ...state,
        servers,
        dirty: true,
        saveError: null,
        pendingChanges,
      };
    });
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

  async function flushPending(): Promise<boolean> {
    const snapshot = get(store);
    if (!snapshot.dirty) {
      return true;
    }

    const entries = Object.entries(snapshot.pendingChanges);
    if (!entries.length) {
      store.update((state) => ({ ...state, dirty: false }));
      return true;
    }

    store.update((state) => ({ ...state, saving: true, saveError: null }));

    let success = true;

    for (const [serverId, payload] of entries) {
      store.update((state) => ({
        ...state,
        pending: { ...state.pending, [serverId]: true },
      }));

      try {
        const response = await patchMcpServer(serverId, payload);
        store.update((state) => {
          const nextPending = { ...state.pending };
          delete nextPending[serverId];

          const nextChanges = { ...state.pendingChanges };
          delete nextChanges[serverId];

          const merged = mergeResponse(state, response);
          const dirty = Object.keys(nextChanges).length > 0;

          return {
            ...merged,
            pending: nextPending,
            pendingChanges: nextChanges,
            dirty,
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
            saving: false,
            saveError: message,
          };
        });
        success = false;
        break;
      }
    }

    if (success) {
      store.update((state) => ({ ...state, saving: false, dirty: false }));
      return true;
    }

    store.update((state) => ({ ...state, saving: false, dirty: true }));
    return false;
  }

  return {
    subscribe: store.subscribe,
    load,
    refresh,
    setServerEnabled,
    setToolEnabled,
    getServer,
    isPending,
    flushPending,
  };
}

export type { McpServersState };
