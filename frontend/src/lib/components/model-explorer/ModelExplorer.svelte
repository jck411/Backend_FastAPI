<script lang="ts">
  import { createEventDispatcher, onDestroy } from 'svelte';
  import { modelStore, type ModelSort } from '../../stores/models';
  import type { ModelRecord } from '../../api/types';
  import { formatContext, formatPrice } from '../../models/utils';
  import ModelCard from './ModelCard.svelte';
  import TogglePillGroup from './TogglePillGroup.svelte';
  import SortControls from './SortControls.svelte';

  export let open = false;

  const dispatch = createEventDispatcher<{ select: { id: string }; close: void }>();

  const {
    filtered,
    facets,
    filters,
    setSearch,
    toggleInputModality,
    toggleOutputModality,
    toggleSeries,
    toggleProvider,
    toggleSupportedParameter,
    toggleModeration,
    setMinContext,
    setMaxPromptPrice,
    setSort,
    resetFilters,
    activeFilters,
  } = modelStore;

  const bodyClass = 'modal-open';

  let cleanup = () => {
    if (typeof document !== 'undefined') {
      document.body.classList.remove(bodyClass);
    }
  };

  $: {
    if (typeof document !== 'undefined') {
      if (open) {
        document.body.classList.add(bodyClass);
      } else {
        document.body.classList.remove(bodyClass);
      }
    }
  }

  onDestroy(() => cleanup());

  function close(): void {
    open = false;
    dispatch('close');
  }

  function handleSelect(model: ModelRecord): void {
    dispatch('select', { id: model.id });
    close();
  }

  function handleSort(sort: ModelSort): void {
    setSort(sort);
  }

  $: filteredModels = $filtered as ModelRecord[];
  $: availableFacets = $facets;
  $: currentFilters = $filters;
  $: filtersActive = $activeFilters;
</script>

{#if open}
  <div class="modal-backdrop" role="presentation" on:click={close}></div>
  <div class="model-explorer" role="dialog" aria-modal="true" aria-labelledby="model-explorer-title">
    <header class="explorer-header">
      <div>
        <h2 id="model-explorer-title">Model Explorer</h2>
        <p class="subtitle">Filter and compare OpenRouter models before selecting them.</p>
      </div>
      <button type="button" class="ghost" on:click={close} aria-label="Close model explorer">×</button>
    </header>

    <section class="controls">
      <label class="search">
        <span class="visually-hidden">Search models</span>
        <input
          type="search"
          placeholder="Search by name, provider, description, or tags"
          value={$filters.search}
          on:input={(event) => setSearch((event.target as HTMLInputElement).value)}
        />
      </label>
      <SortControls selected={$filters.sort} onSelect={handleSort} />
    </section>

    <div class="body">
      <section class="filters">
        <TogglePillGroup
          title="Input modalities"
          options={availableFacets.inputModalities}
          selected={$filters.inputModalities}
          on:toggle={(event) => toggleInputModality(event.detail)}
        emptyMessage="No modality data available."
      />
      <TogglePillGroup
        title="Output modalities"
        options={availableFacets.outputModalities}
        selected={$filters.outputModalities}
        on:toggle={(event) => toggleOutputModality(event.detail)}
        emptyMessage="No modality data available."
      />
      <TogglePillGroup
        title="Series"
        options={availableFacets.series}
        selected={$filters.series}
        on:toggle={(event) => toggleSeries(event.detail)}
        emptyMessage="Series information unavailable."
      />
      <TogglePillGroup
        title="Providers"
        options={availableFacets.providers}
        selected={$filters.providers}
        on:toggle={(event) => toggleProvider(event.detail)}
        emptyMessage="No provider data available."
      />
      <TogglePillGroup
        title="Supported parameters"
        options={availableFacets.supportedParameters}
        selected={$filters.supportedParameters}
        on:toggle={(event) => toggleSupportedParameter(event.detail)}
        emptyMessage="No parameter metadata available."
      />
      <TogglePillGroup
        title="Moderation"
        options={availableFacets.moderation}
        selected={$filters.moderation}
        on:toggle={(event) => toggleModeration(event.detail)}
        emptyMessage="No moderation metadata available."
      />
      <div class="filter-card">
        <header>
          <h3>Context length</h3>
        </header>
        <div class="range-inputs">
          <label>
            <span>Minimum tokens</span>
            <input
              type="number"
              min={availableFacets.minContext ?? 0}
              max={availableFacets.maxContext ?? undefined}
              value={currentFilters.minContext ?? ''}
              placeholder={availableFacets.minContext ? availableFacets.minContext.toString() : ''}
              on:input={(event) => {
                const next = (event.target as HTMLInputElement).value;
                setMinContext(next ? Number(next) : null);
              }}
            />
          </label>
        </div>
        {#if availableFacets.maxContext !== null}
          <p class="hint">Up to {formatContext(availableFacets.maxContext)} available.</p>
        {/if}
      </div>
      <div class="filter-card">
        <header>
          <h3>Prompt price (per 1M tokens)</h3>
        </header>
        <div class="range-inputs">
          <label>
            <span>Max price</span>
            <input
              type="number"
              step="0.001"
              min="0"
              value={currentFilters.maxPromptPrice ?? ''}
              placeholder={availableFacets.maxPromptPrice ? availableFacets.maxPromptPrice.toFixed(3) : ''}
              on:input={(event) => {
                const next = (event.target as HTMLInputElement).value;
                setMaxPromptPrice(next ? Number(next) : null);
              }}
            />
          </label>
        </div>
        {#if availableFacets.minPromptPrice !== null && availableFacets.maxPromptPrice !== null}
          <p class="hint">
            Range {formatPrice(availableFacets.minPromptPrice)} – {formatPrice(availableFacets.maxPromptPrice)}
          </p>
        {/if}
      </div>
      </section>

      <section class="results" aria-live="polite">
        <header class="results-header">
          <div>
            <h3>Models</h3>
            <p class="summary">{filteredModels.length} result{filteredModels.length === 1 ? '' : 's'}</p>
          </div>
          <button type="button" class="ghost" on:click={resetFilters}>Reset filters</button>
        </header>

        {#if filteredModels.length === 0}
          <p class="empty">
            {#if filtersActive}
              No models match your current filters.
            {:else}
              No models available.
            {/if}
          </p>
        {:else}
          <ul class="model-grid">
            {#each filteredModels as model (model.id)}
              <li>
                <ModelCard {model} onSelect={handleSelect} />
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(3, 10, 22, 0.65);
    backdrop-filter: blur(2px);
    z-index: 90;
  }

  .model-explorer {
    position: fixed;
    inset: 4vh 10vw;
    background: #0d1323;
    border: 1px solid #1d2741;
    border-radius: 1.25rem;
    padding: 1.75rem;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    z-index: 100;
    max-height: 90vh;
    overflow: hidden;
  }

  .explorer-header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: flex-start;
  }

  .explorer-header h2 {
    margin: 0;
  }

  .subtitle {
    margin: 0.4rem 0 0;
    color: #9aa2ba;
    font-size: 0.95rem;
  }

  .ghost {
    background: none;
    border: 1px solid #25314d;
    border-radius: 999px;
    color: #f2f4f8;
    padding: 0.4rem 1rem;
    cursor: pointer;
  }

  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: center;
  }

  .search {
    flex: 1 1 260px;
  }

  .search input {
    width: 100%;
    padding: 0.6rem 0.9rem;
    border-radius: 0.9rem;
    border: 1px solid #23314e;
    background: #090e1a;
    color: inherit;
  }

  .body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: grid;
    gap: 1.5rem;
  }

  .filters {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1rem;
  }

  .filter-card {
    border: 1px solid #1e2b46;
    border-radius: 1rem;
    padding: 1rem;
    display: grid;
    gap: 0.75rem;
    background: #10182b;
  }

  .range-inputs {
    display: grid;
    gap: 0.75rem;
  }

  .range-inputs label {
    display: grid;
    gap: 0.35rem;
    font-size: 0.9rem;
  }

  .range-inputs input {
    padding: 0.5rem 0.75rem;
    border-radius: 0.75rem;
    border: 1px solid #25314d;
    background: #090e1a;
    color: inherit;
  }

  .hint {
    margin: 0;
    font-size: 0.85rem;
    color: #7f89a3;
  }

  .results {
    display: grid;
    gap: 1rem;
  }

  .results-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .results-header h3 {
    margin: 0;
  }

  .summary {
    margin: 0.2rem 0 0;
    color: #8a92ac;
    font-size: 0.9rem;
  }

  .model-grid {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1rem;
    overflow-y: auto;
  }

  .empty {
    margin: 0;
    color: #7f89a3;
    font-size: 0.9rem;
  }

  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
  }

  :global(body.modal-open) {
    overflow: hidden;
  }

  @media (max-width: 900px) {
    .model-explorer {
      inset: 2vh 5vw;
      padding: 1.25rem;
    }
  }

  @media (max-width: 640px) {
    .model-explorer {
      inset: 0;
      border-radius: 0;
    }

    .controls {
      flex-direction: column;
      align-items: stretch;
    }
  }
</style>
