<script lang="ts">
  import { afterUpdate, createEventDispatcher } from 'svelte';
  import { get } from 'svelte/store';
  import { createSystemPromptStore } from '../../stores/systemPrompt';
  import { createMcpServersStore } from '../../stores/mcpServers';
  import './model-settings/model-settings-styles.css';
  import './system-settings.css';

  export let open = false;

  const dispatch = createEventDispatcher<{ close: void }>();
  const systemPrompt = createSystemPromptStore();
  const mcpServers = createMcpServersStore();

  let dialogEl: HTMLElement | null = null;
  let hasInitialized = false;
  let wasOpen = false;
  let closing = false;

  $: {
    if (open && !hasInitialized) {
      hasInitialized = true;
      void initialize();
    } else if (!open && hasInitialized) {
      hasInitialized = false;
      systemPrompt.reset();
    }
  }

  afterUpdate(() => {
    if (open && !wasOpen) {
      if (dialogEl) {
        dialogEl.focus();
      }
      wasOpen = true;
    } else if (!open && wasOpen) {
      wasOpen = false;
    }
  });

  async function initialize(): Promise<void> {
    await Promise.all([systemPrompt.load(), mcpServers.load()]);
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

    if (promptSaved && serversSaved && !promptState.saveError && !serversState.saveError) {
      dispatch('close');
    }

    closing = false;
  }

  function handleBackdrop(event: MouseEvent): void {
    if (event.target === event.currentTarget) {
      void closeModal();
    }
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (!open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      void closeModal();
    }
  }

  function handlePromptInput(event: Event): void {
    const target = event.target as HTMLTextAreaElement | null;
    systemPrompt.updateValue(target?.value ?? '');
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

  function formatUpdatedAt(timestamp: string | null): string | null {
    if (!timestamp) return null;
    try {
      const date = new Date(timestamp);
      if (Number.isNaN(date.getTime())) {
        return timestamp;
      }
      return new Intl.DateTimeFormat(undefined, {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        year: 'numeric',
        month: 'short',
        day: '2-digit',
      }).format(date);
    } catch (error) {
      console.warn('Failed to format timestamp', error);
      return timestamp;
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if open}
  <div class="model-settings-layer system-settings-layer">
    <button
      type="button"
      class="model-settings-backdrop"
      aria-label="Close system settings"
      on:click={handleBackdrop}
    ></button>
    <div
      class="model-settings-modal system-settings-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="system-settings-title"
      tabindex="-1"
      bind:this={dialogEl}
    >
      <header class="model-settings-header system-settings-header">
        <div class="model-settings-heading">
          <h2 id="system-settings-title">System settings</h2>
          <p class="model-settings-subtitle">Configure orchestration defaults and MCP servers.</p>
        </div>
        <div class="model-settings-actions">
          <button
            type="button"
            class="modal-close"
            on:click={() => void closeModal()}
            aria-label="Close"
            disabled={$systemPrompt.saving || $mcpServers.saving}
          >
            Close
          </button>
        </div>
      </header>

      <section class="model-settings-body system-settings-body">
        <article class="system-card">
          <header class="system-card-header">
            <div>
              <h3>System prompt</h3>
              <p class="system-card-caption">Applied to new chat sessions when no custom prompt is present.</p>
            </div>
            <div class="system-card-actions">
              <button
                type="button"
                class="ghost"
                on:click={() => systemPrompt.reset()}
                disabled={!$systemPrompt.dirty || $systemPrompt.saving || $mcpServers.saving}
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
              <h3>MCP servers</h3>
              {#if $mcpServers.updatedAt}
                <p class="system-card-caption">
                  Last updated {formatUpdatedAt($mcpServers.updatedAt) ?? ''}
                </p>
              {:else}
                <p class="system-card-caption">Toggle integrations available to the assistant.</p>
              {/if}
            </div>
            <div class="system-card-actions">
              <button
                type="button"
                class="ghost"
                on:click={refreshServers}
                disabled={$mcpServers.refreshing || $mcpServers.saving || $mcpServers.dirty}
              >
                {$mcpServers.refreshing ? 'Refreshing…' : 'Refresh'}
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
                      data-pending={$mcpServers.pending[server.id] ? 'true' : 'false'}
                      data-dirty={$mcpServers.pendingChanges[server.id] ? 'true' : 'false'}
                    >
                      <div class="server-row-header">
                        <div class="server-heading">
                          <h4>{server.id}</h4>
                          <div class="server-meta">
                            <span class:connected={server.connected} class:offline={!server.connected}>
                              {server.connected ? 'Connected' : 'Offline'}
                            </span>
                            {#if server.module}
                              <span aria-hidden="true">•</span>
                              <span title={server.module}>Module: {server.module}</span>
                            {:else if server.command?.length}
                              <span aria-hidden="true">•</span>
                              <span title={server.command.join(' ')}>Command: {server.command.join(' ')}</span>
                            {/if}
                          </div>
                        </div>
                        <label class="toggle">
                          <input
                            type="checkbox"
                            checked={server.enabled}
                            disabled={$mcpServers.pending[server.id] || $mcpServers.saving}
                            on:change={(event) => toggleServer(server.id, (event.target as HTMLInputElement).checked)}
                          />
                          <span>{server.enabled ? 'Enabled' : 'Disabled'}</span>
                        </label>
                      </div>

                      <div class="server-row-body">
                        <p class="status">
                          {server.tool_count} tool{server.tool_count === 1 ? '' : 's'} available
                        </p>

                        {#if server.tools.length}
                          <ul class="tool-list">
                            {#each server.tools as tool}
                              <li class="tool-row" data-disabled={!tool.enabled}>
                                <div class="tool-info">
                                  <span class="tool-name">{tool.name}</span>
                                  <span class="tool-qualified">{tool.qualified_name}</span>
                                </div>
                                <label class="toggle">
                                  <input
                                    type="checkbox"
                                    checked={tool.enabled}
                                    disabled={
                                      !server.enabled ||
                                      $mcpServers.pending[server.id] ||
                                      $mcpServers.saving
                                    }
                                    on:change={(event) => toggleTool(server.id, tool.name, (event.target as HTMLInputElement).checked)}
                                  />
                                  <span>{tool.enabled ? 'Enabled' : 'Disabled'}</span>
                                </label>
                              </li>
                            {/each}
                          </ul>
                        {:else}
                          <p class="status">Tool list unavailable.</p>
                        {/if}

                        {#if server.disabled_tools.length}
                          <p class="status warning">
                            Disabled tool ids: {server.disabled_tools.join(', ')}
                          </p>
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
                <p class="status warning">Pending changes save when you close this modal.</p>
              {/if}
            {/if}
          </div>
        </article>
      </section>

      <footer class="model-settings-footer system-settings-footer">
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
    </div>
  </div>
{/if}
