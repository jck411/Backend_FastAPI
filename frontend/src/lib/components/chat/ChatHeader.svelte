<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  interface SelectableModel {
    id: string;
    name?: string | null;
  }

  const dispatch = createEventDispatcher<{
    openExplorer: void;
    clear: void;
    modelChange: { id: string };
  }>();

  export let selectableModels: SelectableModel[] = [];
  export let selectedModel = '';
  export let modelsLoading = false;
  export let modelsError: string | null = null;
  export let hasMessages = false;

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
</style>
