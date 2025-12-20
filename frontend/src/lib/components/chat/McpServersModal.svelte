<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import { get } from "svelte/store";
  import { createMcpServersStore } from "../../stores/mcpServers";
  import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";
  import "./system-settings.css";

  export let open = false;

  const dispatch = createEventDispatcher<{ close: void }>();
  const mcpServers = createMcpServersStore();

  let hasInitialized = false;
  let closing = false;
  let expandedServers: Set<string> = new Set();

  // Hardcoded host profiles - each machine has its own path
  const HOST_PROFILES = [
    {
      id: "xps13",
      label: "Dell XPS 13",
      path: "/home/jack/gdrive/host_profiles",
    },
    {
      id: "ryzen-desktop",
      label: "Ryzen Desktop",
      path: "/home/human/gdrive/host_profiles",
    },
  ] as const;

  $: {
    if (open && !hasInitialized) {
      hasInitialized = true;
      void mcpServers.load();
    } else if (!open && hasInitialized) {
      hasInitialized = false;
      expandedServers = new Set();
    }
  }

  async function closeModal(): Promise<void> {
    if (closing || $mcpServers.saving) {
      return;
    }

    closing = true;

    const serversSaved = await mcpServers.flushPending();
    const serversState = get(mcpServers);

    if (serversSaved && !serversState.saveError) {
      dispatch("close");
    }

    closing = false;
  }

  function handleHostProfileChange(serverId: string, profileId: string): void {
    const profile = HOST_PROFILES.find((p) => p.id === profileId);
    if (profile) {
      // Set both the host ID and the root path for this profile
      handleShellEnv(serverId, "HOST_PROFILE_ID", profile.id);
      handleShellEnv(serverId, "HOST_ROOT_PATH", profile.path);
    }
  }

  function toggleServer(serverId: string, enabled: boolean): void {
    if ($mcpServers.saving) {
      return;
    }
    mcpServers.setServerEnabled(serverId, enabled);
  }

  function toggleKiosk(serverId: string, enabled: boolean): void {
    if ($mcpServers.saving) {
      return;
    }
    mcpServers.setKioskEnabled(serverId, enabled);
  }

  function toggleFrontend(serverId: string, enabled: boolean): void {
    if ($mcpServers.saving) {
      return;
    }
    mcpServers.setFrontendEnabled(serverId, enabled);
  }

  function toggleCli(serverId: string, enabled: boolean): void {
    if ($mcpServers.saving) {
      return;
    }
    mcpServers.setCliEnabled(serverId, enabled);
  }

  function toggleTool(serverId: string, tool: string, enabled: boolean): void {
    if ($mcpServers.saving) {
      return;
    }
    mcpServers.setToolEnabled(serverId, tool, enabled);
  }

  function handleShellEnv(serverId: string, key: string, value: string): void {
    if ($mcpServers.saving) {
      return;
    }
    mcpServers.setServerEnv(serverId, key, value);
  }

  function refreshServers(): void {
    const snapshot = get(mcpServers);
    if (snapshot.dirty || snapshot.saving) {
      return;
    }
    void mcpServers.refresh();
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
    closeDisabled={$mcpServers.saving}
    on:close={() => void closeModal()}
  >
    <svelte:fragment slot="heading">
      <h2 id="mcp-settings-title">MCP servers</h2>
      <p class="model-settings-subtitle">
        Manage MCP server availability, tools, and client access.
      </p>
    </svelte:fragment>

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
            on:click={refreshServers}
            disabled={$mcpServers.refreshing ||
              $mcpServers.saving ||
              $mcpServers.dirty}
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
          {#if !$mcpServers.servers.length}
            <p class="status">No MCP servers configured.</p>
          {:else}
            <ul class="server-list">
              {#each $mcpServers.servers as server}
                <li
                  class="server-row"
                  data-connected={server.connected}
                  data-pending={$mcpServers.pending[server.id]
                    ? "true"
                    : "false"}
                  data-dirty={$mcpServers.pendingChanges[server.id]
                    ? "true"
                    : "false"}
                >
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
                        {#if server.module}
                          <span aria-hidden="true">&bull;</span>
                          <span title={server.module}
                            >Module: {server.module}</span
                          >
                        {:else if server.command?.length}
                          <span aria-hidden="true">&bull;</span>
                          <span title={server.command.join(" ")}
                            >Command: {server.command.join(" ")}</span
                          >
                        {/if}
                      </div>
                    </div>
                    <div class="server-toggles">
                      <label
                        class="toggle running-toggle"
                        title="Start/stop the server process"
                      >
                        <input
                          type="checkbox"
                          checked={server.enabled}
                          disabled={$mcpServers.pending[server.id] ||
                            $mcpServers.saving}
                          on:change={(event) =>
                            toggleServer(
                              server.id,
                              (event.target as HTMLInputElement).checked,
                            )}
                        />
                        <span>{server.enabled ? "Running" : "Stopped"}</span>
                      </label>
                      <label
                        class="toggle frontend-toggle"
                        class:toggle-disabled={!server.enabled}
                        title={server.enabled
                          ? "Enable for main web frontend"
                          : "Server must be running"}
                      >
                        <input
                          type="checkbox"
                          checked={server.client_enabled?.svelte ?? true}
                          disabled={!server.enabled ||
                            $mcpServers.pending[server.id] ||
                            $mcpServers.saving}
                          on:change={(event) =>
                            toggleFrontend(
                              server.id,
                              (event.target as HTMLInputElement).checked,
                            )}
                        />
                        <span>Frontend</span>
                      </label>
                      <label
                        class="toggle kiosk-toggle"
                        class:toggle-disabled={!server.enabled}
                        title={server.enabled
                          ? "Enable for kiosk voice assistant"
                          : "Server must be running"}
                      >
                        <input
                          type="checkbox"
                          checked={server.client_enabled?.kiosk ?? false}
                          disabled={!server.enabled ||
                            $mcpServers.pending[server.id] ||
                            $mcpServers.saving}
                          on:change={(event) =>
                            toggleKiosk(
                              server.id,
                              (event.target as HTMLInputElement).checked,
                            )}
                        />
                        <span>Kiosk</span>
                      </label>
                      <label
                        class="toggle cli-toggle"
                        class:toggle-disabled={!server.enabled}
                        title={server.enabled
                          ? "Enable for CLI client"
                          : "Server must be running"}
                      >
                        <input
                          type="checkbox"
                          checked={server.client_enabled?.cli ?? false}
                          disabled={!server.enabled ||
                            $mcpServers.pending[server.id] ||
                            $mcpServers.saving}
                          on:change={(event) =>
                            toggleCli(
                              server.id,
                              (event.target as HTMLInputElement).checked,
                            )}
                        />
                        <span>CLI</span>
                      </label>
                    </div>
                  </div>

                  <div class="server-row-body">
                    {#if server.id === "shell-control"}
                      <div class="shell-server-settings">
                        <div class="shell-setting">
                          <div class="shell-setting__info">
                            <span class="field-label">This machine</span>
                            <span class="field-hint">
                              Select which computer you're on. Sets host profile
                              and storage path.
                            </span>
                          </div>
                          <select
                            class="select-control"
                            value={server.env?.HOST_PROFILE_ID ?? ""}
                            disabled={$mcpServers.pending[server.id] ||
                              $mcpServers.saving}
                            on:change={(event) =>
                              handleHostProfileChange(
                                server.id,
                                (event.target as HTMLSelectElement).value,
                              )}
                          >
                            <option value="">-- Select machine --</option>
                            {#each HOST_PROFILES as profile}
                              <option value={profile.id}>
                                {profile.label}
                              </option>
                            {/each}
                          </select>
                        </div>
                      </div>
                    {/if}

                    <button
                      type="button"
                      class="tools-toggle"
                      class:open={expandedServers.has(server.id)}
                      on:click={() => toggleServerTools(server.id)}
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
                              <li class="tool-row" data-disabled={!tool.enabled}>
                                <div class="tool-info">
                                  <span class="tool-name">{tool.name}</span>
                                  <span class="tool-qualified"
                                    >{tool.qualified_name}</span
                                  >
                                </div>
                                <label class="toggle">
                                  <input
                                    type="checkbox"
                                    checked={tool.enabled}
                                    disabled={!server.enabled ||
                                      $mcpServers.pending[server.id] ||
                                      $mcpServers.saving}
                                    on:change={(event) =>
                                      toggleTool(
                                        server.id,
                                        tool.name,
                                        (event.target as HTMLInputElement)
                                          .checked,
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
          {#if $mcpServers.dirty}
            <p class="status warning">
              Pending changes save when you close this modal.
            </p>
          {/if}
        {/if}
      </div>
    </article>

    <footer slot="footer" class="model-settings-footer system-settings-footer">
      {#if $mcpServers.saveError}
        <p class="status error">Resolve the errors above before closing.</p>
      {:else if $mcpServers.saving}
        <p class="status">Saving changes...</p>
      {:else if $mcpServers.dirty}
        <p class="status">Pending changes; closing this modal will save.</p>
      {:else}
        <p class="status">Changes save when you close this modal.</p>
      {/if}
    </footer>
  </ModelSettingsDialog>
{/if}
