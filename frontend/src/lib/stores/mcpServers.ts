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

/** All supported client types. */
export const CLIENT_IDS = ['svelte', 'voice', 'kiosk', 'cli'] as const;
export type ClientId = (typeof CLIENT_IDS)[number];

/** Display labels for each client type. */
export const CLIENT_LABELS: Record<ClientId, string> = {
  svelte: 'Main',
  voice: 'Voice',
  kiosk: 'Kiosk',
  cli: 'CLI',
};

interface McpServersState {
  loading: boolean;
  refreshing: boolean;
  saving: boolean;
  error: string | null;
  saveError: string | null;
  servers: McpServerStatus[];
  updatedAt: string | null;
  /** Server IDs enabled per client (null = all allowed for that client). */
  clientPreferences: Record<ClientId, string[] | null>;
  /** Whether preferences have been loaded. */
  prefsLoaded: boolean;
}

const INITIAL_STATE: McpServersState = {
  loading: false,
  refreshing: false,
  saving: false,
  error: null,
  saveError: null,
  servers: [],
  updatedAt: null,
  clientPreferences: {
    svelte: null,
    voice: null,
    kiosk: null,
    cli: null,
  },
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
      const [response, ...prefsResults] = await Promise.all([
        fetchMcpServers(),
        ...CLIENT_IDS.map((id) => fetchClientPreferences(id)),
      ]);

      const clientPreferences: Record<ClientId, string[] | null> = {
        svelte: null,
        voice: null,
        kiosk: null,
        cli: null,
      };

      CLIENT_IDS.forEach((clientId, index) => {
        const prefs = prefsResults[index];
        clientPreferences[clientId] =
          prefs.enabled_servers.length > 0 ? prefs.enabled_servers : null;
      });

      store.set({
        ...INITIAL_STATE,
        servers: response.servers,
        updatedAt: response.updated_at ?? null,
        clientPreferences,
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
      const current = snapshot.clientPreferences.svelte ?? response.servers.map((s) => s.id);
      if (!current.includes(server.id)) {
        const updated = [...current, server.id];
        try {
          const prefs = await updateClientPreferences('svelte', updated);
          store.update((state) => ({
            ...mergeResponse(state, response),
            clientPreferences: {
              ...state.clientPreferences,
              svelte: prefs.enabled_servers.length > 0 ? prefs.enabled_servers : null,
            },
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

  /** Toggle whether a server is enabled for a specific client (client preferences). */
  async function setClientServerEnabled(
    clientId: ClientId,
    serverId: string,
    enabled: boolean,
  ): Promise<void> {
    const snapshot = get(store);
    const current = snapshot.clientPreferences[clientId] ?? snapshot.servers.map((s) => s.id);
    let updated: string[];
    if (enabled) {
      updated = current.includes(serverId) ? current : [...current, serverId];
    } else {
      updated = current.filter((id) => id !== serverId);
    }

    store.update((state) => ({
      ...state,
      clientPreferences: {
        ...state.clientPreferences,
        [clientId]: updated,
      },
      saving: true,
      saveError: null,
    }));

    try {
      const prefs = await updateClientPreferences(clientId, updated);
      store.update((state) => ({
        ...state,
        clientPreferences: {
          ...state.clientPreferences,
          [clientId]: prefs.enabled_servers.length > 0 ? prefs.enabled_servers : null,
        },
        saving: false,
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update preferences.';
      // Revert optimistic update
      store.update((state) => ({
        ...state,
        clientPreferences: {
          ...state.clientPreferences,
          [clientId]: current.length > 0 ? current : null,
        },
        saving: false,
        saveError: message,
      }));
    }
  }

  /** Check if a server is enabled for a specific client. */
  function isServerEnabledForClient(clientId: ClientId, serverId: string): boolean {
    const snapshot = get(store);
    const prefs = snapshot.clientPreferences[clientId];
    if (prefs === null) return true; // null = all allowed
    return prefs.includes(serverId);
  }

  /** Uncheck all MCP servers for all clients and disable all tools. */
  async function selectNone(): Promise<void> {
    const snapshot = get(store);
    if (!snapshot.servers.length) return;

    store.update((state) => ({ ...state, saving: true, saveError: null }));

    try {
      // Clear client preferences: no servers enabled for any client
      await Promise.all(
        CLIENT_IDS.map((clientId) => updateClientPreferences(clientId, [])),
      );

      // Disable all tools on every server
      await Promise.all(
        snapshot.servers.map((server) => {
          const allToolNames = server.tools.map((t) => t.name);
          if (allToolNames.length === 0) return Promise.resolve();
          return patchMcpServer(server.id, { disabled_tools: allToolNames });
        }),
      );

      const response = await fetchMcpServers();
      const prefsResults = await Promise.all(
        CLIENT_IDS.map((id) => fetchClientPreferences(id)),
      );
      const clientPreferences: Record<ClientId, string[] | null> = {
        svelte: null,
        voice: null,
        kiosk: null,
        cli: null,
      };
      CLIENT_IDS.forEach((clientId, index) => {
        const prefs = prefsResults[index];
        // After selectNone the API returns []; keep [] so UI shows none selected
        clientPreferences[clientId] =
          prefs.enabled_servers.length > 0 ? prefs.enabled_servers : [];
      });

      store.update((state) => ({
        ...state,
        servers: response.servers,
        updatedAt: response.updated_at ?? null,
        clientPreferences,
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
    setClientServerEnabled,
    isServerEnabledForClient,
    selectNone,
  };
}

export type { ClientId, McpServersState };
