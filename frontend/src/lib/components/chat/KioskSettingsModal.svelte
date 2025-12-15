<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte";
  import { get } from "svelte/store";
  import {
    fetchKioskMcpServers,
    fetchKioskModelSettings,
    fetchKioskSystemPrompt,
    fetchKioskSttSettings,
    fetchModels,
    patchKioskMcpServer,
    refreshKioskMcpServers,
    replaceKioskMcpServers,
    updateKioskModelSettings,
    updateKioskSystemPrompt,
    updateKioskSttSettings,
  } from "../../api/client";
  import type { ModelRecord } from "../../api/types";
  import type { KioskSttSettingsResponse, KioskSttSettingsPayload } from "../../api/client";
  import { createMcpServersStore } from "../../stores/mcpServers";
  import { createModelSettingsStore } from "../../stores/modelSettings";
  import { createSystemPromptStore } from "../../stores/systemPrompt";
  import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";
  import "./system-settings.css";

  export let open = false;

  const dispatch = createEventDispatcher<{ close: void }>();

  // Instantiate stores with Kiosk API clients
  const systemPrompt = createSystemPromptStore(
    fetchKioskSystemPrompt,
    updateKioskSystemPrompt
  );

  const mcpServers = createMcpServersStore({
    fetch: fetchKioskMcpServers,
    patch: patchKioskMcpServer,
    refresh: refreshKioskMcpServers,
  });

  const modelSettings = createModelSettingsStore({
    fetch: fetchKioskModelSettings,
    update: updateKioskModelSettings,
  });

  let hasInitialized = false;
  let closing = false;
  let expandedServers: Set<string> = new Set();
  let availableModels: ModelRecord[] = [];
  let modelsLoading = false;

  // STT Settings state
  let sttLoading = false;
  let sttSaving = false;
  let sttError: string | null = null;
  let sttDirty = false;
  let eotTimeoutMs = 5000;
  let eotThreshold = 0.7;

  $: {
    if (open && !hasInitialized) {
      hasInitialized = true;
      void initialize();
    } else if (!open && hasInitialized) {
      hasInitialized = false;
      systemPrompt.reset();
      // modelSettings.reset(); // Model settings store doesn't have a simple reset that clears data
    }
  }

  async function initialize(): Promise<void> {
    modelsLoading = true;
    try {
        const modelsParams = await fetchModels();
        availableModels = modelsParams.data;
    } catch (e) {
        console.error("Failed to load models", e);
    } finally {
        modelsLoading = false;
    }

    // Load STT settings
    sttLoading = true;
    sttError = null;
    try {
      const sttSettings = await fetchKioskSttSettings();
      eotTimeoutMs = sttSettings.eot_timeout_ms;
      eotThreshold = sttSettings.eot_threshold;
    } catch (e) {
      sttError = e instanceof Error ? e.message : "Failed to load STT settings";
      console.error("Failed to load STT settings", e);
    } finally {
      sttLoading = false;
    }

    await Promise.all([
      systemPrompt.load(),
      mcpServers.load(),
      modelSettings.load(""), // Load active settings
    ]);
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

  async function flushModelSettings(): Promise<boolean> {
      const success = await modelSettings.flushSave();
      return success;
  }

  async function flushSttSettings(): Promise<boolean> {
    if (!sttDirty) {
      return true;
    }
    sttSaving = true;
    sttError = null;
    try {
      await updateKioskSttSettings({
        eot_timeout_ms: eotTimeoutMs,
        eot_threshold: eotThreshold,
      });
      sttDirty = false;
      return true;
    } catch (e) {
      sttError = e instanceof Error ? e.message : "Failed to save STT settings";
      return false;
    } finally {
      sttSaving = false;
    }
  }

  async function closeModal(): Promise<void> {
    if (closing || $systemPrompt.saving || $mcpServers.saving || $modelSettings.saving || sttSaving) {
      return;
    }

    closing = true;

    const promptSaved = await flushSystemPrompt();
    const modelSaved = await flushModelSettings();
    const sttSaved = await flushSttSettings();
    const serversSaved = (promptSaved && modelSaved && sttSaved) ? await mcpServers.flushPending() : false;

    const promptState = get(systemPrompt);
    const mcpState = get(mcpServers);
    const modelState = get(modelSettings);

    if (
      promptSaved &&
      modelSaved &&
      sttSaved &&
      serversSaved &&
      !promptState.saveError &&
      !mcpState.saveError &&
      !modelState.saveError &&
      !sttError
    ) {
      dispatch("close");
    }

    closing = false;
  }

  function handlePromptInput(event: Event): void {
    const target = event.target as HTMLTextAreaElement | null;
    systemPrompt.updateValue(target?.value ?? "");
  }

  function handleModelChange(event: Event): void {
      const target = event.target as HTMLSelectElement;
      modelSettings.setModel(target.value);
  }

  function handleEotTimeoutChange(event: Event): void {
    const target = event.target as HTMLInputElement;
    eotTimeoutMs = parseInt(target.value, 10);
    sttDirty = true;
  }

  function handleEotThresholdChange(event: Event): void {
    const target = event.target as HTMLInputElement;
    eotThreshold = parseFloat(target.value);
    sttDirty = true;
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
    labelledBy="kiosk-settings-title"
    modalClass="system-settings-modal"
    bodyClass="system-settings-body"
    layerClass="system-settings-layer"
    closeLabel="Close kiosk settings"
    closeDisabled={$systemPrompt.saving ||
      $mcpServers.saving ||
      $modelSettings.saving ||
      sttSaving}
    on:close={() => void closeModal()}
  >
    <svelte:fragment slot="heading">
      <h2 id="kiosk-settings-title">Kiosk Settings</h2>
      <p class="model-settings-subtitle">
        Configure the isolated voice assistant for the Kiosk.
      </p>
    </svelte:fragment>

    <!-- Model Selection -->
    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Model</h3>
          <p class="system-card-caption">
            Select the LLM used for voice responses.
          </p>
        </div>
      </header>

      <div class="system-card-body">
          {#if $modelSettings.loading || modelsLoading}
            <p class="status">Loading model settings...</p>
          {:else if $modelSettings.error}
             <p class="status error">{$modelSettings.error}</p>
          {:else}
            <select
                class="select-control"
                value={$modelSettings.data?.model ?? ""}
                on:change={handleModelChange}
                disabled={$modelSettings.saving}
            >
                <option value="" disabled>Select a model</option>
                {#each availableModels as model}
                    <option value={model.id}>{model.name || model.id}</option>
                {/each}
            </select>
            {#if $modelSettings.saveError}
                <p class="status error">{$modelSettings.saveError}</p>
            {:else if $modelSettings.dirty}
                <p class="status">Pending changes; closing this modal will save.</p>
            {/if}
          {/if}
      </div>
    </article>

    <!-- STT Settings -->
    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Speech Detection</h3>
          <p class="system-card-caption">
            Configure end-of-turn detection for faster responses.
          </p>
        </div>
      </header>

      <div class="system-card-body">
        {#if sttLoading}
          <p class="status">Loading speech settings...</p>
        {:else if sttError && !sttDirty}
          <p class="status error">{sttError}</p>
        {:else}
          <div class="stt-settings-grid">
            <div class="stt-setting">
              <label for="eot-timeout">
                Silence Timeout: <strong>{(eotTimeoutMs / 1000).toFixed(1)}s</strong>
              </label>
              <p class="stt-setting-caption">
                Max silence before submitting (0.5s - 10s)
              </p>
              <input
                id="eot-timeout"
                type="range"
                min="500"
                max="10000"
                step="500"
                value={eotTimeoutMs}
                on:input={handleEotTimeoutChange}
                disabled={sttSaving}
              />
            </div>
            <div class="stt-setting">
              <label for="eot-threshold">
                Detection Sensitivity: <strong>{(eotThreshold * 100).toFixed(0)}%</strong>
              </label>
              <p class="stt-setting-caption">
                Higher = more accurate but slower; Lower = faster but may interrupt
              </p>
              <input
                id="eot-threshold"
                type="range"
                min="0.5"
                max="0.9"
                step="0.05"
                value={eotThreshold}
                on:input={handleEotThresholdChange}
                disabled={sttSaving}
              />
            </div>
          </div>
          {#if sttError}
            <p class="status error">{sttError}</p>
          {:else if sttDirty}
            <p class="status">Pending changes; closing this modal will save.</p>
          {/if}
        {/if}
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>System prompt</h3>
          <p class="system-card-caption">
            Applied to the Kiosk's conversation context.
          </p>
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="btn btn-ghost btn-small"
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
            class="system-prompt textarea-control"
            rows="6"
            bind:value={$systemPrompt.value}
            on:input={handlePromptInput}
            placeholder="You are a helpful voice assistant..."
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
              Last updated {formatUpdatedAt($mcpServers.updatedAt) ?? ""}
            </p>
          {:else}
            <p class="system-card-caption">
              Toggle specific tools available to the Kiosk.
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
      {#if $mcpServers.saveError || $systemPrompt.saveError || $modelSettings.saveError || sttError}
        <p class="status error">Resolve the errors above before closing.</p>
      {:else if $systemPrompt.saving || $mcpServers.saving || $modelSettings.saving || sttSaving}
        <p class="status">Saving changes…</p>
      {:else if $systemPrompt.dirty || $mcpServers.dirty || $modelSettings.dirty || sttDirty}
        <p class="status">Pending changes; closing this modal will save.</p>
      {:else}
        <p class="status">Changes save when you close this modal.</p>
      {/if}
    </footer>
  </ModelSettingsDialog>
{/if}
