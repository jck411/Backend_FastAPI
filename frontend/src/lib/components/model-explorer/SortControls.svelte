<script lang="ts">
  import type { ModelSort } from '../../stores/models';

  export let selected: ModelSort;
  export let onSelect: (sort: ModelSort) => void;

  const buttons: Array<{ label: string; value: ModelSort }> = [
    { label: 'Newest', value: 'newness' },
    { label: 'Lowest price', value: 'price' },
    { label: 'Longest context', value: 'context' },
  ];
</script>

<div class="sort">
  <span>Sort by</span>
  <div class="sort-buttons">
    {#each buttons as button}
      <button
        type="button"
        class:active={selected === button.value}
        on:click={() => onSelect(button.value)}
      >
        {button.label}
      </button>
    {/each}
  </div>
</div>

<style>
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

  button {
    border-radius: 999px;
    background: none;
    border: 1px solid #25314d;
    color: inherit;
    padding: 0.4rem 0.9rem;
    cursor: pointer;
  }

  button.active {
    background: #38bdf8;
    color: #041225;
    border-color: #38bdf8;
  }
</style>
