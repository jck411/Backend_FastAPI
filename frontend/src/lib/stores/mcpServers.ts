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
  McpServersResponse,
} from '../api/types';

interface McpServersState {
  loading: boolean;
  refreshing: boolean;
  saving: boolean;
  error: string | null;
  saveError: string | null;
  servers: McpServerStatus[];
  updatedAt: string | null;
  /** Server IDs enabled for the main (svelte) client (null = all allowed). */
  enabledServers: string[] | null;
}

const INITIAL_STATE: McpServersState = {
  loading: false,
  refreshing: false,
  saving: false,
  error: null,
  saveError: null,
  servers: [],
  updatedAt: null,
  enabledServers: null,
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
        fetchClientPreferences('svelte'),
      ]);

      store.set({
        ...INITIAL_STATE,
        servers: response.servers,
        updatedAt: response.updated_at ?? null,
        enabledServers: prefs.enabled_servers,
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

  async function setToolEnabled(serverId: string, tool: string, enabled: boolean): Promise<void> {
    const snapshot = get(store);
    const target = snapshot.servers.find((item) => item.id === serverId);
    if (!target) return;

    const disabled = new Set(target.disabled_tools ?? []);
    if (enabled) {
      disabled.delete(tool);
    } else {
      disabled.add(tool);
    }
    const disabledList = Array.from(disabled).sort();

    // Optimistic update
    store.update((state) => ({
      ...state,
      saving: true,
      saveError: null,
      servers: state.servers.map((server) =>
        server.id !== serverId
          ? server
          : {
            ...server,
            disabled_tools: disabledList,
            tools: server.tools.map((item) =>
              item.name === tool ? { ...item, enabled } : item,
            ),
          },
      ),
    }));

    try {
      const response = await patchMcpServer(serverId, { disabled_tools: disabledList });
      store.update((state) => ({
        ...mergeResponse(state, response),
        saving: false,
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update tool.';
      store.update((state) => ({ ...state, saving: false, saveError: message }));
    }
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

  async function connectServer(url: string): Promise<McpServerStatus | null> {
    store.update((state) => ({ ...state, saving: true, saveError: null }));
    try {
      const server = await connectMcpServer(url);
      const response = await fetchMcpServers();

      // Auto-enable the new server in svelte client preferences
      const snapshot = get(store);
      const current = snapshot.enabledServers ?? response.servers.map((s) => s.id);
      if (!current.includes(server.id)) {
        const updated = [...current, server.id];
        try {
          const prefs = await updateClientPreferences('svelte', updated);
          store.update((state) => ({
            ...mergeResponse(state, response),
            enabledServers: prefs.enabled_servers,
            saving: false,
          }));
        } catch {
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
    store.update((state) => ({ ...state, saving: true, saveError: null }));
    try {
      await removeMcpServer(serverId);
      const response = await fetchMcpServers();
      store.update((state) => ({
        ...mergeResponse(state, response),
        saving: false,
      }));
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to remove MCP server.';
      store.update((state) => ({ ...state, saving: false, saveError: message }));
      return false;
    }
  }

  /** Toggle whether a server is enabled for the main (svelte) client. */
  async function setServerEnabled(
    serverId: string,
    enabled: boolean,
  ): Promise<void> {
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
      const prefs = await updateClientPreferences('svelte', updated);
      store.update((state) => ({
        ...state,
        enabledServers: prefs.enabled_servers,
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

  /** Disable all MCP servers for the main client and disable all tools. */
  async function selectNone(): Promise<void> {
    const snapshot = get(store);
    if (!snapshot.servers.length) return;

    store.update((state) => ({ ...state, saving: true, saveError: null }));

    try {
      await updateClientPreferences('svelte', []);

      // Disable all tools on every server
      await Promise.all(
        snapshot.servers.map((server) => {
          const allToolNames = server.tools.map((t) => t.name);
          if (allToolNames.length === 0) return Promise.resolve();
          return patchMcpServer(server.id, { disabled_tools: allToolNames });
        }),
      );

      const [response, prefs] = await Promise.all([
        fetchMcpServers(),
        fetchClientPreferences('svelte'),
      ]);

      store.update((state) => ({
        ...state,
        servers: response.servers,
        updatedAt: response.updated_at ?? null,
        enabledServers: prefs.enabled_servers,
        saving: false,
      }));
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Failed to select none.';
      store.update((state) => ({ ...state, saving: false, saveError: message }));
    }
  }

  return {
    subscribe: store.subscribe,
    load,
    refresh,
    setToolEnabled,
    connectServer,
    removeServer,
    setServerEnabled,
    selectNone,
  };
}

export type { McpServersState };
