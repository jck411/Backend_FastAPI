<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import { createGoogleAuthStore } from "../../stores/googleAuth";
  import {
    CLIENT_IDS,
    CLIENT_LABELS,
    createMcpServersStore,
    type ClientId,
  } from "../../stores/mcpServers";
  import { createMonarchAuthStore } from "../../stores/monarchAuth";
  import { createSpotifyAuthStore } from "../../stores/spotifyAuth";
  import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";
  import "./system-settings.css";

  export let open = false;

  const dispatch = createEventDispatcher<{ close: void }>();
  const mcpServers = createMcpServersStore();
  const googleAuth = createGoogleAuthStore();
  const monarchAuth = createMonarchAuthStore();
  const spotifyAuth = createSpotifyAuthStore();

  let hasInitialized = false;
  let expandedServers: Set<string> = new Set();
  let monarchEmail = "";
  let monarchPassword = "";
  let monarchMfaSecret = "";
  let showMonarchPassword = false;
  let newServerUrl = "";
  let connectingServer = false;

  $: {
    if (open && !hasInitialized) {
      hasInitialized = true;
      void initialize();
    } else if (!open && hasInitialized) {
      hasInitialized = false;
      googleAuth.reset();
      spotifyAuth.reset();
      expandedServers = new Set();
      newServerUrl = "";
    }
  }

  async function initialize(): Promise<void> {
    await Promise.all([
      mcpServers.load(),
      googleAuth.load(),
      monarchAuth.load(),
      spotifyAuth.load(),
    ]);
  }

  function closeModal(): void {
    if ($mcpServers.saving || $googleAuth.authorizing) {
      return;
    }
    dispatch("close");
  }

  function saveMonarch(): void {
    if (!monarchEmail || !monarchPassword) return;
    monarchAuth.save({
      email: monarchEmail,
      password: monarchPassword,
      mfa_secret: monarchMfaSecret || null,
    });
  }

  function toggleClientServer(
    clientId: ClientId,
    serverId: string,
    enabled: boolean,
  ): void {
    if ($mcpServers.saving) {
      return;
    }
    void mcpServers.setClientServerEnabled(clientId, serverId, enabled);
  }

  function toggleTool(serverId: string, tool: string, enabled: boolean): void {
    if ($mcpServers.saving) {
      return;
    }
    void mcpServers.setToolEnabled(serverId, tool, enabled);
  }

  async function handleConnectServer(): Promise<void> {
    const url = newServerUrl.trim();
    if (!url || connectingServer) return;
    connectingServer = true;
    await mcpServers.connectServer(url);
    connectingServer = false;
    newServerUrl = "";
  }

  async function handleRemoveServer(serverId: string): Promise<void> {
    if ($mcpServers.saving) return;
    await mcpServers.removeServer(serverId);
  }

  function refreshServers(): void {
    if ($mcpServers.saving) {
      return;
    }
    void mcpServers.refresh();
  }

  function refreshGoogleAuth(): void {
    if ($googleAuth.loading || $googleAuth.authorizing) {
      return;
    }
    void googleAuth.load();
  }

  async function startGoogleAuthorization(): Promise<void> {
    if ($googleAuth.authorizing) {
      return;
    }
    await googleAuth.authorize();
  }

  function refreshSpotifyAuth(): void {
    if ($spotifyAuth.loading || $spotifyAuth.authorizing) {
      return;
    }
    void spotifyAuth.load();
  }

  async function startSpotifyAuthorization(): Promise<void> {
    if ($spotifyAuth.authorizing) {
      return;
    }
    await spotifyAuth.authorize();
  }

  async function handleReconnectMonarch(): Promise<void> {
    if ($monarchAuth.saving) {
      return;
    }
    const removed = await monarchAuth.remove();
    if (removed) {
      monarchPassword = "";
      monarchMfaSecret = "";
      showMonarchPassword = false;
    }
  }

  function formatUpdatedAt(timestamp: string | null): string | null {
    if (!timestamp) return null;
    try {
      const date = new Date(timestamp);
      if (Number.isNaN(date.getTime())) {
        return timestamp;
      }
      return new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        year: "numeric",
        month: "short",
        day: "2-digit",
      }).format(date);
    } catch (error) {
      console.warn("Failed to format timestamp", error);
      return timestamp;
    }
  }

  function toggleServerTools(serverId: string): void {
    const newExpanded = new Set(expandedServers);
    if (newExpanded.has(serverId)) {
      newExpanded.delete(serverId);
    } else {
      newExpanded.add(serverId);
    }
    expandedServers = newExpanded;
  }
</script>

{#if open}
  <ModelSettingsDialog
    {open}
    labelledBy="mcp-settings-title"
    modalClass="mcp-settings-modal"
    bodyClass="system-settings-body"
    layerClass="system-settings-layer"
    closeLabel="Close MCP servers"
    closeDisabled={$mcpServers.saving || $googleAuth.authorizing}
    onclose={closeModal}
  >
    <svelte:fragment slot="heading">
      <h2 id="mcp-settings-title">MCP servers</h2>
      <p class="model-settings-subtitle">
        Manage MCP server tools and client access.
      </p>
    </svelte:fragment>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Google services</h3>
          <p class="system-card-caption">
            Connect Calendar, Tasks, Gmail, and Drive with a single consent.
          </p>
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="btn btn-primary btn-small auth-reconnect-btn"
            onclick={() => void startGoogleAuthorization()}
            disabled={$googleAuth.loading || $googleAuth.authorizing}
          >
            {$googleAuth.authorizing
              ? "Authorizing..."
              : $googleAuth.authorized
                ? "Reconnect"
                : "Connect"}
          </button>
        </div>
      </header>

      <div class="system-card-body google-auth-body">
        {#if $googleAuth.loading}
          <p class="status">Checking Google authorization...</p>
        {:else if $googleAuth.error}
          <p class="status error">{$googleAuth.error}</p>
          <div class="google-auth-actions">
            <button
              type="button"
              class="btn btn-ghost btn-small"
              onclick={refreshGoogleAuth}
              disabled={$googleAuth.loading || $googleAuth.authorizing}
            >
              Try again
            </button>
          </div>
        {:else if $googleAuth.authorized}
          <p class="status success">
            Connected as <span class="google-auth-email"
              >{$googleAuth.userEmail}</span
            >.
          </p>
          {#if $googleAuth.expiresAt}
            <p class="status muted">
              Current token expires {formatUpdatedAt($googleAuth.expiresAt) ??
                "soon"}.
            </p>
          {:else}
            <p class="status muted">Access will refresh automatically.</p>
          {/if}
        {:else}
          <p class="status">Google services are not connected.</p>
        {/if}

        <ul class="google-services-list">
          {#each $googleAuth.services as service}
            <li>{service}</li>
          {/each}
        </ul>

        <p class="status muted">
          {#if $googleAuth.authorized}
            Click "Reconnect" to refresh Google authorization for these
            integrations.
          {:else}
            Click "Connect" to authorize these integrations for the assistant.
          {/if}
        </p>
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Spotify</h3>
          <p class="system-card-caption">
            Connect Spotify for music control and playback.
          </p>
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="btn btn-primary btn-small auth-reconnect-btn"
            onclick={() => void startSpotifyAuthorization()}
            disabled={$spotifyAuth.loading || $spotifyAuth.authorizing}
          >
            {$spotifyAuth.authorizing
              ? "Authorizing..."
              : $spotifyAuth.authorized
                ? "Reconnect"
                : "Connect"}
          </button>
        </div>
      </header>

      <div class="system-card-body google-auth-body">
        {#if $spotifyAuth.loading}
          <p class="status">Checking Spotify authorization...</p>
        {:else if $spotifyAuth.error}
          <p class="status error">{$spotifyAuth.error}</p>
          <div class="google-auth-actions">
            <button
              type="button"
              class="btn btn-ghost btn-small"
              onclick={refreshSpotifyAuth}
              disabled={$spotifyAuth.loading || $spotifyAuth.authorizing}
            >
              Try again
            </button>
          </div>
        {:else if $spotifyAuth.authorized}
          <p class="status success">
            Connected as <span class="google-auth-email"
              >{$spotifyAuth.userEmail}</span
            >.
          </p>
          <p class="status muted">Access will refresh automatically.</p>
        {:else}
          <p class="status">Spotify is not connected.</p>
        {/if}

        <p class="status muted">
          {#if $spotifyAuth.authorized}
            Click "Reconnect" to refresh Spotify authorization.
          {:else}
            Click "Connect" to authorize music control and playback features.
          {/if}
        </p>
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Monarch Money</h3>
          <p class="system-card-caption">Connect your Monarch Money account.</p>
        </div>
        <div class="system-card-actions">
          {#if $monarchAuth.configured}
            <button
              type="button"
              class="btn btn-primary btn-small auth-reconnect-btn"
              onclick={() => void handleReconnectMonarch()}
              disabled={$monarchAuth.saving}
            >
              Reconnect
            </button>
          {:else}
            <button
              type="button"
              class="btn btn-primary btn-small auth-reconnect-btn"
              onclick={saveMonarch}
              disabled={$monarchAuth.saving ||
                !monarchEmail ||
                !monarchPassword}
            >
              {$monarchAuth.saving ? "Saving..." : "Connect"}
            </button>
          {/if}
        </div>
      </header>

      <div class="system-card-body">
        {#if $monarchAuth.loading}
          <p class="status">Checking Monarch status...</p>
        {:else if $monarchAuth.configured}
          <p class="status success">
            Connected as <span class="google-auth-email"
              >{$monarchAuth.email}</span
            >.
          </p>
        {:else}
          <div class="monarch-form">
            <label>
              Email
              <input
                type="email"
                class="input-control"
                bind:value={monarchEmail}
                placeholder="email@example.com"
              />
            </label>
            <label>
              Password
              <div class="password-input-wrapper">
                <input
                  class="input-control"
                  type={showMonarchPassword ? "text" : "password"}
                  bind:value={monarchPassword}
                  placeholder="Password"
                />
                <button
                  type="button"
                  class="btn btn-ghost btn-icon btn-small"
                  onclick={() => (showMonarchPassword = !showMonarchPassword)}
                  title={showMonarchPassword
                    ? "Hide password"
                    : "Show password"}
                >
                  {#if showMonarchPassword}
                    <!-- Eye Off Icon -->
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    >
                      <path
                        d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"
                      ></path>
                      <line x1="1" y1="1" x2="23" y2="23"></line>
                    </svg>
                  {:else}
                    <!-- Eye Icon -->
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    >
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"
                      ></path>
                      <circle cx="12" cy="12" r="3"></circle>
                    </svg>
                  {/if}
                </button>
              </div>
            </label>
            <label>
              MFA Secret (Optional)
              <input
                type="text"
                class="input-control"
                bind:value={monarchMfaSecret}
                placeholder="MFA Secret"
              />
            </label>
            <p
              class="status muted"
              style="margin-top: -0.5rem; margin-bottom: 1rem; font-size: 0.8em;"
            >
              If you already use an app, you must <strong>reset MFA</strong> in Monarch
              Settings to see the secret key again. Enter the new key here AND in
              your app.
            </p>
            {#if $monarchAuth.error}
              <p class="status error">{$monarchAuth.error}</p>
            {/if}
          </div>
        {/if}
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Server status</h3>
          {#if $mcpServers.updatedAt}
            <p class="system-card-caption">
              Last updated {formatUpdatedAt($mcpServers.updatedAt) ?? ""}
            </p>
          {:else}
            <p class="system-card-caption">
              Toggle integrations available to the assistant.
            </p>
          {/if}
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="btn btn-ghost btn-small"
            onclick={() => void mcpServers.selectNone()}
            disabled={$mcpServers.saving ||
              $mcpServers.refreshing ||
              !$mcpServers.servers.length}
          >
            Select none
          </button>
          <button
            type="button"
            class="btn btn-ghost btn-small"
            onclick={refreshServers}
            disabled={$mcpServers.refreshing || $mcpServers.saving}
          >
            {$mcpServers.refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </header>

      <div class="system-card-body">
        {#if $mcpServers.loading}
          <p class="status">Loading MCP servers...</p>
        {:else if $mcpServers.error}
          <p class="status error">{$mcpServers.error}</p>
        {:else}
          <!-- Add Server -->
          <div class="add-server-row">
            <input
              type="url"
              class="input-control"
              placeholder="http://192.168.1.110:9003/mcp"
              bind:value={newServerUrl}
              disabled={connectingServer || $mcpServers.saving}
              onkeydown={(e) => {
                if (e.key === "Enter") void handleConnectServer();
              }}
            />
            <button
              type="button"
              class="btn btn-primary btn-small"
              onclick={() => void handleConnectServer()}
              disabled={connectingServer ||
                !newServerUrl.trim() ||
                $mcpServers.saving}
            >
              {connectingServer ? "Connecting..." : "Connect"}
            </button>
          </div>

          {#if !$mcpServers.servers.length}
            <p class="status">No MCP servers configured.</p>
          {:else}
            <ul class="server-list">
              {#each $mcpServers.servers as server}
                <li class="server-row" data-connected={server.connected}>
                  <div class="server-row-header">
                    <div class="server-heading">
                      <h4>{server.id}</h4>
                      <div class="server-meta">
                        <span
                          class:connected={server.connected}
                          class:offline={!server.connected}
                        >
                          {server.connected ? "Connected" : "Offline"}
                        </span>
                        <span aria-hidden="true">&bull;</span>
                        <span class="server-url" title={server.url}
                          >{server.url}</span
                        >
                      </div>
                    </div>
                    <div class="server-toggles">
                      <div class="client-toggles-group">
                        {#each CLIENT_IDS as clientId}
                          <label
                            class="toggle client-toggle"
                            title="Enable for {CLIENT_LABELS[clientId]} client"
                          >
                            <input
                              type="checkbox"
                              checked={$mcpServers.clientPreferences[
                                clientId
                              ] === null ||
                                $mcpServers.clientPreferences[
                                  clientId
                                ]?.includes(server.id)}
                              disabled={!server.connected || $mcpServers.saving}
                              onchange={(event) =>
                                toggleClientServer(
                                  clientId,
                                  server.id,
                                  event.currentTarget.checked,
                                )}
                            />
                            <span>{CLIENT_LABELS[clientId]}</span>
                          </label>
                        {/each}
                      </div>
                      <button
                        type="button"
                        class="btn btn-ghost btn-small btn-danger"
                        title="Remove this server"
                        disabled={$mcpServers.saving}
                        onclick={() => void handleRemoveServer(server.id)}
                      >
                        Remove
                      </button>
                    </div>
                  </div>

                  <div class="server-row-body">
                    <button
                      type="button"
                      class="tools-toggle"
                      class:open={expandedServers.has(server.id)}
                      onclick={() => toggleServerTools(server.id)}
                      aria-expanded={expandedServers.has(server.id)}
                      aria-controls="tools-{server.id}"
                    >
                      <span class="tools-toggle__label">
                        {server.tool_count} tool{server.tool_count === 1
                          ? ""
                          : "s"} available
                      </span>
                      <svg
                        class="tools-toggle__icon"
                        width="12"
                        height="12"
                        viewBox="0 0 12 12"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                        aria-hidden="true"
                      >
                        <path
                          d="M2.5 4.5L6 8L9.5 4.5"
                          stroke="currentColor"
                          stroke-width="1.5"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />
                      </svg>
                    </button>

                    {#if expandedServers.has(server.id)}
                      <div id="tools-{server.id}" class="tools-dropdown">
                        {#if server.tools.length}
                          <ul class="tool-list">
                            {#each server.tools as tool}
                              <li
                                class="tool-row"
                                data-disabled={!tool.enabled}
                              >
                                <div class="tool-info">
                                  <span class="tool-name">{tool.name}</span>
                                </div>
                                <label class="toggle">
                                  <input
                                    type="checkbox"
                                    checked={tool.enabled}
                                    disabled={$mcpServers.saving}
                                    onchange={(event) =>
                                      toggleTool(
                                        server.id,
                                        tool.name,
                                        event.currentTarget.checked,
                                      )}
                                  />
                                  <span
                                    >{tool.enabled
                                      ? "Enabled"
                                      : "Disabled"}</span
                                  >
                                </label>
                              </li>
                            {/each}
                          </ul>
                        {:else}
                          <p class="status">Tool list unavailable.</p>
                        {/if}

                        {#if server.disabled_tools.length}
                          <p class="status warning">
                            Disabled tool ids: {server.disabled_tools.join(
                              ", ",
                            )}
                          </p>
                        {/if}
                      </div>
                    {/if}
                  </div>
                </li>
              {/each}
            </ul>
          {/if}
          {#if $mcpServers.saveError}
            <p class="status error">{$mcpServers.saveError}</p>
          {/if}
        {/if}
      </div>
    </article>

    <footer slot="footer" class="model-settings-footer system-settings-footer">
      {#if $mcpServers.saveError}
        <p class="status error">{$mcpServers.saveError}</p>
      {:else if $mcpServers.saving}
        <p class="status">Saving...</p>
      {:else}
        <p class="status muted">Changes are saved automatically.</p>
      {/if}
    </footer>
  </ModelSettingsDialog>
{/if}
