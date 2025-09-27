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
    class="sort-select"
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
    appearance: none;
    background: rgba(9, 14, 26, 0.9);
    border: 1px solid #25314d;
    border-radius: 0.5rem;
    color: #f2f4f8;
    padding: 0.45rem 2rem 0.45rem 0.75rem;
    font-size: 0.9rem;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      background 0.2s ease;
    background-image: url('data:image/svg+xml,%3Csvg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"%3E%3Cpath d="M7 8l3 3 3-3" stroke="%23d4daee" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/%3E%3C/svg%3E');
    background-repeat: no-repeat;
    background-position: right 0.65rem center;
    background-size: 1rem;
    min-width: 140px;
    flex-shrink: 0;
  }

  .sort-select:hover {
    border-color: #38bdf8;
    background-color: rgba(12, 19, 34, 0.95);
  }

  .sort-select:focus {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
    border-color: #38bdf8;
  }

  .sort-select option {
    background: #0a101a;
    color: #f2f4f8;
    padding: 0.5rem;
  }
</style>
