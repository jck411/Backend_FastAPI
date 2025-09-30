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
  let editingPrompt = false;

  $: {
    if (open && !hasInitialized) {
      hasInitialized = true;
      void initialize();
    } else if (!open && hasInitialized) {
      hasInitialized = false;
      editingPrompt = false;
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

  function closeModal(): void {
    editingPrompt = false;
    systemPrompt.reset();
    dispatch('close');
  }

  function handleBackdrop(event: MouseEvent): void {
    if (event.target === event.currentTarget) {
      closeModal();
    }
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (!open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      closeModal();
    }
  }

  function startEditing(): void {
    editingPrompt = true;
  }

  function cancelEditing(): void {
    systemPrompt.reset();
    editingPrompt = false;
  }

  function handlePromptInput(event: Event): void {
    if (!editingPrompt) {
      return;
    }
    const target = event.target as HTMLTextAreaElement | null;
    systemPrompt.updateValue(target?.value ?? '');
  }

  async function savePrompt(): Promise<void> {
    await systemPrompt.save();
    const state = get(systemPrompt);
    if (!state.saveError) {
      editingPrompt = false;
    }
  }

  function toggleServer(serverId: string, enabled: boolean): void {
    void mcpServers.setServerEnabled(serverId, enabled);
  }

  function toggleTool(serverId: string, tool: string, enabled: boolean): void {
    void mcpServers.setToolEnabled(serverId, tool, enabled);
  }

  function refreshServers(): void {
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
          <button type="button" class="modal-close" on:click={closeModal} aria-label="Close">
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
              {#if editingPrompt}
                <button
                  type="button"
                  class="ghost"
                  on:click={cancelEditing}
                  disabled={$systemPrompt.saving}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  class="primary"
                  on:click={savePrompt}
                  disabled={!$systemPrompt.dirty || $systemPrompt.saving}
                >
                  {$systemPrompt.saving ? 'Saving…' : 'Save'}
                </button>
              {:else}
                <button
                  type="button"
                  class="ghost"
                  on:click={startEditing}
                  disabled={$systemPrompt.loading || Boolean($systemPrompt.error)}
                >
                  Edit
                </button>
              {/if}
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
                readonly={!editingPrompt}
              ></textarea>
              {#if $systemPrompt.saveError}
                <p class="status error">{$systemPrompt.saveError}</p>
              {:else if editingPrompt}
                {#if $systemPrompt.dirty}
                  <p class="status">Unsaved changes</p>
                {:else}
                  <p class="status muted">Edit the prompt, then save to apply.</p>
                {/if}
              {:else}
                <p class="status muted">Select edit to modify the current prompt.</p>
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
                disabled={$mcpServers.refreshing}
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
                            disabled={$mcpServers.pending[server.id]}
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
                                    disabled={!server.enabled || $mcpServers.pending[server.id]}
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
            {/if}
          </div>
        </article>
      </section>

      <footer class="model-settings-footer system-settings-footer">
        <p class="status">
          Changes apply immediately to new tool calls once the server acknowledges the update.
        </p>
      </footer>
    </div>
  </div>
{/if}
