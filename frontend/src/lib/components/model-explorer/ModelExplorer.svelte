<script lang="ts">
  import { createEventDispatcher, onDestroy } from "svelte";
  import type { ModelRecord } from "../../api/types";
  import { formatContext } from "../../models/utils";
  import { modelStore, type ModelSort } from "../../stores/models";
  import FilterSection from "./FilterSection.svelte";
  import ModelCard from "./ModelCard.svelte";
  import RangeSlider from "./RangeSlider.svelte";
  import SortControls from "./SortControls.svelte";
  import TogglePillGroup from "./TogglePillGroup.svelte";

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

  const dispatch = createEventDispatcher<{
    select: { id: string };
    close: void;
  }>();

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

  const bodyClass = "modal-open";

  let cleanup = () => {
    if (typeof document !== "undefined") {
      document.body.classList.remove(bodyClass);
    }
  };

  $: {
    if (typeof document !== "undefined") {
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
    dispatch("close");
  }

  function handleSelect(model: ModelRecord): void {
    dispatch("select", { id: model.id });
    close();
  }

  function handleSort(sort: ModelSort): void {
    setSort(sort);
  }

  let currentFilters: FilterState;
  let contextIndex = 0;
  let priceRange: PriceRange = { min: 0, max: 0 };
  let priceLabel = "";
  let contextSliderDisabled = false;
  let priceSliderDisabled = false;
  let contextScale: string[] = [];
  let priceScale: string[] = [];

  const contextSliderId = "context-length-slider";
  const priceSliderId = "prompt-price-slider";
  const CONTEXT_STOPS = [4000, 16000, 32000, 64000, 128000, 256000, 1_000_000];
  const CONTEXT_STOP_COUNT = CONTEXT_STOPS.length;
  const CONTEXT_ANY_INDEX = 0;
  const CONTEXT_SCALE_LABELS = [
    "Any",
    ...CONTEXT_STOPS.map((value) => formatContextStop(value)),
  ];
  const PRICE_STOPS = [0, 0.1, 0.2, 0.5, 1, 5, 10];
  const PRICE_STOP_COUNT = PRICE_STOPS.length;
  const PRICE_UNBOUNDED_INDEX = PRICE_STOP_COUNT;
  const PRICE_UNBOUNDED_LABEL = "$10+";
  const PRICE_SCALE_LABELS = PRICE_STOPS.map((stop) => formatStopLabel(stop));

  $: filteredModels = $filtered as ModelRecord[];
  $: availableFacets = $facets;
  $: currentFilters = $filters as FilterState;
  $: filtersActive = $activeFilters;
  $: activeFilterCount = countActiveFilters(currentFilters);
  $: filterStatus =
    activeFilterCount > 0
      ? `${activeFilterCount} active filter${activeFilterCount === 1 ? "" : "s"}`
      : "All models shown.";

  $: contextMax = availableFacets.maxContext ?? null;
  $: contextSliderDisabled = availableFacets.maxContext === null;
  $: contextIndex = contextSliderDisabled
    ? CONTEXT_ANY_INDEX
    : indexForContext(currentFilters?.minContext ?? null);
  $: contextScale = contextSliderDisabled ? [] : CONTEXT_SCALE_LABELS;

  $: priceSliderDisabled = availableFacets.maxPromptPrice === null;
  $: priceRange = (() => {
    if (priceSliderDisabled) {
      return { min: 0, max: PRICE_UNBOUNDED_INDEX };
    }
    const minIndex = indexForMinPrice(currentFilters?.minPromptPrice ?? null);
    const maxIndex = indexForMaxPrice(currentFilters?.maxPromptPrice ?? null);
    const clampedMin = clampIndex(minIndex, 0, PRICE_STOP_COUNT - 1);
    const clampedMax = clampIndex(maxIndex, 0, PRICE_UNBOUNDED_INDEX);
    if (clampedMin > clampedMax) {
      return { min: clampedMax, max: clampedMax };
    }
    return { min: clampedMin, max: clampedMax };
  })();
  $: priceLabel = (() => {
    const minFilter = currentFilters?.minPromptPrice;
    const maxFilter = currentFilters?.maxPromptPrice;
    const minLabel =
      minFilter === null ? PRICE_SCALE_LABELS[0] : formatStopLabel(minFilter);
    const maxLabel =
      maxFilter === null ? PRICE_UNBOUNDED_LABEL : formatStopLabel(maxFilter);
    return `${minLabel} – ${maxLabel}`;
  })();
  $: priceScale = priceSliderDisabled ? [] : PRICE_SCALE_LABELS;

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

  const STOP_EPSILON = 1e-9;

  function clampIndex(value: number, min: number, max: number): number {
    if (!Number.isFinite(value)) return min;
    if (value < min) return min;
    if (value > max) return max;
    return Math.round(value);
  }

  function findNearestStopIndex(value: number): number {
    let nearestIndex = 0;
    let nearestDiff = Number.POSITIVE_INFINITY;
    for (let index = 0; index < PRICE_STOP_COUNT; index += 1) {
      const diff = Math.abs(PRICE_STOPS[index] - value);
      if (diff < nearestDiff) {
        nearestDiff = diff;
        nearestIndex = index;
      }
    }
    return nearestIndex;
  }

  function indexForMinPrice(value: number | null): number {
    if (value === null || value <= 0) {
      return 0;
    }
    const exactIndex = PRICE_STOPS.findIndex(
      (stop) => Math.abs(stop - value) <= STOP_EPSILON,
    );
    if (exactIndex >= 0) {
      return exactIndex;
    }
    return findNearestStopIndex(value);
  }

  function indexForMaxPrice(value: number | null): number {
    if (value === null) {
      return PRICE_UNBOUNDED_INDEX;
    }
    const exactIndex = PRICE_STOPS.findIndex(
      (stop) => Math.abs(stop - value) <= STOP_EPSILON,
    );
    if (exactIndex >= 0) {
      return exactIndex;
    }
    return findNearestStopIndex(value);
  }

  function findNearestContextIndex(value: number): number {
    let nearestIndex = 0;
    let nearestDiff = Number.POSITIVE_INFINITY;
    for (let index = 0; index < CONTEXT_STOP_COUNT; index += 1) {
      const diff = Math.abs(CONTEXT_STOPS[index] - value);
      if (diff < nearestDiff) {
        nearestDiff = diff;
        nearestIndex = index;
      }
    }
    return nearestIndex + 1;
  }

  function indexForContext(value: number | null): number {
    if (value === null || value <= 0) {
      return CONTEXT_ANY_INDEX;
    }
    for (let index = 0; index < CONTEXT_STOP_COUNT; index += 1) {
      if (Math.abs(CONTEXT_STOPS[index] - value) <= STOP_EPSILON) {
        return index + 1;
      }
    }
    return findNearestContextIndex(value);
  }

  function valueForContextIndex(index: number): number | null {
    if (index <= CONTEXT_ANY_INDEX) {
      return null;
    }
    const stopIndex = Math.min(Math.max(index - 1, 0), CONTEXT_STOP_COUNT - 1);
    return CONTEXT_STOPS[stopIndex];
  }

  function valueForMinIndex(index: number): number | null {
    if (index <= 0) {
      return null;
    }
    const safeIndex = Math.min(index, PRICE_STOP_COUNT - 1);
    return PRICE_STOPS[safeIndex];
  }

  function valueForMaxIndex(index: number): number | null {
    if (index >= PRICE_UNBOUNDED_INDEX) {
      return null;
    }
    const safeIndex = Math.min(Math.max(index, 0), PRICE_STOP_COUNT - 1);
    return PRICE_STOPS[safeIndex];
  }

  function formatStopLabel(value: number): string {
    if (value <= 0) {
      return "FREE";
    }
    const abs = Math.abs(value);
    const digits =
      abs >= 10
        ? 0
        : abs >= 1
        ? 0
        : abs >= 0.1
        ? 1
        : abs >= 0.01
        ? 2
        : 3;
    const formatted = value
      .toFixed(digits)
      .replace(/\.0+$/, "")
      .replace(/(\.\d*?)0+$/, "$1");
    return `$${formatted}`;
  }

  function formatContextStop(value: number): string {
    if (!Number.isFinite(value) || value <= 0) {
      return "Any";
    }
    if (value >= 1_000_000) {
      return "1M";
    }
    if (value >= 1000) {
      const rounded = Math.round(value / 1000);
      return `${rounded}K`;
    }
    return `${value}`;
  }

  function handleContextSlider(nextValue: number): void {
    if (contextSliderDisabled) {
      setMinContext(null);
      return;
    }

    const index = clampIndex(nextValue, CONTEXT_ANY_INDEX, CONTEXT_STOP_COUNT);
    setMinContext(valueForContextIndex(index));
  }

  function handlePriceRangeChange(event: CustomEvent<PriceRange>): void {
    if (priceSliderDisabled) {
      setMinPromptPrice(null);
      setMaxPromptPrice(null);
      return;
    }

    const raw = event.detail;
    const minIndex = clampIndex(raw.min, 0, PRICE_STOP_COUNT - 1);
    const maxIndex = clampIndex(raw.max, 0, PRICE_UNBOUNDED_INDEX);

    setMinPromptPrice(valueForMinIndex(minIndex));
    setMaxPromptPrice(valueForMaxIndex(maxIndex));
  }
</script>

{#if open}
  <div class="modal-backdrop" role="presentation" on:click={close}></div>
  <div
    class="model-explorer"
    role="dialog"
    aria-modal="true"
    aria-labelledby="model-explorer-title"
  >
    <header class="explorer-header">
      <div>
        <h2 id="model-explorer-title">Model Explorer</h2>
        <p class="subtitle">
          Filter and compare OpenRouter models before selecting them.
        </p>
      </div>
      <button
        type="button"
        class="ghost"
        on:click={close}
        aria-label="Close model explorer">×</button
      >
    </header>

    <section class="controls">
      <label class="search">
        <span class="visually-hidden">Search models</span>
        <input
          type="search"
          placeholder="Search by name, provider, description, or tags"
          value={$filters.search}
          on:input={(event) =>
            setSearch((event.target as HTMLInputElement).value)}
        />
      </label>
      <SortControls selected={$filters.sort} onSelect={handleSort} />
    </section>

    <div class="body">
      <aside class="filters-panel" aria-label="Filter models">
        <header class="filters-header">
          <div>
            <h3>Filters</h3>
            <p class="filters-status" class:muted={activeFilterCount === 0}>
              {filterStatus}
            </p>
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
                <p class="hint">
                  All models offer {formatContext(contextMax)} context.
                </p>
              {/if}
            {:else}
              <div class="slider-group">
                <div class="slider-header">
                  <span class="slider-label">Minimum tokens</span>
                  <span class="slider-value">
                    {currentFilters.minContext === null
                      ? "Any"
                      : formatContext(currentFilters.minContext)}
                  </span>
                </div>
                <input
                  id={contextSliderId}
                  class="slider"
                  type="range"
                  min={CONTEXT_ANY_INDEX}
                  max={CONTEXT_STOP_COUNT}
                  step={1}
                  value={contextIndex}
                  on:input={(event) =>
                    handleContextSlider(
                      Number((event.target as HTMLInputElement).value),
                    )}
                  aria-label="Minimum context tokens"
                />
                <div class="slider-scale context-scale">
                  {#each contextScale as label, index (label + index)}
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
                <p class="hint">
                  All models share {formatStopLabel(
                    availableFacets.maxPromptPrice ?? 0,
                  )} pricing.
                </p>
              {/if}
            {:else}
              <div class="slider-group">
                <div class="slider-header">
                  <span class="slider-label">Prompt price (per 1M tokens)</span>
                  <span class="slider-value">{priceLabel}</span>
                </div>
                <RangeSlider
                  id={priceSliderId}
                  min={0}
                  max={PRICE_UNBOUNDED_INDEX}
                  step={1}
                  value={priceRange}
                  on:input={handlePriceRangeChange}
                  on:change={handlePriceRangeChange}
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
            <p class="summary">
              {filteredModels.length} result{filteredModels.length === 1
                ? ""
                : "s"}
            </p>
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
    transition:
      border-color 0.2s ease,
      color 0.2s ease,
      background 0.2s ease;
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
