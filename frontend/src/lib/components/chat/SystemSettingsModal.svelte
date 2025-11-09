<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import { get } from "svelte/store";
  import { createMcpServersStore } from "../../stores/mcpServers";
  import { createGoogleAuthStore } from "../../stores/googleAuth";
  import { createSystemPromptStore } from "../../stores/systemPrompt";
  import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";
  import "./system-settings.css";

  export let open = false;

  const dispatch = createEventDispatcher<{ close: void }>();
  const systemPrompt = createSystemPromptStore();
  const mcpServers = createMcpServersStore();
  const googleAuth = createGoogleAuthStore();

  let hasInitialized = false;
  let closing = false;
  let expandedServers: Set<string> = new Set();

  $: {
    if (open && !hasInitialized) {
      hasInitialized = true;
      void initialize();
    } else if (!open && hasInitialized) {
      hasInitialized = false;
      systemPrompt.reset();
      googleAuth.reset();
    }
  }

  async function initialize(): Promise<void> {
    await Promise.all([systemPrompt.load(), mcpServers.load(), googleAuth.load()]);
  }

  async function flushSystemPrompt(): Promise<boolean> {
    const state = get(systemPrompt);
    if (!state.dirty) {
      return true;
    }
    await systemPrompt.save();
    const latest = get(systemPrompt);
    return !latest.saveError;
  }

  async function closeModal(): Promise<void> {
    if (closing || $systemPrompt.saving || $mcpServers.saving) {
      return;
    }

    closing = true;

    const promptSaved = await flushSystemPrompt();
    const serversSaved = promptSaved ? await mcpServers.flushPending() : false;

    const promptState = get(systemPrompt);
    const serversState = get(mcpServers);

    if (
      promptSaved &&
      serversSaved &&
      !promptState.saveError &&
      !serversState.saveError
    ) {
      dispatch("close");
    }

    closing = false;
  }

  function handlePromptInput(event: Event): void {
    const target = event.target as HTMLTextAreaElement | null;
    systemPrompt.updateValue(target?.value ?? "");
  }

  function toggleServer(serverId: string, enabled: boolean): void {
    if ($mcpServers.saving) {
      return;
    }
    mcpServers.setServerEnabled(serverId, enabled);
  }

  function toggleTool(serverId: string, tool: string, enabled: boolean): void {
    if ($mcpServers.saving) {
      return;
    }
    mcpServers.setToolEnabled(serverId, tool, enabled);
  }

  function refreshServers(): void {
    const snapshot = get(mcpServers);
    if (snapshot.dirty || snapshot.saving) {
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
    labelledBy="system-settings-title"
    modalClass="system-settings-modal"
    bodyClass="system-settings-body"
    layerClass="system-settings-layer"
    closeLabel="Close system settings"
    closeDisabled={$systemPrompt.saving || $mcpServers.saving || $googleAuth.authorizing}
    on:close={() => void closeModal()}
  >
    <svelte:fragment slot="heading">
      <h2 id="system-settings-title">System settings</h2>
      <p class="model-settings-subtitle">
        Configure orchestration defaults and MCP servers.
      </p>
    </svelte:fragment>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>System prompt</h3>
          <p class="system-card-caption">
            Applied to new chat sessions when no custom prompt is present.
          </p>
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="ghost"
            on:click={() => systemPrompt.reset()}
            disabled={!$systemPrompt.dirty ||
              $systemPrompt.saving ||
              $mcpServers.saving}
          >
            Reset
          </button>
        </div>
      </header>

      <div class="system-card-body">
        {#if $systemPrompt.loading}
          <p class="status">Loading system prompt…</p>
        {:else if $systemPrompt.error}
          <p class="status error">{$systemPrompt.error}</p>
        {:else}
          <textarea
            class="system-prompt"
            rows="6"
            bind:value={$systemPrompt.value}
            on:input={handlePromptInput}
            placeholder="Provide guidance for the assistant to follow at the start of new conversations."
            disabled={$systemPrompt.saving}
          ></textarea>
          {#if $systemPrompt.saveError}
            <p class="status error">{$systemPrompt.saveError}</p>
          {:else if $systemPrompt.dirty}
            <p class="status">Pending changes; closing this modal will save.</p>
          {:else}
            <p class="status muted">Changes save when you close this modal.</p>
          {/if}
        {/if}
      </div>
    </article>

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
            class="primary"
            on:click={() => void startGoogleAuthorization()}
            disabled={$googleAuth.loading || $googleAuth.authorizing}
          >
            {$googleAuth.authorizing
              ? "Authorizing…"
              : $googleAuth.authorized
              ? "Reconnect Google Services"
              : "Connect Google Services"}
          </button>
        </div>
      </header>

      <div class="system-card-body google-auth-body">
        {#if $googleAuth.loading}
          <p class="status">Checking Google authorization…</p>
        {:else if $googleAuth.error}
          <p class="status error">{$googleAuth.error}</p>
          <div class="google-auth-actions">
            <button
              type="button"
              class="ghost"
              on:click={refreshGoogleAuth}
              disabled={$googleAuth.loading || $googleAuth.authorizing}
            >
              Try again
            </button>
          </div>
        {:else if $googleAuth.authorized}
          <p class="status success">
            Connected as <span class="google-auth-email">{$googleAuth.userEmail}</span>.
          </p>
          {#if $googleAuth.expiresAt}
            <p class="status muted">
              Current token expires {formatUpdatedAt($googleAuth.expiresAt) ?? "soon"}.
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
          Click "Connect Google Services" to authorize these integrations for the assistant.
        </p>
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>MCP servers</h3>
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
            class="ghost"
            on:click={refreshServers}
            disabled={$mcpServers.refreshing ||
              $mcpServers.saving ||
              $mcpServers.dirty}
          >
            {$mcpServers.refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      <div class="system-card-body">
        {#if $mcpServers.loading}
          <p class="status">Loading MCP servers…</p>
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
                          <span aria-hidden="true">•</span>
                          <span title={server.module}
                            >Module: {server.module}</span
                          >
                        {:else if server.command?.length}
                          <span aria-hidden="true">•</span>
                          <span title={server.command.join(" ")}
                            >Command: {server.command.join(" ")}</span
                          >
                        {/if}
                      </div>
                    </div>
                    <label class="toggle">
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
                      <span>{server.enabled ? "Enabled" : "Disabled"}</span>
                    </label>
                  </div>

                  <div class="server-row-body">
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
                              <li
                                class="tool-row"
                                data-disabled={!tool.enabled}
                              >
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
      {#if $mcpServers.saveError || $systemPrompt.saveError}
        <p class="status error">Resolve the errors above before closing.</p>
      {:else if $systemPrompt.saving || $mcpServers.saving}
        <p class="status">Saving changes…</p>
      {:else if $systemPrompt.dirty || $mcpServers.dirty}
        <p class="status">Pending changes; closing this modal will save.</p>
      {:else}
        <p class="status">Changes save when you close this modal.</p>
      {/if}
    </footer>
  </ModelSettingsDialog>
{/if}
