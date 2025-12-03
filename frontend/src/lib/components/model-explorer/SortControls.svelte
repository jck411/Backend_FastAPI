<script lang="ts">
  import type { ModelSort } from "../../stores/models";

  export let selected: ModelSort;
  export let onSelect: (sort: ModelSort) => void;

  const options: Array<{ label: string; value: ModelSort }> = [
    { label: "Newest", value: "newness" },
    { label: "Lowest price", value: "price" },
    { label: "Longest context", value: "context" },
  ];

  function handleChange(event: Event) {
    const target = event.target as HTMLSelectElement;
    onSelect(target.value as ModelSort);
  }
</script>

<div class="sort">
  <label for="sort-select" class="sort-label">Sort by</label>
  <select
    id="sort-select"
    class="select-control sort-select"
    value={selected}
    on:change={handleChange}
  >
    {#each options as option}
      <option value={option.value}>{option.label}</option>
    {/each}
  </select>
</div>

<style>
  .sort {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.95rem;
    flex-wrap: nowrap;
    white-space: nowrap;
  }

  .sort-label {
    color: #d4daee;
    font-weight: 500;
    white-space: nowrap;
  }

  .sort-select {
    min-width: 140px;
    flex-shrink: 0;
  }
</style>
