import { get, writable } from 'svelte/store';
import {
  connectMcpServer,
  fetchClientPreferences,
  fetchMcpServers,
  patchMcpServer,
  refreshMcpServers,
  removeMcpServer,
  updateClientPreferences,
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
  /** Server IDs enabled for the current client (null = all allowed). */
  enabledServers: string[] | null;
  /** Whether preferences have been loaded. */
  prefsLoaded: boolean;
}

const CLIENT_ID = 'svelte';

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
  enabledServers: null,
  prefsLoaded: false,
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
      const [response, prefs] = await Promise.all([
        fetchMcpServers(),
        fetchClientPreferences(CLIENT_ID),
      ]);
      store.set({
        ...INITIAL_STATE,
        servers: response.servers,
        updatedAt: response.updated_at ?? null,
        enabledServers: prefs.enabled_servers.length > 0 ? prefs.enabled_servers : null,
        prefsLoaded: true,
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
        let message = 'Failed to update MCP server.';
        if (error instanceof Error) {
          message = error.message;
        } else if (typeof error === 'object' && error !== null) {
          const errObj = error as Record<string, unknown>;
          message = String(errObj.detail || errObj.message || errObj.error || JSON.stringify(error));
        } else if (typeof error === 'string') {
          message = error;
        }
        // Ensure we never show [object Object]
        if (message.includes('[object Object]')) {
          message = 'Failed to save MCP server settings. Check server logs for details.';
        }
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

  async function connectServer(url: string): Promise<McpServerStatus | null> {
    store.update((state) => ({ ...state, saving: true, saveError: null }));
    try {
      const server = await connectMcpServer(url);
      // Reload the full list to get consistent state
      const response = await fetchMcpServers();

      // Auto-enable the new server in client preferences ("Use in chat")
      const snapshot = get(store);
      const current = snapshot.enabledServers ?? response.servers.map((s) => s.id);
      if (!current.includes(server.id)) {
        const updated = [...current, server.id];
        try {
          const prefs = await updateClientPreferences(CLIENT_ID, updated);
          store.update((state) => ({
            ...mergeResponse(state, response),
            enabledServers: prefs.enabled_servers.length > 0 ? prefs.enabled_servers : null,
            saving: false,
          }));
        } catch {
          // Preference update failed, but server is still connected
          store.update((state) => ({
            ...mergeResponse(state, response),
            saving: false,
          }));
        }
      } else {
        store.update((state) => ({
          ...mergeResponse(state, response),
          saving: false,
        }));
      }
      return server;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to connect to MCP server.';
      store.update((state) => ({ ...state, saving: false, saveError: message }));
      return null;
    }
  }

  async function removeServer(serverId: string): Promise<boolean> {
    store.update((state) => ({
      ...state,
      saving: true,
      saveError: null,
      pending: { ...state.pending, [serverId]: true },
    }));
    try {
      await removeMcpServer(serverId);
      const response = await fetchMcpServers();
      store.update((state) => {
        const nextPending = { ...state.pending };
        delete nextPending[serverId];
        return {
          ...mergeResponse(state, response),
          saving: false,
          pending: nextPending,
        };
      });
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to remove MCP server.';
      store.update((state) => {
        const nextPending = { ...state.pending };
        delete nextPending[serverId];
        return { ...state, saving: false, saveError: message, pending: nextPending };
      });
      return false;
    }
  }

  /** Toggle whether a server is enabled for this frontend (client preferences). */
  async function setClientServerEnabled(serverId: string, enabled: boolean): Promise<void> {
    const snapshot = get(store);
    const current = snapshot.enabledServers ?? snapshot.servers.map((s) => s.id);
    let updated: string[];
    if (enabled) {
      updated = current.includes(serverId) ? current : [...current, serverId];
    } else {
      updated = current.filter((id) => id !== serverId);
    }

    store.update((state) => ({
      ...state,
      enabledServers: updated,
      saving: true,
      saveError: null,
    }));

    try {
      const prefs = await updateClientPreferences(CLIENT_ID, updated);
      store.update((state) => ({
        ...state,
        enabledServers: prefs.enabled_servers.length > 0 ? prefs.enabled_servers : null,
        saving: false,
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update preferences.';
      // Revert optimistic update
      store.update((state) => ({
        ...state,
        enabledServers: current.length > 0 ? current : null,
        saving: false,
        saveError: message,
      }));
    }
  }

  /** Check if a server is enabled in client preferences. */
  function isServerEnabledForClient(serverId: string): boolean {
    const snapshot = get(store);
    if (snapshot.enabledServers === null) return true; // null = all allowed
    return snapshot.enabledServers.includes(serverId);
  }

  return {
    subscribe: store.subscribe,
    load,
    refresh,
    setServerEnabled,
    setToolEnabled,
    connectServer,
    removeServer,
    setClientServerEnabled,
    isServerEnabledForClient,
    getServer,
    isPending,
    flushPending,
  };
}

export type { McpServersState };
