<script lang="ts">
  import { createEventDispatcher, onDestroy, onMount } from "svelte";
  import type { ModelRecord } from "../../api/types";
  import {
    modelStore,
    type ModelFilters,
    type ModelSort,
    type MultiSelectKey,
  } from "../../stores/models";
  import FilterPanel from "./FilterPanel.svelte";
  import ModelExplorerHeader from "./ModelExplorerHeader.svelte";
  import ModelResults from "./ModelResults.svelte";
  import type { FilterCategoryKey, FilterChip } from "./types";

  export let open = false;

  const dispatch = createEventDispatcher<{
    select: { id: string };
    close: void;
  }>();

  const {
    filtered,
    filters,
    setSearch,
    setSort,
    activeFilters,
    setSelectionState,
  } = modelStore;

  const filterCategories: Record<FilterCategoryKey, { label: string }> = {
    inputModalities: { label: "Input" },
    outputModalities: { label: "Output" },
    series: { label: "Series" },
    providers: { label: "Provider" },
    supportedParameters: { label: "Parameter" },
    moderation: { label: "Moderation" },
  };

  const categoryOrder: FilterCategoryKey[] = [
    "inputModalities",
    "outputModalities",
    "series",
    "providers",
    "supportedParameters",
    "moderation",
  ];

  const compactMediaQuery = "(max-width: 1024px)";

  let compactLayout = false;
  let filtersVisible = true;
  let filtersManuallyToggled = false;
  let filterChips: FilterChip[] = [];

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

  function handleSearch(value: string): void {
    setSearch(value);
  }

  $: filteredModels = $filtered as ModelRecord[];
  $: filtersActive = $activeFilters;
  $: currentFilters = $filters as ModelFilters;
  $: filterChips = currentFilters ? buildFilterChips(currentFilters) : [];

  function buildFilterChips(filters: ModelFilters): FilterChip[] {
    const chips: FilterChip[] = [];
    for (const key of categoryOrder) {
      const selection = filters[key];
      if (!selection) continue;
      const config = filterCategories[key];
      const categoryLabel = config?.label ?? key;
      for (const value of selection.include) {
        chips.push(createChip(key, categoryLabel, value, "include"));
      }
      for (const value of selection.exclude) {
        chips.push(createChip(key, categoryLabel, value, "exclude"));
      }
    }
    return chips;
  }

  function createChip(
    category: FilterCategoryKey,
    categoryLabel: string,
    value: string,
    state: "include" | "exclude",
  ): FilterChip {
    const normalized = value.trim();
    return {
      id: `${category}:${state}:${normalized}`,
      category,
      categoryLabel,
      value: normalized,
      valueLabel: formatValueLabel(normalized),
      state,
    };
  }

  function formatValueLabel(value: string): string {
    return value.replace(/[_-]/g, " ") || value;
  }

  function setCompactLayout(matches: boolean): void {
    compactLayout = matches;
    if (matches) {
      if (!filtersManuallyToggled) {
        filtersVisible = false;
      }
    } else {
      filtersVisible = true;
      filtersManuallyToggled = false;
    }
  }

  function toggleFilters(): void {
    filtersVisible = !filtersVisible;
    filtersManuallyToggled = true;
  }

  function handleFilterChipClear(event: CustomEvent<FilterChip>): void {
    const chip = event.detail;
    setSelectionState(chip.category as MultiSelectKey, chip.value, "neutral");
  }

  onMount(() => {
    if (typeof window === "undefined") {
      return;
    }

    const mediaQuery = window.matchMedia(compactMediaQuery);

    setCompactLayout(mediaQuery.matches);

    const handleChange = (event: MediaQueryListEvent) => {
      setCompactLayout(event.matches);
    };

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", handleChange);
      return () => mediaQuery.removeEventListener("change", handleChange);
    }

    mediaQuery.addListener(handleChange);
    return () => mediaQuery.removeListener(handleChange);
  });
</script>

{#if open}
  <div class="modal-backdrop" role="presentation" on:click={close}></div>
  <div
    class="model-explorer"
    role="dialog"
    aria-modal="true"
    aria-labelledby="model-explorer-title"
    data-compact={compactLayout}
  >
    <ModelExplorerHeader
      resultCount={filteredModels.length}
      searchValue={$filters.search}
      onSearch={handleSearch}
      sort={$filters.sort}
      onSort={handleSort}
      onClose={close}
    />

    <div class="body" data-compact={compactLayout}>
      {#if compactLayout}
        <div class="body-toolbar">
          <button
            type="button"
            class="filters-toggle"
            class:open={filtersVisible}
            on:click={toggleFilters}
            aria-expanded={filtersVisible}
            aria-controls="model-explorer-filters"
          >
            <span class="filters-toggle__label">Filters</span>
            {#if filtersActive}
              <span class="filters-toggle__status">Active</span>
            {/if}
          </button>
        </div>
      {/if}

      <div
        id="model-explorer-filters"
        class="filters-panel-container"
        data-compact={compactLayout}
        data-open={filtersVisible}
      >
        <FilterPanel />
      </div>

      <ModelResults
        models={filteredModels}
        {filtersActive}
        {filterChips}
        onSelect={handleSelect}
        on:clearFilter={handleFilterChipClear}
      />
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
    display: grid;
    grid-template-columns: minmax(320px, 380px) minmax(0, 1fr);
    grid-template-rows: auto 1fr;
    column-gap: 1.75rem;
    row-gap: 1.25rem;
    z-index: 100;
    max-height: 90vh;
    overflow: hidden;
  }

  .model-explorer[data-compact="true"] {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  :global(.explorer-header) {
    grid-column: 1;
    grid-row: 1;
    align-self: start;
  }

  .body {
    flex: 1;
    min-height: 0;
  }

  .body[data-compact="false"] {
    display: contents;
  }

  .body[data-compact="true"] {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .body-toolbar {
    display: none;
  }

  .filters-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    border-radius: 999px;
    border: 1px solid #25314d;
    background: rgba(11, 17, 29, 0.9);
    color: #f2f4f8;
    padding: 0.45rem 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      color 0.2s ease,
      background 0.2s ease;
  }

  .filters-toggle:hover {
    border-color: #38bdf8;
    color: #38bdf8;
  }

  .filters-toggle.open {
    border-color: #38bdf8;
    color: #38bdf8;
    background: rgba(16, 25, 43, 0.95);
  }

  .filters-toggle__status {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #041225;
    background: rgba(56, 189, 248, 0.28);
    border-radius: 999px;
    padding: 0.12rem 0.5rem;
  }

  .filters-panel-container {
    min-height: 0;
  }

  .body[data-compact="false"] .filters-panel-container {
    display: contents;
  }

  .filters-panel-container[data-compact="true"]:not([data-open="true"]) {
    display: none;
  }

  .body[data-compact="false"] :global(.filters-panel) {
    grid-column: 1;
    grid-row: 2;
    align-self: stretch;
  }

  .body[data-compact="false"] :global(.results) {
    grid-column: 2;
    grid-row: 1 / span 2;
    align-self: stretch;
  }

  :global(body.modal-open) {
    overflow: hidden;
  }

  @media (max-width: 1024px) {
    .model-explorer {
      max-height: none;
    }

    .body-toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .filters-panel-container[data-compact="true"] :global(.filters-panel) {
      max-height: min(60vh, 540px);
      overflow-y: auto;
    }
  }

  @media (max-width: 768px) {
    .model-explorer {
      inset: 2vh;
      padding: 1.25rem;
    }
  }

  @media (max-width: 640px) {
    .model-explorer {
      inset: 0;
      border-radius: 0;
      height: 100dvh;
      max-height: none;
      overflow-y: auto;
      padding: 1rem 1rem calc(1rem + env(safe-area-inset-bottom));
    }

    .body {
      gap: 1rem;
    }

    .filters-toggle {
      width: 100%;
      justify-content: space-between;
    }

    .filters-panel-container[data-compact="true"] :global(.filters-panel) {
      max-height: none;
      box-shadow: 0 18px 36px rgba(4, 9, 18, 0.45);
    }
  }
</style>
