<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import type { ModelRecord } from "../../api/types";
  import ModelCard from "./ModelCard.svelte";
  import ActiveFilterSummary from "./ActiveFilterSummary.svelte";
  import type { FilterChip } from "./types";

  export let models: ModelRecord[] = [];
  export let filtersActive = false;
  export let onSelect: (model: ModelRecord) => void;
  export let filterChips: FilterChip[] = [];

  const dispatch = createEventDispatcher<{ clearFilter: FilterChip }>();

  function handleClear(event: CustomEvent<FilterChip>): void {
    dispatch("clearFilter", event.detail);
  }
</script>

<section class="results" aria-live="polite">
  <ActiveFilterSummary chips={filterChips} on:clear={handleClear} />
  {#if models.length === 0}
    <p class="empty">
      {#if filtersActive}
        No models match your current filters.
      {:else}
        No models available.
      {/if}
    </p>
  {:else}
    <ul class="model-grid">
      {#each models as model (model.id)}
        <li>
          <ModelCard {model} {onSelect} />
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .results {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    min-height: 0;
    flex: 1;
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

  @media (max-width: 768px) {
    .model-grid {
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      padding: 0;
    }
  }

  @media (max-width: 480px) {
    .model-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
