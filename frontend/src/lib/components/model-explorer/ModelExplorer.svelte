<script lang="ts">
  import { createEventDispatcher, onDestroy } from 'svelte';
  import { modelStore, type ModelSort } from '../../stores/models';
  import type { ModelRecord } from '../../api/types';
  import { formatContext, formatPrice } from '../../models/utils';
  import ModelCard from './ModelCard.svelte';
  import TogglePillGroup from './TogglePillGroup.svelte';
  import SortControls from './SortControls.svelte';
  import FilterSection from './FilterSection.svelte';
  import RangeSlider from './RangeSlider.svelte';

  export let open = false;

  type FilterState = {
    search: string;
    inputModalities: string[];
    outputModalities: string[];
    series: string[];
    providers: string[];
    supportedParameters: string[];
    moderation: string[];
    minContext: number | null;
    minPromptPrice: number | null;
    maxPromptPrice: number | null;
    sort: ModelSort;
  };

  type PriceRange = {
    min: number;
    max: number;
  };

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
    setMinPromptPrice,
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

  let currentFilters: FilterState;
  let contextStep = 1;
  let priceStep = 0.001;
  let contextValue = 0;
  let priceRange: PriceRange = { min: 0, max: 0 };
  let priceLabel = '';
  let contextSliderDisabled = false;
  let priceSliderDisabled = false;
  let priceScale: string[] = [];

  const contextSliderId = 'context-length-slider';
  const priceSliderId = 'prompt-price-slider';
  const CONTEXT_SCALE = ['4K', '64K', '1M'];
  const PRICE_SCALE = ['FREE', '$0.5', '$10+'];

  $: filteredModels = $filtered as ModelRecord[];
  $: availableFacets = $facets;
  $: currentFilters = $filters as FilterState;
  $: filtersActive = $activeFilters;
  $: activeFilterCount = countActiveFilters(currentFilters);
  $: filterStatus = activeFilterCount > 0
    ? `${activeFilterCount} active filter${activeFilterCount === 1 ? '' : 's'}`
    : 'All models shown.';

  $: contextMin = availableFacets.minContext ?? 0;
  $: contextMax = availableFacets.maxContext ?? contextMin;
  $: contextSliderDisabled = availableFacets.maxContext === null || contextMin === contextMax;
  $: contextStep = deriveContextStep(contextMin, contextMax);
  $: contextValue = clampIntegerValue(currentFilters?.minContext ?? contextMin, contextMin, contextMax);

  $: priceMin = availableFacets.minPromptPrice ?? 0;
  $: priceMax = availableFacets.maxPromptPrice ?? priceMin;
  $: priceSliderDisabled = availableFacets.maxPromptPrice === null || priceMin === priceMax;
  $: priceStep = derivePriceStep(priceMin, priceMax);
  $: priceRange = (() => {
    const range = {
      min: clampDecimalValue(currentFilters?.minPromptPrice ?? priceMin, priceMin, priceMax),
      max: clampDecimalValue(currentFilters?.maxPromptPrice ?? priceMax, priceMin, priceMax),
    };
    if (range.min > range.max) {
      return { min: range.max, max: range.max };
    }
    return range;
  })();
  $: priceLabel = (() => {
    const [minScale,, maxScale] = PRICE_SCALE;
    const minFilter = currentFilters?.minPromptPrice;
    const maxFilter = currentFilters?.maxPromptPrice;
    const minLabel = minFilter === null || minFilter <= priceMin ? minScale : formatPrice(minFilter);
    const maxLabel = maxFilter === null || maxFilter >= priceMax ? maxScale : formatPrice(maxFilter);
    return `${minLabel.toUpperCase()} – ${maxLabel.toUpperCase()}`;
  })();
  $: priceScale = priceSliderDisabled ? [] : PRICE_SCALE;

  function countActiveFilters(filters: FilterState): number {
    let count = 0;
    if (filters.search.trim()) {
      count += 1;
    }

    count += filters.inputModalities.length;
    count += filters.outputModalities.length;
    count += filters.series.length;
    count += filters.providers.length;
    count += filters.supportedParameters.length;
    count += filters.moderation.length;

    if (filters.minContext !== null) {
      count += 1;
    }

    if (filters.minPromptPrice !== null) {
      count += 1;
    }

    if (filters.maxPromptPrice !== null) {
      count += 1;
    }

    return count;
  }

  function clampIntegerValue(value: number, min: number, max: number): number {
    if (!Number.isFinite(value)) return min;
    if (value < min) return min;
    if (value > max) return max;
    return Math.round(value);
  }

  function clampDecimalValue(value: number, min: number, max: number): number {
    if (!Number.isFinite(value)) return max;
    if (value < min) return min;
    if (value > max) return max;
    return Number(value.toFixed(3));
  }

  function deriveContextStep(min: number, max: number): number {
    const span = max - min;
    if (!Number.isFinite(span) || span <= 0) {
      return 1;
    }
    const approx = Math.round(span / 40);
    return Math.max(approx, 1);
  }

  function derivePriceStep(min: number, max: number): number {
    const span = max - min;
    if (!Number.isFinite(span) || span <= 0) {
      return 0.001;
    }
    const approx = span / 40;
    if (approx <= 0.001) return 0.001;
    if (approx <= 0.005) return 0.005;
    if (approx <= 0.01) return 0.01;
    if (approx <= 0.05) return 0.05;
    if (approx <= 0.1) return 0.1;
    if (approx <= 0.5) return 0.25;
    if (approx <= 1) return 0.5;
    if (approx <= 2) return 1;
    if (approx <= 5) return 2.5;
    return 5;
  }

  function roundPriceValue(value: number): number {
    if (!Number.isFinite(value)) {
      return value;
    }
    if (priceStep >= 1) return Number(value.toFixed(2));
    if (priceStep >= 0.1) return Number(value.toFixed(2));
    if (priceStep >= 0.01) return Number(value.toFixed(3));
    return Number(value.toFixed(4));
  }

  function handleContextSlider(nextValue: number): void {
    const base = availableFacets.minContext ?? 0;
    const max = availableFacets.maxContext;
    if (max === null) {
      setMinContext(null);
      return;
    }

    if (nextValue <= base + contextStep / 2) {
      setMinContext(null);
      return;
    }

    setMinContext(Math.round(nextValue));
  }

  function handlePriceRangeChange(event: CustomEvent<PriceRange>): void {
    const range = event.detail;
    const max = availableFacets.maxPromptPrice;
    if (max === null) {
      setMinPromptPrice(null);
      setMaxPromptPrice(null);
      return;
    }

    const min = availableFacets.minPromptPrice ?? priceMin;
    const epsilon = Math.max(priceStep / 2, 0.0005);

    if (Math.abs(range.min - min) <= epsilon) {
      setMinPromptPrice(null);
    } else {
      setMinPromptPrice(roundPriceValue(range.min));
    }

    if (Math.abs(range.max - max) <= epsilon) {
      setMaxPromptPrice(null);
    } else {
      setMaxPromptPrice(roundPriceValue(range.max));
    }
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
      <SortControls selected={$filters.sort} onSelect={handleSort} />
    </section>

    <div class="body">
      <aside class="filters-panel" aria-label="Filter models">
        <header class="filters-header">
          <div>
            <h3>Filters</h3>
            <p class="filters-status" class:muted={activeFilterCount === 0}>{filterStatus}</p>
          </div>
          <button
            type="button"
            class="ghost small"
            on:click={resetFilters}
            disabled={!filtersActive}
          >
            Clear all
          </button>
        </header>
        <div class="filters-content">
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
          <FilterSection title="Context length">
            {#if contextSliderDisabled}
              {#if availableFacets.maxContext === null}
                <p class="hint">No context metadata available.</p>
              {:else}
                <p class="hint">All models offer {formatContext(contextMax)} context.</p>
              {/if}
            {:else}
              <div class="slider-group">
                <div class="slider-header">
                  <span class="slider-label">Minimum tokens</span>
                  <span class="slider-value">
                    {currentFilters.minContext === null
                      ? 'Any'
                      : formatContext(currentFilters.minContext)}
                  </span>
                </div>
                <input
                  id={contextSliderId}
                  class="slider"
                  type="range"
                  min={contextMin}
                  max={contextMax}
                  step={contextStep}
                  value={contextValue}
                  on:input={(event) => handleContextSlider(Number((event.target as HTMLInputElement).value))}
                  aria-label="Minimum context tokens"
                />
                <div class="slider-scale context-scale">
                  {#each CONTEXT_SCALE as label, index (label + index)}
                    <span>{label}</span>
                  {/each}
                </div>
              </div>
            {/if}
          </FilterSection>
          <FilterSection title="Prompt pricing">
            {#if priceSliderDisabled}
              {#if availableFacets.maxPromptPrice === null}
                <p class="hint">No pricing metadata available.</p>
              {:else}
                <p class="hint">All models share {formatPrice(priceMax)} pricing.</p>
              {/if}
            {:else}
              <div class="slider-group">
                <div class="slider-header">
                  <span class="slider-label">Prompt price (per 1M tokens)</span>
                  <span class="slider-value">{priceLabel}</span>
                </div>
                <RangeSlider
                  id={priceSliderId}
                  min={priceMin}
                  max={priceMax}
                  step={priceStep}
                  value={priceRange}
                  on:input={handlePriceRangeChange}
                  ariaLabelMin="Minimum prompt price"
                  ariaLabelMax="Maximum prompt price"
                  disabled={priceSliderDisabled}
                />
                {#if priceScale.length > 0}
                  <div class="slider-scale price-scale">
                    {#each priceScale as label, index (label + index)}
                      <span>{label}</span>
                    {/each}
                  </div>
                {/if}
              </div>
            {/if}
          </FilterSection>
          <TogglePillGroup
            title="Series"
            options={availableFacets.series}
            selected={$filters.series}
            on:toggle={(event) => toggleSeries(event.detail)}
            emptyMessage="Series information unavailable."
          />
          <TogglePillGroup
            title="Supported parameters"
            options={availableFacets.supportedParameters}
            selected={$filters.supportedParameters}
            on:toggle={(event) => toggleSupportedParameter(event.detail)}
            emptyMessage="No parameter metadata available."
          />
          <TogglePillGroup
            title="Providers"
            options={availableFacets.providers}
            selected={$filters.providers}
            on:toggle={(event) => toggleProvider(event.detail)}
            emptyMessage="No provider data available."
          />
          <TogglePillGroup
            title="Moderation"
            options={availableFacets.moderation}
            selected={$filters.moderation}
            on:toggle={(event) => toggleModeration(event.detail)}
            emptyMessage="No moderation metadata available."
          />
        </div>
      </aside>

      <section class="results" aria-live="polite">
        <header class="results-header">
          <div>
            <h3>Models</h3>
            <p class="summary">{filteredModels.length} result{filteredModels.length === 1 ? '' : 's'}</p>
          </div>
          <button
            type="button"
            class="ghost small results-reset"
            on:click={resetFilters}
            disabled={!filtersActive}
          >
            Clear all
          </button>
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
    inset: 4vh;
    background: #080d18;
    border: 1px solid #141d33;
    border-radius: 1rem;
    padding: 1.5rem;
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
    transition: border-color 0.2s ease, color 0.2s ease, background 0.2s ease;
  }

  .ghost:hover:not(:disabled) {
    border-color: #38bdf8;
    color: #38bdf8;
  }

  .ghost:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .ghost.small {
    padding: 0.35rem 0.85rem;
    font-size: 0.85rem;
    border-radius: 0.85rem;
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
    border-radius: 0.85rem;
    border: 1px solid #16203a;
    background: rgba(9, 14, 26, 0.85);
    color: inherit;
  }

  .body {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
    gap: 1.5rem;
  }

  .filters-panel {
    border: 1px solid #141d33;
    border-radius: 1rem;
    background: rgba(8, 13, 24, 0.85);
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    padding: 1.25rem;
    min-height: 0;
  }

  .filters-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .filters-header h3 {
    margin: 0;
  }

  .filters-status {
    margin: 0.2rem 0 0;
    font-size: 0.82rem;
    color: #9ca4bc;
  }

  .filters-status.muted {
    color: #6f7892;
  }

  .filters-content {
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
  }

  .slider-group {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
  }

  .slider-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    font-size: 0.88rem;
  }

  .slider-label {
    color: #b9c2d7;
  }

  .slider-value {
    font-variant-numeric: tabular-nums;
    color: #f0f4ff;
    font-weight: 600;
  }

  .slider {
    width: 100%;
    appearance: none;
    height: 0.35rem;
    border-radius: 999px;
    background: rgba(34, 49, 78, 0.6);
    outline: none;
    cursor: pointer;
    accent-color: #2563eb;
  }

  .slider:disabled {
    cursor: not-allowed;
    opacity: 0.45;
  }

  .slider::-webkit-slider-thumb {
    appearance: none;
    width: 1rem;
    height: 1rem;
    border-radius: 50%;
    background: #1d9bf0;
    border: 2px solid #0f172a;
    box-shadow: 0 2px 4px rgba(9, 15, 26, 0.35);
  }

  .slider::-moz-range-thumb {
    width: 1rem;
    height: 1rem;
    border-radius: 50%;
    background: #1d9bf0;
    border: 2px solid #0f172a;
    box-shadow: 0 2px 4px rgba(9, 15, 26, 0.35);
  }

  .slider::-moz-range-track {
    background: transparent;
  }

  .slider-scale {
    display: flex;
    justify-content: space-between;
    font-size: 0.78rem;
    color: #6f7892;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .price-scale {
    gap: 0.5rem;
  }

  .slider-scale span {
    flex: 1;
    text-align: center;
  }

  .slider-scale span:first-child {
    text-align: left;
  }

  .slider-scale span:last-child {
    text-align: right;
  }

  .hint {
    margin: 0;
    font-size: 0.85rem;
    color: #7f89a3;
  }

  .results {
    display: grid;
    grid-template-rows: auto 1fr;
    gap: 1rem;
    min-height: 0;
  }

  .results-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .results-reset {
    display: none;
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
    padding: 0 0.25rem 0 0;
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

  @media (max-width: 1024px) {
    .body {
      grid-template-columns: 1fr;
    }

    .filters-panel {
      order: 2;
      max-height: none;
    }

    .filters-content {
      max-height: none;
      flex: none;
      min-height: auto;
      overflow: visible;
    }

    .results-reset {
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
  }

  @media (max-width: 900px) {
    .model-explorer {
      inset: 2vh;
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
