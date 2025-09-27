<script lang="ts">
  import { formatContext } from "../../models/utils";
  import { modelStore } from "../../stores/models";
  import FilterSection from "./FilterSection.svelte";
  import RangeSlider from "./RangeSlider.svelte";
  import TogglePillGroup from "./TogglePillGroup.svelte";
  import {
    CONTEXT_ANY_INDEX,
    CONTEXT_SCALE_LABELS,
    CONTEXT_STOP_COUNT,
    PRICE_SCALE_LABELS,
    PRICE_STOP_COUNT,
    PRICE_UNBOUNDED_INDEX,
    PRICE_UNBOUNDED_LABEL,
    clampIndex,
    countActiveFilters,
    formatStopLabel,
    indexForContext,
    indexForMaxPrice,
    indexForMinPrice,
    valueForContextIndex,
    valueForMaxIndex,
    valueForMinIndex,
    type FilterState,
  } from "./filters/utils";

  type FacetState = {
    inputModalities: string[];
    outputModalities: string[];
    minContext: number | null;
    maxContext: number | null;
    minPromptPrice: number | null;
    maxPromptPrice: number | null;
    series: string[];
    providers: string[];
    supportedParameters: string[];
    moderation: string[];
  };

  type PriceRange = {
    min: number;
    max: number;
  };

  const {
    facets,
    filters,
    toggleInputModality,
    toggleOutputModality,
    toggleSeries,
    toggleProvider,
    toggleSupportedParameter,
    toggleModeration,
    setMinContext,
    setMinPromptPrice,
    setMaxPromptPrice,
    resetFilters,
    activeFilters,
  } = modelStore;

  const contextSliderId = "context-length-slider";
  const priceSliderId = "prompt-price-slider";

  let currentFilters: FilterState;
  let availableFacets: FacetState | null = null;
  let filtersActive: boolean;
  let activeFilterCount = 0;
  let filterStatus = "";
  let contextMax: number | null = null;
  let contextSliderDisabled = false;
  let contextIndex = 0;
  let contextScale: string[] = [];
  let priceSliderDisabled = false;
  let priceRange: PriceRange = { min: 0, max: 0 };
  let priceLabel = "";
  let priceScale: string[] = [];

  $: availableFacets = $facets as FacetState;
  $: currentFilters = $filters as FilterState;
  $: filtersActive = $activeFilters;
  $: activeFilterCount = countActiveFilters(currentFilters);
  $: filterStatus =
    activeFilterCount > 0
      ? `${activeFilterCount} active filter${activeFilterCount === 1 ? "" : "s"}`
      : "All models shown.";

  $: {
    const maxContextValue = availableFacets?.maxContext ?? null;
    contextMax = maxContextValue;
    contextSliderDisabled = maxContextValue === null;
    contextIndex = contextSliderDisabled
      ? CONTEXT_ANY_INDEX
      : indexForContext(currentFilters?.minContext ?? null);
    contextScale = contextSliderDisabled ? [] : CONTEXT_SCALE_LABELS;
  }

  $: {
    const maxPriceValue = availableFacets?.maxPromptPrice ?? null;
    priceSliderDisabled = maxPriceValue === null;
  }
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
      options={availableFacets?.inputModalities ?? []}
      selected={currentFilters?.inputModalities ?? []}
      on:toggle={(event) => toggleInputModality(event.detail)}
      emptyMessage="No modality data available."
    />
    <TogglePillGroup
      title="Output modalities"
      options={availableFacets?.outputModalities ?? []}
      selected={currentFilters?.outputModalities ?? []}
      on:toggle={(event) => toggleOutputModality(event.detail)}
      emptyMessage="No modality data available."
    />
    <FilterSection
      title="Context length"
      forceOpen={currentFilters?.minContext !== null}
    >
      {#if contextSliderDisabled}
        {#if availableFacets?.maxContext === null || availableFacets?.maxContext === undefined}
          <p class="hint">No context metadata available.</p>
        {:else}
          <p class="hint">All models offer {formatContext(contextMax)} context.</p>
        {/if}
      {:else}
        <div class="slider-group">
          <div class="slider-header">
            <span class="slider-label">Minimum tokens</span>
            <span class="slider-value">
              {currentFilters?.minContext === null
                ? "Any"
                : formatContext(currentFilters?.minContext ?? 0)}
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
              handleContextSlider(Number((event.target as HTMLInputElement).value))}
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
    <FilterSection
      title="Prompt pricing"
      forceOpen={currentFilters?.minPromptPrice !== null ||
        currentFilters?.maxPromptPrice !== null}
    >
      {#if priceSliderDisabled}
        {#if availableFacets?.maxPromptPrice === null || availableFacets?.maxPromptPrice === undefined}
          <p class="hint">No pricing metadata available.</p>
        {:else}
          <p class="hint">
            All models share {formatStopLabel(
              availableFacets?.maxPromptPrice ?? 0,
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
      options={availableFacets?.series ?? []}
      selected={currentFilters?.series ?? []}
      on:toggle={(event) => toggleSeries(event.detail)}
      emptyMessage="Series information unavailable."
    />
    <TogglePillGroup
      title="Supported parameters"
      options={availableFacets?.supportedParameters ?? []}
      selected={currentFilters?.supportedParameters ?? []}
      on:toggle={(event) => toggleSupportedParameter(event.detail)}
      variant="columns"
      emptyMessage="No parameter metadata available."
    />
    <TogglePillGroup
      title="Providers"
      options={availableFacets?.providers ?? []}
      selected={currentFilters?.providers ?? []}
      on:toggle={(event) => toggleProvider(event.detail)}
      emptyMessage="No provider data available."
    />
    <TogglePillGroup
      title="Moderation"
      options={availableFacets?.moderation ?? []}
      selected={currentFilters?.moderation ?? []}
      on:toggle={(event) => toggleModeration(event.detail)}
      variant="compact"
      emptyMessage="No moderation metadata available."
    />
  </div>
</aside>

<style>
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

  @media (max-width: 1024px) {
    .filters-panel {
      order: -1;
      max-height: none;
    }

    .filters-content {
      max-height: none;
      flex: none;
      min-height: auto;
      overflow: visible;
    }
  }

  @media (max-width: 900px) {
    .filters-panel {
      order: -1;
    }
  }

  @media (max-width: 480px) {
    .filters-panel {
      padding: 1rem;
    }
  }
</style>
