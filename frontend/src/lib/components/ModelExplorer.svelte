<script lang="ts">
  import { createEventDispatcher, onDestroy } from 'svelte';
  import { modelStore, type ModelSort } from '../stores/models';
  import type { ModelRecord } from '../api/types';

  export let open = false;

  const dispatch = createEventDispatcher<{ select: { id: string }; close: void }>();

  const { filtered, facets, filters, setSearch, toggleInputModality, toggleOutputModality, setMinContext, setMaxPromptPrice, setSort, resetFilters } = modelStore;

  const bodyClass = 'modal-open';

  const bodyObserver = () => {
    if (typeof document === 'undefined') {
      return () => {};
    }
    return () => {
      document.body.classList.remove(bodyClass);
    };
  };

  let cleanup = bodyObserver();

  $: {
    if (typeof document !== 'undefined') {
      if (open) {
        document.body.classList.add(bodyClass);
      } else {
        document.body.classList.remove(bodyClass);
      }
    }
  }

  onDestroy(() => cleanup?.());

  function close(): void {
    open = false;
    dispatch('close');
  }

  function handleSelect(model: ModelRecord): void {
    dispatch('select', { id: model.id });
    close();
  }

  function isInputSelected(modality: string): boolean {
    return $filters.inputModalities.includes(modality);
  }

  function isOutputSelected(modality: string): boolean {
    return $filters.outputModalities.includes(modality);
  }

  function handleSort(sort: ModelSort): void {
    setSort(sort);
  }

  function formatPrice(value: number | null): string {
    if (value === null) {
      return '—';
    }
    if (value >= 1) {
      return `$${value.toFixed(2)}`;
    }
    if (value >= 0.01) {
      return `$${value.toFixed(3)}`;
    }
    return `$${value.toFixed(4)}`;
  }

  function formatContext(value: number | null): string {
    if (value === null) return 'Unknown';
    if (value >= 1000) {
      return `${(value / 1000).toFixed(1)}k tokens`;
    }
    return `${value} tokens`;
  }

  $: filteredModels = $filtered as ModelRecord[];
  $: availableFacets = $facets;
  $: currentFilters = $filters;

  function extractPromptPrice(pricing: ModelRecord['pricing'] | null | undefined): number | null {
    if (!pricing) return null;
    const prompt = pricing.prompt ?? pricing.request ?? pricing.completion ?? null;
    if (typeof prompt === 'number') return Number.isFinite(prompt) ? prompt : null;
    if (typeof prompt === 'string') {
      const parsed = Number(prompt);
      return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
  }

  function extractContextLength(model: ModelRecord): number | null {
    const candidates = [
      (model as Record<string, unknown>).max_context,
      (model as Record<string, unknown>).context_length,
      (model as Record<string, unknown>).context_window,
      (model as Record<string, unknown>).context_tokens,
      (model.stats as Record<string, unknown> | undefined)?.context_length,
    ];
    for (const candidate of candidates) {
      if (typeof candidate === 'number' && Number.isFinite(candidate)) {
        return candidate;
      }
      if (typeof candidate === 'string' && candidate.trim()) {
        const parsed = Number(candidate);
        if (Number.isFinite(parsed)) return parsed;
      }
    }
    return null;
  }
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
      <div class="sort">
        <span>Sort by</span>
        <div class="sort-buttons">
          <button
            type="button"
            class:active={$filters.sort === 'newness'}
            on:click={() => handleSort('newness')}
          >
            Newest
          </button>
          <button
            type="button"
            class:active={$filters.sort === 'price'}
            on:click={() => handleSort('price')}
          >
            Lowest price
          </button>
          <button
            type="button"
            class:active={$filters.sort === 'context'}
            on:click={() => handleSort('context')}
          >
            Longest context
          </button>
        </div>
      </div>
    </section>

    <section class="filters">
      <div class="filter-card">
        <header>
          <h3>Input modalities</h3>
        </header>
        <div class="options">
          {#if availableFacets.inputModalities.length === 0}
            <p class="empty">No modality data available.</p>
          {:else}
            {#each availableFacets.inputModalities as modality}
              <button
                type="button"
                class:active={isInputSelected(modality)}
                on:click={() => toggleInputModality(modality)}
              >
                {modality}
              </button>
            {/each}
          {/if}
        </div>
      </div>

      <div class="filter-card">
        <header>
          <h3>Output modalities</h3>
        </header>
        <div class="options">
          {#if availableFacets.outputModalities.length === 0}
            <p class="empty">No modality data available.</p>
          {:else}
            {#each availableFacets.outputModalities as modality}
              <button
                type="button"
                class:active={isOutputSelected(modality)}
                on:click={() => toggleOutputModality(modality)}
              >
                {modality}
              </button>
            {/each}
          {/if}
        </div>
      </div>

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
        <p class="empty">No models match your current filters.</p>
      {:else}
        <ul class="model-grid">
          {#each filteredModels as model (model.id)}
            <li>
              <article class="model-card">
                <header>
                  <h4>{model.name ?? model.id}</h4>
                  <p class="model-id">{model.id}</p>
                </header>
                {#if model.description}
                  <p class="description">{model.description}</p>
                {/if}
                <dl class="metadata">
                  <div>
                    <dt>Context</dt>
                    <dd>{formatContext(extractContextLength(model))}</dd>
                  </div>
                  <div>
                    <dt>Prompt price</dt>
                    <dd>{formatPrice(extractPromptPrice(model.pricing ?? null))}</dd>
                  </div>
                  {#if model.provider?.display_name}
                    <div>
                      <dt>Provider</dt>
                      <dd>{model.provider.display_name}</dd>
                    </div>
                  {/if}
                </dl>
                <footer>
                  <button type="button" class="primary" on:click={() => handleSelect(model)}>
                    Use this model
                  </button>
                </footer>
              </article>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
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
    display: grid;
    grid-template-rows: auto auto auto 1fr;
    gap: 1.5rem;
    z-index: 100;
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

  .controls .search {
    flex: 1 1 260px;
  }

  .controls input[type='search'] {
    width: 100%;
    padding: 0.6rem 0.9rem;
    border-radius: 0.9rem;
    border: 1px solid #23314e;
    background: #090e1a;
    color: inherit;
  }

  .sort {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-size: 0.95rem;
  }

  .sort-buttons {
    display: inline-flex;
    gap: 0.5rem;
  }

  .sort-buttons button {
    border-radius: 999px;
    background: none;
    border: 1px solid #25314d;
    color: inherit;
    padding: 0.4rem 0.9rem;
    cursor: pointer;
  }

  .sort-buttons button.active {
    background: #38bdf8;
    color: #041225;
    border-color: #38bdf8;
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

  .filter-card h3 {
    margin: 0;
    font-size: 1rem;
  }

  .options {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .options button {
    border-radius: 999px;
    border: 1px solid #25314d;
    background: none;
    color: inherit;
    padding: 0.35rem 0.8rem;
    cursor: pointer;
    text-transform: capitalize;
  }

  .options button.active {
    background: #17263f;
    border-color: #38bdf8;
    color: #38bdf8;
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
    overflow: hidden;
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

  .model-card {
    border: 1px solid #1f2c48;
    border-radius: 1rem;
    padding: 1rem;
    display: grid;
    gap: 0.75rem;
    background: #0c1324;
    height: 100%;
  }

  .model-card header {
    display: grid;
    gap: 0.2rem;
  }

  .model-card h4 {
    margin: 0;
    font-size: 1.1rem;
  }

  .model-id {
    margin: 0;
    color: #69738d;
    font-size: 0.85rem;
  }

  .description {
    margin: 0;
    color: #9aa2ba;
    font-size: 0.9rem;
  }

  .metadata {
    margin: 0;
    display: grid;
    gap: 0.5rem;
  }

  .metadata div {
    display: flex;
    justify-content: space-between;
    font-size: 0.9rem;
  }

  .metadata dt {
    color: #7d87a2;
  }

  .metadata dd {
    margin: 0;
  }

  .primary {
    border-radius: 999px;
    border: none;
    background: #38bdf8;
    color: #041225;
    padding: 0.5rem 1.2rem;
    font-weight: 600;
    cursor: pointer;
  }

  .empty {
    margin: 0;
    color: #7f89a3;
    font-size: 0.9rem;
  }

  :global(body.modal-open) {
    overflow: hidden;
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

    .sort {
      width: 100%;
      justify-content: space-between;
    }
  }
</style>
