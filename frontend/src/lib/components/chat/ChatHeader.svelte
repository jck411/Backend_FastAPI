<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { WebSearchSettings } from '../../stores/chat';

  interface SelectableModel {
    id: string;
    name?: string | null;
  }

  const dispatch = createEventDispatcher<{
    openExplorer: void;
    clear: void;
    modelChange: { id: string };
    webSearchChange: { settings: Partial<WebSearchSettings> };
    openModelSettings: void;
  }>();

  export let selectableModels: SelectableModel[] = [];
  export let selectedModel = '';
  export let modelsLoading = false;
  export let modelsError: string | null = null;
  export let hasMessages = false;
  export let webSearch: WebSearchSettings = {
    enabled: false,
    engine: null,
    maxResults: null,
    searchPrompt: '',
    contextSize: null,
  };

  let webSearchMenuOpen = false;
  let webSearchCloseTimeout: ReturnType<typeof setTimeout> | null = null;

  function handleWebSearchChange(settings: Partial<WebSearchSettings>): void {
    dispatch('webSearchChange', { settings });
  }

  function cancelWebSearchMenuClose(): void {
    if (webSearchCloseTimeout) {
      clearTimeout(webSearchCloseTimeout);
      webSearchCloseTimeout = null;
    }
  }

  function openWebSearchMenu(): void {
    cancelWebSearchMenuClose();
    webSearchMenuOpen = true;
  }

  function scheduleWebSearchMenuClose(): void {
    cancelWebSearchMenuClose();
    webSearchCloseTimeout = setTimeout(() => {
      webSearchMenuOpen = false;
      webSearchCloseTimeout = null;
    }, 250);
  }

  function closeWebSearchMenu(): void {
    cancelWebSearchMenuClose();
    webSearchMenuOpen = false;
  }

  function openWebSearchMenuIfEnabled(): void {
    if (!webSearch.enabled) return;
    openWebSearchMenu();
  }

  function handleWebSearchButtonClick(): void {
    if (webSearch.enabled) {
      handleWebSearchChange({ enabled: false });
      closeWebSearchMenu();
    } else {
      handleWebSearchChange({ enabled: true });
      openWebSearchMenu();
    }
  }

  function handleWebSearchEngine(event: Event): void {
    const target = event.currentTarget as HTMLSelectElement | null;
    if (!target) return;
    const value = target.value;
    if (value === 'native' || value === 'exa') {
      handleWebSearchChange({ engine: value });
    } else {
      handleWebSearchChange({ engine: null });
    }
  }

  function handleWebSearchContext(event: Event): void {
    const target = event.currentTarget as HTMLSelectElement | null;
    if (!target) return;
    const value = target.value;
    if (value === 'low' || value === 'medium' || value === 'high') {
      handleWebSearchChange({ contextSize: value });
    } else {
      handleWebSearchChange({ contextSize: null });
    }
  }

  function handleWebSearchMaxResults(event: Event): void {
    const target = event.currentTarget as HTMLInputElement | null;
    if (!target) return;
    const raw = target.value.trim();
    if (!raw) {
      handleWebSearchChange({ maxResults: null });
      return;
    }
    handleWebSearchChange({ maxResults: Number(raw) });
  }

  function handleWebSearchPrompt(event: Event): void {
    const target = event.currentTarget as HTMLTextAreaElement | null;
    if (!target) return;
    handleWebSearchChange({ searchPrompt: target.value });
  }

  function handleWebSearchFocusOut(event: FocusEvent): void {
    const container = event.currentTarget as HTMLElement | null;
    const nextTarget = event.relatedTarget as Node | null;
    if (!container || !nextTarget || !container.contains(nextTarget)) {
      closeWebSearchMenu();
    }
  }

  function handleWebSearchKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeWebSearchMenu();
    }
  }

  function handleExplorerClick(): void {
    dispatch('openExplorer');
  }

  function handleClear(): void {
    dispatch('clear');
  }

  function handleModelChange(event: Event): void {
    const target = event.target as HTMLSelectElement | null;
    if (!target) return;
    dispatch('modelChange', { id: target.value });
  }

  function handleOpenModelSettings(): void {
    dispatch('openModelSettings');
  }

  let wasWebSearchEnabled = webSearch.enabled;

  $: {
    if (!webSearch.enabled && wasWebSearchEnabled) {
      closeWebSearchMenu();
    }
    wasWebSearchEnabled = webSearch.enabled;
  }
</script>

<header class="topbar">
  <div class="topbar-content">
    <div class="controls">
      <button class="ghost" type="button" on:click={handleExplorerClick}>Explorer</button>

      <select
        on:change={handleModelChange}
        bind:value={selectedModel}
        disabled={modelsLoading}
      >
        {#if modelsLoading}
          <option>Loading…</option>
        {:else if modelsError}
          <option disabled>{`Failed to load models — ${modelsError}`}</option>
        {:else if !selectableModels.length}
          <option disabled>No models</option>
        {:else}
          {#each selectableModels as model (model.id)}
            <option value={model.id}>{model.name ?? model.id}</option>
          {/each}
        {/if}
      </select>

      <button
        class="ghost"
        type="button"
        on:click={handleOpenModelSettings}
        disabled={modelsLoading || !selectedModel}
      >
        Model settings
      </button>

      <div
        class="web-search"
        data-enabled={webSearch.enabled}
        data-open={webSearchMenuOpen}
        role="group"
        aria-label="Web search settings"
        on:mouseenter={openWebSearchMenuIfEnabled}
        on:mouseleave={scheduleWebSearchMenuClose}
        on:focusin={openWebSearchMenuIfEnabled}
        on:focusout={handleWebSearchFocusOut}
      >
        <button
          type="button"
          class="web-search-summary"
          aria-haspopup="true"
          aria-expanded={webSearch.enabled && webSearchMenuOpen}
          on:keydown={handleWebSearchKeydown}
          on:click={handleWebSearchButtonClick}
        >
          <span>Web search</span>
          <span class="status" data-enabled={webSearch.enabled}>
            {webSearch.enabled ? 'On' : 'Off'}
          </span>
        </button>
        {#if webSearchMenuOpen && webSearch.enabled}
          <div class="web-search-menu">
            <div class="web-search-fields" aria-disabled={!webSearch.enabled}>
              <label>
                <span>Engine</span>
                <select
                  value={webSearch.engine ?? ''}
                  disabled={!webSearch.enabled}
                  on:change={handleWebSearchEngine}
                >
                  <option value="">Auto</option>
                  <option value="native">Native</option>
                  <option value="exa">Exa</option>
                </select>
              </label>
              <label>
                <span>Context</span>
                <select
                  value={webSearch.contextSize ?? ''}
                  disabled={!webSearch.enabled}
                  on:change={handleWebSearchContext}
                >
                  <option value="">Default</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </label>
              <label>
                <span>Max results</span>
                <input
                  type="number"
                  min="1"
                  max="25"
                  step="1"
                  value={webSearch.maxResults ?? ''}
                  disabled={!webSearch.enabled}
                  on:input={handleWebSearchMaxResults}
                />
              </label>
              <label class="prompt">
                <span>Search prompt</span>
                <textarea
                  rows="2"
                  value={webSearch.searchPrompt}
                  disabled={!webSearch.enabled}
                  placeholder="Use default prompt"
                  on:input={handleWebSearchPrompt}
                ></textarea>
              </label>
            </div>
          </div>
        {/if}
      </div>

      <button class="ghost" type="button" on:click={handleClear} disabled={!hasMessages}>
        Clear
      </button>
    </div>
  </div>
</header>

<style>
  .topbar {
    height: var(--header-h);
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    background: transparent;
    position: relative;
    z-index: 20;
    padding: 0 2rem;
  }
  .topbar-content {
    width: 100%;
    max-width: 800px;
    display: flex;
    align-items: center;
    justify-content: flex-start;
  }
  .controls {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }
  .controls .web-search {
    position: relative;
    display: inline-flex;
    align-items: center;
  }
  .controls select {
    appearance: none;
    padding: 0.45rem 2rem 0.45rem 0.75rem;
    border-radius: 0.5rem;
    background: rgba(9, 14, 26, 0.9);
    color: #f2f4f8;
    border: 1px solid #25314d;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      background 0.2s ease,
      color 0.2s ease;
    background-image: url('data:image/svg+xml,%3Csvg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"%3E%3Cpath d="M7 8l3 3 3-3" stroke="%23d4daee" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/%3E%3C/svg%3E');
    background-repeat: no-repeat;
    background-position: right 0.65rem center;
    background-size: 1rem;
    min-width: 160px;
  }
  .controls select:hover {
    border-color: #38bdf8;
    background-color: rgba(12, 19, 34, 0.95);
    color: #f8fafc;
  }
  .controls select:focus {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
    border-color: #38bdf8;
    box-shadow: none;
  }
  .controls select:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    background: rgba(9, 14, 26, 0.6);
  }
  .controls select option {
    background: #0a101a;
    color: #f2f4f8;
  }
  .controls .ghost {
    background: none;
    border: 1px solid #25314d;
    border-radius: 999px;
    color: #f2f4f8;
    padding: 0.55rem 1.1rem;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      color 0.2s ease,
      background 0.2s ease;
  }
  .controls .ghost:hover:not(:disabled) {
    border-color: #38bdf8;
    color: #38bdf8;
  }
  .controls .ghost:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .web-search-summary {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    border: 1px solid #25314d;
    border-radius: 999px;
    padding: 0.55rem 1.1rem;
    cursor: pointer;
    background: none;
    color: #f2f4f8;
    font: inherit;
    transition:
      border-color 0.2s ease,
      color 0.2s ease,
      background 0.2s ease;
  }
  .web-search-summary:hover,
  .web-search-summary:focus-visible {
    border-color: #38bdf8;
    color: #38bdf8;
    outline: none;
  }
  .web-search[data-open='true'] .web-search-summary {
    border-color: #38bdf8;
    color: #38bdf8;
  }
  .web-search .status {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 0.1rem 0.4rem;
    border-radius: 999px;
    border: 1px solid rgba(62, 90, 140, 0.6);
    color: #9fb3d8;
  }
  .web-search .status[data-enabled='true'] {
    border-color: rgba(56, 189, 248, 0.4);
    color: #7dd3fc;
  }
  .web-search-menu {
    display: none;
    position: absolute;
    top: calc(100% + 0.25rem);
    right: 0;
    width: min(320px, 80vw);
    background: rgba(8, 14, 24, 0.96);
    border: 1px solid rgba(67, 91, 136, 0.6);
    border-radius: 0.75rem;
    padding: 1rem;
    box-shadow: 0 12px 24px rgba(3, 8, 20, 0.6);
    z-index: 50;
    flex-direction: column;
    gap: 0.75rem;
  }
  .web-search-menu::before {
    content: '';
    position: absolute;
    top: -0.25rem;
    left: 0;
    right: 0;
    height: 0.25rem;
  }
  .web-search[data-open='true'] .web-search-menu {
    display: flex;
  }
  .web-search-fields {
    display: grid;
    gap: 0.75rem;
  }
  .web-search-fields label {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    font-size: 0.75rem;
    color: #9fb3d8;
  }
  .web-search-fields select,
  .web-search-fields input,
  .web-search-fields textarea {
    background: rgba(12, 19, 34, 0.9);
    border: 1px solid rgba(57, 82, 124, 0.55);
    border-radius: 0.5rem;
    color: #f2f4f8;
    padding: 0.4rem 0.6rem;
    font: inherit;
  }
  .web-search-fields textarea {
    resize: vertical;
    min-height: 3.5rem;
  }
  .web-search-fields select:disabled,
  .web-search-fields input:disabled,
  .web-search-fields textarea:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
